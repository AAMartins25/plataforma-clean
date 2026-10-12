"""Prazo único por aprovação efetiva, com banco isolado e relógio fixo."""
from datetime import datetime, timedelta
from unittest.mock import patch
import pytest
from app import models as m
from test_compras_fluxo import ambiente_compra, motor
from test_reembolso_manual_fluxo import duplicata

AGORA=datetime(2026,10,10,12)
class Relogio(datetime):
    @classmethod
    def utcnow(cls):return AGORA

@pytest.mark.parametrize('duplicado',[False,True])
@pytest.mark.parametrize('criacao,aprovacao,status,elegivel',[
    (0,0,'APPROVED',True), (30,2,'APPROVED',True),
    (30,None,'PENDING',False), (1,1,'IN_PROCESS',False),
    (30,6,'APPROVED',True), (30,8,'APPROVED',False),
    (30,7,'APPROVED',True), (30,7+1/86400000000,'APPROVED',False),
    (0,None,'APPROVED',False), (30,-1,'APPROVED',False),
])
def test_listagem_e_solicitacao_mesma_regra(ambiente_compra,criacao,aprovacao,status,elegivel,duplicado):
    main,client,factory,_,_=ambiente_compra;pid=duplicata(ambiente_compra)
    with factory() as db:
        if not duplicado:pid=db.query(m.Pagamento).filter_by(mp_payment_id="101").one().id
        p=db.get(m.Pagamento,pid);p.criado_em=AGORA-timedelta(days=criacao)
        p.aprovado_em=AGORA-timedelta(days=aprovacao) if aprovacao is not None else None
        p.status=status;db.commit()
    with patch.object(main,'datetime',Relogio):
        lista=client.get('/me/compras/reembolso').json()
        ids={p['pagamento_id'] for p in lista['compras']} if lista['tipo']=='elegiveis' else set()
        assert (pid in ids)==elegivel
        if elegivel:
            linha=next(p for p in lista['compras'] if p['pagamento_id']==pid)
            assert linha['mp_payment_id']==('102' if duplicado else '101')
            assert linha['ocorrencia_financeira']==('COBRANCA_DUPLICADA' if duplicado else None)
            assert linha['data_limite_reembolso']==(AGORA-timedelta(days=aprovacao)+timedelta(days=7)).isoformat()+'Z'
        r=client.post(f'/me/reembolso/{pid}',json={})
        assert r.status_code==(200 if elegivel else 400),r.text
    with factory() as db:
        assert db.get(m.Pagamento,pid).status==('REFUND_REQUESTED' if elegivel else status)
        assert db.query(m.ReembolsoFinanceiro).count()==0
        assert db.query(m.PeriodoAcessoPagamento).count()==1
