"""028–031 em banco descartável vazio, nunca no banco de homologação."""
import os
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url


def test_migracoes_em_sequencia_preservam_legado_e_estrutura():
    url=os.environ.get('VENDAS_TEST_PG_DSN')
    if not url:
        pytest.skip('PostgreSQL descartável exclusivo não configurado')
    parsed=make_url(url)
    assert parsed.database=='compras_test_venda_20261108'
    assert parsed.host is None and parsed.query.get('host')=='/tmp/resumao-recuperacao-031-validacao-pg'
    engine=create_engine(url, isolation_level='AUTOCOMMIT')
    try:
        with engine.connect() as c:
            assert c.exec_driver_sql("select count(*) from pg_tables where schemaname='public'").scalar_one()==0
            c.exec_driver_sql('create table usuarios(id integer primary key)')
            c.exec_driver_sql('create table cursos(id integer primary key)')
            c.exec_driver_sql('create table tempo_acesso_curso(id integer primary key,curso_id integer references cursos(id),meses integer,valor_cents integer)')
            c.exec_driver_sql('create table contratacoes_curso(id integer primary key)')
            c.exec_driver_sql('create table acessos_curso(id integer primary key)')
            c.exec_driver_sql('insert into usuarios values(1)')
            c.exec_driver_sql('insert into cursos values(1),(2)')
            c.exec_driver_sql('insert into tempo_acesso_curso values(1,1,4,12345),(2,2,8,54321)')
            scripts=Path(__file__).parent/'migrations'
            for name in ('028_importacao_cursos.sql','029_referencia_preco_provisorio.sql'):
                c.connection.driver_connection.execute((scripts/name).read_text())
            c.exec_driver_sql("insert into importacoes_curso(chave,hash_requisicao,usuario_id,curso_id) values('teste','hash',1,2)")
            for name in ('030_modalidade_demonstracao.sql','031_idempotencia_acesso_admin.sql'):
                c.connection.driver_connection.execute((scripts/name).read_text())
            assert c.exec_driver_sql('select id,precos_provisorios,demonstracao_por_ordem from cursos order by id').all()==[(1,False,False),(2,False,True)]
            assert c.exec_driver_sql('select id,valor_cents,valor_provisorio_original_cents from tempo_acesso_curso order by id').all()==[(1,12345,None),(2,54321,None)]
            assert c.exec_driver_sql("select count(*) from pg_constraint where conrelid='public.operacoes_acesso_admin'::regclass").scalar_one()==4
            assert c.exec_driver_sql('select count(*) from operacoes_acesso_admin').scalar_one()==0
    finally:
        engine.dispose()
