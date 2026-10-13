"""Isolamento dos oito eventos de teste; SQLite/provedor exclusivamente simulados."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from sqlalchemy import select, update, text
from app import models as m
from app.pausa_financeira import inbox, isolamentos, IDS_HISTORICOS
from test_compras_fluxo import ambiente_compra, motor
from test_transacoes_mp import preparar, confirmar
from test_pausa_financeira import modo, enviar, admin


def historicos(a):
    modo(a, 'PAUSADO'); modo(a, 'RECUPERACAO')
    with a[2].kw['bind'].begin() as c:
        for ident in range(1, 11):
            c.execute(inbox.insert().values(id=ident,chave=f'historico:{ident}',payment_id='999',
                fonte='WEBHOOK',recebida_em=datetime.now(timezone.utc),
                estado='CONCLUIDO' if ident in (5,6) else 'ERRO',tentativas=2,
                erro='registro original',resultado={'teste':True}))
        if c.dialect.name == 'postgresql':
            c.execute(text("SELECT setval(pg_get_serial_sequence('notificacoes_mp','id'),10,true)"))
    return {'geracao':2,'motivo':'Decisão do proprietário: somente testes históricos'}


def snapshot(a):
    with a[2].kw['bind'].connect() as c:
        return [dict(r) for r in c.execute(select(inbox).order_by(inbox.c.id)).mappings()]


def isolar(a, body):
    return a[1].post('/admin/financeiro/notificacoes/isolamento',json=body)


def test_auditoria_repeticao_nao_altera_historico_e_reabertura(ambiente_compra):
    a=ambiente_compra;body=historicos(a);antes=snapshot(a)
    a[3].reset_mock();a[4].reset_mock()
    r=isolar(a,body)
    assert r.status_code==200 and r.json()['ids']==list(IDS_HISTORICOS)
    assert snapshot(a)==antes
    with a[2].kw['bind'].connect() as c:
        auditoria=[dict(r) for r in c.execute(select(isolamentos)).mappings()]
        assert len(auditoria)==8
        assert all(r['isolada_por']==2 and r['geracao']==2 and r['motivo']==body['motivo'] for r in auditoria)
    assert isolar(a,{**body,'motivo':'não substituir auditoria'}).status_code==200
    with a[2].kw['bind'].connect() as c:
        assert [dict(r) for r in c.execute(select(isolamentos)).mappings()]==auditoria
    assert a[1].get('/admin/financeiro/manutencao').json()['geracao']==2
    pendencias=a[1].get('/admin/financeiro/notificacoes').json()
    assert len(pendencias['isolamentos'])==8 and all(r['isolada'] for r in pendencias['pendencias'])
    assert a[1].post('/admin/financeiro/notificacoes/recuperar',json={'limite':5}).json()['resultados']==[]
    for ident in IDS_HISTORICOS:
        assert a[1].post('/admin/financeiro/notificacoes/recuperar',json={'notificacao_id':ident}).json()['resultados']==[]
        assert not a[0].app.state.protecao_financeira.processar(ident,True)['processado']
    a[3].assert_not_called();a[4].assert_not_called()
    assert snapshot(a)==antes
    assert a[1].post('/admin/financeiro/manutencao',json={'modo':'NORMAL','geracao':2,'motivo':'teste'}).status_code==409
    assert modo(a,'NORMAL').status_code==200
    with a[2]() as db:
        assert db.query(m.Pagamento).count()==0 and db.query(m.ContratacaoCurso).count()==0


def test_outro_evento_mesmo_pagamento_nao_herda_isolamento(ambiente_compra):
    a=ambiente_compra;body=historicos(a);assert isolar(a,body).status_code==200
    p=a[0].app.state.protecao_financeira
    # SQL fixture fixa IDs; avançar sequência PostgreSQL fica a cargo do teste PG.
    with a[2].kw['bind'].begin() as c:
        c.execute(inbox.insert().values(id=11,chave='novo:evento',payment_id='999',fonte='WEBHOOK',
            recebida_em=datetime.now(timezone.utc),estado='PENDENTE',tentativas=0))
    assert modo(a,'NORMAL').status_code==409
    with patch.object(p,'processor',return_value={'ok':True,'status':'CANCELLED'}), \
         patch.object(p,'consulta',return_value=object()):
        r=a[1].post('/admin/financeiro/notificacoes/recuperar',json={'notificacao_id':11})
    assert r.json()['resultados']==[{'id':11,'processado':True,'status':'CANCELLED'}]
    assert all(r['estado']=='ERRO' for r in snapshot(a) if r['id'] in IDS_HISTORICOS)
    assert modo(a,'NORMAL').status_code==200


@pytest.mark.parametrize('variacao',['faltante','concluida','geracao','modo','motivo'])
def test_isolamento_invalido_atomico(ambiente_compra,variacao):
    a=ambiente_compra;body=historicos(a)
    if variacao in ('faltante','concluida'):
        with a[2].kw['bind'].begin() as c:
            if variacao=='faltante':c.execute(inbox.delete().where(inbox.c.id==10))
            else:c.execute(update(inbox).where(inbox.c.id==10).values(estado='CONCLUIDO'))
    if variacao=='geracao':body['geracao']=1
    if variacao=='modo':modo(a,'PAUSADO')
    if variacao=='motivo':body['motivo']='   '
    antes=snapshot(a)
    assert isolar(a,body).status_code in (409,503)
    assert snapshot(a)==antes
    with a[2].kw['bind'].connect() as c:assert c.execute(select(isolamentos)).all()==[]


def test_permissoes_e_revogacao_auditada(ambiente_compra):
    a=ambiente_compra;body=historicos(a)
    a[0].app.dependency_overrides[a[0].get_usuario_atual]=lambda:SimpleNamespace(id=1,is_admin=False)
    assert isolar(a,body).status_code==403
    a[0].app.dependency_overrides.pop(a[0].get_usuario_atual)
    assert isolar(a,body).status_code==401
    admin(a);assert isolar(a,body).status_code==200
    assert a[1].post('/admin/financeiro/notificacoes/11/isolamento/revogar',json=body).status_code==422
    r=a[1].post('/admin/financeiro/notificacoes/1/isolamento/revogar',json=body)
    assert r.status_code==200 and modo(a,'NORMAL').status_code==409
    with a[2].kw['bind'].connect() as c:
        row=c.execute(select(isolamentos).where(isolamentos.c.notificacao_id==1)).mappings().one()
        assert row['isolada_por']==2 and row['revogada_por']==2 and row['revogada_em'] is not None
    assert isolar(a,body).status_code==409


def test_legado_pendente_nao_reutiliza_nem_cria_cobranca(ambiente_compra):
    a=ambiente_compra;preparar(a,legado=True)
    a[3].reset_mock();a[4].reset_mock()
    with a[2]() as db:did=db.query(m.DemonstracaoCurso).one().id
    r=a[1].post('/checkout/mercadopago',json={'tempo_acesso_id':1,'demonstracao_id':did})
    assert r.status_code==409 and 'legada' in r.json()['detail']
    a[3].assert_not_called();a[4].assert_not_called()
    with a[2]() as db:assert db.query(m.Pagamento).count()==1


def test_seguro_reutilizado_sem_nova_preferencia(ambiente_compra):
    a=ambiente_compra;pid,_,_,_=preparar(a)
    a[3].reset_mock()
    with a[2]() as db:did=db.query(m.DemonstracaoCurso).one().id
    r=a[1].post('/checkout/mercadopago',json={'tempo_acesso_id':1,'demonstracao_id':did})
    assert r.status_code==200 and r.json()['pagamento_id']==pid
    a[3].assert_not_called()


@pytest.mark.parametrize('status',['in_mediation','charged_back','refunded','cancelled'])
def test_evento_financeiro_nao_bloqueia_acesso_automaticamente(ambiente_compra,status):
    a=ambiente_compra;pid,dados,tx,_=preparar(a)
    tx['101']=dados(101,'approved');assert confirmar(a,101).status_code==200
    with a[2]() as db:
        antes=[(x.id,x.ativo,x.data_inicio,x.data_fim) for x in db.query(m.AcessoCurso)]
        contratos=[(x.id,x.data_inicio,x.data_fim) for x in db.query(m.ContratacaoCurso)]
    tx['101']=dados(101,status)
    assert enviar(a,101,'evento-posterior').status_code==200
    with a[2]() as db:
        assert [(x.id,x.ativo,x.data_inicio,x.data_fim) for x in db.query(m.AcessoCurso)]==antes
        assert [(x.id,x.data_inicio,x.data_fim) for x in db.query(m.ContratacaoCurso)]==contratos
        assert db.query(m.PeriodoAcessoPagamento).count()==1
        assert db.query(m.ContestacaoPagamento).filter(m.ContestacaoPagamento.bloqueio_executado_em.isnot(None)).count()==0


@pytest.mark.parametrize('extra', [{'ids':[11]}, {'isolada_por':1}, {'notificacao_id':5}])
def test_parametros_nao_autorizados_rejeitados(ambiente_compra, extra):
    a=ambiente_compra;body=historicos(a);antes=snapshot(a)
    assert isolar(a,{**body,**extra}).status_code==422
    assert snapshot(a)==antes
    with a[2].kw['bind'].connect() as c:assert c.execute(select(isolamentos)).all()==[]


@pytest.mark.parametrize('metodo',['pix','visa'])
def test_nova_venda_apos_isolamento_pendente_aprovada_idempotente(ambiente_compra,metodo):
    a=ambiente_compra;pid,dados,tx,_=preparar(a)
    body=historicos(a);antes=snapshot(a)
    assert isolar(a,body).status_code==200
    assert modo(a,'NORMAL').status_code==200
    tx['101']={**dados(101,'pending'),'payment_method_id':metodo}
    r=enviar(a,101,'novo-pendente')
    assert r.status_code==200 and r.json()['processado'] is True
    with a[2]() as db:
        assert db.get(m.Pagamento,pid).status=='PENDING'
        assert db.query(m.ContratacaoCurso).count()==0
    tx['101']={**dados(101,'approved'),'payment_method_id':metodo}
    for evento in ('novo-aprovado','novo-aprovado','nova-repeticao-aprovada'):
        assert enviar(a,101,evento).status_code==200
    with a[2]() as db:
        assert db.query(m.ContratacaoCurso).count()==1
        assert db.query(m.PeriodoAcessoPagamento).count()==1
        assert db.query(m.AcessoCurso).filter_by(ativo=True).count()==1
    assert snapshot(a)[:10]==antes
    with a[2].kw['bind'].connect() as c:
        assert len(c.execute(select(isolamentos)).all())==8
        assert c.execute(select(inbox.c.estado).where(inbox.c.id>10)).scalars().all()==['CONCLUIDO']*3


def test_confirmacao_navegador_apos_isolamento(ambiente_compra):
    a=ambiente_compra;pid,dados,tx,_=preparar(a)
    body=historicos(a);antes=snapshot(a)
    assert isolar(a,body).status_code==200
    assert modo(a,'NORMAL').status_code==200
    a[0].app.dependency_overrides[a[0].get_usuario_atual]=lambda:SimpleNamespace(id=1,email='1@teste.local',is_admin=False)
    tx['101']=dados(101,'approved')
    for _ in range(2):assert confirmar(a,101).status_code==200
    with a[2]() as db:
        assert db.query(m.ContratacaoCurso).count()==1
        assert db.query(m.PeriodoAcessoPagamento).count()==1
    assert snapshot(a)==antes


def test_isolamento_preserva_pagamentos_e_todos_os_direitos(ambiente_compra):
    a=ambiente_compra;pid,dados,tx,_=preparar(a)
    tx['101']=dados(101,'approved');assert confirmar(a,101).status_code==200
    body=historicos(a)
    tabelas=(m.Pagamento,m.OportunidadeCompra,m.ContratacaoCurso,m.AcessoCurso,
             m.PeriodoAcessoPagamento,m.DemonstracaoCurso,m.ReembolsoFinanceiro,m.ContestacaoPagamento)
    def dados_locais():
        with a[2]() as db:
            return {t.__tablename__:[dict(r) for r in db.execute(select(t.__table__).order_by(t.id)).mappings()] for t in tabelas}
    antes=dados_locais();eventos=snapshot(a)
    assert isolar(a,body).status_code==200
    assert modo(a,'NORMAL').status_code==200
    assert dados_locais()==antes and snapshot(a)==eventos


def test_contestacao_exige_devolucao_antes_do_bloqueio_e_preserva_direitos(ambiente_compra):
    from sqlalchemy.exc import IntegrityError
    a=ambiente_compra;pid,dados,tx,_=preparar(a)
    tx['101']=dados(101,'approved');assert confirmar(a,101).status_code==200
    with a[2]() as db:
        direitos=[(x.id,x.ativo,x.data_fim) for x in db.query(m.AcessoCurso)]
        db.add(m.ContestacaoPagamento(pagamento_id=pid,valor_cents=4990,
               bloqueio_executado_em=datetime.utcnow(),bloqueio_executado_por=2))
        with pytest.raises(IntegrityError):db.commit()
        db.rollback()
        contestacao=m.ContestacaoPagamento(pagamento_id=pid,valor_cents=4990)
        db.add(contestacao);db.commit()
        contestacao.devolucao_confirmada_em=datetime.utcnow()
        contestacao.devolucao_confirmada_por=2
        contestacao.referencia_devolucao='comprovante exclusivamente simulado'
        db.commit()
        assert contestacao.bloqueio_executado_em is None
        assert [(x.id,x.ativo,x.data_fim) for x in db.query(m.AcessoCurso)]==direitos
        assert db.query(m.ContratacaoCurso).count()==1
