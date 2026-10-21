"""Regressão administrativa com sessão isolada e API financeira simulada."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from app import models as m, schemas
from test_compras_fluxo import ambiente_compra, motor
from test_reembolso_manual_fluxo import duplicata, admin, registrar


@pytest.mark.parametrize('acao,status',[('aprovar','REFUND_IN_PROCESS'),('recusar','REFUND_DENIED')])
def test_decisao_admin_preserva_acesso(ambiente_compra,acao,status):
    main,client,factory,_,_=ambiente_compra;pid=duplicata(ambiente_compra)
    assert client.post(f'/me/reembolso/{pid}',json={}).status_code==200
    admin(ambiente_compra)
    with factory() as db:
        a=db.query(m.AcessoCurso).one();antes=(a.ativo,a.data_fim)
    assert client.post(f'/admin/reembolsos/{pid}/{acao}',json={}).status_code==200
    with factory() as db:
        assert db.get(m.Pagamento,pid).status==status
        a=db.query(m.AcessoCurso).one();assert (a.ativo,a.data_fim)==antes
    assert client.post(f'/admin/reembolsos/{pid}/{acao}',json={}).status_code==400


@pytest.mark.parametrize('acao',['aprovar','recusar','pix-manual'])
def test_usuario_comum_nao_pode_decidir_ou_registrar(ambiente_compra,acao):
    pid=duplicata(ambiente_compra)
    r=ambiente_compra[1].post(f'/admin/reembolsos/{pid}/{acao}',json={'valor_cents':4990,'referencia_comprovante':'teste'})
    assert r.status_code==403


@pytest.mark.parametrize('acao',['aprovar','recusar','pix-manual'])
def test_nao_permite_decidir_sem_solicitacao(ambiente_compra,acao):
    pid=duplicata(ambiente_compra);admin(ambiente_compra)
    r=ambiente_compra[1].post(f'/admin/reembolsos/{pid}/{acao}',json={'valor_cents':4990,'referencia_comprovante':'teste'})
    assert r.status_code==400


def aprovado(ambiente):
    pid=duplicata(ambiente)
    ambiente[1].post(f'/me/reembolso/{pid}',json={});admin(ambiente)
    ambiente[1].post(f'/admin/reembolsos/{pid}/aprovar',json={})
    return pid


@pytest.mark.parametrize('payload',[{'valor_cents':100,'referencia_comprovante':'teste'},
    {'valor_cents':4990,'referencia_comprovante':' '},{'valor_cents':0,'referencia_comprovante':'teste'}])
def test_pix_manual_rejeita_valor_ou_comprovante_invalido(ambiente_compra,payload):
    pid=aprovado(ambiente_compra)
    assert ambiente_compra[1].post(f'/admin/reembolsos/{pid}/pix-manual',json=payload).status_code in (400,422)
    with ambiente_compra[2]() as db:assert db.query(m.ReembolsoFinanceiro).count()==0


def test_pix_manual_trata_duplicidade_no_banco(ambiente_compra):
    main,_,factory,_,_=ambiente_compra;pid=aprovado(ambiente_compra)
    with factory() as db:
        with patch.object(db,'commit',side_effect=IntegrityError('INSERT',{},Exception('duplicidade'))):
            with pytest.raises(HTTPException) as erro:
                main.registrar_reembolso_pix_manual(pid,schemas.ReembolsoPixManualCreate(valor_cents=4990,referencia_comprovante='teste'),db,SimpleNamespace(id=2,is_admin=True))
        assert erro.value.status_code==409
    with factory() as db:assert db.query(m.ReembolsoFinanceiro).count()==0


def test_falha_commit_reembolso_executa_rollback(ambiente_compra):
    main,client,factory,_,_=ambiente_compra;pid=aprovado(ambiente_compra)
    rid=registrar(client,pid).json()['reembolso_id']
    with factory() as db:
        with patch.object(db,'commit',side_effect=RuntimeError('falha simulada')):
            with pytest.raises(RuntimeError):main.confirmar_reembolso_pix_manual(rid,True,db,SimpleNamespace(id=2,is_admin=True))
    with factory() as db:
        assert db.get(m.ReembolsoFinanceiro,rid).status=='PENDENTE'
        assert db.get(m.ReembolsoFinanceiro,rid).confirmado_por is None
        assert db.get(m.Pagamento,pid).status=='REFUND_IN_PROCESS'


def test_reembolso_normal_mantem_recalculo_existente(ambiente_compra):
    main,client,factory,_,_=ambiente_compra;duplicata(ambiente_compra)
    with factory() as db:pid=db.query(m.Pagamento).filter_by(mp_payment_id='101').one().id
    assert client.post(f'/me/reembolso/{pid}',json={}).status_code==200
    admin(ambiente_compra)
    client.post(f'/admin/reembolsos/{pid}/aprovar',json={})
    rid=registrar(client,pid).json()['reembolso_id']
    with patch.object(main,'recalcular_acesso_apos_reembolso',wraps=main.recalcular_acesso_apos_reembolso) as recalcular:
        r=client.post(f'/admin/reembolsos/{rid}/pix-manual/confirmar?confirmacao_extrato=true',json={})
    assert r.status_code==200,r.text
    recalcular.assert_called_once()
    # A demonstração concedida no fixture continua sendo um direito independente.
    with factory() as db:
        assert db.query(m.AcessoCurso).one().ativo
        assert db.query(m.ContratacaoCurso).count()==1
        assert db.query(m.PeriodoAcessoPagamento).count()==1
