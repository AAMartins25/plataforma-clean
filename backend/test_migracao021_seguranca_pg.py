"""021 real em PostgreSQL descartável. Nunca usa DATABASE_URL de produção.

Opt-in: JURIDICO_021_TEST_ADMIN_URL (superusuário local) e
JURIDICO_021_TEST_POSTGRES_PASSWORD. Cria um banco exclusivo por teste.
Roles anon/authenticated/service_role/api_021_grupo e postgres devem existir;
postgres deve ser NOSUPERUSER NOBYPASSRLS. Ver procedimento da migração.
"""
import os
import uuid
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import psycopg
from psycopg import sql
import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

BASE = Path(__file__).parent
MIGRACAO = (BASE / 'migrations/021_aceites_juridicos.sql').read_text()
IMPORTACAO = (BASE / 'documentos_juridicos/1.0/documentos-1.0.sql').read_text()
TABELAS = ('documentos_juridicos_versoes', 'politica_aceite_juridico',
           'aceites_juridicos', 'aceites_juridicos_documentos', 'aceites_juridicos_pagamentos')
SEQUENCIAS = tuple(t + '_id_seq' for t in TABELAS[:3])
ROLES = ('anon', 'authenticated', 'service_role')


@pytest.fixture
def banco(monkeypatch):
    valor = os.getenv('JURIDICO_021_TEST_ADMIN_URL')
    if not valor:
        pytest.skip('PostgreSQL local explicitamente autorizado não configurado')
    admin_url = make_url(valor)
    assert admin_url.host in ('127.0.0.1', 'localhost', '::1'), 'Somente PostgreSQL local'
    senha = os.environ['JURIDICO_021_TEST_POSTGRES_PASSWORD']
    nome = 'teste_juridico021_' + uuid.uuid4().hex[:12]
    admin_dsn = admin_url.set(drivername='postgresql').render_as_string(hide_password=False)
    with psycopg.connect(admin_dsn, autocommit=True) as c:
        assert c.execute("SELECT rolsuper FROM pg_roles WHERE rolname=current_user").fetchone()[0]
        assert c.execute("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname='postgres'").fetchone() == (False, False)
        c.execute(sql.SQL('CREATE DATABASE {} OWNER postgres').format(sql.Identifier(nome)))
    owner_url = admin_url.set(database=nome, username='postgres', password=senha)
    owner_dsn = owner_url.set(drivername='postgresql').render_as_string(hide_password=False)
    cliente_admin = admin_url.set(database=nome, drivername='postgresql').render_as_string(hide_password=False)
    monkeypatch.setenv('DATABASE_URL', owner_url.set(drivername='postgresql+psycopg').render_as_string(hide_password=False))
    monkeypatch.setenv('AMBIENTE_TESTE', '1')
    monkeypatch.setenv('SECRET_KEY', 'chave-local-de-teste-sem-validade-em-producao-021')
    try:
        yield owner_dsn, cliente_admin
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as c:
            c.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(nome)))


def executar(dsn, comando):
    with psycopg.connect(dsn, autocommit=True) as c:
        try:
            c.execute(comando)
        except Exception:
            c.execute('ROLLBACK')
            raise


def preparar_minimo(dsn):
    with psycopg.connect(dsn, autocommit=True) as c:
        for tabela in ('usuarios', 'cursos', 'tempo_acesso_curso', 'oportunidades_compra', 'pagamentos'):
            c.execute(sql.SQL('CREATE TABLE {} (id integer PRIMARY KEY)').format(sql.Identifier(tabela)))


def defaults_amplos(dsn, herdado=False):
    executar(dsn, '''
        ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO PUBLIC, anon, authenticated, service_role;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO PUBLIC, anon, authenticated, service_role;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO PUBLIC, anon, authenticated, service_role;
    ''' + ('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO api_021_grupo;' if herdado else ''))


def sem_objetos(dsn):
    with psycopg.connect(dsn, autocommit=True) as c:
        for nome in TABELAS + SEQUENCIAS:
            assert c.execute('SELECT to_regclass(%s)', ('public.' + nome,)).fetchone()[0] is None
        assert c.execute("SELECT to_regprocedure('public.impedir_alteracao_evidencia_juridica()')").fetchone()[0] is None


def test_rollback_integral_e_reexecucao(banco):
    dsn, _ = banco
    preparar_minimo(dsn)
    defaults_amplos(dsn)
    with pytest.raises(psycopg.errors.DivisionByZero):
        executar(dsn, MIGRACAO.rsplit('COMMIT;', 1)[0] + 'SELECT 1/0; COMMIT;')
    sem_objetos(dsn)
    executar(dsn, MIGRACAO)
    with pytest.raises(psycopg.errors.DuplicateTable):
        executar(dsn, MIGRACAO)
    with psycopg.connect(dsn) as c:
        assert c.execute('SELECT habilitada FROM politica_aceite_juridico WHERE id=1').fetchone() == (False,)


@pytest.mark.parametrize('herdar', [True, False], ids=['INHERIT', 'NOINHERIT'])
def test_acesso_herdado_aborta_sem_publicar_objetos(banco, herdar):
    dsn, admin = banco
    preparar_minimo(dsn)
    defaults_amplos(dsn, herdado=True)
    executar(admin, 'GRANT api_021_grupo TO authenticated WITH INHERIT ' + ('TRUE' if herdar else 'FALSE'))
    try:
        with pytest.raises(psycopg.errors.RaiseException, match='acesso de API'):
            executar(dsn, MIGRACAO)
        sem_objetos(dsn)
    finally:
        executar(admin, 'GRANT api_021_grupo TO authenticated WITH INHERIT TRUE')


def test_role_incorreta_e_politica_inesperada_abortam(banco):
    dsn, admin = banco
    preparar_minimo(dsn)
    with pytest.raises(psycopg.errors.RaiseException, match='exige execução como postgres'):
        executar(admin, MIGRACAO)
    sem_objetos(dsn)
    alterada = MIGRACAO.replace(
        'ALTER TABLE public.aceites_juridicos ENABLE ROW LEVEL SECURITY;',
        'ALTER TABLE public.aceites_juridicos ENABLE ROW LEVEL SECURITY;\n'
        'CREATE POLICY indevida ON public.aceites_juridicos FOR SELECT TO anon USING (true);')
    with pytest.raises(psycopg.errors.RaiseException, match='RLS incompatível'):
        executar(dsn, alterada)
    sem_objetos(dsn)


def test_backend_importacao_e_isolamento(banco, monkeypatch):
    import json
    from app import models as m
    from test_compras_fluxo import ambiente_compra, contrato
    dsn, admin = banco
    engine = create_engine(make_url(dsn).set(drivername='postgresql+psycopg'))
    fixture = ambiente_compra.__wrapped__(engine, monkeypatch)
    main, client, factory, post, get = next(fixture)
    try:
        defaults_amplos(dsn)
        # ACL da tabela histórica não deve ser afetada pelo REVOKE jurídico.
        executar(dsn, 'GRANT SELECT ON public.usuarios TO anon;')
        with psycopg.connect(dsn) as c:
            acl = c.execute("SELECT relacl FROM pg_class WHERE oid='public.usuarios'::regclass").fetchone()
        executar(dsn, MIGRACAO)
        with psycopg.connect(dsn) as c:
            assert c.execute("SELECT relacl FROM pg_class WHERE oid='public.usuarios'::regclass").fetchone() == acl
            rows = c.execute('SELECT relrowsecurity,relforcerowsecurity,relowner::regrole::text FROM pg_class WHERE relname=ANY(%s)', (list(TABELAS),)).fetchall()
            assert len(rows) == 5 and all(r == (True, False, 'postgres') for r in rows)
            assert c.execute('SELECT count(*) FROM pg_policy WHERE polrelid=ANY(%s::regclass[])', (list(TABELAS),)).fetchone() == (0,)
        executar(dsn, IMPORTACAO)
        manifesto = json.loads((BASE/'documentos_juridicos/1.0/manifesto.json').read_text())['documentos']
        with factory() as db:
            docs = db.query(m.DocumentoJuridicoVersao).all()
            assert len(docs) == 2
            ids = {d.tipo:d.id for d in docs}
            for d in docs:
                item = next(x for x in manifesto if x['tipo'] == d.tipo)
                assert d.versao == '1.0'
                assert d.conteudo.encode() == (BASE/'documentos_juridicos/1.0'/item['texto']).read_bytes()
                assert sha256(d.conteudo.encode()).hexdigest() == d.sha256 == item['texto_sha256']
                assert sha256((BASE/'documentos_juridicos/1.0'/item['pdf']).read_bytes()).hexdigest() == d.pdf_sha256 == item['pdf_sha256']
        assert client.get('/public/juridico/vigente').json() == {'obrigatorio':False,'documentos':[]}
        assert client.post('/checkout/mercadopago', json={'tempo_acesso_id':1}).status_code == 200
        with factory() as db:
            cid = contrato(db, dias=10)
            fim = db.get(m.ContratacaoCurso, cid).data_fim
        assert client.post('/checkout/mercadopago',json={'tempo_acesso_id':1,'tipo_compra':'RENOVACAO','contratacao_id':cid}).status_code == 200
        with factory() as db:
            assert db.query(m.AceiteJuridico).count() == 0
            p = db.get(m.PoliticaAceiteJuridico,1)
            p.termos_id,p.privacidade_id,p.habilitada = ids['TERMOS'],ids['PRIVACIDADE'],True
            db.commit()
        post.reset_mock(); get.reset_mock()
        for extra in ({}, {'tipo_compra':'RENOVACAO','contratacao_id':cid}):
            assert client.post('/checkout/mercadopago',json={'tempo_acesso_id':1,**extra}).status_code == 400
        assert client.post('/checkout/mercadopago',json={'tempo_acesso_id':1,'aceite_juridico':{'aceito':True,'termos_id':9999,'privacidade_id':ids['PRIVACIDADE']}}).status_code == 409
        post.assert_not_called();get.assert_not_called()
        student = {'id':2}
        main.app.dependency_overrides[main.get_usuario_atual] = lambda:SimpleNamespace(id=student['id'],email='fixture@teste.local',is_admin=False)
        def resposta(pid, status=200):
            r = Mock(status_code=status)
            r.json.return_value = {'id':pid,'init_point':'https://example.com/simulado','collector_id':123456}
            return r
        post.return_value = resposta('pref_seguranca',201)
        get.side_effect = lambda url,**kwargs:resposta(url.rsplit('/',1)[-1])
        aceite = {'aceito':True,'termos_id':ids['TERMOS'],'privacidade_id':ids['PRIVACIDADE']}
        for _ in range(2):
            assert client.post('/checkout/mercadopago',json={'tempo_acesso_id':1,'aceite_juridico':aceite}).status_code == 200
        student['id'] = 1
        assert client.post('/checkout/mercadopago',json={'tempo_acesso_id':1,'tipo_compra':'RENOVACAO','contratacao_id':cid,'aceite_juridico':aceite}).status_code == 200
        assert post.call_count == 1 and get.call_count == 2
        with factory() as db:
            assert db.query(m.AceiteJuridico).count() == 3
            assert db.query(m.AceiteJuridicoDocumento).count() == 6
            assert db.query(m.AceiteJuridicoPagamento).count() == 3
            assert db.query(m.PeriodoAcessoPagamento).count() == 0
            assert db.get(m.ContratacaoCurso,cid).data_fim == fim
        for d in client.get('/public/juridico/vigente').json()['documentos']:
            assert client.get(d['url']).status_code == 200
            assert sha256(client.get(d['pdf_url']).content).hexdigest() == d['pdf_sha256']
        # Verificações por role real, inclusive service_role com BYPASSRLS.
        for role in ROLES:
            for tabela in TABELAS:
                with psycopg.connect(admin) as c:
                    c.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)))
                    with pytest.raises(psycopg.errors.InsufficientPrivilege):
                        c.execute(sql.SQL('SELECT * FROM public.{}').format(sql.Identifier(tabela)))
            for seq in SEQUENCIAS:
                with psycopg.connect(admin) as c:
                    c.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)))
                    with pytest.raises(psycopg.errors.InsufficientPrivilege):
                        c.execute('SELECT nextval(%s)', ('public.'+seq,))
            with psycopg.connect(admin) as c:
                assert c.execute("SELECT has_function_privilege(%s,'public.impedir_alteracao_evidencia_juridica()','EXECUTE')", (role,)).fetchone() == (False,)
        # Se SELECT for concedido futuramente a anon, RLS ainda oculta os 3 eventos.
        with psycopg.connect(admin) as c:
            c.execute('GRANT SELECT ON public.aceites_juridicos TO anon')
            c.execute('SET LOCAL ROLE anon')
            assert c.execute('SELECT * FROM public.aceites_juridicos').fetchall() == []
            c.rollback()
        with factory() as db:
            db.get(m.PoliticaAceiteJuridico,1).habilitada = False
            db.commit()
        assert client.get('/public/juridico/vigente').json()['obrigatorio'] is False
    finally:
        try:
            next(fixture)
        except StopIteration:
            pass
        engine.dispose()
