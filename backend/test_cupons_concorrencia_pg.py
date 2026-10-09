"""Concorrência e atomicidade em PostgreSQL exclusivamente local descartável."""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, local
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from app import cupons_admin,models as m,schemas
from test_compras_fluxo import ambiente_compra

@pytest.fixture
def motor():
    url=os.getenv('CUPONS_TEST_DATABASE_URL')
    if not url:pytest.skip('Defina CUPONS_TEST_DATABASE_URL para PostgreSQL descartável')
    parsed=make_url(url)
    assert parsed.host in ('localhost','127.0.0.1') and parsed.database.startswith('cupons_test_')
    assert parsed.get_backend_name()=='postgresql'
    engine=create_engine(url,connect_args={'options':'-c lock_timeout=10000 -c statement_timeout=20000'})
    with engine.begin() as c:
        c.execute(text('DROP SCHEMA public CASCADE'))
        c.execute(text('CREATE SCHEMA public'))
    yield engine
    engine.dispose()

def endpoint(main):
    return next(r.endpoint for r in main.app.routes if r.path=='/admin/cupons-desconto/gerar')

def test_geracao_concorrente_colisoes(ambiente_compra,monkeypatch):
    main,_,factory,_,_=ambiente_compra
    dados_thread=local()
    def codigo():
        # Ambos os lotes percorrem os mesmos códigos, forçando colisões reais.
        dados_thread.n=getattr(dados_thread,'n',0)+1
        return f'AB{dados_thread.n:03d}'
    monkeypatch.setattr(cupons_admin,'gerar_codigo',codigo)
    barreira=Barrier(2)
    def gerar(_):
        with factory() as db:
            barreira.wait(timeout=5)
            return endpoint(main)(schemas.CupomDescontoGerarRequest(quantidade=100),db,SimpleNamespace(is_admin=True))
    with ThreadPoolExecutor(max_workers=2) as executor:resultados=list(executor.map(gerar,range(2)))
    assert all(len(lote)==100 for lote in resultados)
    assert len({c['codigo'] for lote in resultados for c in lote})==200
    with factory() as db:assert db.query(m.CupomDesconto).count()==201

def test_rollback_postgresql(ambiente_compra,monkeypatch):
    main,_,factory,_,_=ambiente_compra
    codigos=iter(['AB001'])
    monkeypatch.setattr(cupons_admin,'gerar_codigo',lambda:next(codigos,'AW265'))
    with factory() as db:
        with pytest.raises(HTTPException) as erro:
            endpoint(main)(schemas.CupomDescontoGerarRequest(quantidade=2),db,SimpleNamespace(is_admin=True))
        assert erro.value.status_code==409
    with factory() as db:assert [c.codigo for c in db.query(m.CupomDesconto)]==['AW265']
