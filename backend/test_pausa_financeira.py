"""Pausa e recuperação isoladas. Provedor simulado, sem dotenv/DB de produção."""
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import select, update, text
from sqlalchemy.exc import OperationalError
from app import models as m
from app.pausa_financeira import controle, inbox, Modo, Reconciliar, Protecao, financeiro
from test_compras_fluxo import ambiente_compra, motor
from test_transacoes_mp import preparar


def admin(ambiente):
    main=ambiente[0]
    main.app.dependency_overrides[main.get_usuario_atual]=lambda:SimpleNamespace(id=2,is_admin=True, tipo_admin="admin_geral")


def modo(ambiente, estado):
    admin(ambiente)
    c=ambiente[1]
    geracao=c.get('/admin/financeiro/manutencao').json()['geracao']
    return c.post('/admin/financeiro/manutencao',json={'modo':estado,'geracao':geracao,
        'motivo':'teste isolado','conferencia_provedor':True})


def enviar(ambiente, tx=101, evento='evento-1', valido=True):
    main,client=ambiente[:2]
    main.MP_WEBHOOK_SECRET='segredo-exclusivo-do-teste'
    req='requisicao-teste';ts='1234567890'
    manifest=f'id:{tx};request-id:{req};ts:{ts};'
    mac=hmac.new(main.MP_WEBHOOK_SECRET.encode(),manifest.encode(),hashlib.sha256).hexdigest()
    return client.post(f'/webhooks/mercadopago?type=payment&data.id={tx}',
        headers={'x-request-id':req,'x-signature':f'ts={ts},v1={mac if valido else "invalido"}'},
        json={'id':evento,'type':'payment','data':{'id':str(tx)}})


def test_ativar_desativar_e_auditoria(ambiente_compra):
    a=ambiente_compra
    assert modo(a,'PAUSADO').status_code==200
    estado=a[1].get('/admin/financeiro/manutencao').json()
    assert estado['modo']=='PAUSADO' and estado['geracao']==1 and estado['alterado_por']==2
    r=a[1].post('/admin/financeiro/manutencao',json={'modo':'NORMAL','geracao':0,'motivo':'obsoleto'})
    assert r.status_code==409
    r=a[1].post('/admin/financeiro/manutencao',json={'modo':'NORMAL','geracao':1,'motivo':'sem conferencia'})
    assert r.status_code==409
    assert modo(a,'NORMAL').status_code==200


@pytest.mark.parametrize('rota',[
    '/checkout/mercadopago','/pagamentos/confirmar','/admin/pagamentos/revalidar',
    '/me/reembolso/1','/admin/reembolsos/1/aprovar','/admin/reembolsos/1/recusar',
    '/admin/reembolsos/1/pix-manual','/admin/reembolsos/1/pix-manual/confirmar',
    '/admin/acessos','/cursos/1/demonstracao'])
def test_bloqueia_rotas_sem_efeitos(ambiente_compra,rota):
    a=ambiente_compra
    assert modo(a,'PAUSADO').status_code==200
    r=a[1].post(rota,json={})
    assert r.status_code==503 and r.headers['retry-after']=='60'
    assert 'não foi rejeitado ou cancelado' in r.json()['detail']
    a[3].assert_not_called();a[4].assert_not_called()
    with a[2]() as db:assert db.query(m.Pagamento).count()==0


def test_cors_e_leituras_nao_bloqueadas(ambiente_compra):
    a=ambiente_compra;modo(a,'PAUSADO')
    r=a[1].post('/pagamentos/confirmar',json={},headers={'Origin':'https://resumaoonline.com.br'})
    assert r.status_code==503 and r.headers['access-control-allow-origin']=='https://resumaoonline.com.br'
    assert a[1].get('/admin/reembolsos').status_code==200
    assert not financeiro('GET','/admin/reembolsos')
    assert not financeiro('POST','/login')


@pytest.mark.parametrize('rota',['/admin/financeiro/manutencao','/admin/financeiro/notificacoes'])
def test_exige_administrador(ambiente_compra,rota):
    assert ambiente_compra[1].get(rota).status_code==403


def test_exige_autenticacao_e_admin_nas_operacoes(ambiente_compra):
    a=ambiente_compra
    for rota,body in [('/admin/financeiro/manutencao',{'modo':'PAUSADO','geracao':0,'motivo':'teste'}),
                      ('/admin/financeiro/notificacoes/recuperar',{})]:
        assert a[1].post(rota,json=body).status_code==403
    a[0].app.dependency_overrides.pop(a[0].get_usuario_atual)
    assert a[1].get('/admin/financeiro/manutencao').status_code==401


def test_falta_controle_falha_fechada(ambiente_compra):
    a=ambiente_compra
    with a[2].kw['bind'].begin() as c:c.execute(controle.delete())
    assert a[1].post('/checkout/mercadopago',json={'tempo_acesso_id':1}).status_code==503
    a[3].assert_not_called()


def test_webhook_pausa_duravel_autenticado_duplicado(ambiente_compra):
    a=ambiente_compra;preparar(a);modo(a,'PAUSADO')
    assert enviar(a,valido=False).status_code==401
    a[4].reset_mock()
    for _ in range(2):assert enviar(a).json()['armazenado'] is True
    a[4].assert_not_called()
    with a[2].kw['bind'].connect() as c:
        rows=c.execute(select(inbox)).mappings().all()
        assert len(rows)==1 and rows[0]['estado']=='PENDENTE' and rows[0]['tentativas']==0
        assert 'segredo' not in str(rows) and 'x-signature' not in str(rows)
    with a[2]() as db:assert db.query(m.ContratacaoCurso).count()==0


def test_persistencia_falha_nao_ack(ambiente_compra):
    a=ambiente_compra
    with patch.object(a[0].app.state.protecao_financeira,'armazenar',
        side_effect=OperationalError('fixture',{},Exception('simulado'))):
        assert enviar(a).status_code==503


def test_aprovacoes_recuperadas_acesso_unico(ambiente_compra):
    a=ambiente_compra;_,dados,transacoes,_=preparar(a)
    modo(a,'PAUSADO')
    for tx in (101,102):
        transacoes[str(tx)]=dados(tx,'approved')
        assert enviar(a,tx,f'evento-{tx}').status_code==200
    with a[2]() as db:assert db.query(m.ContratacaoCurso).count()==0
    assert modo(a,'NORMAL').status_code==409
    assert modo(a,'RECUPERACAO').status_code==200
    assert a[1].post('/pagamentos/confirmar',json={'payment_id':'101'}).status_code==503
    r=a[1].post('/admin/financeiro/notificacoes/recuperar',json={'limite':5})
    assert r.status_code==200 and all(x['processado'] for x in r.json()['resultados'])
    assert a[1].post('/admin/financeiro/notificacoes/recuperar',json={}).json()['resultados']==[]
    with a[2]() as db:
        assert db.query(m.Pagamento).count()==2
        assert db.query(m.ContratacaoCurso).count()==1
        assert db.query(m.PeriodoAcessoPagamento).count()==1
        assert db.query(m.Pagamento).filter_by(ocorrencia_financeira='COBRANCA_DUPLICADA').count()==1
    assert modo(a,'NORMAL').status_code==200
    assert enviar(a,101,'evento-101').status_code==200
    with a[2]() as db:assert db.query(m.PeriodoAcessoPagamento).count()==1


def test_falha_processamento_e_retry(ambiente_compra):
    a=ambiente_compra;preparar(a)
    p=a[0].app.state.protecao_financeira
    original=p.processor
    with patch.object(p,'processor',side_effect=RuntimeError('erro pessoal não persistir')):
        assert enviar(a).status_code==200
    with a[2].kw['bind'].connect() as c:
        row=c.execute(select(inbox)).mappings().one()
        assert row['estado']=='ERRO' and row['tentativas']==1
        assert 'pessoal' not in row['erro']
    modo(a,'RECUPERACAO')
    r=a[1].post('/admin/financeiro/notificacoes/recuperar',json={})
    assert r.json()['resultados'][0]['processado']
    with a[2].kw['bind'].connect() as c:
        row=c.execute(select(inbox)).mappings().one()
        assert row['estado']=='CONCLUIDO' and row['tentativas']==2


def test_preserva_solicitacao_reembolso(ambiente_compra):
    a=ambiente_compra;pid,dados,transacoes,_=preparar(a)
    transacoes['101']=dados(101,'approved')
    assert a[1].post('/pagamentos/confirmar',json={'payment_id':'101','curso_id':1}).status_code==200
    assert a[1].post(f'/me/reembolso/{pid}',json={}).status_code==200
    modo(a,'PAUSADO');enviar(a,101,'estado-posterior');modo(a,'RECUPERACAO')
    assert a[1].post('/admin/financeiro/notificacoes/recuperar',json={}).status_code==200
    with a[2]() as db:
        assert db.get(m.Pagamento,pid).status=='REFUND_REQUESTED'
        assert db.query(m.ReembolsoFinanceiro).count()==0
        assert db.query(m.PeriodoAcessoPagamento).count()==1


def test_reconciliacao_descobre_transacao_sem_linha_local(ambiente_compra):
    a=ambiente_compra;_,dados,transacoes,_=preparar(a)
    for tx in (101,102):transacoes[str(tx)]=dados(tx,'approved')
    modo(a,'PAUSADO');modo(a,'RECUPERACAO')
    original=a[4].side_effect
    def api(url,**kwargs):
        if url.endswith('/payments/search'):
            assert kwargs['params']['range']=='date_last_updated'
            assert 'status' not in kwargs['params']
            r=Mock(status_code=200)
            r.json.return_value={'results':[{'id':101},{'id':102}],
                'paging':{'total':2,'offset':0,'limit':50}}
            return r
        return original(url,**kwargs)
    a[4].side_effect=api
    payload={'inicio':(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat(),
        'fim':datetime.now(timezone.utc).isoformat(),'pagina':0}
    r=a[1].post('/admin/financeiro/notificacoes/reconciliar',json=payload)
    assert r.status_code==200 and r.json()['armazenadas']==2
    assert r.json()['conferencia_provedor_obrigatoria']
    assert a[1].post('/admin/financeiro/notificacoes/reconciliar',json=payload).status_code==200
    assert a[1].post('/admin/financeiro/notificacoes/recuperar',json={'limite':5}).status_code==200
    with a[2]() as db:
        assert {p.mp_payment_id for p in db.query(m.Pagamento)}=={'101','102'}
        assert db.query(m.ContratacaoCurso).count()==1
    with a[2].kw['bind'].connect() as c:assert len(c.execute(select(inbox)).all())==2


def test_bootstrap_nao_recupera_com_logica_antiga(ambiente_compra):
    a=ambiente_compra;p=a[0].app.state.protecao_financeira
    p.definitivo=False
    assert modo(a,'PAUSADO').status_code==200
    assert modo(a,'RECUPERACAO').status_code==409


def test_reconciliacao_paginada(ambiente_compra):
    a=ambiente_compra;modo(a,'RECUPERACAO')
    def api(url,**kwargs):
        offset=kwargs['params']['offset']
        resposta=Mock(status_code=200)
        resposta.json.return_value={'results':[{'id':1000+i} for i in range(offset,min(offset+50,51))],
            'paging':{'total':51,'offset':offset,'limit':50}}
        return resposta
    a[4].side_effect=api
    body={'inicio':(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat(),
        'fim':datetime.now(timezone.utc).isoformat()}
    assert a[1].post('/admin/financeiro/notificacoes/reconciliar',json=body).json()['proxima_pagina']==1
    body['pagina']=1
    assert a[1].post('/admin/financeiro/notificacoes/reconciliar',json=body).json()['proxima_pagina'] is None
    with a[2].kw['bind'].connect() as c:assert len(c.execute(select(inbox)).all())==51


@pytest.mark.parametrize('variacao',['sem_fuso','fim_anterior','janela_longa','resposta_invalida','offset_errado','limite_excedido'])
def test_reconciliacao_interrompe_incompatibilidades(ambiente_compra,variacao):
    a=ambiente_compra;modo(a,'RECUPERACAO')
    inicio=datetime.now(timezone.utc)-timedelta(hours=1);fim=datetime.now(timezone.utc)
    if variacao=='sem_fuso':inicio=inicio.replace(tzinfo=None)
    if variacao=='fim_anterior':fim=inicio-timedelta(hours=1)
    if variacao=='janela_longa':inicio=fim-timedelta(days=8)
    result=Mock(status_code=200)
    result.json.return_value={'results':[{'id':'101'}], 'paging':{'offset':0,'limit':50,'total':1}}
    if variacao=='resposta_invalida':result.json.return_value={}
    if variacao=='offset_errado':result.json.return_value['paging']['offset']=1
    if variacao=='limite_excedido':result.json.return_value['paging']['total']=20000
    a[4].side_effect=None;a[4].return_value=result
    r=a[1].post('/admin/financeiro/notificacoes/reconciliar',json={'inicio':inicio.isoformat(),'fim':fim.isoformat()})
    assert r.status_code in (400,409,502)
    with a[2].kw['bind'].connect() as c:assert c.execute(select(inbox)).first() is None


def preparar_selecao(a):
    pid, dados, transacoes, _ = preparar(a, legado=True)
    transacoes['101'] = dados(101, 'cancelled')
    with a[2]() as db:
        p = db.get(m.Pagamento, pid)
        p.mp_payment_id = '101'
        p.status = 'CANCELLED'
        db.commit()
    modo(a, 'PAUSADO')
    for ident, tx in ((1, '999'), (5, '101'), (6, '101')):
        with a[2].kw['bind'].begin() as c:
            c.execute(inbox.insert().values(id=ident, chave=f'selecao:{ident}',
                payment_id=tx, fonte='RECONCILIACAO', recebida_em=datetime.now(timezone.utc),
                estado='ERRO' if ident == 1 else 'PENDENTE',
                tentativas=2 if ident == 1 else 0))
    modo(a, 'RECUPERACAO')
    return pid


def test_selecao_cancelado_preserva_direitos_e_demais_notificacoes(ambiente_compra):
    a = ambiente_compra
    with a[2]() as db:
        from test_compras_fluxo import contrato
        contrato(db, origem='ADMIN')
    pid = preparar_selecao(a)
    with a[2]() as db:
        antes = [(c.id, c.data_inicio, c.data_fim) for c in db.query(m.ContratacaoCurso)]
        demos = [(d.id, d.data_fim) for d in db.query(m.DemonstracaoCurso)]
    a[4].reset_mock()
    for ident in (5, 6):
        r = a[1].post('/admin/financeiro/notificacoes/recuperar',
            json={'notificacao_id': ident, 'limite': 5})
        assert r.status_code == 200
        assert r.json()['resultados'] == [{'id': ident, 'processado': True, 'status': 'CANCELLED'}]
        if ident == 5:
            with a[2].kw['bind'].connect() as c:
                rows = {row['id']: row for row in c.execute(select(inbox)).mappings()}
                assert rows[1]['estado'] == 'ERRO' and rows[1]['tentativas'] == 2
                assert rows[6]['estado'] == 'PENDENTE' and rows[6]['tentativas'] == 0
    assert all('/v1/payments/101' in call.args[0] for call in a[4].call_args_list)
    with a[2]() as db:
        assert db.query(m.Pagamento).count() == 1
        assert db.get(m.Pagamento, pid).aprovado_em is None
        assert [(c.id, c.data_inicio, c.data_fim) for c in db.query(m.ContratacaoCurso)] == antes
        assert [(d.id, d.data_fim) for d in db.query(m.DemonstracaoCurso)] == demos
        assert db.query(m.PeriodoAcessoPagamento).count() == 0
        assert db.query(m.AcessoCurso).count() == 0
    with a[2].kw['bind'].connect() as c:
        rows = {r['id']: r for r in c.execute(select(inbox)).mappings()}
        assert rows[1]['estado'] == 'ERRO' and rows[1]['tentativas'] == 2
        assert all(rows[i]['estado'] == 'CONCLUIDO' and rows[i]['tentativas'] == 1 for i in (5, 6))
    a[4].reset_mock()
    for ident in (5, 987):
        assert a[1].post('/admin/financeiro/notificacoes/recuperar',
            json={'notificacao_id': ident}).json()['resultados'] == []
    a[4].assert_not_called()


def test_selecao_falha_rollback_sem_avancar_fila(ambiente_compra):
    a = ambiente_compra
    pid = preparar_selecao(a)
    p = a[0].app.state.protecao_financeira
    def falha(tx, db, **kwargs):
        db.get(m.Pagamento, pid).status = 'APPROVED'
        db.commit()  # Deve ser somente flush dentro da unidade de recuperação.
        raise RuntimeError('falha simulada')
    with patch.object(p, 'processor', side_effect=falha):
        r = a[1].post('/admin/financeiro/notificacoes/recuperar', json={'notificacao_id': 5})
    assert r.status_code == 200 and not r.json()['resultados'][0]['processado']
    with a[2]() as db:
        assert db.get(m.Pagamento, pid).status == 'CANCELLED'
        assert db.query(m.ContratacaoCurso).count() == 0
    with a[2].kw['bind'].connect() as c:
        rows = {r['id']: r for r in c.execute(select(inbox)).mappings()}
        assert rows[5]['estado'] == 'ERRO' and rows[5]['tentativas'] == 1
        assert rows[6]['estado'] == 'PENDENTE' and rows[6]['tentativas'] == 0
        assert rows[1]['tentativas'] == 2
    assert a[1].post('/admin/financeiro/notificacoes/recuperar',
        json={'notificacao_id': 5}).json()['resultados'][0]['processado']


@pytest.mark.parametrize('ident', [0, -1, True, '5', 1.5])
def test_selecao_id_invalido(ambiente_compra, ident):
    a = ambiente_compra
    admin(a)
    assert a[1].post('/admin/financeiro/notificacoes/recuperar',
        json={'notificacao_id': ident}).status_code == 422
    a[4].assert_not_called()


def test_selecao_preserva_autorizacao_e_modo(ambiente_compra):
    a = ambiente_compra
    preparar_selecao(a)
    a[0].app.dependency_overrides[a[0].get_usuario_atual] = lambda: SimpleNamespace(id=1, is_admin=False)
    assert a[1].post('/admin/financeiro/notificacoes/recuperar', json={'notificacao_id': 5}).status_code == 403
    a[0].app.dependency_overrides.pop(a[0].get_usuario_atual)
    assert a[1].post('/admin/financeiro/notificacoes/recuperar', json={'notificacao_id': 5}).status_code == 401
    admin(a)
    assert modo(a, 'PAUSADO').status_code == 200
    r = a[1].post('/admin/financeiro/notificacoes/recuperar', json={'notificacao_id': 5})
    assert r.status_code == 503
    with a[2]() as db: assert db.query(m.ContratacaoCurso).count() == 0
