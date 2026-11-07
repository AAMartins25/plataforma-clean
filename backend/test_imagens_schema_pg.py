"""DDL de imagens em contêiner descartável, sem rede/portas/banco configurado."""
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4

import pytest


@pytest.mark.skipif(os.getenv("IMAGENS_TESTAR_POSTGRES") != "1", reason="Requer Docker local e postgres:17.6 já disponível")
def test_schema_privado_constraints_e_cascata():
    nome = "resumao-imagens-teste-" + uuid4().hex[:12]
    def comando(*args, entrada=None, verificar=True):
        return subprocess.run(args, input=entrada, text=True, capture_output=True,
                              check=verificar, timeout=20)
    def sql(texto, verificar=True):
        return comando("docker", "exec", "-i", nome, "psql", "-U", "postgres",
                       "-d", "imagens_test", "-v", "ON_ERROR_STOP=1", entrada=texto, verificar=verificar)
    comando("docker", "run", "--detach", "--rm", "--network", "none", "--name", nome,
            "-e", "POSTGRES_PASSWORD=senha-sintetica-local", "-e", "POSTGRES_DB=imagens_test", "postgres:17.6")
    try:
        for _ in range(60):
            if comando("docker", "exec", nome, "pg_isready", "-h", "127.0.0.1", "-U", "postgres", verificar=False).returncode == 0:
                break
            time.sleep(.25)
        sql("CREATE ROLE anon; CREATE ROLE authenticated; CREATE TABLE usuarios(id INTEGER PRIMARY KEY); CREATE TABLE materiais(id INTEGER PRIMARY KEY);")
        migracao = (Path(__file__).parent / "migrations/024_imagens_teoria.sql").read_text()
        sql(migracao); sql(migracao)
        assert "t" in sql("SELECT relrowsecurity FROM pg_class WHERE relname='imagens_teoria';").stdout
        for papel in ("anon", "authenticated"):
            r = sql(f"SET ROLE {papel}; SELECT * FROM imagens_teoria;", verificar=False)
            assert r.returncode != 0 and "permission denied" in r.stderr
        sql("""INSERT INTO usuarios VALUES (1); INSERT INTO materiais VALUES (1);
            INSERT INTO imagens_teoria(id,chave,autor_id,mime,tamanho,largura,altura,sha256)
            VALUES ('teste','teste.png',1,'image/png',10,90,40,'hash');
            INSERT INTO imagens_teoria_materiais VALUES (1,'teste');
            DELETE FROM materiais WHERE id=1;
            DO $$ BEGIN
              IF (SELECT count(*) FROM imagens_teoria_materiais) != 0 OR (SELECT count(*) FROM imagens_teoria) != 1
              THEN RAISE EXCEPTION 'Cascata removeu o arquivo compartilhável'; END IF;
            END $$;""")
        r = sql("UPDATE imagens_teoria SET tamanho=5242881 WHERE id='teste';", verificar=False)
        assert r.returncode != 0 and "check constraint" in r.stderr
    finally:
        comando("docker", "stop", "--time", "2", nome)
