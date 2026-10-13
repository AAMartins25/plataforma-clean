"""Transações distintas com API simulada e banco isolado."""
import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from app import models as m
from test_compras_fluxo import ambiente_compra, motor, contrato, demo


def preparar(ambiente, renovacao=False, cupom=False, legado=False):
    main, client, factory, _, get = ambiente
    payload = {'tempo_acesso_id': 1}
    with factory() as db:
        if renovacao:
            payload['contratacao_id'] = contrato(db, dias=5)
            payload['tipo_compra'] = 'RENOVACAO'
        else:
            payload['demonstracao_id'] = demo(db)
    if cupom:
        payload['codigo_cupom'] = 'AW265'
    if legado:
        from app.oportunidades import obter_oportunidade
        with factory() as db:
            op = obter_oportunidade(db, 1, 1, 'NOVA', demonstracao_id=payload.get('demonstracao_id'))
            antigo = m.Pagamento(usuario_id=1,curso_id=1,tempo_acesso_id=1,
                valor_cents=4990,status='PENDENTE',tipo_compra='NOVA',
                oportunidade_id=op.id,mp_preference_id='pref_legada')
            db.add(antigo);db.commit();pid=antigo.id
    else:
        r = client.post('/checkout/mercadopago', json=payload)
        assert r.status_code == 200, r.text
        pid = r.json()['pagamento_id']
    with factory() as db:
        raiz = db.get(m.Pagamento, pid)
        valor, pref = raiz.valor_cents / 100, raiz.mp_preference_id
        identidade = raiz.checkout_identidade
    def dados(tx, status='pending'):
        return {'id': str(tx), 'status': status, 'payment_method_id': 'pix',
                'transaction_amount': valor, 'currency_id': 'BRL',
                'date_approved': datetime.utcnow().isoformat() + 'Z',
                'external_reference': ('checkout:'+identidade if identidade else f'user:1|curso:1|tempo:1|pagamento:{pid}'),
                'collector_id':123456,'live_mode':True,
                'order': {'id': 'ordem'}}
    transacoes = {str(i): dados(i) for i in (101, 102, 103)}
    ordem = {'id': 'ordem', 'preference_id': pref,
             'external_reference': dados(101)['external_reference'],
             'payments': [{'id': str(i)} for i in (101, 102, 103)]}
    def api(url, **kwargs):
        if '/merchant_orders/' in url:
            corpo = ordem
        elif '/checkout/preferences/' in url:
            corpo = {'id': pref, 'init_point': 'https://example.com/simulado'}
        else:
            corpo = transacoes[url.rsplit('/', 1)[1]]
        resposta = Mock(status_code=200)
        resposta.json.return_value = corpo
        return resposta
    get.side_effect = api
    return pid, dados, transacoes, ordem


def confirmar(ambiente, tx):
    return ambiente[1].post('/pagamentos/confirmar', json={'payment_id': tx, 'curso_id': 1})


async def webhook(main, db, tx):
    request = SimpleNamespace(query_params={'type': 'payment', 'data.id': str(tx)},
                              headers={})
    async def json():
        return {'type': 'payment', 'data': {'id': str(tx)}}
    request.json = json
    return await main.webhook_mercadopago(request, db)


def test_tres_tentativas_identidades_e_checkout(ambiente_compra):
    pid, _, _, _ = preparar(ambiente_compra, cupom=True)
    for tx in (101, 102, 103, 102, 101):
        r = confirmar(ambiente_compra, tx)
        assert r.status_code == 200, r.text
        assert r.json()['status'] == 'PENDING' and not r.json()['liberou_acesso']
    main, client, f, post, _ = ambiente_compra
    with f() as db:
        linhas = db.query(m.Pagamento).order_by(m.Pagamento.id).all()
        assert [p.mp_payment_id for p in linhas] == ['101', '102', '103']
        assert [p.pagamento_origem_id for p in linhas] == [None, pid, pid]
        assert all(p.codigo_cupom == 'AW265' and p.valor_cents == linhas[0].valor_cents for p in linhas)
        assert db.query(m.ContratacaoCurso).count() == 0
        did = db.query(m.DemonstracaoCurso).one().id
    r = client.post('/checkout/mercadopago', json={'tempo_acesso_id': 1, 'demonstracao_id': did, 'codigo_cupom': 'AW265'})
    assert r.json()['pagamento_id'] == pid
    post.assert_called_once()


@pytest.mark.parametrize('primeira', [101, 102])
@pytest.mark.parametrize('renovacao', [False, True])
def test_aprovacoes_unicas_e_duplicadas(ambiente_compra, primeira, renovacao):
    pid, dados, transacoes, _ = preparar(ambiente_compra, renovacao=renovacao)
    for tx in (101, 102): assert confirmar(ambiente_compra, tx).status_code == 200
    segunda = 203 - primeira
    transacoes[str(primeira)] = dados(primeira, 'approved')
    assert confirmar(ambiente_compra, primeira).json()['liberou_acesso']
    transacoes[str(segunda)] = dados(segunda, 'approved')
    r = confirmar(ambiente_compra, segunda)
    assert r.json()['ocorrencia_financeira'] == 'COBRANCA_DUPLICADA'
    assert not confirmar(ambiente_compra, primeira).json()['liberou_acesso']
    with ambiente_compra[2]() as db:
        assert db.query(m.ContratacaoCurso).count() == 1
        assert db.query(m.PeriodoAcessoPagamento).count() == 1
        assert db.query(m.Pagamento).filter(m.Pagamento.aprovado_em.isnot(None)).count() == 2
        assert db.query(m.OportunidadeCompra).one().concluida_em is not None
    ambiente_compra[3].assert_called_once()  # Somente criação da preferência; nenhum estorno.


@pytest.mark.parametrize('erro', ['pref', 'reference', 'order_id', 'payments', 'id', 'user', 'course', 'amount', 'currency', 'missing_order'])
def test_vinculos_invalidos_nao_criam_linha(ambiente_compra, erro):
    pid, _, transacoes, ordem = preparar(ambiente_compra, legado=True)
    assert confirmar(ambiente_compra, 101).status_code == 200
    p = transacoes['102']
    if erro == 'pref': ordem['preference_id'] = 'outra'
    elif erro == 'reference': ordem['external_reference'] = 'outra'
    elif erro == 'order_id': ordem['id'] = 'outra'
    elif erro == 'payments': ordem['payments'] = []
    elif erro == 'id': p['id'] = '999'
    elif erro == 'user': p['external_reference'] = p['external_reference'].replace('user:1', 'user:2')
    elif erro == 'course': p['external_reference'] = p['external_reference'].replace('curso:1', 'curso:2')
    elif erro == 'amount': p['transaction_amount'] = 0.01
    elif erro == 'currency': p['currency_id'] = 'USD'
    else: p.pop('order')
    assert confirmar(ambiente_compra, 102).status_code in (403, 409)
    with ambiente_compra[2]() as db:
        assert db.query(m.Pagamento).count() == 1
        assert db.get(m.Pagamento, pid).mp_payment_id == '101'


def test_falha_contratacao_rollback_integral(ambiente_compra):
    _, dados, transacoes, _ = preparar(ambiente_compra)
    assert confirmar(ambiente_compra, 101).status_code == 200
    transacoes['102'] = dados(102, 'approved')
    main, _, f, _, _ = ambiente_compra
    with patch.object(main, 'registrar_contratacao', side_effect=RuntimeError('Falha simulada')):
        with pytest.raises(RuntimeError): confirmar(ambiente_compra, 102)
    with f() as db:
        assert db.query(m.Pagamento).count() == 1
        assert db.query(m.PeriodoAcessoPagamento).count() == 0
        assert db.query(m.OportunidadeCompra).one().concluida_em is None


def test_admin_descobre_nova_transacao(ambiente_compra):
    _, dados, transacoes, _ = preparar(ambiente_compra)
    assert confirmar(ambiente_compra, 101).status_code == 200
    transacoes['102'] = dados(102, 'approved')
    main, _, f, _, _ = ambiente_compra
    with f() as db:
        r = main.admin_revalidar_pagamento({'mp_payment_id': '102'}, db, SimpleNamespace(is_admin=True))
        assert r['liberou_acesso']
    assert confirmar(ambiente_compra, 102).json()['liberou_acesso'] is False


def test_historico_sem_oportunidade_nao_inferido(ambiente_compra):
    pid, _, _, _ = preparar(ambiente_compra, legado=True)
    assert confirmar(ambiente_compra, 101).status_code == 200
    with ambiente_compra[2]() as db:
        db.get(m.Pagamento, pid).oportunidade_id = None
        db.commit()
    assert confirmar(ambiente_compra, 102).status_code == 409
    assert confirmar(ambiente_compra, 101).status_code == 200


def test_raiz_recusada_com_tentativa_pendente_reabre_mesma_preferencia(ambiente_compra):
    pid, dados, tx, _ = preparar(ambiente_compra)
    tx['101'] = dados(101, 'rejected')
    assert confirmar(ambiente_compra, 101).status_code == 200
    assert confirmar(ambiente_compra, 102).status_code == 200
    _, c, f, post, _ = ambiente_compra
    with f() as db: did = db.query(m.DemonstracaoCurso).one().id
    r = c.post('/checkout/mercadopago', json={'tempo_acesso_id': 1, 'demonstracao_id': did})
    assert r.status_code == 200 and r.json()['pagamento_id'] == pid
    post.assert_called_once()


def test_tentativas_nao_consumem_limite_de_titulos(ambiente_compra):
    pid, dados, tx, _ = preparar(ambiente_compra)
    for t in (101, 102, 103):
        tx[str(t)] = dados(t, 'rejected')
        assert confirmar(ambiente_compra, t).status_code == 200
    main, c, f, post, get = ambiente_compra
    with f() as db:
        origem = db.get(m.Pagamento, pid)
        did = db.query(m.DemonstracaoCurso).one().id
        for i in range(5):
            db.add(m.Pagamento(usuario_id=1, curso_id=1, tempo_acesso_id=1,
                oportunidade_id=origem.oportunidade_id, valor_cents=4990, status='REJECTED',
                mp_preference_id=f'titulo-{i}', tipo_compra='NOVA'))
        db.commit()
    r = c.post('/checkout/mercadopago', json={'tempo_acesso_id': 2, 'demonstracao_id': did})
    assert r.status_code == 200, r.text  # 6 preferências, 2 tentativas: ainda não atingiu oito.
    assert post.call_count == 2


def test_webhook_historico_sem_referencia_da_raiz(ambiente_compra):
    pid, _, tx, _ = preparar(ambiente_compra, legado=True)
    assert confirmar(ambiente_compra, 101).status_code == 200
    with ambiente_compra[2]() as db:
        db.get(m.Pagamento, pid).oportunidade_id = None
        db.commit()
    tx['101']['external_reference'] = 'user:1|curso:1|tempo:1'
    main, _, f, _, _ = ambiente_compra
    with patch.object(main, 'validar_assinatura_mercadopago', return_value=True):
        with f() as db:
            assert asyncio.run(webhook(main, db, 101))['status'] == 'PENDING'


def test_indisponibilidade_da_ordem_nao_cria_tentativa(ambiente_compra):
    pid, _, _, _ = preparar(ambiente_compra, legado=True)
    assert confirmar(ambiente_compra, 101).status_code == 200
    get = ambiente_compra[4]
    api = get.side_effect
    def falha(url, **kwargs):
        if '/merchant_orders/' in url: return Mock(status_code=503)
        return api(url, **kwargs)
    get.side_effect = falha
    assert confirmar(ambiente_compra, 102).status_code == 502
    with ambiente_compra[2]() as db: assert db.query(m.Pagamento).count() == 1


@pytest.mark.parametrize('status', ['REFUND_REQUESTED', 'REFUND_IN_PROCESS', 'REFUNDED'])
def test_nova_confirmacao_nao_sobrescreve_reembolso(ambiente_compra, status):
    pid, dados, tx, _ = preparar(ambiente_compra)
    tx['101'] = dados(101, 'approved')
    assert confirmar(ambiente_compra, 101).status_code == 200
    with ambiente_compra[2]() as db:
        db.get(m.Pagamento, pid).status = status
        db.commit()
    retorno = confirmar(ambiente_compra, 101)
    assert retorno.status_code == 200 and retorno.json()['status'] == status
    assert retorno.json()['mp_status'] == 'APPROVED' and not retorno.json()['liberou_acesso']
    main, _, f, _, _ = ambiente_compra
    with patch.object(main, 'validar_assinatura_mercadopago', return_value=True):
        with f() as db:
            retorno = asyncio.run(webhook(main, db, 101))
            assert retorno['status'] == status and not retorno['liberou_acesso']
    with f() as db:
        assert db.get(m.Pagamento, pid).status == status
        assert db.query(m.PeriodoAcessoPagamento).count() == 1
