"""Fluxo manual com SQLite isolado; provedor sempre simulado."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from app import models as m
from test_compras_fluxo import ambiente_compra, motor
from test_transacoes_mp import preparar, confirmar


def duplicata(ambiente, vencedor=101):
    main, client, factory, _, _ = ambiente
    if motor_do(factory).dialect.name == 'sqlite':
        with motor_do(factory).connect() as c:
            c.connection.driver_connection.create_function('BTRIM', 1, lambda v: None if v is None else v.strip())
    m.Base.metadata.create_all(motor_do(factory), tables=[m.ReembolsoFinanceiro.__table__, m.ContestacaoPagamento.__table__])
    _, dados, transacoes, _ = preparar(ambiente)
    for tx in (vencedor, 203-vencedor):
        transacoes[str(tx)] = dados(tx, 'approved')
        assert confirmar(ambiente, tx).status_code == 200
    with factory() as db:
        p = db.query(m.Pagamento).filter_by(mp_payment_id=str(203-vencedor)).one()
        assert p.ocorrencia_financeira == 'COBRANCA_DUPLICADA'
        return p.id


def motor_do(factory):
    return factory.kw['bind']


def admin(ambiente):
    ambiente[0].app.dependency_overrides[ambiente[0].get_usuario_atual] = lambda: SimpleNamespace(id=2, is_admin=True)


def registrar(client, pid):
    return client.post(f'/admin/reembolsos/{pid}/pix-manual', json={'valor_cents':4990, 'referencia_comprovante':'extrato-teste'})


@pytest.mark.parametrize('vencedor', [101, 102])
def test_solicitacao_necessaria_e_confirmacao_preserva_acesso(ambiente_compra, vencedor):
    main, client, factory, post, get = ambiente_compra
    pid = duplicata(ambiente_compra, vencedor)
    # Duplicidade, isoladamente, não abre solicitação nem autoriza devolução.
    admin(ambiente_compra)
    assert registrar(client, pid).status_code == 400
    assert client.post(f'/admin/reembolsos/{pid}/aprovar', json={}).status_code == 400
    main.app.dependency_overrides[main.get_usuario_atual] = lambda: SimpleNamespace(id=1, is_admin=False)
    elegiveis = client.get('/me/compras/reembolso').json()['compras']
    assert pid in {p['pagamento_id'] for p in elegiveis}
    assert client.post(f'/me/reembolso/{pid}', json={}).status_code == 200
    assert registrar(client, pid).status_code == 403
    admin(ambiente_compra)
    assert client.post(f'/admin/reembolsos/{pid}/aprovar', json={}).status_code == 200
    with factory() as db:
        acesso = db.query(m.AcessoCurso).one()
        snapshot = (acesso.id, acesso.ativo, acesso.data_fim)
        contratos = [(c.id,c.data_inicio,c.data_fim) for c in db.query(m.ContratacaoCurso).all()]
    r = registrar(client, pid)
    assert r.status_code == 200, r.text
    rid = r.json()['reembolso_id']
    assert registrar(client, pid).status_code == 409
    linha = next(p for p in client.get('/admin/reembolsos').json() if p['pagamento_id']==pid)
    assert linha['reembolso_id']==rid and linha['reembolso_status']=='PENDENTE'
    assert client.post(f'/admin/reembolsos/{rid}/pix-manual/confirmar?confirmacao_extrato=false', json={}).status_code == 400
    main.app.dependency_overrides[main.get_usuario_atual] = lambda: SimpleNamespace(id=1, is_admin=False)
    assert client.post(f'/admin/reembolsos/{rid}/pix-manual/confirmar?confirmacao_extrato=true', json={}).status_code == 403
    admin(ambiente_compra)
    chamadas = (post.call_count, get.call_count)
    with patch.object(main, 'recalcular_acesso_apos_reembolso', side_effect=AssertionError('Duplicata não recalcula direitos')):
        r = client.post(f'/admin/reembolsos/{rid}/pix-manual/confirmar?confirmacao_extrato=true', json={'confirmado_por':1})
    assert r.status_code==200, r.text
    assert client.post(f'/admin/reembolsos/{rid}/pix-manual/confirmar?confirmacao_extrato=true', json={}).status_code == 400
    with factory() as db:
        acesso=db.query(m.AcessoCurso).one()
        assert (acesso.id,acesso.ativo,acesso.data_fim)==snapshot
        assert [(c.id,c.data_inicio,c.data_fim) for c in db.query(m.ContratacaoCurso).all()]==contratos
        assert db.query(m.PeriodoAcessoPagamento).count()==1
        p=db.get(m.Pagamento,pid)
        assert p.ocorrencia_financeira=='COBRANCA_DUPLICADA' and p.status=='REFUNDED'
        assert p.mp_payment_id==str(203-vencedor)
        rf=db.get(m.ReembolsoFinanceiro,rid)
        assert rf.confirmado_por==2 and rf.confirmado_em and rf.status=='CONFIRMADO'
    assert chamadas==(post.call_count,get.call_count)  # Nenhuma API financeira.


def test_prazo_e_propriedade_preservados(ambiente_compra):
    main,client,factory,_,_=ambiente_compra
    pid=duplicata(ambiente_compra)
    main.app.dependency_overrides[main.get_usuario_atual]=lambda:SimpleNamespace(id=3,is_admin=False)
    assert client.post(f'/me/reembolso/{pid}',json={}).status_code==404
    main.app.dependency_overrides[main.get_usuario_atual]=lambda:SimpleNamespace(id=1,is_admin=False)
    with factory() as db:
        db.get(m.Pagamento,pid).aprovado_em=datetime.utcnow()-timedelta(days=8);db.commit()
    assert client.post(f'/me/reembolso/{pid}',json={}).status_code==400


def test_inconsistencia_periodo_impede_confirmacao(ambiente_compra):
    main,client,factory,_,_=ambiente_compra
    pid=duplicata(ambiente_compra)
    assert client.post(f'/me/reembolso/{pid}',json={}).status_code==200
    admin(ambiente_compra)
    assert client.post(f'/admin/reembolsos/{pid}/aprovar',json={}).status_code==200
    rid=registrar(client,pid).json()['reembolso_id']
    with factory() as db:
        periodo=db.query(m.PeriodoAcessoPagamento).one()
        db.add(m.PeriodoAcessoPagamento(pagamento_id=pid, usuario_id=1,curso_id=1,contratacao_id=periodo.contratacao_id,
            data_inicio=periodo.data_inicio,data_fim=periodo.data_fim));db.commit()
    r=client.post(f'/admin/reembolsos/{rid}/pix-manual/confirmar?confirmacao_extrato=true',json={})
    assert r.status_code==409,r.text
    with factory() as db:
        assert db.get(m.ReembolsoFinanceiro,rid).status=='PENDENTE'
        assert db.get(m.Pagamento,pid).status=='REFUND_IN_PROCESS'


@pytest.mark.parametrize('canal',['retorno','webhook','admin'])
@pytest.mark.parametrize('estado',['approved','refunded','charged_back'])
def test_reconciliacao_preserva_confirmacao_manual(ambiente_compra, canal, estado):
    import asyncio
    from test_transacoes_mp import webhook
    main,client,factory,_,_=ambiente_compra
    pid=duplicata(ambiente_compra)
    assert client.post(f'/me/reembolso/{pid}',json={}).status_code==200
    admin(ambiente_compra)
    assert client.post(f'/admin/reembolsos/{pid}/aprovar',json={}).status_code==200
    rid=registrar(client,pid).json()['reembolso_id']
    assert client.post(f'/admin/reembolsos/{rid}/pix-manual/confirmar?confirmacao_extrato=true',json={}).status_code==200
    # A resposta confiável do provedor é simulada independentemente da devolução externa.
    with factory() as db:
        pagamento=db.get(m.Pagamento,pid)
        raiz=db.get(m.Pagamento,pagamento.pagamento_origem_id)
        resposta={'id':pagamento.mp_payment_id,'status':estado,'payment_method_id':'pix',
            'transaction_amount':49.90,'currency_id':'BRL',
            'external_reference':f'user:1|curso:1|tempo:1|pagamento:{raiz.id}'}
        rf=db.get(m.ReembolsoFinanceiro,rid);confirmado=rf.confirmado_em
        acesso=db.query(m.AcessoCurso).one();snapshot=(acesso.ativo,acesso.data_fim)
        with patch.object(main,'consultar_pagamento') as api,patch.object(main,'validar_assinatura_mercadopago',return_value=True):
            api.return_value.status_code=200;api.return_value.json.return_value=resposta
            if canal=='admin':r=main.admin_revalidar_pagamento({'mp_payment_id':'102'},db,SimpleNamespace(id=2,is_admin=True))
            elif canal=='webhook':r=asyncio.run(webhook(main,db,102))
            else:r=main.confirmar_pagamento({'payment_id':'102','curso_id':1},db,SimpleNamespace(id=1))
        assert r['status']=='REFUNDED' and r['mp_status']==estado.upper()
        assert not r['liberou_acesso']
    with factory() as db:
        assert db.get(m.Pagamento,pid).ocorrencia_financeira=='COBRANCA_DUPLICADA'
        rf=db.get(m.ReembolsoFinanceiro,rid)
        assert rf.status=='CONFIRMADO' and rf.confirmado_em==confirmado and rf.confirmado_por==2
        a=db.query(m.AcessoCurso).one();assert (a.ativo,a.data_fim)==snapshot


@pytest.mark.parametrize('estado',['refunded','charged_back'])
def test_estado_provedor_nao_confirma_pix_manual(ambiente_compra,estado):
    main,client,factory,_,_=ambiente_compra
    pid=duplicata(ambiente_compra)
    assert client.post(f'/me/reembolso/{pid}',json={}).status_code==200
    admin(ambiente_compra)
    client.post(f'/admin/reembolsos/{pid}/aprovar',json={})
    rid=registrar(client,pid).json()['reembolso_id']
    with factory() as db:
        p=db.get(m.Pagamento,pid);raiz=p.pagamento_origem_id
        dados={'id':'102','status':estado,'transaction_amount':49.90,'currency_id':'BRL',
            'external_reference':f'user:1|curso:1|tempo:1|pagamento:{raiz}'}
        with patch.object(main,'consultar_pagamento') as api:
            api.return_value.status_code=200;api.return_value.json.return_value=dados
            main.admin_revalidar_pagamento({'mp_payment_id':'102'},db,SimpleNamespace(id=2,is_admin=True))
    with factory() as db:
        assert db.get(m.ReembolsoFinanceiro,rid).status=='PENDENTE'
        assert db.get(m.ReembolsoFinanceiro,rid).confirmado_por is None
        assert db.get(m.Pagamento,pid).status=='REFUND_IN_PROCESS'
        assert db.get(m.Pagamento,pid).mp_status==estado.upper()


@pytest.mark.parametrize('canal',['retorno','webhook','admin'])
@pytest.mark.parametrize('estado',['refunded','charged_back'])
def test_ocorrencia_reconcilia_sem_inventar_devolucao_manual(ambiente_compra,canal,estado):
    import asyncio
    from test_transacoes_mp import webhook
    main,client,factory,_,_=ambiente_compra;pid=duplicata(ambiente_compra)
    with factory() as db:
        p=db.get(m.Pagamento,pid);raiz=p.pagamento_origem_id
        acesso=db.query(m.AcessoCurso).one();snapshot=(acesso.ativo,acesso.data_fim)
        dados={'id':'102','status':estado,'transaction_amount':49.90,'currency_id':'BRL',
            'external_reference':f'user:1|curso:1|tempo:1|pagamento:{raiz}'}
        with patch.object(main,'consultar_pagamento') as api,patch.object(main,'validar_assinatura_mercadopago',return_value=True):
            api.return_value.status_code=200;api.return_value.json.return_value=dados
            if canal=='admin':r=main.admin_revalidar_pagamento({'mp_payment_id':'102'},db,SimpleNamespace(id=2,is_admin=True))
            elif canal=='webhook':r=asyncio.run(webhook(main,db,102))
            else:r=main.confirmar_pagamento({'payment_id':'102','curso_id':1},db,SimpleNamespace(id=1))
        assert r['mp_status']==estado.upper() and r['status']==estado.upper() and not r['liberou_acesso']
    with factory() as db:
        assert db.query(m.ReembolsoFinanceiro).count()==0
        assert db.get(m.Pagamento,pid).ocorrencia_financeira=='COBRANCA_DUPLICADA'
        a=db.query(m.AcessoCurso).one();assert (a.ativo,a.data_fim)==snapshot
        assert db.query(m.PeriodoAcessoPagamento).count()==1


def test_ausencia_periodo_vencedor_impede_confirmacao(ambiente_compra):
    _,client,factory,_,_=ambiente_compra;pid=duplicata(ambiente_compra)
    assert client.post(f'/me/reembolso/{pid}',json={}).status_code==200
    admin(ambiente_compra);client.post(f'/admin/reembolsos/{pid}/aprovar',json={})
    rid=registrar(client,pid).json()['reembolso_id']
    with factory() as db:
        db.delete(db.query(m.PeriodoAcessoPagamento).one());db.commit()
    assert client.post(f'/admin/reembolsos/{rid}/pix-manual/confirmar?confirmacao_extrato=true',json={}).status_code==409
    with factory() as db:
        assert db.get(m.ReembolsoFinanceiro,rid).status=='PENDENTE'
        assert db.get(m.Pagamento,pid).status=='REFUND_IN_PROCESS'
