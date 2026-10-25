"""Banco isolado e Mercado Pago simulado; nenhuma credencial real."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest
from fastapi import HTTPException
from app import models as m
from app.contestacoes import registrar_observacao
from app.direitos_acesso import contrato_vigente, curso_vigente
from test_compras_fluxo import motor, ambiente_compra


def compra(db, inicio=None, fim=None, contrato=None, renovacao=False, mp='101'):
    agora = datetime.utcnow()
    inicio = inicio or agora-timedelta(days=2)
    fim = fim or agora+timedelta(days=28)
    if contrato is None:
        contrato = m.ContratacaoCurso(usuario_id=1, curso_id=1, origem='PAGAMENTO',
            data_inicio=inicio, data_fim=fim)
        db.add(contrato); db.flush()
    else:
        contrato.data_fim = max(contrato.data_fim, fim)
    p = m.Pagamento(usuario_id=1,curso_id=1,contratacao_id=contrato.id,
        status='APPROVED',mp_status='APPROVED',valor_cents=4990,mp_payment_id=mp,
        aprovado_em=inicio,tempo_acesso_id=1,provedor='MERCADO_PAGO',moeda='BRL',
        tipo_compra='RENOVACAO' if renovacao else 'NOVA',
        vencimento_original=inicio if renovacao else None)
    db.add(p);db.flush()
    db.add(m.PeriodoAcessoPagamento(pagamento_id=p.id,contratacao_id=contrato.id,
        usuario_id=1,curso_id=1,data_inicio=inicio,data_fim=fim))
    a=db.query(m.AcessoCurso).filter_by(usuario_id=1,curso_id=1).first()
    if a:a.data_fim=max(a.data_fim,fim)
    else:db.add(m.AcessoCurso(usuario_id=1,curso_id=1,ativo=True,data_inicio=inicio,data_fim=fim))
    db.commit()
    return p.id, contrato.id


def caso(db, pagamento_id, comprovado=True):
    p=db.get(m.Pagamento,pagamento_id)
    c=registrar_observacao(db,p,{'id':str(9000+pagamento_id)} if comprovado else None)
    if comprovado:
        # Fixture explícita de consulta canônica integral já processada.
        from app.pausa_financeira import inbox, agora
        db.execute(inbox.insert().values(chave=f'c:fixture-{pagamento_id}',
            payment_id=c.mp_dispute_id,fonte='WEBHOOK',recebida_em=agora(),
            estado='CONCLUIDO',tentativas=1,resultado={'tipo':'CONTESTACAO',
            'escopo':'INTEGRAL_VERIFICADO','pagamentos_mp':[p.mp_payment_id],
            'moeda':'BRL','valor_cents':p.valor_cents}))
    db.commit();return c.id


def admin(main):
    main.app.dependency_overrides[main.get_usuario_atual]=lambda:SimpleNamespace(id=2,is_admin=True, tipo_admin="admin_geral")


def confirmar(client,ident,ref='extrato-testado'):
    return client.post(f'/admin/contestacoes/{ident}/confirmar-devolucao',
        json={'referencia_devolucao':ref,'confirmacao_devolucao':True})


def bloquear(client,ident):
    return client.post(f'/admin/contestacoes/{ident}/bloquear-acesso?confirmacao_bloqueio=true')


def test_compra_aberta_devolucao_e_bloqueio_independentes(ambiente_compra):
    main,c,f,_,_=ambiente_compra
    with f() as db:
        pid,cid=compra(db);ident=caso(db,pid)
        assert contrato_vigente(db,db.get(m.ContratacaoCurso,cid))
        db.get(m.Pagamento,pid).status='CHARGED_BACK';db.commit()
        assert curso_vigente(db,1,1)
    admin(main)
    assert bloquear(c,ident).status_code==409
    assert confirmar(c,ident).status_code==200
    with f() as db:
        assert curso_vigente(db,1,1)
        assert db.get(m.ContestacaoPagamento,ident).bloqueio_executado_em is None
    assert bloquear(c,ident).status_code==200
    with f() as db:
        assert not curso_vigente(db,1,1)
        assert not contrato_vigente(db,db.get(m.ContratacaoCurso,cid))
        assert db.get(m.AcessoCurso,1).ativo
        assert db.query(m.PeriodoAcessoPagamento).count()==1
        assert db.get(m.ContratacaoCurso,cid).data_fim is not None
        assert db.get(m.Pagamento,pid).status=='CHARGED_BACK'
        # Contexto de estudo não pode autorizar pelo intervalo agregado.
        with pytest.raises(HTTPException) as e:main.validar_contexto_estudo(db,SimpleNamespace(id=1),1,cid)
        assert e.value.status_code==403
    # Repetição e confirmação conflitante não reescrevem auditoria.
    with f() as db: anterior=db.get(m.ContestacaoPagamento,ident).bloqueio_executado_em
    assert bloquear(c,ident).status_code==200
    assert confirmar(c,ident,'outra-referencia').status_code==409
    with f() as db:assert db.get(m.ContestacaoPagamento,ident).bloqueio_executado_em==anterior


@pytest.mark.parametrize('direito',['outra_compra','renovacao_atual','renovacao_futura','admin','concessao','demo'])
def test_direitos_independentes(ambiente_compra,direito):
    main,c,f,_,_=ambiente_compra;agora=datetime.utcnow()
    with f() as db:
        if direito=='renovacao_atual':
            pid,cid=compra(db,inicio=agora-timedelta(days=40),fim=agora-timedelta(days=10))
            compra(db,contrato=db.get(m.ContratacaoCurso,cid),inicio=agora-timedelta(days=10),fim=agora+timedelta(days=20),renovacao=True,mp='102')
        else:
            pid,cid=compra(db)
            if direito=='outra_compra':compra(db,mp='102')
            elif direito=='renovacao_futura':
                con=db.get(m.ContratacaoCurso,cid)
                compra(db,contrato=con,inicio=con.data_fim,fim=con.data_fim+timedelta(days=30),renovacao=True,mp='102')
            elif direito=='admin':db.add(m.ContratacaoCurso(usuario_id=1,curso_id=1,origem='ADMIN',data_inicio=agora-timedelta(days=1),data_fim=None))
            elif direito=='concessao':db.add(m.ConcessaoAcessoAdmin(usuario_id=1,curso_id=1,ativo=True,data_inicio=agora-timedelta(days=1)))
            else:db.add(m.DemonstracaoCurso(usuario_id=1,curso_id=1,ativo=True,data_inicio=agora-timedelta(days=1),data_fim=agora+timedelta(days=1),liberado_novamente_em=agora))
            db.commit()
        ident=caso(db,pid)
    admin(main);assert confirmar(c,ident).status_code==200
    assert bloquear(c,ident).status_code==200
    with f() as db:
        assert curso_vigente(db,1,1)==(direito!='renovacao_futura')
        if direito=='renovacao_futura':
            assert contrato_vigente(db,db.get(m.ContratacaoCurso,cid),agora+timedelta(days=35))


@pytest.mark.parametrize('alteracao',['sem_periodo','sem_contrato','intervalo','cache_desconhecido','renovacao_sem_origem','valor_parcial'])
def test_historico_ambiguo_nao_bloqueia(ambiente_compra,alteracao):
    main,c,f,_,_=ambiente_compra
    with f() as db:
        pid,cid=compra(db);ident=caso(db,pid)
        per=db.query(m.PeriodoAcessoPagamento).filter_by(pagamento_id=pid).one()
        if alteracao=='sem_periodo':db.delete(per)
        elif alteracao=='sem_contrato':db.get(m.Pagamento,pid).contratacao_id=None
        elif alteracao=='intervalo':per.data_inicio+=timedelta(days=1)
        elif alteracao=='cache_desconhecido':db.query(m.AcessoCurso).one().data_fim=None
        elif alteracao=='valor_parcial':db.get(m.ContestacaoPagamento,ident).valor_cents=1000
        else:db.get(m.Pagamento,pid).tipo_compra='RENOVACAO'
        db.commit()
    admin(main);assert confirmar(c,ident).status_code==200
    r=bloquear(c,ident);assert r.status_code==409 and r.json()['detail']['codigo']=='CONFERENCIA_NECESSARIA'
    assert c.get('/admin/contestacoes').json()['contestacoes'][0]['situacao_acesso']=='CONFERENCIA_NECESSARIA'
    with f() as db:assert db.get(m.ContestacaoPagamento,ident).bloqueio_executado_em is None


def test_autorizacao_listagem_e_validacao(ambiente_compra):
    main,c,f,_,_=ambiente_compra
    with f() as db:pid,cid=compra(db);ident=caso(db,pid)
    assert c.get('/admin/contestacoes').status_code==403
    assert confirmar(c,ident).status_code==403
    assert bloquear(c,ident).status_code==403
    main.app.dependency_overrides.pop(main.get_usuario_atual)
    assert c.get('/admin/contestacoes').status_code==401
    admin(main)
    assert c.get('/admin/contestacoes').json()['contestacoes'][0]['mp_payment_id']=='101'
    assert c.get('/admin/contestacoes?pagina=0').status_code==422
    assert c.post(f'/admin/contestacoes/{ident}/confirmar-devolucao',json={'referencia_devolucao':' ','confirmacao_devolucao':True}).status_code==422
    assert c.post(f'/admin/contestacoes/{ident}/confirmar-devolucao',json={'referencia_devolucao':'extrato','confirmacao_devolucao':False}).status_code==400
    assert c.post(f'/admin/contestacoes/{ident}/bloquear-acesso').status_code==400


def test_registro_duplicado_preserva_auditoria(ambiente_compra):
    main,c,f,_,_=ambiente_compra
    with f() as db:pid,cid=compra(db);ident=caso(db,pid)
    admin(main);confirmar(c,ident);bloquear(c,ident)
    with f() as db:
        original=db.get(m.ContestacaoPagamento,ident)
        data=original.devolucao_confirmada_em
        for _ in range(2):registrar_observacao(db,db.get(m.Pagamento,pid),{'id':str(9000+pid),'reason':'fraud'})
        db.commit()
        assert db.query(m.ContestacaoPagamento).count()==1
        assert original.mp_dispute_id==str(9000+pid) and original.devolucao_confirmada_em==data
        with pytest.raises(HTTPException):registrar_observacao(db,db.get(m.Pagamento,pid),{'id':'998'})


def mp_dados(pid='101',status='charged_back'):
    return {'id':int(pid),'status':status,'external_reference':'user:1|curso:1|tempo:1|pagamento:1',
        'transaction_amount':49.90,'currency_id':'BRL','collector_id':123456}


def test_payment_charged_back_registra_sem_bloqueio(ambiente_compra):
    main,c,f,_,_=ambiente_compra
    with f() as db:pid,cid=compra(db)
    resposta=Mock(status_code=200);resposta.json.return_value=mp_dados()
    with f() as db:
        main.processar_pagamento_mp('101',db,resposta_mp=resposta)
        main.processar_pagamento_mp('101',db,resposta_mp=resposta)
    with f() as db:
        assert db.query(m.ContestacaoPagamento).count()==1
        assert curso_vigente(db,1,1)


@pytest.mark.parametrize('problema',[None,'assinatura','id','multiplos','parcial','provedor_indisponivel','caso_id'])
def test_webhook_caso_canonico(ambiente_compra,problema):
    main,c,f,_,_=ambiente_compra
    with f() as db:pid,cid=compra(db)
    caso_mp={'id':'999','payments':[101], 'currency':'BRL','amount':49.90,'reason':'unauthorized'}
    payload={'type':'topic_chargebacks_wh','id':500,'data':{'id':999,'payment_id':666}}
    if problema=='id':payload['data']['id']=998
    if problema=='multiplos':caso_mp['payments']=[101,102]
    if problema=='parcial':caso_mp['amount']=20
    if problema=='caso_id':caso_mp['id']='998'
    resp_caso=Mock(status_code=503 if problema=='provedor_indisponivel' else 200)
    resp_caso.json.return_value=caso_mp
    resp_payment=Mock(status_code=200);resp_payment.json.return_value=mp_dados(status='approved')
    # O corpo do evento não é fonte de identidade/valor: consulta autenticada.
    with patch.object(main,'validar_assinatura_mercadopago',return_value=problema!='assinatura'),patch('app.contestacoes.requests.get',side_effect=[resp_caso,resp_payment]*2):
        r=c.post('/webhooks/mercadopago?data.id=999',json=payload)
        if problema=='assinatura':
            assert r.status_code==401
        elif problema:
            assert r.status_code==200 and r.json()['armazenado']
            assert not r.json()['processado']
        else:
            assert r.status_code==200,r.text
            assert c.post('/webhooks/mercadopago?data.id=999',json=payload).status_code==200
    with f() as db:
        assert db.query(m.ContestacaoPagamento).count()==(0 if problema else 1)
        assert curso_vigente(db,1,1)
        assert db.get(m.Pagamento,pid).status=='APPROVED'


def test_dashboard_e_conteudo_nao_usam_cache_bloqueado(ambiente_compra):
    main,c,f,_,_=ambiente_compra
    with f() as db:
        pid,cid=compra(db);ident=caso(db,pid)
        db.get(m.Usuario,1).email="aluno@example.com";db.commit()
        usuario=db.get(m.Usuario,1)
    main.app.dependency_overrides[main.get_usuario_atual]=lambda:usuario
    assert len(c.get('/me/cursos').json())==1
    assert c.get('/me').json()['tem_cursos'] is True
    admin(main);assert confirmar(c,ident).status_code==200;assert bloquear(c,ident).status_code==200
    main.app.dependency_overrides[main.get_usuario_atual]=lambda:usuario
    assert c.get('/me/cursos').json()==[]
    assert c.get('/me').json()['tem_cursos'] is False
    # Revalidar somente o cache não pode devolver o acesso.
    with f() as db:
        a=db.query(m.AcessoCurso).one();a.ativo=True;db.commit()
        assert not curso_vigente(db,1,1)


def test_endpoints_ia_nao_aceitam_anonimo_e_escritas_exigem_admin(ambiente_compra):
    main,c,_,_,_=ambiente_compra
    for rota in ('quiz-ia','cartoes-ia','questoes-ia'):
        assert c.post('/'+rota,json={}).status_code==403
    main.app.dependency_overrides.pop(main.get_usuario_atual)
    for rota in ('quiz-ia','cartoes-ia','questoes-ia'):
        assert c.get('/pastas/1/'+rota).status_code==401


def test_webhook_chargeback_nao_modifica_reembolso_pendente(ambiente_compra):
    main,c,f,_,_=ambiente_compra
    with f() as db:
        pid,cid=compra(db);db.get(m.Pagamento,pid).status='REFUND_IN_PROCESS';db.commit()
    resp=Mock(status_code=200);resp.json.return_value=mp_dados()
    with f() as db:main.processar_pagamento_mp('101',db,resposta_mp=resp)
    with f() as db:
        assert db.get(m.Pagamento,pid).status=='REFUND_IN_PROCESS'
        assert db.query(m.ContestacaoPagamento).one().bloqueio_executado_em is None
        assert curso_vigente(db,1,1)
