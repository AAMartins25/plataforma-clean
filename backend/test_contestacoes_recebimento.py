"""Autenticação real do tópico oficial com caso e pagamento inteiramente simulados."""
import hashlib
import hmac
from unittest.mock import Mock, patch
import pytest
from sqlalchemy import select
from app import models as m
from app.pausa_financeira import inbox
from app.direitos_acesso import curso_vigente
from test_compras_fluxo import motor, ambiente_compra
from test_contestacoes_reconstruido import compra, mp_dados

@pytest.mark.parametrize('signature', ['valida','invalida','outro_recurso','ausente'])
def test_official_chargeback_hmac_authentication(ambiente_compra,signature):
    main,c,f,_,_=ambiente_compra
    with f() as db:compra(db)
    main.MP_WEBHOOK_SECRET='segredo-ficticio-exclusivo'
    recurso='998' if signature=='outro_recurso' else '999'
    manifest=f'id:{recurso};request-id:notificacao-ficticia;ts:1234567890;'
    digest=hmac.new(main.MP_WEBHOOK_SECRET.encode(),manifest.encode(),hashlib.sha256).hexdigest()
    headers={'x-request-id':'notificacao-ficticia'}
    if signature!='ausente':headers['x-signature']=f'ts=1234567890,v1={digest if signature!="invalida" else "incorreto"}'
    def canonical(url,**kw):
        r=Mock(status_code=200)
        r.json.return_value=({'id':123456} if url.endswith('/users/me') else {'id':'999','payments':[101],'currency':'BRL','amount':49.90}
            if '/chargebacks/' in url else mp_dados(status='approved'))
        return r
    with patch('app.contestacoes.requests.get',side_effect=canonical) as get:
        r=c.post('/webhooks/mercadopago?data.id=999&type=topic_chargebacks_wh',headers=headers,
            json={'type':'topic_chargebacks_wh','id':500,'data':{'id':999,'payment_id':666}})
    assert r.status_code==(200 if signature=='valida' else 401),r.text
    with f() as db:
        assert curso_vigente(db,1,1)
        if signature=='valida':
            assert get.call_count==3 and r.json()['processado']
            assert db.query(m.ContestacaoPagamento).one().bloqueio_executado_em is None
            assert db.execute(select(inbox.c.estado)).scalar_one()=='CONCLUIDO'
        else:
            assert get.call_count==0
            assert not db.execute(select(inbox.c.id)).first()

@pytest.mark.parametrize('account', ['valida','indisponivel','identidade_invalida','recebedor_divergente'])
def test_chargeback_sends_authenticated_seller_header(ambiente_compra,account):
    main,c,f,_,_=ambiente_compra
    with f() as db:compra(db)
    calls=[]
    def canonical(url,**kw):
        calls.append(url)
        r=Mock(status_code=200)
        if url.endswith('/users/me'):
            r.status_code=503 if account=='indisponivel' else 200
            r.json.return_value={'id':'invalido' if account=='identidade_invalida' else 123456}
        elif '/chargebacks/' in url:
            assert kw['headers']['X-Caller-Id']=='123456'
            r.json.return_value={'id':'999','payments':[101],'currency':'BRL','amount':49.90}
        else:
            data=mp_dados(status='approved')
            if account=='recebedor_divergente':data['collector_id']=654321
            r.json.return_value=data
        return r
    with patch.object(main,'validar_assinatura_mercadopago',return_value=True), \
            patch('app.contestacoes.requests.get',side_effect=canonical):
        r=c.post('/webhooks/mercadopago?data.id=999&type=topic_chargebacks_wh',
            json={'type':'topic_chargebacks_wh','id':501,'data':{'id':999,'user_id':654321}})
    assert r.status_code==200 and r.json()['armazenado']
    assert r.json()['processado'] is (account=='valida'),r.text
    with f() as db:
        assert curso_vigente(db,1,1)
        assert db.query(m.ContestacaoPagamento).count()==(1 if account=='valida' else 0)
        if account!='valida':assert db.execute(select(inbox.c.estado)).scalar_one()=='ERRO'
    if account in ('indisponivel','identidade_invalida'):
        assert len(calls)==1
