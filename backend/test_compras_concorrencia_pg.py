"""Concorrência real apenas em PostgreSQL local compras_test_* descartável."""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from test_compras_fluxo import ambiente_compra,demo,contrato

@pytest.fixture
def motor():
    url=os.getenv('COMPRAS_TEST_DATABASE_URL')
    if not url:pytest.skip('Defina COMPRAS_TEST_DATABASE_URL')
    parsed=make_url(url)
    assert parsed.host in ('localhost','127.0.0.1') and parsed.database.startswith('compras_test_')
    assert parsed.get_backend_name()=='postgresql'
    engine=create_engine(url,connect_args={'options':'-c lock_timeout=10000 -c statement_timeout=20000'})
    with engine.begin() as c:
        c.execute(text('DROP SCHEMA public CASCADE'));c.execute(text('CREATE SCHEMA public'))
    yield engine
    engine.dispose()

def paralelo(factory,funcao):
    barreira=Barrier(2)
    def executar(i):
        with factory() as db:
            barreira.wait(timeout=5)
            try:return funcao(db,i)
            except HTTPException as e:db.rollback();return e.status_code
    with ThreadPoolExecutor(max_workers=2) as executor:return list(executor.map(executar,(0,1)))

def test_quarto_demo_concorrente(ambiente_compra):
    main,_,factory,_,_=ambiente_compra
    with factory() as db:demo(db,1);demo(db,2)
    resultados=paralelo(factory,lambda db,i:main.iniciar_demonstracao_curso(3+i,db,SimpleNamespace(id=1)))
    assert sum(isinstance(r,dict) for r in resultados)==1 and 409 in resultados
    from app.models import DemonstracaoCurso
    with factory() as db:assert db.query(DemonstracaoCurso).count()==3

def test_mesma_demo_concorrente_respeita_intervalo(ambiente_compra):
    main,_,factory,_,_=ambiente_compra
    resultados=paralelo(factory,lambda db,i:main.iniciar_demonstracao_curso(1,db,SimpleNamespace(id=1)))
    assert sum(isinstance(r,dict) for r in resultados)==1 and 400 in resultados

def test_checkout_concorrente_reabre_preferencia(ambiente_compra):
    main,_,factory,post,get=ambiente_compra
    actor=SimpleNamespace(id=1,email='teste@teste.local')
    resultados=paralelo(factory,lambda db,i:main.criar_checkout_mp({'tempo_acesso_id':1},db,actor))
    assert resultados[0]['pagamento_id']==resultados[1]['pagamento_id']
    assert post.call_count==1 and get.call_count==1
