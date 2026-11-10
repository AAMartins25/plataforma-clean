"""Migração aditiva em contêiner novo, sem rede, volumes ou banco configurado."""
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4

import pytest


@pytest.mark.skipif(os.getenv('QUESTOES_TESTAR_POSTGRES')!='1',reason='Requer Docker local e postgres:17.6')
def test_migracao_legado_idempotencia_rls_e_imagens_compartilhadas():
    nome='resumao-questoes-migracao-'+uuid4().hex[:10]
    def comando(*args,entrada=None,check=True):
        return subprocess.run(args,input=entrada,capture_output=True,text=True,check=check,timeout=30)
    def sql(entrada,check=True):
        return comando('docker','exec','-i',nome,'psql','-U','postgres','-d','questoes_editor_test','-v','ON_ERROR_STOP=1','-At',entrada=entrada,check=check)
    comando('docker','run','--detach','--rm','--network','none','--name',nome,
        '-e','POSTGRES_PASSWORD=senha-sintetica-local','-e','POSTGRES_DB=questoes_editor_test','postgres:17.6')
    try:
        for _ in range(60):
            if comando('docker','exec',nome,'pg_isready','-h','127.0.0.1','-U','postgres',check=False).returncode==0:break
            time.sleep(.25)
        sql('''CREATE ROLE anon; CREATE ROLE authenticated;
            CREATE TABLE questoes(id integer PRIMARY KEY, enunciado text NOT NULL, comentario text);
            CREATE TABLE alternativas(id integer PRIMARY KEY, questao_id integer REFERENCES questoes ON DELETE CASCADE, texto text);
            CREATE TABLE imagens_teoria(id varchar(36) PRIMARY KEY);
            INSERT INTO questoes VALUES(1,E'Legado <b>literal</b> & x < y\\nLinha 2','Comentário antigo');
            INSERT INTO alternativas VALUES(1,1,'Alternativa antiga');
            ALTER DEFAULT PRIVILEGES GRANT ALL ON TABLES TO anon, authenticated;''')
        antes=sql('SELECT row_to_json(q) FROM questoes q; SELECT row_to_json(a) FROM alternativas a;').stdout
        migracao=(Path(__file__).parent/'migrations/025_questoes_html.sql').read_text()
        sql(migracao);sql(migracao)
        depois=sql('SELECT row_to_json(q) FROM (SELECT id,enunciado,comentario FROM questoes) q; SELECT row_to_json(a) FROM (SELECT id,questao_id,texto FROM alternativas) a;').stdout
        assert depois==antes
        assert sql('SELECT enunciado_formato IS NULL AND comentario_formato IS NULL FROM questoes; SELECT texto_formato IS NULL FROM alternativas;').stdout.strip()=='t\nt'
        assert sql("SELECT relrowsecurity FROM pg_class WHERE relname='imagens_questoes';").stdout.strip()=='t'
        for papel in ['anon','authenticated']:
            r=sql(f'SET ROLE {papel}; SELECT * FROM imagens_questoes;',check=False)
            assert r.returncode!=0 and 'permission denied' in r.stderr
        sql("INSERT INTO imagens_teoria VALUES('imagem-compartilhada'); INSERT INTO questoes VALUES(2,'Cópia',NULL,'html_v1',NULL); INSERT INTO imagens_questoes VALUES('imagem-compartilhada',1),('imagem-compartilhada',2);")
        assert sql("DELETE FROM imagens_teoria WHERE id='imagem-compartilhada';",check=False).returncode!=0
        sql('DELETE FROM questoes WHERE id=1;')
        assert sql('SELECT count(*) FROM imagens_questoes; SELECT count(*) FROM imagens_teoria;').stdout.strip()=='1\n1'
    finally:
        comando('docker','stop','--time','2',nome,check=False)
