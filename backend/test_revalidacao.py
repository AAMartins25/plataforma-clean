"""Revalidação com identidade real em banco isolado e MP simulado."""
from datetime import datetime,timedelta
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from app import models as m
from test_compras_fluxo import ambiente_compra,motor,contrato
from test_transacoes_mp import preparar

def revalidar(ambiente):
    with ambiente[2]() as db:
        try:
            return ambiente[0].admin_revalidar_pagamento({'mp_payment_id':'101'},db,SimpleNamespace(is_admin=True, tipo_admin="admin_geral"))
        except Exception:
            db.rollback();raise

@pytest.mark.parametrize('dias,libera',[(200,False),(1,True)])
def test_compra_vencida_ou_vigente(ambiente_compra,dias,libera):
    pid,dados,tx,_=preparar(ambiente_compra);tx['101']=dados(101,'approved')
    aprovacao=datetime.utcnow()-timedelta(days=dias)
    tx['101']['date_approved']=aprovacao.isoformat()+'Z'
    r=revalidar(ambiente_compra)
    assert r['liberou_acesso']==libera
    with ambiente_compra[2]() as db:
        assert db.query(m.PeriodoAcessoPagamento).one().data_inicio==aprovacao
        assert db.get(m.Pagamento,pid).aprovado_em==aprovacao
    assert revalidar(ambiente_compra)['liberou_acesso'] is False

@pytest.mark.parametrize('status',['REFUND_REQUESTED','REFUND_IN_PROCESS','REFUNDED'])
def test_reconciliacao_nao_sobrescreve_reembolso(ambiente_compra,status):
    pid,_,_,_=preparar(ambiente_compra)
    with ambiente_compra[2]() as db:
        db.get(m.Pagamento,pid).status=status;db.commit()
    retorno=revalidar(ambiente_compra)
    assert retorno['status']==status and not retorno['liberou_acesso']
    with ambiente_compra[2]() as db:
        assert db.get(m.Pagamento,pid).status==status
        assert db.get(m.Pagamento,pid).mp_payment_id == '101'
        assert db.get(m.Pagamento,pid).mp_status == 'PENDING'

def test_compra_antiga_nao_reduz_prazo_atual(ambiente_compra):
    _,dados,tx,_=preparar(ambiente_compra)
    tx['101']=dados(101,'approved')
    tx['101']['date_approved']=(datetime.utcnow()-timedelta(days=60)).isoformat()+'Z'
    with ambiente_compra[2]() as db:
        limite=datetime.utcnow()+timedelta(days=300)
        db.add(m.AcessoCurso(usuario_id=1,curso_id=1,ativo=True,data_inicio=datetime.utcnow(),data_fim=limite));db.commit()
    revalidar(ambiente_compra)
    with ambiente_compra[2]() as db:assert db.query(m.AcessoCurso).one().data_fim==limite

def test_revalidacao_exige_admin(ambiente_compra):
    with ambiente_compra[2]() as db:
        with pytest.raises(HTTPException) as erro:
            ambiente_compra[0].admin_revalidar_pagamento({'mp_payment_id':'101'},db,SimpleNamespace(is_admin=False))
    assert erro.value.status_code==403
