"""Reembolsos/contestações: SQLite em memória e provedor simulado, sem dados reais."""
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from sqlalchemy import text
from app import models as m
import app.direitos_acesso as da
import app.desempenho as desempenho
import app.contestacoes as cont
from test_compras_fluxo import motor, ambiente_compra
from app.bloqueios_reembolso import metadata as metadata_bloqueios, bloqueios_reembolso
import app.reembolsos_acesso as reembolsos_acesso
from test_contestacoes_reconstruido import compra, caso, admin, confirmar, bloquear

T0 = datetime(2035, 1, 1, 12)
class Clock(datetime):
    at = T0
    @classmethod
    def utcnow(cls): return cls.at

@pytest.fixture
def env(ambiente_compra, monkeypatch):
    Clock.at = T0
    monkeypatch.setenv('MP_COLLECTOR_ID', '123456')
    main = ambiente_compra[0]
    metadata_bloqueios.create_all(ambiente_compra[2].kw['bind'])
    for module in (main, da, desempenho, cont, reembolsos_acesso):
        monkeypatch.setattr(module, 'datetime', Clock)
    return ambiente_compra

def student(main):
    main.app.dependency_overrides[main.get_usuario_atual] = lambda: SimpleNamespace(id=1,email='1@teste.local',is_admin=False)

def evidence(name, **values):
    print('EVIDENCE', name, json.dumps(values, default=str, ensure_ascii=False))

def academic_tables(factory):
    tables = {m.ProgressoAula.__table__}
    while True:
        deps = {fk.column.table for table in tables for fk in table.foreign_keys}
        if deps <= tables: break
        tables |= deps
    m.Base.metadata.create_all(factory.kw['bind'], tables=list(tables))
    with factory() as db:
        db.add(m.Pasta(id=1,nome='Pasta fictícia',tipo='TEORIA'))
        db.flush()
        db.add(m.Aula(id=1,pasta_id=1,titulo='Aula fictícia'))
        db.commit()

def referencia_simulada(factory, pagamento_id):
    # Preserva o contrato de identidade segura já vigente na main remota.
    with factory() as db:
        pagamento = db.get(m.Pagamento, pagamento_id)
        if pagamento.checkout_identidade:
            return 'checkout:' + pagamento.checkout_identidade
    return f'user:1|curso:1|tempo:1|pagamento:{pagamento_id}'


def setup_payment(env, origin='ADMIN', admin_end=5, independent=False):
    main,c,f,_,get = env
    academic_tables(f)
    if origin == 'ADMIN':
        admin(main)
        Clock.at = T0 - timedelta(days=20)
        r = c.post('/admin/acessos',json={'usuario_id':1,'curso_id':1,'data_fim':(T0+timedelta(days=admin_end)).isoformat()+'Z'})
        assert r.status_code == 200, r.text
        cid = r.json()['contratacao_id']
        Clock.at = T0
        student(main)
        r = c.post('/checkout/mercadopago',json={'tempo_acesso_id':1,'tipo_compra':'RENOVACAO','contratacao_id':cid})
    else:
        student(main)
        r = c.post('/checkout/mercadopago',json={'tempo_acesso_id':1})
    assert r.status_code == 200, r.text
    pid = r.json()['pagamento_id']
    response = Mock(status_code=200)
    response.json.return_value = {'id':'701','status':'approved','payment_method_id':'credit_card',
        'date_approved':T0.isoformat()+'Z','transaction_amount':49.90,'currency_id':'BRL',
        'external_reference':referencia_simulada(f,pid),'collector_id':123456,'live_mode':True}
    get.return_value = response
    r = c.post('/pagamentos/confirmar',json={'payment_id':'701','curso_id':1})
    assert r.status_code == 200, r.text
    with f() as db:
        p = db.get(m.Pagamento,pid)
        cid = p.contratacao_id
        p.moeda = 'BRL'
        p.provedor = 'MERCADO_PAGO'
        db.add(m.ProgressoAula(usuario_id=1,pasta_id=1,aula_id=1,contratacao_id=cid,concluida=True))
        if independent:
            db.add(m.ConcessaoAcessoAdmin(usuario_id=1,curso_id=1,data_inicio=T0-timedelta(days=1),data_fim=T0+timedelta(days=60),ativo=True))
        db.commit()
    return pid,cid

def state(env,cid):
    main,c,f,_,_ = env
    student(main)
    courses = c.get('/me/cursos')
    assert courses.status_code == 200, courses.text
    expired = c.get('/me/desempenho/contextos-expirados')
    assert expired.status_code == 200, expired.text
    course_history = c.get('/me/cursos/historico')
    assert course_history.status_code == 200, course_history.text
    with f() as db:
        try:
            main.validar_contexto_estudo(db,SimpleNamespace(id=1),1,cid)
            authorized = True
        except Exception as e:
            assert getattr(e,'status_code',None) == 403
            authorized = False
        a = db.query(m.AcessoCurso).one()
        ct = db.get(m.ContratacaoCurso,cid)
        return {'listed':bool(courses.json()),'study_allowed':authorized,
            'course_valid':da.curso_vigente(db,1,1),'aggregate_active':a.ativo,
            'aggregate_end':a.data_fim,'contract_end':ct.data_fim,
            'expired_contexts':len(expired.json()), 'course_history':len(course_history.json()),
            'progress':db.query(m.ProgressoAula).filter_by(contratacao_id=cid,concluida=True).count(),
            'periods':db.query(m.PeriodoAcessoPagamento).count()}

@pytest.mark.parametrize('origin',['ADMIN','PAGAMENTO'])
def test_refund_requires_separate_manual_block(env,origin):
    main,c,f,_,_ = env
    pid,cid = setup_payment(env,origin)
    student(main)
    assert c.post(f'/me/reembolso/{pid}').status_code == 200
    requested = state(env,cid)
    assert requested['study_allowed'] and requested['listed']
    admin(main)
    assert c.post(f'/admin/reembolsos/{pid}/aprovar').status_code == 200
    r=c.post(f'/admin/reembolsos/{pid}/pix-manual',json={'valor_cents':4990,'referencia_comprovante':'fictício'})
    assert r.status_code==200,r.text
    rid=r.json()['reembolso_id']
    assert c.post(f'/admin/reembolsos/{rid}/pix-manual/confirmar?confirmacao_extrato=false').status_code==400
    r=c.post(f'/admin/reembolsos/{rid}/pix-manual/confirmar?confirmacao_extrato=true')
    assert r.status_code==200,r.text
    immediate=state(env,cid)
    assert immediate['study_allowed'] and immediate['progress']==1 and immediate['periods']==1
    assert immediate == requested  # confirmar a devolução não muda nenhum direito
    admin(main)
    result = c.post(f'/admin/reembolsos/{rid}/bloquear-acesso?confirmacao_bloqueio=true')
    assert result.status_code == 200, result.text
    after = state(env,cid)
    assert after['progress'] == 1 and after['periods'] == 1
    if origin == 'ADMIN':
        assert after['listed'] and after['study_allowed']
        assert after['aggregate_end'] == requested['aggregate_end']
        Clock.at = T0 + timedelta(days=6)
        later = state(env,cid)
        assert not later['listed'] and not later['study_allowed'] and not later['course_valid']
        assert later['expired_contexts'] == 1
    else:
        assert not after['listed'] and not after['study_allowed'] and not after['course_valid']
        assert after['expired_contexts'] == 1
    # Repetir não altera a decisão nem o histórico financeiro/acadêmico.
    with f() as db:
        decision = db.execute(bloqueios_reembolso.select()).first()
        before = tuple(decision)
        contract = db.get(m.ContratacaoCurso,cid)
        original_contract = (contract.origem, contract.data_inicio, contract.data_fim)
    admin(main)
    assert c.post(f'/admin/reembolsos/{rid}/bloquear-acesso?confirmacao_bloqueio=true').status_code == 200
    with f() as db:
        assert tuple(db.execute(bloqueios_reembolso.select()).one()) == before
        contract = db.get(m.ContratacaoCurso,cid)
        assert (contract.origem, contract.data_inicio, contract.data_fim) == original_contract
        assert db.get(m.Pagamento,pid).status == 'REFUNDED'
    evidence('refund_'+origin,confirmation_preserved=True,blocked=after)

@pytest.mark.parametrize('origin',['ADMIN','PAGAMENTO'])
def test_contestation_manual_block_and_access_consumers(env,origin):
    main,c,f,_,_=env
    pid,cid=setup_payment(env,origin)
    if origin=='ADMIN': Clock.at=T0+timedelta(days=6)
    with f() as db:
        ident=caso(db,pid)
    before=state(env,cid)
    assert before['study_allowed'] and before['course_valid']
    admin(main)
    assert bloquear(c,ident).status_code==409
    assert c.post(f'/admin/contestacoes/{ident}/confirmar-devolucao',json={'referencia_devolucao':'fake','confirmacao_devolucao':False}).status_code==400
    assert confirmar(c,ident).status_code==200
    confirmed=state(env,cid)
    assert confirmed['study_allowed'] and confirmed['course_valid']
    admin(main)
    assert c.post(f'/admin/contestacoes/{ident}/bloquear-acesso').status_code==400
    r=bloquear(c,ident)
    assert r.status_code==200,r.text
    after=state(env,cid)
    assert after['progress']==1 and after['periods']==1
    assert not after['course_valid'] and not after['study_allowed'] and not after['listed']
    assert after['expired_contexts']==1 and after['course_history']==1
    with f() as db:
        assert db.get(m.ContestacaoPagamento,ident).bloqueio_executado_em is not None
        assert db.get(m.ContratacaoCurso,cid).origem == origin
        desempenho.validar_contexto_historico(db,SimpleNamespace(id=1),1,cid)
    evidence('contest_'+origin,opening=before,confirmed=confirmed,block_status=r.status_code,block=r.json(),after=after)

@pytest.mark.parametrize('right',['concessao','outra_compra','renovacao_futura'])
def test_manual_block_preserves_other_rights(env,right):
    main,c,f,_,_=env
    pid,cid=setup_payment(env,'PAGAMENTO',independent=right=='concessao')
    with f() as db:
        if right=='outra_compra':
            compra(db,inicio=T0-timedelta(days=1),fim=T0+timedelta(days=80),mp='702')
        elif right=='renovacao_futura':
            ct=db.get(m.ContratacaoCurso,cid)
            compra(db,contrato=ct,inicio=ct.data_fim,fim=ct.data_fim+timedelta(days=30),renovacao=True,mp='702')
        ident=caso(db,pid)
    admin(main)
    assert confirmar(c,ident).status_code==200
    assert bloquear(c,ident).status_code==200
    after=state(env,cid)
    assert after['course_valid']==(right!='renovacao_futura')
    assert after['progress']==1
    later = None
    if right=='concessao':
        Clock.at = T0+timedelta(days=61)
        later = state(env,cid)
        assert not later['course_valid'] and not later['listed'] and not later['study_allowed']
    if right=='renovacao_futura':
        with f() as db:
            ct=db.get(m.ContratacaoCurso,cid)
            assert da.contrato_vigente(db,ct,T0+timedelta(days=130))
        Clock.at=T0+timedelta(days=130)
        resumed=state(env,cid)
        assert resumed['listed'] and resumed['study_allowed'] and resumed['course_valid']
        assert resumed['expired_contexts']==0
    evidence('independent_'+right,after=after,later=later)

def test_refund_limits_and_admin_authorization(env):
    main,c,f,_,_=env
    pid,cid=setup_payment(env,'ADMIN')
    assert c.post(f'/admin/reembolsos/{pid}/aprovar').status_code==403
    with f() as db: ident=caso(db,pid)
    assert bloquear(c,ident).status_code==403
    Clock.at=T0+timedelta(days=7,seconds=1)
    assert c.post(f'/me/reembolso/{pid}').status_code==400
    with f() as db: assert db.get(m.Pagamento,pid).status=='APPROVED'
    evidence('limits',refund_after_7days=400,nonadmin_refund=403,nonadmin_block=403)

@pytest.mark.parametrize('origin',['ADMIN','PAGAMENTO'])
@pytest.mark.parametrize('mp_status',['charged_back','refunded'])
def test_card_event_and_case_opening_do_not_block(env,origin,mp_status):
    main,c,f,_,get=env
    pid,cid=setup_payment(env,origin)
    data=dict(get.return_value.json.return_value)
    data['status']=mp_status
    get.return_value.json.return_value=data
    with f() as db:
        result=main.processar_pagamento_mp('701',db)
        assert result['ok']
    if mp_status=='charged_back':
        with f() as db:
            result=cont.receber_caso(db,{'id':'9701','reason':'simulada'},data,'701',{})
            ident=result['contestacao_id']
    after=state(env,cid)
    with f() as db:
        p=db.get(m.Pagamento,pid)
        assert p.mp_status==mp_status.upper()
        if mp_status=='charged_back':
            case=db.get(m.ContestacaoPagamento,ident)
            assert case.bloqueio_executado_em is None and case.devolucao_confirmada_em is None
    assert after['listed'] and after['study_allowed'] and after['course_valid']
    evidence('card_open_'+origin,mp_status=mp_status.upper(),after=after)

def test_refund_with_valid_future_renewal_preserves_access_and_listing(env):
    main,c,f,_,_=env
    pid,cid=setup_payment(env,'PAGAMENTO')
    with f() as db:
        ct=db.get(m.ContratacaoCurso,cid)
        start=ct.data_fim
        renewed_pid,_=compra(db,contrato=ct,inicio=start,fim=start+timedelta(days=30),renovacao=True,mp='702')
        db.get(m.Pagamento,renewed_pid).aprovado_em=T0
        db.commit()
    student(main)
    assert c.post(f'/me/reembolso/{pid}').status_code==200
    admin(main)
    assert c.post(f'/admin/reembolsos/{pid}/aprovar').status_code==200
    r=c.post(f'/admin/reembolsos/{pid}/pix-manual',json={'valor_cents':4990,'referencia_comprovante':'fictício'})
    assert r.status_code==200,r.text
    rid=r.json()['reembolso_id']
    r=c.post(f'/admin/reembolsos/{rid}/pix-manual/confirmar?confirmacao_extrato=true')
    assert r.status_code==200,r.text
    assert c.post(f'/admin/reembolsos/{rid}/bloquear-acesso?confirmacao_bloqueio=true').status_code==200
    before_future=state(env,cid)
    assert not before_future['listed'] and not before_future['study_allowed']
    Clock.at=start+timedelta(days=1)
    later=state(env,cid)
    assert later['course_valid'] and later['study_allowed'] and later['listed']
    assert later['periods']==2 and later['progress']==1
    evidence('future_valid_renewal_after_refund',later=later)


def confirm_refund(env,pid):
    main,c,_,_,_=env
    student(main)
    assert c.post(f'/me/reembolso/{pid}').status_code==200
    admin(main)
    assert c.post(f'/admin/reembolsos/{pid}/aprovar').status_code==200
    r=c.post(f'/admin/reembolsos/{pid}/pix-manual',json={'valor_cents':4990,'referencia_comprovante':'fictício'})
    assert r.status_code==200,r.text
    rid=r.json()['reembolso_id']
    assert c.post(f'/admin/reembolsos/{rid}/pix-manual/confirmar?confirmacao_extrato=true').status_code==200
    return rid


def test_refund_block_requires_admin_confirmation_and_real_return(env):
    main,c,f,_,_=env
    pid,cid=setup_payment(env,'ADMIN')
    student(main)
    assert c.post(f'/me/reembolso/{pid}').status_code==200
    admin(main)
    assert c.post(f'/admin/reembolsos/{pid}/aprovar').status_code==200
    r=c.post(f'/admin/reembolsos/{pid}/pix-manual',json={'valor_cents':4990,'referencia_comprovante':'fictício'})
    rid=r.json()['reembolso_id']
    url=f'/admin/reembolsos/{rid}/bloquear-acesso?confirmacao_bloqueio=true'
    assert c.post(url).status_code==409
    assert c.post(f'/admin/reembolsos/{rid}/bloquear-acesso').status_code==400
    assert c.post(f'/admin/reembolsos/{rid}/pix-manual/confirmar?confirmacao_extrato=true').status_code==200
    student(main)
    assert c.post(url).status_code==403
    with f() as db: assert db.execute(bloqueios_reembolso.select()).first() is None


def test_schema_pending_preserves_existing_flows_and_refuses_new_write(env):
    main,c,f,_,_=env
    pid,cid=setup_payment(env,'PAGAMENTO')
    rid=confirm_refund(env,pid)
    metadata_bloqueios.drop_all(f.kw['bind'])  # somente tabela criada nesta fixture em memória
    assert state(env,cid)['listed']
    admin(main)
    assert c.get('/admin/reembolsos').status_code==200
    r=c.post(f'/admin/reembolsos/{rid}/bloquear-acesso?confirmacao_bloqueio=true')
    assert r.status_code==503
    assert state(env,cid)['study_allowed']


@pytest.mark.parametrize('flow',['reembolso','contestacao'])
def test_admin_paid_renewal_future_right_and_historical_records(env,flow):
    main,c,f,_,_=env
    pid,cid=setup_payment(env,'ADMIN')
    with f() as db:
        contract=db.get(m.ContratacaoCurso,cid)
        future_start=contract.data_fim
        next_pid,_=compra(db,contrato=contract,inicio=future_start,
            fim=future_start+timedelta(days=30),renovacao=True,mp='702')
        db.get(m.Pagamento,next_pid).aprovado_em=T0
        db.commit()
    if flow=='reembolso':
        rid=confirm_refund(env,pid)
    else:
        with f() as db: ident=caso(db,pid)
        admin(main)
        assert confirmar(c,ident).status_code==200
    with f() as db:
        financial=[tuple(getattr(p,col.name) for col in m.Pagamento.__table__.columns)
                   for p in db.query(m.Pagamento).order_by(m.Pagamento.id)]
        academic=[(p.id,p.contratacao_id,p.concluida,p.data_conclusao) for p in db.query(m.ProgressoAula)]
        concessions=[(p.id,p.ativo,p.data_inicio,p.data_fim) for p in db.query(m.ConcessaoAcessoAdmin)]
    admin(main)
    r=c.post(f'/admin/reembolsos/{rid}/bloquear-acesso?confirmacao_bloqueio=true') if flow=='reembolso' else bloquear(c,ident)
    assert r.status_code==200,r.text
    assert state(env,cid)['study_allowed']  # concessão original ainda vigente
    Clock.at=T0+timedelta(days=6)
    assert not state(env,cid)['listed']
    Clock.at=future_start+timedelta(days=1)
    resumed=state(env,cid)
    assert resumed['listed'] and resumed['study_allowed'] and resumed['course_valid']
    with f() as db:
        assert db.get(m.ContratacaoCurso,cid).origem=='ADMIN'
        assert financial==[tuple(getattr(p,col.name) for col in m.Pagamento.__table__.columns)
                   for p in db.query(m.Pagamento).order_by(m.Pagamento.id)]
        assert academic==[(p.id,p.contratacao_id,p.concluida,p.data_conclusao) for p in db.query(m.ProgressoAula)]
        assert concessions==[(p.id,p.ativo,p.data_inicio,p.data_fim) for p in db.query(m.ConcessaoAcessoAdmin)]


def test_admin_renewal_after_paid_period_remains_an_independent_right(env):
    main,c,f,_,_=env
    pid,cid=setup_payment(env,'ADMIN')
    with f() as db:
        end=db.get(m.ContratacaoCurso,cid).data_fim
    Clock.at=end-timedelta(days=5)
    admin(main)
    r=c.post('/admin/acessos',json={'usuario_id':1,'curso_id':1,'data_fim':(end+timedelta(days=60)).isoformat()+'Z'})
    assert r.status_code==200,r.text
    assert r.json()['contratacao_id']==cid
    with f() as db: ident=caso(db,pid)
    assert confirmar(c,ident).status_code==200
    assert bloquear(c,ident).status_code==200
    assert state(env,cid)['study_allowed']
    Clock.at=end+timedelta(days=1)
    assert state(env,cid)['listed'] and state(env,cid)['study_allowed']


def test_inconsistent_admin_history_refuses_block_without_changing_rights(env):
    main,c,f,_,_=env
    pid,cid=setup_payment(env,'ADMIN')
    with f() as db:
        concession=db.query(m.ConcessaoAcessoAdmin).one()
        concession.data_fim=T0-timedelta(days=1)  # lacuna sem explicação histórica
        db.commit()
        ident=caso(db,pid)
    admin(main)
    assert confirmar(c,ident).status_code==200
    assert bloquear(c,ident).status_code==409
    with f() as db: assert db.get(m.ContestacaoPagamento,ident).bloqueio_executado_em is None
    assert state(env,cid)['study_allowed']


def test_manual_refund_block_is_protected_by_financial_pause(env):
    from app.pausa_financeira import controle
    main,c,f,_,_=env
    pid,cid=setup_payment(env,'PAGAMENTO')
    rid=confirm_refund(env,pid)
    with f() as db:
        db.execute(controle.update().values(modo='PAUSADO'))
        db.commit()
    r=c.post(f'/admin/reembolsos/{rid}/bloquear-acesso?confirmacao_bloqueio=true')
    assert r.status_code==503
    with f() as db: assert db.execute(bloqueios_reembolso.select()).first() is None


def test_profile_remains_read_only_during_financial_pause(env):
    from app.pausa_financeira import controle
    main,c,f,_,_=env
    pid,cid=setup_payment(env,'PAGAMENTO')
    with f() as db:
        Clock.at=db.get(m.ContratacaoCurso,cid).data_fim+timedelta(days=1)
        user=db.get(m.Usuario,1)
        user.email='aluno@example.com'
        db.execute(controle.update().values(modo='PAUSADO'))
        db.commit()
        # Carregar todos os atributos antes de separar a sessão de teste.
        db.refresh(user)
    main.app.dependency_overrides[main.get_usuario_atual]=lambda:user
    r=c.get('/me')
    assert r.status_code==200,r.text
    assert not r.json()['tem_cursos']
    with f() as db: assert db.query(m.AcessoCurso).one().ativo  # nenhuma escrita no cache


@pytest.mark.parametrize('flow',['reembolso','contestacao'])
def test_another_admin_contract_does_not_reopen_blocked_context(env,flow):
    main,c,f,_,_=env
    pid,cid=setup_payment(env,'ADMIN')
    admin(main)
    r=c.post('/admin/acessos',json={'usuario_id':1,'curso_id':1,
        'data_fim':(T0+timedelta(days=60)).isoformat()+'Z'})
    assert r.status_code==200,r.text
    other_cid=r.json()['contratacao_id']
    assert other_cid!=cid  # regra administrativa fora da janela permanece
    if flow=='reembolso':
        rid=confirm_refund(env,pid)
        r=c.post(f'/admin/reembolsos/{rid}/bloquear-acesso?confirmacao_bloqueio=true')
    else:
        with f() as db: ident=caso(db,pid)
        admin(main)
        assert confirmar(c,ident).status_code==200
        r=bloquear(c,ident)
    assert r.status_code==200,r.text
    Clock.at=T0+timedelta(days=6)
    assert not state(env,cid)['study_allowed']
    assert state(env,other_cid)['study_allowed'] and state(env,other_cid)['listed']


def test_financial_confirmation_of_other_period_does_not_inherit_manual_block(env):
    main,c,f,_,_=env
    pid,cid=setup_payment(env,'ADMIN')
    with f() as db:
        ct=db.get(m.ContratacaoCurso,cid)
        start=ct.data_fim
        next_pid,_=compra(db,contrato=ct,inicio=start,
            fim=start+timedelta(days=30),renovacao=True,mp='702')
        db.get(m.Pagamento,next_pid).aprovado_em=T0
        db.commit()
    rid=confirm_refund(env,pid)
    assert c.post(f'/admin/reembolsos/{rid}/bloquear-acesso?confirmacao_bloqueio=true').status_code==200
    student(main)
    assert c.post(f'/me/reembolso/{next_pid}').status_code==200
    admin(main)
    assert c.post(f'/admin/reembolsos/{next_pid}/aprovar').status_code==200
    r=c.post(f'/admin/reembolsos/{next_pid}/pix-manual',json={'valor_cents':4990,'referencia_comprovante':'fictício-2'})
    rid2=r.json()['reembolso_id']
    Clock.at=start+timedelta(days=1)
    assert c.post(f'/admin/reembolsos/{rid2}/pix-manual/confirmar?confirmacao_extrato=true').status_code==200
    assert state(env,cid)['listed'] and state(env,cid)['study_allowed']
    admin(main)
    assert c.post(f'/admin/reembolsos/{rid2}/bloquear-acesso?confirmacao_bloqueio=true').status_code==200
    assert not state(env,cid)['listed'] and not state(env,cid)['study_allowed']

@pytest.mark.parametrize('future', [False, True])
def test_renewal_window_uses_unblocked_right_and_preserves_future(env, future):
    main,c,f,_,get=env
    pid,cid=setup_payment(env,'ADMIN')
    with f() as db:
        original_end=db.get(m.ContratacaoCurso,cid).data_fim
        if future:
            compra(db,contrato=db.get(m.ContratacaoCurso,cid),inicio=original_end,
                fim=original_end+timedelta(days=30),renovacao=True,mp='702')
    rid=confirm_refund(env,pid)
    assert c.post(f'/admin/reembolsos/{rid}/bloquear-acesso?confirmacao_bloqueio=true').status_code==200
    student(main)
    course=c.get('/me/cursos').json()[0]
    ct=next(x for x in course['contratacoes'] if x['id']==cid)
    assert ct['renovacao_disponivel'] is (not future)
    r=c.post('/checkout/mercadopago',json={'tempo_acesso_id':1,'tipo_compra':'RENOVACAO','contratacao_id':cid})
    if future:
        assert r.status_code==409,r.text
        with f() as db:
            assert da.contrato_vigente(db,db.get(m.ContratacaoCurso,cid),original_end+timedelta(days=1))
        return
    assert r.status_code==200,r.text
    new_pid=r.json()['pagamento_id']
    with f() as db:
        assert db.get(m.Pagamento,new_pid).vencimento_original==T0+timedelta(days=5)
        old_periods=[(p.id,p.data_inicio,p.data_fim) for p in db.query(m.PeriodoAcessoPagamento)]
    response=Mock(status_code=200)
    response.json.return_value={'id':'703','status':'approved','payment_method_id':'credit_card',
        'date_approved':T0.isoformat()+'Z','transaction_amount':49.90,'currency_id':'BRL',
        'external_reference':referencia_simulada(f,new_pid),'collector_id':123456,'live_mode':True}
    get.return_value=response
    r=c.post('/pagamentos/confirmar',json={'payment_id':'703','curso_id':1})
    assert r.status_code==200,r.text
    with f() as db:
        ct=db.get(m.ContratacaoCurso,cid)
        assert ct.origem=='ADMIN'
        assert ct.data_fim>=original_end
        assert db.get(m.Pagamento,new_pid).contratacao_id==cid
        for ident,start,end in old_periods:
            p=db.get(m.PeriodoAcessoPagamento,ident)
            assert (p.data_inicio,p.data_fim)==(start,end)
        if future:assert da.contrato_vigente(db,ct,original_end+timedelta(days=1))
        # O novo período também pode ser bloqueado sem perder o histórico antigo.
        da.conferir_historico(db,db.get(m.Pagamento,new_pid))
    assert state(env,cid)['study_allowed']

@pytest.mark.parametrize('origin', ['ADMIN','PAGAMENTO'])
@pytest.mark.parametrize('channel', ['confirmacao','webhook','revalidacao'])
def test_replacement_renewal_preserves_other_periods_and_can_be_blocked(env, origin, channel):
    from unittest.mock import patch
    main,c,f,_,get=env
    first,cid=setup_payment(env,origin)
    if origin=='ADMIN':
        returned=first
    else:
        with f() as db:
            end=db.get(m.ContratacaoCurso,cid).data_fim
        Clock.at=end-timedelta(days=5)
        student(main)
        r=c.post('/checkout/mercadopago',json={'tempo_acesso_id':1,'tipo_compra':'RENOVACAO','contratacao_id':cid})
        assert r.status_code==200,r.text
        returned=r.json()['pagamento_id']
        get.return_value=Mock(status_code=200)
        get.return_value.json.return_value={'id':'702','status':'approved','payment_method_id':'credit_card',
            'date_approved':Clock.at.isoformat()+'Z','transaction_amount':49.90,'currency_id':'BRL',
            'external_reference':referencia_simulada(f,returned),'collector_id':123456,'live_mode':True}
        assert c.post('/pagamentos/confirmar',json={'payment_id':'702','curso_id':1}).status_code==200
    rid=confirm_refund(env,returned)
    assert c.post(f'/admin/reembolsos/{rid}/bloquear-acesso?confirmacao_bloqueio=true').status_code==200
    with f() as db:
        nominal=db.get(m.ContratacaoCurso,cid).data_fim
        deadline=da.vencimento_renovacao(db,db.get(m.ContratacaoCurso,cid),Clock.at)
    student(main)
    r=c.post('/checkout/mercadopago',json={'tempo_acesso_id':1,'tipo_compra':'RENOVACAO','contratacao_id':cid})
    assert r.status_code==200,r.text
    pid=r.json()['pagamento_id']
    get.return_value=Mock(status_code=200)
    get.return_value.json.return_value={'id':'703','status':'approved','payment_method_id':'credit_card',
        'date_approved':Clock.at.isoformat()+'Z','transaction_amount':49.90,'currency_id':'BRL',
        'external_reference':referencia_simulada(f,pid),'collector_id':123456,'live_mode':True}
    if channel=='confirmacao':
        r=c.post('/pagamentos/confirmar',json={'payment_id':'703','curso_id':1})
    elif channel=='webhook':
        with patch.object(main,'validar_assinatura_mercadopago',return_value=True):
            r=c.post('/webhooks/mercadopago?data.id=703',json={'type':'payment','id':901,'data':{'id':703}})
        assert r.json()['processado'],r.text
    else:
        admin(main)
        r=c.post('/admin/pagamentos/revalidar',json={'mp_payment_id':'703'})
    assert r.status_code==200,r.text
    with f() as db:
        ct=db.get(m.ContratacaoCurso,cid)
        assert ct.origem==origin and ct.data_fim==nominal
        paid=db.query(m.PeriodoAcessoPagamento).filter_by(pagamento_id=pid).one()
        assert paid.data_inicio==deadline
        da.conferir_historico(db,db.get(m.Pagamento,pid))
        assert db.query(m.ProgressoAula).filter_by(contratacao_id=cid).count()==1
    # Bloquear a reposição deve preservar o direito original ainda vigente.
    replacement_refund=confirm_refund(env,pid)
    assert c.post(f'/admin/reembolsos/{replacement_refund}/bloquear-acesso?confirmacao_bloqueio=true').status_code==200
    assert state(env,cid)['study_allowed']
    Clock.at=deadline+timedelta(seconds=1)
    assert not state(env,cid)['study_allowed']


def test_renewal_boundary_after_manual_block_is_exactly_fifteen_days(env):
    main,c,f,_,_=env
    pid,cid=setup_payment(env,'ADMIN')
    # Concessão original legítima com 15 dias + 1 segundo restantes.
    with f() as db:
        grant=db.query(m.ConcessaoAcessoAdmin).one()
        grant.data_fim=T0+timedelta(days=15,seconds=1)
        db.commit()
    rid=confirm_refund(env,pid)
    assert c.post(f'/admin/reembolsos/{rid}/bloquear-acesso?confirmacao_bloqueio=true').status_code==200
    student(main)
    payload={'tempo_acesso_id':1,'tipo_compra':'RENOVACAO','contratacao_id':cid}
    assert c.post('/checkout/mercadopago',json=payload).status_code==409
    Clock.at+=timedelta(seconds=1)
    assert c.post('/checkout/mercadopago',json=payload).status_code==200

@pytest.mark.parametrize('future', [False, True])
def test_official_chargeback_admin_paid_renewal_to_manual_block(env, future):
    from unittest.mock import patch
    main,c,f,_,_=env
    pid,cid=setup_payment(env,'ADMIN')
    with f() as db:
        end=db.get(m.ContratacaoCurso,cid).data_fim
        if future:
            compra(db,contrato=db.get(m.ContratacaoCurso,cid),inicio=end,
                fim=end+timedelta(days=30),renovacao=True,mp='702')
    def canonical(url,**kw):
        r=Mock(status_code=200)
        r.json.return_value=({'id':123456} if url.endswith('/users/me') else {'id':'999','payments':[701],'currency':'BRL','amount':49.90}
            if '/chargebacks/' in url else {'id':701,'status':'charged_back','transaction_amount':49.90,'collector_id':123456,
                'currency_id':'BRL','external_reference':referencia_simulada(f,pid),'collector_id':123456,'live_mode':True})
        return r
    with patch.object(main,'validar_assinatura_mercadopago',return_value=True), \
            patch('app.contestacoes.requests.get',side_effect=canonical):
        r=c.post('/webhooks/mercadopago?data.id=999&type=topic_chargebacks_wh',
            json={'id':1,'type':'topic_chargebacks_wh','data':{'id':999,'payment_id':666}})
    assert r.status_code==200 and r.json()['processado'],r.text
    with f() as db:
        case=db.query(m.ContestacaoPagamento).one()
        ident=case.id
        assert case.devolucao_confirmada_em is None and case.bloqueio_executado_em is None
        assert db.get(m.ContratacaoCurso,cid).origem=='ADMIN'
    assert state(env,cid)['study_allowed']
    admin(main)
    assert bloquear(c,ident).status_code==409
    assert confirmar(c,ident).status_code==200
    assert state(env,cid)['study_allowed']
    admin(main)
    assert bloquear(c,ident).status_code==200
    assert state(env,cid)['study_allowed']  # concessão original permanece
    Clock.at=T0+timedelta(days=6)
    assert not state(env,cid)['study_allowed']
    Clock.at=end+timedelta(days=1)
    assert state(env,cid)['study_allowed'] is future
    with f() as db:
        assert db.get(m.ContratacaoCurso,cid).origem=='ADMIN'
        assert db.query(m.ProgressoAula).filter_by(contratacao_id=cid).count()==1
        assert db.query(m.PeriodoAcessoPagamento).count()==(2 if future else 1)


def test_nova_compra_orienta_renovacao_no_prazo_efetivo(env):
    main,c,f,_,_=env
    _,cid=setup_payment(env,'PAGAMENTO')
    with f() as db:
        ct=db.get(m.ContratacaoCurso,cid)
        end=ct.data_fim
        pid,_=compra(db,contrato=ct,inicio=end,fim=end+timedelta(days=120),renovacao=True,mp='702')
        Clock.at=end-timedelta(days=5)
        db.get(m.Pagamento,pid).aprovado_em=Clock.at
        db.commit()
    rid=confirm_refund(env,pid)
    assert c.post(f'/admin/reembolsos/{rid}/bloquear-acesso?confirmacao_bloqueio=true').status_code==200
    student(main)
    r=c.post('/checkout/mercadopago',json={'tempo_acesso_id':1})
    assert r.status_code==409
    assert isinstance(r.json()['detail'],dict),r.text
    assert r.json()['detail']['codigo']=='USE_RENOVACAO',r.text
