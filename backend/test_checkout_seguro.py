"""Novos checkouts com provedor simulado, sem conexões externas."""
from unittest.mock import Mock, patch
import pytest
import requests
from app import models as m
from test_compras_fluxo import ambiente_compra, motor
from test_transacoes_mp import preparar, confirmar
from test_pausa_financeira import enviar, modo


def test_identidade_persistida_antes_do_envio(ambiente_compra):
    main,client,f,post,_=ambiente_compra
    def enviar_preferencia(*a,**kw):
        with f() as db:
            p=db.query(m.Pagamento).one()
            assert p.status=='CHECKOUT_INDEFINIDO'
            assert p.checkout_recebedor_id=='123456'
            assert kw['json']['external_reference']=='checkout:'+p.checkout_identidade
            assert len(p.checkout_identidade)==43
        r=Mock(status_code=201);r.json.return_value={'id':'pref','init_point':'https://example.com','collector_id':123456}
        return r
    post.side_effect=enviar_preferencia
    assert client.post('/checkout/mercadopago',json={'tempo_acesso_id':1}).status_code==200


@pytest.mark.parametrize('metodo',['pix','visa'])
def test_duas_aprovacoes_sem_merchant_order(ambiente_compra,metodo):
    pid,dados,tx,_=preparar(ambiente_compra)
    api=ambiente_compra[4].side_effect
    def negar_ordem(url,**kw):
        assert '/merchant_orders/' not in url
        return api(url,**kw)
    ambiente_compra[4].side_effect=negar_ordem
    assert confirmar(ambiente_compra,101).json()['status']=='PENDING'
    for ident in (101,102):
        tx[str(ident)]=dados(ident,'approved');tx[str(ident)]['payment_method_id']=metodo
    assert confirmar(ambiente_compra,101).json()['liberou_acesso']
    assert confirmar(ambiente_compra,102).json()['ocorrencia_financeira']=='COBRANCA_DUPLICADA'
    tx['101']=dados(101,'pending')
    assert confirmar(ambiente_compra,101).json()['status']=='APPROVED'
    with ambiente_compra[2]() as db:
        assert db.query(m.PeriodoAcessoPagamento).count()==1
        assert db.query(m.ContratacaoCurso).count()==1
        assert db.query(m.Pagamento).count()==2
        assert db.get(m.Pagamento,pid).checkout_identidade is not None
    assert ambiente_compra[3].call_count==1


@pytest.mark.parametrize('campo,valor',[
 ('collector_id',999),('collector_id',None),('live_mode',False),('live_mode',1),
 ('currency_id','USD'),('transaction_amount',1),('id','999'),
 ('external_reference',None),('external_reference','checkout:invalido'),
 ('external_reference','checkout:'+'A'*43),('external_reference','user:1|curso:1|tempo:1|pagamento:1'),
 ('status','desconhecido')])
def test_evidencia_invalida_rollback(ambiente_compra,campo,valor):
    pid,_,tx,_=preparar(ambiente_compra)
    tx['101'][campo]=valor
    assert confirmar(ambiente_compra,101).status_code in (400,409,502)
    with ambiente_compra[2]() as db:
        assert db.get(m.Pagamento,pid).mp_payment_id is None
        assert db.query(m.PeriodoAcessoPagamento).count()==0


def test_sem_recebedor_nao_cria_checkout(ambiente_compra,monkeypatch):
    monkeypatch.delenv('MP_COLLECTOR_ID')
    assert ambiente_compra[1].post('/checkout/mercadopago',json={'tempo_acesso_id':1}).status_code==503
    ambiente_compra[3].assert_not_called()
    with ambiente_compra[2]() as db: assert db.query(m.Pagamento).count()==0


@pytest.mark.parametrize('falha',['timeout','http','json','incompleto'])
def test_resultado_incerto_impede_nova_preferencia(ambiente_compra,falha):
    _,client,f,post,get=ambiente_compra
    if falha=='timeout':post.side_effect=requests.Timeout('SEGREDO')
    else:
        r=Mock(status_code=503 if falha=='http' else 201)
        r.text='SEGREDO'
        if falha=='json':r.json.side_effect=ValueError('SEGREDO')
        else:r.json.return_value={}
        post.return_value=r
    result=client.post('/checkout/mercadopago',json={'tempo_acesso_id':1})
    assert result.status_code==502 and 'SEGREDO' not in result.text
    assert client.post('/checkout/mercadopago',json={'tempo_acesso_id':1}).status_code==409
    with f() as db:
        assert db.query(m.OportunidadeCompra).count()==1
        raiz=db.query(m.Pagamento).one()
        assert raiz.checkout_identidade and raiz.status=='CHECKOUT_INDEFINIDO'
        ident=raiz.checkout_identidade
    from datetime import datetime
    dados={'id':'101','external_reference':'checkout:'+ident,'collector_id':123456,'live_mode':True,
        'status':'approved','transaction_amount':49.90,'currency_id':'BRL',
        'date_approved':datetime.utcnow().isoformat()+'Z'}
    r=Mock(status_code=200);r.json.return_value=dados;get.return_value=r
    assert confirmar(ambiente_compra,101).status_code==409
    assert post.call_count==1


def test_webhooks_repetidos_e_fora_ordem(ambiente_compra):
    _,dados,tx,_=preparar(ambiente_compra)
    tx['101']=dados(101,'approved')
    for _ in range(2): assert enviar(ambiente_compra,101,'seguro1').status_code==200
    tx['101']=dados(101,'pending')
    assert enviar(ambiente_compra,101,'seguro2').status_code==200
    with ambiente_compra[2]() as db:
        assert db.query(m.PeriodoAcessoPagamento).count()==1
        assert db.query(m.ContratacaoCurso).count()==1


def test_referencia_outra_compra_nao_associa(ambiente_compra):
    pid,_,tx,_=preparar(ambiente_compra)
    assert confirmar(ambiente_compra,101).status_code==200
    with ambiente_compra[2]() as db:
        op=m.OportunidadeCompra(usuario_id=1,curso_id=1,tipo_compra='NOVA')
        db.add(op);db.flush()
        raiz=m.Pagamento(usuario_id=1,curso_id=1,tempo_acesso_id=1,valor_cents=4990,
            status='PENDENTE',tipo_compra='NOVA',oportunidade_id=op.id,
            moeda='BRL',provedor='MERCADO_PAGO',checkout_recebedor_id='123456',
            checkout_identidade='B'*43,checkout_meses=4,mp_preference_id='outra')
        db.add(raiz);db.commit()
    tx['101']['external_reference']='checkout:'+'B'*43
    assert confirmar(ambiente_compra,101).status_code==409


def test_periodo_snapshot_independente_do_catalogo(ambiente_compra):
    from dateutil.relativedelta import relativedelta
    _,dados,tx,_=preparar(ambiente_compra)
    with ambiente_compra[2]() as db:
        db.get(m.TempoAcessoCurso,1).meses=6
        db.commit()
    tx['101']=dados(101,'approved')
    assert confirmar(ambiente_compra,101).json()['liberou_acesso']
    with ambiente_compra[2]() as db:
        periodo=db.query(m.PeriodoAcessoPagamento).one()
        assert periodo.data_fim==periodo.data_inicio+relativedelta(months=4)


@pytest.mark.parametrize('campo,valor',[('collector_id',999),('collector_id',None),('external_reference','SEGREDO-OUTRA')])
def test_resposta_preferencia_sem_vinculo_nao_abre_checkout(ambiente_compra,campo,valor):
    _,c,f,post,_=ambiente_compra
    post.return_value.json.return_value={'id':'pref','init_point':'https://example.com','collector_id':123456,campo:valor}
    r=c.post('/checkout/mercadopago',json={'tempo_acesso_id':1})
    assert r.status_code==502 and 'SEGREDO' not in r.text
    assert c.post('/checkout/mercadopago',json={'tempo_acesso_id':1}).status_code==409
    with f() as db:
        p=db.query(m.Pagamento).one()
        assert p.status=='CHECKOUT_INDEFINIDO' and p.mp_preference_id is None
    post.assert_called_once()


def test_referencia_nao_aparece_em_logs(ambiente_compra,caplog):
    pid,dados,tx,_=preparar(ambiente_compra)
    ref=dados(101)['external_reference']
    tx['101']=dados(101,'approved')
    assert confirmar(ambiente_compra,101).json()['liberou_acesso']
    assert ref not in caplog.text
    assert ref[len('checkout:'):] not in caplog.text
    assert ambiente_compra[0].MP_ACCESS_TOKEN not in caplog.text


def test_incerto_legado_mantem_validacao_merchant(ambiente_compra):
    pid,dados,tx,ordem=preparar(ambiente_compra,legado=True)
    with ambiente_compra[2]() as db:
        p=db.get(m.Pagamento,pid);p.status='CHECKOUT_INDEFINIDO';p.mp_preference_id=None;db.commit()
    tx['101']=dados(101,'approved')
    assert confirmar(ambiente_compra,101).json()['liberou_acesso']
    assert any('/merchant_orders/' in call.args[0] for call in ambiente_compra[4].call_args_list)
    with ambiente_compra[2]() as db:
        assert db.get(m.Pagamento,pid).mp_preference_id==ordem['preference_id']
