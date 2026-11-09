"""Opt-in: PostgreSQL descartável sem rede, socket exclusivo e provedor simulado."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, text, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker
from app import models as m
from app.bloqueios_reembolso import bloqueios_reembolso, decisoes
from app.direitos_acesso import contrato_vigente
from app.pausa_financeira import inbox
from test_contestacoes_reconstruido import compra
from test_questoes_pratica_patch import carregar_main_isolado

SOCKET='/tmp/resumao-direitos023-socket'
MIGRATIONS=Path(__file__).parent/'migrations'

def url(database, user='postgres'):
    return f'postgresql+psycopg2://{user}@/{database}?host={SOCKET}'

@pytest.fixture
def pg():
    if os.getenv('RESUMAO_DIREITOS023_PG')!='isolado':
        pytest.skip('Exige PostgreSQL descartável no socket exclusivo, sem rede')
    name='resumao_direitos023_test_'+uuid4().hex[:12]
    role='backend023_'+uuid4().hex[:12]
    owner=create_engine(url('postgres'),isolation_level='AUTOCOMMIT')
    with owner.connect() as c:
        c.execute(text(f'CREATE DATABASE {name}'))
        c.execute(text(f'CREATE ROLE {role} LOGIN'))
    engine=create_engine(url(name))
    tables={x.__table__ for x in (m.Usuario,m.Curso,m.Pagamento,m.ContratacaoCurso,
        m.AcessoCurso,m.PeriodoAcessoPagamento,m.ConcessaoAcessoAdmin,m.DemonstracaoCurso,
        m.ContestacaoPagamento,m.ReembolsoFinanceiro)}
    while True:
        deps={fk.column.table for t in tables for fk in t.foreign_keys}
        if deps<=tables:break
        tables|=deps
    m.Base.metadata.create_all(engine,tables=list(tables))
    for script in ('016_pausa_financeira_webhooks.sql','014_pagamentos_multiplas_transacoes.sql',
                   '015_reembolsos_manual_auditoria.sql'):
        with engine.connect() as c:
            c.connection.driver_connection.cursor().execute((MIGRATIONS/script).read_text())
    factory=sessionmaker(bind=engine)
    with factory() as db:
        db.add_all([m.Usuario(id=i,nome='Fictício',email=f'{i}@example.com',senha_hash='teste',
            cpf=str(i),telefone='0',is_admin=i==2,tipo_admin='admin_geral' if i==2 else None) for i in (1,2)])
        db.add(m.Curso(id=1,nome='Fictício',ativo=True));db.flush()
        db.add(m.TempoAcessoCurso(id=1,curso_id=1,meses=1,valor_cents=4990));db.commit()
        pid,cid=compra(db)
        p=db.get(m.Pagamento,pid);p.status='REFUNDED'
        r=m.ReembolsoFinanceiro(pagamento_id=pid,metodo='PIX_MANUAL',valor_cents=4990,status='CONFIRMADO',
            confirmado_em=datetime.utcnow(),confirmado_por=2,referencia_comprovante='extrato simulado')
        db.add(r);db.commit();rid=r.id
    def snapshot():
        with engine.connect() as c:
            return {t:c.execute(text(f"SELECT coalesce(json_agg(row_to_json(t) ORDER BY id)::text,'[]') FROM {t} t")).scalar()
                for t in ('usuarios','pagamentos','reembolsos_financeiros','contratacoes_curso','periodos_acesso_pagamento','acessos_curso')}
    with engine.begin() as c:
        # A migração precisa neutralizar concessões amplas herdadas de defaults.
        c.execute(text(f'ALTER DEFAULT PRIVILEGES GRANT ALL ON TABLES TO {role}'))
    before=snapshot()
    migration=(MIGRATIONS/'023_bloqueios_acesso_reembolso.sql').read_text()
    with engine.connect() as c:
        c.execute(text("SELECT set_config('resumao.app_role',:role,false)"),{'role':role})
        c.connection.driver_connection.cursor().execute(migration)
    assert snapshot()==before
    with engine.begin() as c:
        # Privilégios das tabelas anteriores exclusivamente para a fixture efêmera.
        for table in tables:
            c.execute(text(f'GRANT SELECT,INSERT,UPDATE,DELETE ON {table.name} TO {role}'))
        c.execute(text(f'GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}'))
        c.execute(text(f'GRANT SELECT,INSERT,UPDATE ON controle_financeiro,notificacoes_mp TO {role}'))
        for table in ('controle_financeiro','notificacoes_mp'):
            # 016 já usa RLS; o papel de teste precisa da configuração prévia do backend.
            c.execute(text(f'CREATE POLICY fixture_backend ON {table} TO {role} USING (true) WITH CHECK (true)'))
        c.execute(text("UPDATE controle_financeiro SET modo='NORMAL'"))
    app_engine=create_engine(url(name,role),connect_args={'options':'-c lock_timeout=8000 -c statement_timeout=15000'})
    app_factory=sessionmaker(bind=app_engine)
    try:
        with carregar_main_isolado(app_factory,app_engine) as main:
            yield SimpleNamespace(main=main,engine=engine,app_engine=app_engine,f=app_factory,
                role=role,pid=pid,cid=cid,rid=rid,migration=migration,snapshot=snapshot,before=before)
    finally:
        app_engine.dispose();engine.dispose()
        with owner.connect() as c:
            c.execute(text(f'DROP DATABASE {name} WITH (FORCE)'))
            c.execute(text(f'DROP ROLE {role}'))
        owner.dispose()


def endpoint(main,path):
    return next(r.endpoint for r in main.app.routes if getattr(r,'path',None)==path)


def test_migration_structure_rls_app_permissions_and_historical_data(pg):
    with pg.app_engine.connect() as c:
        assert c.execute(text('SELECT current_user')).scalar()==pg.role
        assert c.execute(text("SELECT relrowsecurity FROM pg_class WHERE oid='public.bloqueios_acesso_reembolso'::regclass")).scalar()
        assert c.execute(text("SELECT count(*) FROM pg_constraint WHERE conrelid='public.bloqueios_acesso_reembolso'::regclass AND contype='f'")).scalar()==3
        assert c.execute(text("SELECT count(*) FROM pg_policies WHERE tablename='bloqueios_acesso_reembolso'")).scalar()==2
        assert not c.execute(text("SELECT has_table_privilege(current_user,'bloqueios_acesso_reembolso','UPDATE')")).scalar()
        assert not c.execute(text("SELECT has_table_privilege(current_user,'bloqueios_acesso_reembolso','DELETE')")).scalar()
    block=endpoint(pg.main,'/admin/reembolsos/{reembolso_id}/bloquear-acesso')
    with pg.f() as db:
        assert contrato_vigente(db,db.get(m.ContratacaoCurso,pg.cid))
        block(pg.rid,True,db,SimpleNamespace(id=2,is_admin=True,tipo_admin='admin_geral'))
    with pg.f() as db:
        assert len(decisoes(db,1,1))==1
        assert not contrato_vigente(db,db.get(m.ContratacaoCurso,pg.cid))
    assert pg.snapshot()==pg.before
    with pg.engine.begin() as c:
        c.execute(text(f'CREATE ROLE visitante_{pg.role}'))
        c.execute(text(f'GRANT USAGE ON SCHEMA public TO visitante_{pg.role}'))
        c.execute(text(f'GRANT SELECT,INSERT ON bloqueios_acesso_reembolso TO visitante_{pg.role}'))
    try:
        with pg.engine.begin() as c:
            c.execute(text(f'SET LOCAL ROLE visitante_{pg.role}'))
            assert c.execute(text('SELECT count(*) FROM bloqueios_acesso_reembolso')).scalar()==0
            with pytest.raises(DBAPIError):
                c.execute(text('INSERT INTO bloqueios_acesso_reembolso VALUES (999,999,now(),2)'))
    finally:
        with pg.engine.begin() as c:
            c.execute(text(f'DROP OWNED BY visitante_{pg.role}'))
            c.execute(text(f'DROP ROLE visitante_{pg.role}'))


def test_manual_block_concurrent_idempotent_application_role(pg):
    block=endpoint(pg.main,'/admin/reembolsos/{reembolso_id}/bloquear-acesso')
    barrier=Barrier(2)
    def execute(i):
        with pg.f() as db:
            barrier.wait(timeout=10)
            return block(pg.rid,True,db,SimpleNamespace(id=2,is_admin=True,tipo_admin='admin_geral'))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(execute,(0,1)))
    assert len(results)==2
    with pg.f() as db:
        assert len(db.execute(select(bloqueios_reembolso)).all())==1
    assert pg.snapshot()==pg.before


def test_chargeback_concurrent_canonical_events_commit_without_automatic_block(pg):
    p=pg.main.app.state.protecao_financeira
    p.headers_contestacoes=lambda:{'Authorization':'Bearer pagamento-simulado'}
    ids=[p.armazenar('999','c:concorrencia-'+str(i),'WEBHOOK',{'envelope_valido':True}) for i in range(2)]
    def response(url,**kw):
        r=Mock(status_code=200)
        r.json.return_value=({'id':123456} if url.endswith('/users/me') else {'id':'999','payments':[101],'currency':'BRL','amount':49.90}
            if '/chargebacks/' in url else {'id':101,'status':'charged_back','currency_id':'BRL','collector_id':123456,
                'transaction_amount':49.90,'external_reference':f'user:1|curso:1|tempo:1|pagamento:{pg.pid}'})
        return r
    # Duas instâncias de consumidor simulam processos diferentes do backend.
    from copy import copy
    other=copy(p)
    from threading import BoundedSemaphore
    other.consumidores=BoundedSemaphore(1)
    barrier=Barrier(2)
    def consume(i):
        barrier.wait(timeout=10)
        return (p if i==0 else other).processar(ids[i])
    with patch('app.contestacoes.requests.get',side_effect=response):
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(consume,(0,1)))
    assert all(r['processado'] for r in results),results
    with pg.f() as db:
        case=db.query(m.ContestacaoPagamento).one()
        assert case.bloqueio_executado_em is None and case.devolucao_confirmada_em is None
        assert contrato_vigente(db,db.get(m.ContratacaoCurso,pg.cid))
        assert db.get(m.Pagamento,pg.pid).status=='REFUNDED'
        assert all(e=='CONCLUIDO' for e in db.execute(select(inbox.c.estado)).scalars())


def test_migration_reapply_is_atomic_and_lock_timeout_preserves_data(pg):
    with pg.engine.connect() as c:
        import psycopg2
        with pytest.raises(psycopg2.Error):
            c.connection.driver_connection.cursor().execute(pg.migration)
        c.connection.driver_connection.rollback()
        assert c.execute(text('SELECT count(*) FROM bloqueios_acesso_reembolso')).scalar()==0
    assert pg.snapshot()==pg.before


def test_migration_missing_role_and_concurrent_ddl_rollback_safely(pg):
    import psycopg2
    with pg.engine.begin() as c:
        c.execute(text('DROP TABLE bloqueios_acesso_reembolso'))
    with pg.engine.connect() as c:
        c.execute(text("SELECT set_config('resumao.app_role','',false)"))
        with pytest.raises(psycopg2.Error, match='papel exclusivo'):
            c.connection.driver_connection.cursor().execute(pg.migration)
        c.rollback()
        assert c.execute(text("SELECT to_regclass('public.bloqueios_acesso_reembolso')")).scalar() is None
    # Um escritor/DDL existente não será interrompido pela migração: ela expira.
    with pg.engine.connect() as held:
        held.execute(text('LOCK TABLE usuarios IN ACCESS EXCLUSIVE MODE'))
        with pg.engine.connect() as c:
            c.execute(text("SELECT set_config('resumao.app_role',:role,false)"),{'role':pg.role})
            with pytest.raises(psycopg2.errors.LockNotAvailable):
                c.connection.driver_connection.cursor().execute(pg.migration)
            c.rollback()
        held.rollback()
    with pg.engine.connect() as c:
        assert c.execute(text("SELECT to_regclass('public.bloqueios_acesso_reembolso')")).scalar() is None
    assert pg.snapshot()==pg.before
