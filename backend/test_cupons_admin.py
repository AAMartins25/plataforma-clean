"""Gestão de cupons com banco isolado e checkout simulado."""
import re
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool
from sqlalchemy.exc import SQLAlchemyError
from app import models as m
from app import cupons_admin
from test_compras_fluxo import ambiente_compra

@pytest.fixture
def motor():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    @event.listens_for(engine,'connect')
    def conectar(c,_):
        c.isolation_level=None
        c.execute('PRAGMA foreign_keys=ON')
    @event.listens_for(engine,'begin')
    def iniciar(c): c.exec_driver_sql('BEGIN')
    yield engine
    engine.dispose()

@pytest.fixture
def ambiente(ambiente_compra):
    main,c,factory,post,get=ambiente_compra
    main.app.dependency_overrides[main.get_usuario_atual]=lambda:SimpleNamespace(id=2,is_admin=True)
    return main,c,factory,post,get

ROTAS=[('get','/admin/cupons-desconto',None),('get','/admin/vendedores',None),
       ('post','/admin/cupons-desconto/gerar',{'quantidade':1}),
       ('put','/admin/cupons-desconto/1/vendedor',{'vendedor_id':None}),
       ('put','/admin/cupons-desconto/1/status?ativo=false',{})]

@pytest.mark.parametrize('metodo,url,dados',ROTAS)
@pytest.mark.parametrize('autenticado',[False,True])
def test_permissoes(ambiente,metodo,url,dados,autenticado):
    main,c,f,_,_=ambiente
    if autenticado:main.app.dependency_overrides[main.get_usuario_atual]=lambda:SimpleNamespace(id=1,is_admin=False)
    else:main.app.dependency_overrides.pop(main.get_usuario_atual)
    r=getattr(c,metodo)(url,**({'json':dados} if dados is not None else {}))
    assert r.status_code==(403 if autenticado else 401),r.text
    with f() as db:assert db.query(m.CupomDesconto).count()==1

@pytest.mark.parametrize('quantidade',[1,100])
def test_geracao(ambiente,quantidade):
    _,c,f,_,_=ambiente
    r=c.post('/admin/cupons-desconto/gerar',json={'quantidade':quantidade})
    assert r.status_code==200,r.text
    novos=r.json()
    assert len(novos)==quantidade
    assert len({x['codigo'] for x in novos})==quantidade
    assert all(re.fullmatch('[A-Z]{2}[0-9]{3}',x['codigo']) and x['ativo'] and x['vendedor_id'] is None and x['percentual_desconto']==12 for x in novos)
    with f() as db:assert db.query(m.CupomDesconto).count()==quantidade+1
    assert len(c.get('/admin/cupons-desconto').json())==quantidade+1

@pytest.mark.parametrize('quantidade,status',[(0,400),(-1,400),(101,400),(1.5,422),('abc',422),(None,422)])
def test_quantidade_invalida(ambiente,quantidade,status):
    _,c,f,_,_=ambiente
    assert c.post('/admin/cupons-desconto/gerar',json={'quantidade':quantidade}).status_code==status
    with f() as db:assert db.query(m.CupomDesconto).count()==1

def test_colisao_recuperada(ambiente,monkeypatch):
    _,c,_,_,_=ambiente
    codigos=iter(['AW265','AB001','AB001','AB002'])
    monkeypatch.setattr(cupons_admin,'gerar_codigo',lambda:next(codigos))
    assert [x['codigo'] for x in c.post('/admin/cupons-desconto/gerar',json={'quantidade':2}).json()]==['AB001','AB002']

def test_esgotamento_rollback_integral(ambiente,monkeypatch):
    _,c,f,_,_=ambiente
    codigos=iter(['AB001'])
    monkeypatch.setattr(cupons_admin,'gerar_codigo',lambda:next(codigos,'AW265'))
    assert c.post('/admin/cupons-desconto/gerar',json={'quantidade':2}).status_code==409
    with f() as db:assert [x.codigo for x in db.query(m.CupomDesconto)]==['AW265']

def test_falha_sql_rollback_integral(ambiente,monkeypatch):
    _,c,f,_,_=ambiente
    contador=[0]
    def falhar(*args):
        contador[0]+=1
        if contador[0]==2:raise SQLAlchemyError('detalhe confidencial simulado')
    event.listen(m.CupomDesconto,'before_insert',falhar)
    try:
        r=c.post('/admin/cupons-desconto/gerar',json={'quantidade':2})
        assert r.status_code==500 and 'confidencial' not in r.text
        with f() as db:assert db.query(m.CupomDesconto).count()==1
    finally:event.remove(m.CupomDesconto,'before_insert',falhar)

def test_vendedores_vinculo_status_e_compra(ambiente):
    main,c,f,post,_=ambiente
    with f() as db:db.add(m.Vendedor(id=2,nome='Inativo',ativo=False));db.commit()
    assert {v['id'] for v in c.get('/admin/vendedores').json()}=={1,2}
    novo=c.post('/admin/cupons-desconto/gerar',json={'quantidade':1}).json()[0]
    url=f"/admin/cupons-desconto/{novo['id']}"
    assert c.post('/cupons-desconto/validar',json={'codigo_cupom':novo['codigo']}).status_code==400
    assert c.put(url+'/vendedor',json={'vendedor_id':999}).status_code==404
    assert c.put(url+'/vendedor',json={'vendedor_id':2}).status_code==400
    assert c.put(url+'/vendedor',json={'vendedor_id':1}).status_code==200
    assert c.post('/cupons-desconto/validar',json={'codigo_cupom':novo['codigo']}).json()['percentual_desconto']==12
    main.app.dependency_overrides[main.get_usuario_atual]=lambda:SimpleNamespace(id=1,email='1@teste.local',is_admin=False)
    r=c.post('/checkout/mercadopago',json={'tempo_acesso_id':1,'codigo_cupom':novo['codigo']})
    assert r.status_code==200 and r.json()['valor_cents']==4391,r.text
    post.assert_called_once()
    main.app.dependency_overrides[main.get_usuario_atual]=lambda:SimpleNamespace(id=2,is_admin=True)
    assert c.put(url+'/status?ativo=false',json={}).json()['ativo'] is False
    assert c.post('/cupons-desconto/validar',json={'codigo_cupom':novo['codigo']}).status_code==400
    assert c.put(url+'/status?ativo=true',json={}).status_code==200
    with f() as db:db.get(m.Vendedor,1).ativo=False;db.commit()
    assert c.put(url+'/vendedor',json={'vendedor_id':None}).json()['vendedor_id'] is None
    with f() as db:
        assert db.query(m.Pagamento).one().vendedor_id==1
        assert db.query(m.CupomDesconto).count()==2

@pytest.mark.parametrize('rota',['vendedor','status?ativo=true'])
def test_inexistente(ambiente,rota):
    _,c,_,_,_=ambiente
    assert c.put('/admin/cupons-desconto/999/'+rota,json={'vendedor_id':None}).status_code==404

def test_troca_de_vendedor_preserva_original_e_listagem(ambiente):
    _,c,f,_,_=ambiente
    with f() as db:db.add(m.Vendedor(id=3,nome='Outro ativo',ativo=True));db.commit()
    r=c.put('/admin/cupons-desconto/1/vendedor',json={'vendedor_id':3})
    assert r.status_code==200 and r.json()['vendedor_id']==3
    assert c.get('/admin/cupons-desconto').json()[0]['vendedor_id']==3
    with f() as db:
        assert db.get(m.Vendedor,1).nome=='Parceiro'
        assert db.get(m.CupomDesconto,1).percentual_desconto==12

@pytest.mark.parametrize('dados',[{'vendedor_id':'abc'},{'vendedor_id':1.5}])
def test_vendedor_payload_invalido(ambiente,dados):
    _,c,f,_,_=ambiente
    assert c.put('/admin/cupons-desconto/1/vendedor',json=dados).status_code==422
    with f() as db:assert db.get(m.CupomDesconto,1).vendedor_id==1

def test_listas_vazias(ambiente):
    _,c,f,_,_=ambiente
    with f() as db:db.query(m.CupomDesconto).delete();db.query(m.Vendedor).delete();db.commit()
    assert c.get('/admin/cupons-desconto').json()==[]
    assert c.get('/admin/vendedores').json()==[]
