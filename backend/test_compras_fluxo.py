"""Aquisição em bancos isolados; Mercado Pago sempre simulado."""
from datetime import datetime,timedelta
from types import SimpleNamespace
from unittest.mock import Mock,patch
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,event,text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import models as m
from test_questoes_pratica_patch import carregar_main_isolado

@pytest.fixture
def motor():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    @event.listens_for(engine,'connect')
    def fk(c,_): c.execute('PRAGMA foreign_keys=ON')
    yield engine
    engine.dispose()

@pytest.fixture
def ambiente_compra(motor):
    tabelas={modelo.__table__ for modelo in (m.Usuario,m.Curso,m.TempoAcessoCurso,m.ContratacaoCurso,
        m.DemonstracaoCurso,m.AcessoCurso,m.Vendedor,m.CupomDesconto,m.OportunidadeCompra,
        m.Pagamento,m.PeriodoAcessoPagamento,m.ConcessaoAcessoAdmin)}
    while True:
        dependencias={fk.column.table for tabela in tabelas for fk in tabela.foreign_keys}
        if dependencias <= tabelas: break
        tabelas |= dependencias
    m.Base.metadata.create_all(motor,tables=list(tabelas))
    with motor.begin() as c: c.execute(text('CREATE UNIQUE INDEX test_acesso_unico ON acessos_curso(usuario_id,curso_id)'))
    factory=sessionmaker(bind=motor,autoflush=False)
    with factory() as db:
        for i in (1,2): db.add(m.Usuario(id=i,nome='Teste',email=f'{i}@teste.local',senha_hash='teste',cpf=str(i),telefone='0',is_admin=i==2))
        for i in range(1,8): db.add(m.Curso(id=i,nome=f'Curso {i}',ativo=True))
        db.flush()
        for i,meses in enumerate((4,8,12),1): db.add(m.TempoAcessoCurso(id=i,curso_id=1,meses=meses,valor_cents=4990*i,ativo=True))
        db.add(m.Vendedor(id=1,nome='Parceiro',ativo=True))
        db.flush();db.add(m.CupomDesconto(codigo='AW265',vendedor_id=1,percentual_desconto=12,ativo=True));db.commit()
    with carregar_main_isolado(factory,motor) as main:
        main.MP_ACCESS_TOKEN="simulado-sem-validade"
        main.app.dependency_overrides[main.get_usuario_atual]=lambda:SimpleNamespace(id=1,email='1@teste.local',is_admin=False)
        response=Mock(status_code=201);response.json.return_value={'id':'pref_teste','init_point':'https://example.com/simulado'}
        with patch.object(main.requests,'post',return_value=response) as post,patch.object(main.requests,'get',return_value=response) as get:
            with TestClient(main.app) as client: yield main,client,factory,post,get
        main.app.dependency_overrides.clear()

def contrato(db,origem='PAGAMENTO',dias=30,curso=1):
    agora=datetime.utcnow();c=m.ContratacaoCurso(usuario_id=1,curso_id=curso,origem=origem,data_inicio=agora-timedelta(days=2),data_fim=agora+timedelta(days=dias))
    db.add(c);db.commit();return c.id

def demo(db,curso=1,dias=1,ativo=True,usuario=1):
    agora=datetime.utcnow();d=m.DemonstracaoCurso(usuario_id=usuario,curso_id=curso,data_inicio=agora-timedelta(hours=1),data_fim=agora+timedelta(days=dias),liberado_novamente_em=agora+timedelta(days=29),ativo=ativo)
    db.add(d);db.commit();return d.id

@pytest.mark.parametrize('quantidade',[0,1,2,3])
def test_limite_demo(ambiente_compra,quantidade):
    _,c,factory,_,_=ambiente_compra
    with factory() as db:
        for i in range(1,quantidade+1): demo(db,i)
    r=c.post('/cursos/4/demonstracao')
    assert r.status_code==(409 if quantidade==3 else 200)
    if quantidade==3: assert r.json()['detail'].startswith('Você já possui acesso gratuito a 3 cursos.')

@pytest.mark.parametrize('variacao',['expirada','inativa','futura','duplicada','admin','outro_aluno','curso_inativo'])
def test_contagem_so_cursos_validos(ambiente_compra,variacao):
    _,c,factory,_,_=ambiente_compra
    with factory() as db:
        demo(db,1);demo(db,2)
        if variacao=='expirada':demo(db,3,-1)
        elif variacao=='inativa':demo(db,3,ativo=False)
        elif variacao=='duplicada':demo(db,1)
        elif variacao=='admin':contrato(db,'ADMIN',curso=3)
        elif variacao=='outro_aluno':demo(db,3,usuario=2)
        elif variacao=='curso_inativo':demo(db,3);db.get(m.Curso,3).ativo=False;db.commit()
        else:
            did=demo(db,3);db.get(m.DemonstracaoCurso,did).data_inicio=datetime.utcnow()+timedelta(hours=1);db.commit()
    assert c.post('/cursos/4/demonstracao').status_code==200

def test_intervalo_30_dias(ambiente_compra):
    _,c,factory,_,_=ambiente_compra
    with factory() as db: did=demo(db,1,-1)
    assert c.post('/cursos/1/demonstracao').status_code==400
    with factory() as db:db.get(m.DemonstracaoCurso,did).liberado_novamente_em=datetime.utcnow()-timedelta(seconds=1);db.commit()
    assert c.post('/cursos/1/demonstracao').status_code==200

@pytest.mark.parametrize('origem,dias,bloqueado',[('PAGAMENTO',30,True),('PAGAMENTO',10,True),('PAGAMENTO',-1,False),('ADMIN',30,False)])
def test_acesso_pago_nao_pede_demo_admin_preservado(ambiente_compra,origem,dias,bloqueado):
    _,c,factory,_,_=ambiente_compra
    with factory() as db: cid=contrato(db,origem,dias)
    r=c.post('/cursos/1/demonstracao');assert r.status_code==(409 if bloqueado else 200)
    if bloqueado:assert 'enquanto seu acesso pago estiver vigente' in r.json()['detail']
    with factory() as db:assert db.get(m.ContratacaoCurso,cid).origem==origem

@pytest.mark.parametrize('origem,dias,status',[('PAGAMENTO',30,409),('PAGAMENTO',10,409),('PAGAMENTO',-1,200),('ADMIN',30,200)])
def test_compra_duplicada(ambiente_compra,origem,dias,status):
    _,c,factory,post,_=ambiente_compra
    with factory() as db: cid=contrato(db,origem,dias)
    r=c.post('/checkout/mercadopago',json={'tempo_acesso_id':1})
    assert r.status_code==status,r.text
    if status==409:
        post.assert_not_called()
        if dias==10:assert r.json()['detail']['contratacao_id']==cid
        else:assert 'últimos 15 dias' in r.json()['detail']
    with factory() as db:assert db.query(m.ContratacaoCurso).count()==1

@pytest.mark.parametrize('origem',['PAGAMENTO','ADMIN'])
def test_renovacao_preservada(ambiente_compra,origem):
    _,c,factory,post,_=ambiente_compra
    with factory() as db:cid=contrato(db,origem,10)
    r=c.post('/checkout/mercadopago',json={'tempo_acesso_id':1,'tipo_compra':'RENOVACAO','contratacao_id':cid})
    assert r.status_code==200,r.text
    assert post.call_args.kwargs['json']['expires'] is True

@pytest.mark.parametrize('tempo',[1,2,3])
def test_cupom_e_conversao_demo(ambiente_compra,tempo):
    _,c,factory,post,_=ambiente_compra
    with factory() as db:did=demo(db)
    assert c.post('/cupons-desconto/validar',json={'codigo_cupom':' aw265 '}).json()['percentual_desconto']==12
    r=c.post('/checkout/mercadopago',json={'tempo_acesso_id':tempo,'demonstracao_id':did,'codigo_cupom':' aw265 '})
    assert r.status_code==200,r.text
    esperado=4990*tempo-(4990*tempo*12+50)//100
    assert r.json()['valor_cents']==esperado
    assert post.call_args.kwargs['json']['items'][0]['unit_price']==esperado/100
    with factory() as db:
        assert db.query(m.OportunidadeCompra).one().demonstracao_id==did
        assert db.get(m.DemonstracaoCurso,did).ativo

@pytest.mark.parametrize('invalido',['inexistente','inativo','vendedor_inativo','sem_vendedor'])
def test_cupom_invalido_na_validacao_e_checkout(ambiente_compra,invalido):
    _,c,factory,post,_=ambiente_compra
    with factory() as db:
        cupom=db.query(m.CupomDesconto).one()
        if invalido=='inativo':cupom.ativo=False
        elif invalido=='vendedor_inativo':db.get(m.Vendedor,1).ativo=False
        elif invalido=='sem_vendedor':cupom.vendedor_id=None
        db.commit()
    codigo='XXXXX' if invalido=='inexistente' else 'AW265'
    assert c.post('/cupons-desconto/validar',json={'codigo_cupom':codigo}).status_code==400
    assert c.post('/checkout/mercadopago',json={'tempo_acesso_id':1,'codigo_cupom':codigo}).status_code==400
    post.assert_not_called()

def test_pendente_reutilizado_sem_cobrar_novamente(ambiente_compra):
    _,c,factory,post,get=ambiente_compra
    a=c.post('/checkout/mercadopago',json={'tempo_acesso_id':1}).json()
    b=c.post('/checkout/mercadopago',json={'tempo_acesso_id':1}).json()
    assert a['pagamento_id']==b['pagamento_id']
    assert post.call_count==1 and get.call_count==1
    with factory() as db:assert db.query(m.Pagamento).count()==1

def test_falha_mp_rollback(ambiente_compra):
    _,c,factory,post,_=ambiente_compra
    post.return_value.status_code=500;post.return_value.text='simulado'
    assert c.post('/checkout/mercadopago',json={'tempo_acesso_id':1}).status_code==502
    with factory() as db:
        assert db.query(m.Pagamento).count()==0
        assert db.query(m.OportunidadeCompra).count()==0

def test_concessao_admin_sem_limite_e_preserva_historico(ambiente_compra):
    main,c,factory,_,_=ambiente_compra
    with factory() as db:
        for i in (1,2,3):demo(db,i)
        contrato(db,'PAGAMENTO',curso=4)
    main.app.dependency_overrides[main.get_usuario_atual]=lambda:SimpleNamespace(id=2,is_admin=True)
    for curso in (4,5,6,7):
        r=c.post('/admin/acessos',json={'usuario_id':1,'curso_id':curso,'data_fim':(datetime.utcnow()+timedelta(days=60)).isoformat()+'Z'})
        assert r.status_code==200,r.text
    with factory() as db:
        assert db.query(m.ConcessaoAcessoAdmin).count()==4
        assert db.query(m.ContratacaoCurso).filter_by(origem='ADMIN').count()==4
        assert db.query(m.ContratacaoCurso).filter_by(origem='PAGAMENTO').count()==1
        assert db.query(m.DemonstracaoCurso).count()==3


def test_confirmacao_webhook_idempotencia_e_cobranca_legada(ambiente_compra):
    main,c,factory,_,get=ambiente_compra
    compra=c.post('/checkout/mercadopago',json={'tempo_acesso_id':1}).json()
    pid=compra['pagamento_id']
    def aprovado(pagamento):
        return {'id':'mp_simulado','status':'approved','date_approved':datetime.utcnow().isoformat()+'Z',
            'transaction_amount':49.90,'currency_id':'BRL',
            'external_reference':f'user:1|curso:1|tempo:1|pagamento:{pagamento}'}
    get.return_value.status_code=200;get.return_value.json.return_value=aprovado(pid)
    with patch.object(main,'validar_assinatura_mercadopago',return_value=True):
        for _ in range(2):
            r=c.post('/webhooks/mercadopago?type=payment&data.id=mp_simulado',json={'type':'payment'})
            assert r.status_code==200,r.text
        r=c.post('/pagamentos/confirmar',json={'payment_id':'mp_simulado','curso_id':1})
        assert r.status_code==200,r.text
        with factory() as db:
            assert db.query(m.ContratacaoCurso).count()==1
            assert db.query(m.PeriodoAcessoPagamento).count()==1
            original=db.get(m.Pagamento,pid)
            legado=m.Pagamento(usuario_id=1,curso_id=1,tempo_acesso_id=1,status='PENDENTE',valor_cents=4990,
                tipo_compra='NOVA',oportunidade_id=original.oportunidade_id,mp_preference_id='legado')
            db.add(legado);db.commit();segundo=legado.id
        get.return_value.json.return_value=aprovado(segundo)
        r=c.post('/webhooks/mercadopago?type=payment&data.id=outro_simulado',json={'type':'payment'})
        assert r.status_code==200,r.text
        assert r.json()['ocorrencia_financeira']=='COBRANCA_DUPLICADA'
    with factory() as db:
        assert db.query(m.ContratacaoCurso).count()==1
        assert db.query(m.Pagamento).count()==2
        assert db.get(m.Pagamento,pid).aprovado_em is not None

@pytest.mark.parametrize('origem',['ADMIN','PAGAMENTO'])
def test_renovacao_fora_janela_bloqueada_sem_mp(ambiente_compra,origem):
    _,c,factory,post,_=ambiente_compra
    with factory() as db:cid=contrato(db,origem,30)
    assert c.post('/checkout/mercadopago',json={'tempo_acesso_id':1,'tipo_compra':'RENOVACAO','contratacao_id':cid}).status_code==409
    post.assert_not_called()

def test_reabrir_pendente_falha_sem_novo_titulo(ambiente_compra):
    _,c,factory,post,get=ambiente_compra
    assert c.post('/checkout/mercadopago',json={'tempo_acesso_id':1}).status_code==200
    get.return_value.status_code=503
    assert c.post('/checkout/mercadopago',json={'tempo_acesso_id':1}).status_code==502
    assert post.call_count==1
    with factory() as db:assert db.query(m.Pagamento).count()==1

def test_limite_oito_titulos_preservado(ambiente_compra):
    _,c,factory,post,_=ambiente_compra
    r=c.post('/checkout/mercadopago',json={'tempo_acesso_id':1})
    pid=r.json()['pagamento_id']
    with factory() as db:
        oid=db.get(m.Pagamento,pid).oportunidade_id
        for i in range(7):db.add(m.Pagamento(usuario_id=1,curso_id=1,tempo_acesso_id=1,status='REJECTED',valor_cents=4990,tipo_compra='NOVA',oportunidade_id=oid,mp_preference_id=f'legado{i}'))
        db.commit()
    assert c.post('/checkout/mercadopago',json={'tempo_acesso_id':1}).status_code==200
    assert c.post('/checkout/mercadopago',json={'tempo_acesso_id':2}).status_code==409
    assert post.call_count==1
    with factory() as db:assert db.query(m.Pagamento).count()==8
