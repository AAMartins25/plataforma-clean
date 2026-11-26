"""Migração 032 em PostgreSQL descartável; nunca acessa DATABASE_URL."""
import os
from pathlib import Path
import subprocess
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(os.environ.get('TEST_MIGRACAO032_PG') != '1',
                                reason='Requer contêiner PostgreSQL de teste explícito')
CONTAINER = os.environ.get('TEST_MIGRACAO032_CONTAINER', '')
PERMITIDOS = {'teste-uf-nacional-15', 'teste-uf-nacional-17'}
SQL_027 = (Path(__file__).parent / 'migrations/027_metadados_cursos.sql').read_text()
SQL_032 = (Path(__file__).parent / 'migrations/032_uf_nacional_cursos.sql').read_text()


def psql(sql, banco, ok=True):
    assert CONTAINER in PERMITIDOS
    resultado = subprocess.run(['docker', 'exec', '-i', CONTAINER, 'psql', '-X', '-U', 'postgres',
                                '-d', banco, '-v', 'ON_ERROR_STOP=1', '-At'],
                               input=sql, text=True, capture_output=True)
    assert (resultado.returncode == 0) == ok, resultado.stderr
    return resultado.stdout.strip() if ok else resultado.stderr


@pytest.fixture
def banco():
    nome = 'uf032_' + uuid4().hex
    psql(f'CREATE DATABASE {nome}', 'postgres')
    try:
        psql('''CREATE TABLE usuarios(id integer PRIMARY KEY,nome text NOT NULL);
                CREATE TABLE cursos(id integer PRIMARY KEY,nome varchar(255) NOT NULL,
                    ativo boolean,publicado boolean,descricao_publica text);
                INSERT INTO cursos VALUES(1,'Legado',true,false,'Conteúdo');''', nome)
        psql(SQL_027, nome)
        psql("UPDATE cursos SET uf='RO' WHERE id=1; INSERT INTO cursos(id,nome,uf) VALUES(2,'Sem UF',NULL);", nome)
        yield nome
    finally:
        psql(f'DROP DATABASE {nome}', 'postgres')


def test_migracao_preserva_dados_e_e_reaplicavel(banco):
    psql(SQL_032 + SQL_032, banco)
    assert psql("SELECT string_agg(id||':'||coalesce(uf,'NULL'),',' ORDER BY id) FROM cursos", banco) == '1:RO,2:NULL'
    assert psql("SELECT character_maximum_length FROM information_schema.columns WHERE table_name='cursos' AND column_name='uf'", banco) == '8'
    assert psql("SELECT convalidated FROM pg_constraint WHERE conrelid='cursos'::regclass AND conname='ck_cursos_uf_metadado'", banco) == 'f'
    psql("INSERT INTO cursos(id,nome,uf) VALUES(3,'Nacional','NACIONAL'),(4,'SP','SP'),(6,'Regional','REGIONAL')", banco)
    for uf in ('XX', 'nacional', 'regional', 'NACIONALL', 'REGIONALL'):
        psql(f"INSERT INTO cursos(id,nome,uf) VALUES(5,'Inválido','{uf}')", banco, ok=False)
    psql(SQL_032, banco)
    assert psql('SELECT count(*) FROM cursos', banco) == '5'


def test_constraint_inesperada_cancela_migracao_sem_alterar_dados(banco):
    psql("ALTER TABLE cursos ADD CONSTRAINT uf_outro CHECK (uf IS NULL OR uf <> 'SP') NOT VALID", banco)
    erro = psql(SQL_032, banco, ok=False)
    assert 'Outra constraint' in erro
    assert psql("SELECT character_maximum_length FROM information_schema.columns WHERE table_name='cursos' AND column_name='uf'", banco) == '2'
    assert psql('SELECT uf FROM cursos WHERE id=1', banco) == 'RO'


def test_constraint_incompativel_cancela_migracao(banco):
    psql("ALTER TABLE cursos DROP CONSTRAINT ck_cursos_uf_metadado; ALTER TABLE cursos ADD CONSTRAINT ck_cursos_uf_metadado CHECK (uf IS NULL OR uf='RO') NOT VALID", banco)
    erro = psql(SQL_032, banco, ok=False)
    assert 'incompatível' in erro
    assert psql('SELECT uf FROM cursos WHERE id=1', banco) == 'RO'


def test_preserva_estado_de_constraint_validada(banco):
    psql('ALTER TABLE cursos VALIDATE CONSTRAINT ck_cursos_uf_metadado', banco)
    psql(SQL_032, banco)
    assert psql("SELECT convalidated FROM pg_constraint WHERE conrelid='cursos'::regclass AND conname='ck_cursos_uf_metadado'", banco) == 't'
