"""Correções de escopo e recebimento durável; SQLite e provedor simulado."""
from unittest.mock import Mock, patch
import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from app import models as m
from app.pausa_financeira import inbox, controle
from app.direitos_acesso import curso_vigente
from app.contestacoes import registrar_observacao
from test_compras_fluxo import motor, ambiente_compra
from test_contestacoes_reconstruido import compra, caso, admin, confirmar, bloquear, mp_dados


def entregar(ambiente, caso_mp=None, evento=500, envelope=None, falha=False):
    main,c,_,_,_=ambiente
    payload=envelope or {'type':'topic_chargebacks_wh','id':evento,'data':{'id':999}}
    caso_mp=caso_mp or {'id':'999','payments':[101],'currency':'BRL','amount':49.90}
    def consultar(url, **kw):
        r=Mock(status_code=503 if falha else 200)
        r.json.return_value=caso_mp if '/chargebacks/' in url else mp_dados(status='approved')
        return r
    with patch.object(main,'validar_assinatura_mercadopago',return_value=True), \
         patch('app.contestacoes.requests.get',side_effect=consultar) as get:
        resposta=c.post('/webhooks/mercadopago?data.id=999',json=payload)
    return resposta, get.call_count


def generico(ambiente):
    main,_,f,_,_=ambiente
    with f() as db:pid,cid=compra(db)
    resposta=Mock(status_code=200);resposta.json.return_value=mp_dados()
    with f() as db:main.processar_pagamento_mp('101',db,resposta_mp=resposta)
    with f() as db:ident=db.query(m.ContestacaoPagamento).one().id
    return pid,cid,ident


def test_generico_e_identificador_sem_prova_nao_autorizam_bloqueio(ambiente_compra):
    main,c,f,_,_=ambiente_compra
    pid,cid,ident=generico(ambiente_compra)
    admin(main);assert confirmar(c,ident).status_code==200
    for forjar_identificador in (False,True):
        if forjar_identificador:
            with f() as db:
                registro=db.get(m.ContestacaoPagamento,ident)
                registro.mp_dispute_id='999';registro.status='ESCOPO_INTEGRAL_MP';db.commit()
        r=bloquear(c,ident)
        assert r.status_code==409 and r.json()['detail']['codigo']=='CONFERENCIA_NECESSARIA'
    with f() as db:
        assert curso_vigente(db,1,1)
        assert db.get(m.ContestacaoPagamento,ident).bloqueio_executado_em is None


@pytest.mark.parametrize('pagamentos,valor', [([101],20),([101,102],99.80)])
def test_generico_seguido_de_especifico_ambiguo_preserva_evento_e_acesso(ambiente_compra,pagamentos,valor):
    main,c,f,_,_=ambiente_compra
    pid,cid,ident=generico(ambiente_compra)
    admin(main);assert confirmar(c,ident).status_code==200
    with f() as db:
        data=db.get(m.ContestacaoPagamento,ident).devolucao_confirmada_em
    r,_=entregar(ambiente_compra,{'id':'999','payments':pagamentos,'currency':'BRL','amount':valor})
    assert r.status_code==200 and r.json()['armazenado'] and not r.json()['processado']
    assert bloquear(c,ident).status_code==409
    resposta=c.get('/admin/contestacoes').json()
    assert resposta['contestacoes'][0]['situacao_acesso']=='CONFERENCIA_NECESSARIA'
    assert resposta['pendencias'][0]['caso_mp']=='999'
    assert resposta['pendencias'][0]['pagamentos_mp']==[str(p) for p in pagamentos]
    with f() as db:
        registro=db.get(m.ContestacaoPagamento,ident)
        assert registro.devolucao_confirmada_em==data and registro.bloqueio_executado_em is None
        evento=db.execute(select(inbox)).mappings().one()
        assert evento['estado']=='ERRO' and evento['resultado']['escopo']=='CONFERENCIA_NECESSARIA'
        assert evento['payment_id']=='999' and curso_vigente(db,1,1)


def test_comprovacao_integral_libera_apenas_acao_manual(ambiente_compra):
    main,c,f,_,_=ambiente_compra
    pid,cid,ident=generico(ambiente_compra)
    admin(main);assert confirmar(c,ident).status_code==200
    r,chamadas=entregar(ambiente_compra)
    assert r.status_code==200 and r.json()['processado'] and chamadas==2
    with f() as db:
        registro=db.get(m.ContestacaoPagamento,ident)
        assert registro.mp_dispute_id=='999' and registro.bloqueio_executado_em is None
        assert curso_vigente(db,1,1)
        prova=db.execute(select(inbox.c.resultado)).scalar_one()
        assert prova['escopo']=='INTEGRAL_VERIFICADO' and prova['pagamentos_mp']==['101']
    assert c.get('/admin/contestacoes').json()['contestacoes'][0]['situacao_acesso']=='BLOQUEIO_DISPONIVEL'
    assert bloquear(c,ident).status_code==200
    with f() as db:assert not curso_vigente(db,1,1)
    r,chamadas=entregar(ambiente_compra)
    assert r.status_code==200 and chamadas==0
    with f() as db:assert db.query(m.ContestacaoPagamento).count()==1


def test_evento_parcial_posterior_invalida_prova_integral_anterior(ambiente_compra):
    main,c,f,_,_=ambiente_compra
    pid,cid,ident=generico(ambiente_compra)
    assert entregar(ambiente_compra)[0].json()['processado']
    admin(main);assert confirmar(c,ident).status_code==200
    assert c.get('/admin/contestacoes').json()['contestacoes'][0]['situacao_acesso']=='BLOQUEIO_DISPONIVEL'
    entregar(ambiente_compra,{'id':'999','payments':[101],'currency':'BRL','amount':20},evento=501)
    assert bloquear(c,ident).status_code==409
    with f() as db:
        assert len(db.execute(select(inbox.c.id)).all())==2
        assert curso_vigente(db,1,1)


@pytest.mark.parametrize('tipo', ['indisponivel','envelope','caso_incompativel','sem_pagamentos'])
def test_evento_inconclusivo_fica_visivel_sem_associacao_presumida(ambiente_compra,tipo):
    main,c,f,_,_=ambiente_compra
    with f() as db:compra(db)
    caso_mp={'id':'998' if tipo=='caso_incompativel' else '999','payments':[] if tipo=='sem_pagamentos' else [101], 'currency':'BRL','amount':49.90}
    payload={'type':'topic_chargebacks_wh','id':500,'data':{'id':998 if tipo=='envelope' else 999}}
    r,_=entregar(ambiente_compra,caso_mp,envelope=payload,falha=tipo=='indisponivel')
    assert r.status_code==200 and r.json()['armazenado'] and not r.json()['processado']
    admin(main)
    pendencias=c.get('/admin/contestacoes').json()['pendencias']
    assert len(pendencias)==1 and pendencias[0]['situacao']=='CONFERENCIA_NECESSARIA'
    with f() as db:
        assert db.query(m.ContestacaoPagamento).count()==0
        assert db.execute(select(inbox.c.estado)).scalar_one()=='ERRO'
        assert curso_vigente(db,1,1)


def test_sem_persistencia_nao_confirma_recebimento(ambiente_compra):
    main,c,_,_,_=ambiente_compra
    with patch.object(main,'validar_assinatura_mercadopago',return_value=True), \
         patch.object(main.app.state.protecao_financeira,'armazenar',side_effect=SQLAlchemyError('simulado')), \
         patch('app.contestacoes.requests.get') as get:
        r=c.post('/webhooks/mercadopago?data.id=999',json={'type':'chargebacks','id':500,'data':{'id':999}})
    assert r.status_code==503 and get.call_count==0


def test_assinatura_invalida_nao_alimenta_inbox(ambiente_compra):
    main,c,f,_,_=ambiente_compra
    with patch.object(main,'validar_assinatura_mercadopago',return_value=False):
        r=c.post('/webhooks/mercadopago?data.id=999',json={'type':'chargebacks','id':500,'data':{'id':999}})
    assert r.status_code==401
    with f() as db:assert not db.execute(select(inbox.c.id)).first()


def test_pausa_preserva_recebimento_e_recuperacao_mantem_historico(ambiente_compra):
    main,c,f,_,_=ambiente_compra
    with f() as db:compra(db)
    with f.begin() as db:db.execute(controle.update().values(modo='PAUSADO'))
    r,chamadas=entregar(ambiente_compra)
    assert r.status_code==200 and r.json()['armazenado'] and chamadas==0
    with f() as db:assert db.execute(select(inbox.c.estado)).scalar_one()=='PENDENTE'
    with f.begin() as db:db.execute(controle.update().values(modo='NORMAL'))
    r,_=entregar(ambiente_compra,falha=True)
    assert not r.json()['processado']
    r,_=entregar(ambiente_compra)
    assert r.json()['processado']
    with f() as db:
        evento=db.execute(select(inbox)).mappings().one()
        assert evento['estado']=='CONCLUIDO' and evento['tentativas']==2
        assert any(p.get('escopo')=='CONFERENCIA_NECESSARIA' for p in evento['resultado']['historico'])


def test_json_invalido_com_topico_especifico_permanece_registrado(ambiente_compra):
    main,c,f,_,_=ambiente_compra
    with patch.object(main,'validar_assinatura_mercadopago',return_value=True):
        r=c.post('/webhooks/mercadopago?data.id=999&type=chargebacks',
            content='{invalido',headers={'Content-Type':'application/json','x-request-id':'evento-json-invalido'})
    assert r.status_code==200 and r.json()['armazenado']
    with f() as db:
        evento=db.execute(select(inbox)).mappings().one()
        assert evento['estado']=='ERRO' and not evento['resultado']['envelope_valido']


def test_falha_de_dominio_nao_grava_comprovacao_integral(ambiente_compra):
    main,c,f,_,_=ambiente_compra
    with f() as db:compra(db)
    with patch('app.contestacoes.receber_caso',side_effect=RuntimeError('falha simulada')):
        r,_=entregar(ambiente_compra)
    assert r.status_code==200 and not r.json()['processado']
    with f() as db:
        assert db.query(m.ContestacaoPagamento).count()==0
        evento=db.execute(select(inbox)).mappings().one()
        assert evento['estado']=='ERRO'
        assert evento['resultado']['escopo']=='CONFERENCIA_NECESSARIA'
        assert evento['resultado']['pagamentos_mp']==['101']


def test_eventos_sem_identidade_nao_se_fundem_nem_viram_prova(ambiente_compra):
    main,c,f,_,_=ambiente_compra
    with patch.object(main,'validar_assinatura_mercadopago',return_value=True), \
         patch('app.contestacoes.requests.get') as get:
        for _ in range(2):
            r=c.post('/webhooks/mercadopago?data.id=999',json={'type':'chargebacks','data':{'id':999}})
            assert r.status_code==200 and r.json()['armazenado'] and not r.json()['processado']
    assert get.call_count==0
    with f() as db:
        eventos=db.execute(select(inbox)).mappings().all()
        assert len(eventos)==2
        assert all(e['estado']=='ERRO' and e['resultado']['escopo']=='CONFERENCIA_NECESSARIA' for e in eventos)


def test_recuperacao_administrativa_despacha_caso_sem_confundir_id_de_pagamento(ambiente_compra):
    main,c,f,_,_=ambiente_compra
    with f() as db:compra(db)
    r,_=entregar(ambiente_compra,falha=True)
    assert r.json()['armazenado'] and not r.json()['processado']
    with f() as db:ident=db.execute(select(inbox.c.id)).scalar_one()
    with f.begin() as db:db.execute(controle.update().values(modo='RECUPERACAO'))
    urls=[]
    def consultar(url,**kw):
        urls.append(url)
        resp=Mock(status_code=200)
        resp.json.return_value=({'id':'999','payments':[101],'currency':'BRL','amount':49.90}
            if '/chargebacks/' in url else mp_dados(status='approved'))
        return resp
    with patch('app.contestacoes.requests.get',side_effect=consultar):
        resultado=main.app.state.protecao_financeira.recuperar(1,notificacao_id=ident)
    assert resultado['resultados'][0]['processado']
    assert urls==['https://api.mercadopago.com/v1/chargebacks/999',
        'https://api.mercadopago.com/v1/payments/101']
    with f() as db:
        assert db.execute(select(inbox.c.estado)).scalar_one()=='CONCLUIDO'
        assert db.query(m.ContestacaoPagamento).one().bloqueio_executado_em is None
