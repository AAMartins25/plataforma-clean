"""Concorrência real em banco local novo; cria fixtures ORM, não executa migrações."""
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine, text
from uuid import uuid4
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from app import models as m
from app.contestacoes import registrar_observacao, Confirmacao
from test_contestacoes_reconstruido import compra, caso
from test_questoes_pratica_patch import carregar_main_isolado


@pytest.fixture(scope='module')
def pg():
    url=os.getenv('CONTESTACOES_PG_TEST_DSN')
    if not url:pytest.skip('Defina CONTESTACOES_PG_TEST_DSN para banco local vazio')
    parsed=make_url(url)
    assert parsed.host in ('localhost','127.0.0.1')
    assert parsed.database.startswith('compras_test_contestacoes_reconstruido')
    assert parsed.get_backend_name()=='postgresql'
    schema='contestacoes_teste_'+uuid4().hex
    engine=create_engine(url,connect_args={'options':f'-c lock_timeout=8000 -c statement_timeout=15000 -c search_path={schema},pg_catalog'})
    with engine.begin() as c:
        c.execute(text(f'CREATE SCHEMA {schema}'))
    # Schema exclusivo de cada execução; não remove dados de outras execuções.
    tables={x.__table__ for x in (m.Usuario,m.Curso,m.Pagamento,m.ContratacaoCurso,
        m.AcessoCurso,m.PeriodoAcessoPagamento,m.ContestacaoPagamento,m.ConcessaoAcessoAdmin,m.DemonstracaoCurso)}
    while True:
        deps={fk.column.table for t in tables for fk in t.foreign_keys}
        if deps<=tables:break
        tables|=deps
    m.Base.metadata.create_all(engine,tables=list(tables))
    from app.pausa_financeira import metadata,controle,agora
    metadata.create_all(engine)
    with engine.begin() as c:c.execute(controle.insert().values(id=1,modo='NORMAL',geracao=0,alterado_em=agora(),motivo='teste local'))
    f=sessionmaker(bind=engine)
    with f() as db:
        db.add_all([m.Usuario(id=i,nome='Teste',email=f'{i}@local.test',senha_hash='teste',cpf=str(i),telefone='0',is_admin=i==2) for i in (1,2)])
        db.add(m.Curso(id=1,nome='Teste',ativo=True));db.flush()
        db.add(m.TempoAcessoCurso(id=1,curso_id=1,meses=1,valor_cents=4990));db.commit()
    with carregar_main_isolado(f,engine) as main:
        yield main,f
    engine.dispose()


def paralelo(f,fn):
    barrier=Barrier(2)
    def executar(i):
        with f() as db:
            barrier.wait(timeout=5)
            return fn(db,i)
    with ThreadPoolExecutor(max_workers=2) as pool:
        return list(pool.map(executar,(0,1)))


def endpoint(main,final):
    return next(r.endpoint for r in main.app.routes if getattr(r,'path','').endswith(final))


def test_registro_concorrente_unico(pg):
    main,f=pg
    with f() as db:
        pid,cid=compra(db)
    def registrar(db,i):
        from app.financeiro_transacional import protegido
        @protegido
        def executar(db):
            db.query(m.Usuario).filter_by(id=1).with_for_update().one()
            p=db.query(m.Pagamento).filter_by(id=pid).with_for_update().one()
            c=registrar_observacao(db,p,{'id':'999'})
            db.commit();return c.id
        return executar(db)
    resultados=paralelo(f,registrar)
    assert resultados[0]==resultados[1]
    with f() as db:assert db.query(m.ContestacaoPagamento).filter_by(mp_dispute_id='999').count()==1


def test_confirmacao_e_bloqueio_concorrentes_idempotentes(pg):
    main,f=pg
    with f() as db:
        pid,cid=compra(db,mp='102');ident=caso(db,pid)
    confirmar=endpoint(main,'/confirmar-devolucao');bloquear=endpoint(main,'/bloquear-acesso')
    admin=SimpleNamespace(id=2,is_admin=True)
    dados=Confirmacao(referencia_devolucao='extrato local',confirmacao_devolucao=True)
    paralelo(f,lambda db,i:confirmar(ident,dados,db,admin))
    paralelo(f,lambda db,i:bloquear(ident,True,db,admin))
    with f() as db:
        c=db.get(m.ContestacaoPagamento,ident)
        assert c.devolucao_confirmada_por==2 and c.bloqueio_executado_por==2
        assert db.query(m.PeriodoAcessoPagamento).filter_by(pagamento_id=pid).count()==1
        assert db.get(m.Pagamento,pid).status=='APPROVED'


def test_renovacao_concorrente_ao_bloqueio_preserva_periodo(pg):
    from datetime import timedelta
    from app.financeiro_transacional import protegido
    from app.direitos_acesso import contrato_vigente
    main,f=pg
    with f() as db:
        pid,cid=compra(db,mp='103');ident=caso(db,pid)
    actor=SimpleNamespace(id=2,is_admin=True)
    with f() as db:
        endpoint(main,'/confirmar-devolucao')(ident,
            Confirmacao(referencia_devolucao='extrato terceiro',confirmacao_devolucao=True),db,actor)
    @protegido
    def renovar(db):
        db.query(m.Usuario).filter_by(id=1).with_for_update().one()
        con=db.query(m.ContratacaoCurso).filter_by(id=cid).with_for_update().one()
        compra(db,contrato=con,inicio=con.data_fim,
            fim=con.data_fim+timedelta(days=30),renovacao=True,mp='104')
        return True
    resultados=paralelo(f,lambda db,i: renovar(db) if i else
        endpoint(main,'/bloquear-acesso')(ident,True,db,actor))
    assert len(resultados)==2
    with f() as db:
        con=db.get(m.ContratacaoCurso,cid)
        periodos=db.query(m.PeriodoAcessoPagamento).filter_by(contratacao_id=cid).order_by(m.PeriodoAcessoPagamento.data_inicio).all()
        assert len(periodos)==2
        assert contrato_vigente(db,con,periodos[1].data_inicio+timedelta(days=1))
        assert not contrato_vigente(db,con,periodos[0].data_inicio+timedelta(days=1))
