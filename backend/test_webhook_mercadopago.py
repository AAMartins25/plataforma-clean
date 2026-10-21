"""Webhook assinado com banco isolado; sem chamada ao Mercado Pago real."""
from unittest.mock import patch
import pytest
from app import models as m
from test_compras_fluxo import ambiente_compra, motor
from test_transacoes_mp import preparar
from itertools import count
eventos=count()

def notificar(ambiente,tx=101):
    from test_pausa_financeira import enviar
    return enviar(ambiente,tx,f'evento-regressao-{next(eventos)}')

@pytest.mark.parametrize('campo,valor',[
    ('transaction_amount',39.90),('currency_id','USD'),
    ('external_reference','user:1|curso:1|tempo:2|pagamento:{pid}'),
])
def test_webhook_rejeita_dados_divergentes(ambiente_compra,campo,valor):
    pid,_,tx,_=preparar(ambiente_compra)
    tx['101'][campo]=valor.format(pid=pid) if isinstance(valor,str) else valor
    with patch.object(ambiente_compra[0],'validar_assinatura_mercadopago',return_value=True):
        r=notificar(ambiente_compra)
        assert r.status_code==200 and r.json()['armazenado']
        assert r.json()['erro_codigo']==409 and not r.json()['processado']
    with ambiente_compra[2]() as db:
        assert db.get(m.Pagamento,pid).aprovado_em is None
        assert db.query(m.ContratacaoCurso).count()==0

def test_webhook_aprova_e_repeticao_nao_duplica(ambiente_compra):
    _,dados,tx,_=preparar(ambiente_compra)
    tx['101']=dados(101,'approved')
    with patch.object(ambiente_compra[0],'validar_assinatura_mercadopago',return_value=True):
        for _ in range(2): assert notificar(ambiente_compra).status_code==200
    with ambiente_compra[2]() as db:
        assert db.query(m.ContratacaoCurso).count()==1
        assert db.query(m.PeriodoAcessoPagamento).count()==1

@pytest.mark.parametrize('status',['pending','rejected','cancelled','refunded','charged_back','in_process'])
def test_webhook_status_tardio_preserva_periodo(ambiente_compra,status):
    pid,dados,tx,_=preparar(ambiente_compra)
    with patch.object(ambiente_compra[0],'validar_assinatura_mercadopago',return_value=True):
        tx['101']=dados(101,'approved');notificar(ambiente_compra)
        tx['101']=dados(101,status)
        assert notificar(ambiente_compra).status_code==200
    with ambiente_compra[2]() as db:
        assert db.query(m.PeriodoAcessoPagamento).count()==1
        assert db.get(m.Pagamento,pid).aprovado_em is not None
        assert db.get(m.Pagamento,pid).status==('APPROVED' if status in ('pending','rejected') else status.upper())

def test_webhook_falha_na_concessao_desfaz_pagamento(ambiente_compra):
    pid,dados,tx,_=preparar(ambiente_compra);tx['101']=dados(101,'approved')
    main=ambiente_compra[0]
    with patch.object(main,'validar_assinatura_mercadopago',return_value=True),patch.object(main,'registrar_contratacao',side_effect=RuntimeError('Falha simulada')):
        r=notificar(ambiente_compra)
        assert r.status_code==200 and r.json()['armazenado']
        assert r.json()['erro_codigo']==500 and not r.json()['processado']
    with ambiente_compra[2]() as db:
        assert db.get(m.Pagamento,pid).aprovado_em is None
        assert db.query(m.PeriodoAcessoPagamento).count()==0

def test_webhook_assinatura_invalida_nao_consulta_mp(ambiente_compra):
    preparar(ambiente_compra);get=ambiente_compra[4];get.reset_mock()
    with patch.object(ambiente_compra[0],'validar_assinatura_mercadopago',return_value=False):
        assert notificar(ambiente_compra).status_code==401
    get.assert_not_called()
