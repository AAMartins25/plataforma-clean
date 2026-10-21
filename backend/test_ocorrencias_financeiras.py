"""Ocorrências financeiras sem concessão, com persistência isolada."""
from datetime import timedelta
from unittest.mock import patch
import pytest
from app import models as m
from test_compras_fluxo import ambiente_compra,motor
from test_transacoes_mp import preparar,confirmar
from test_webhook_mercadopago import notificar

@pytest.mark.parametrize('tipo',['COBRANCA_DUPLICADA','APROVACAO_FORA_PRAZO'])
def test_ocorrencia_e_repeticoes_nao_prorrogam_acesso(ambiente_compra,tipo):
    pid,dados,tx,_=preparar(ambiente_compra,renovacao=True)
    with ambiente_compra[2]() as db:
        raiz=db.get(m.Pagamento,pid);cid=raiz.contratacao_id
        fim=db.get(m.ContratacaoCurso,cid).data_fim
        if tipo=='COBRANCA_DUPLICADA':db.get(m.OportunidadeCompra,raiz.oportunidade_id).concluida_em=fim-timedelta(days=1)
        db.commit()
    tx['101']=dados(101,'approved')
    if tipo=='APROVACAO_FORA_PRAZO':tx['101']['date_approved']=(fim+timedelta(seconds=1)).isoformat()+'Z'
    with patch.object(ambiente_compra[0],'validar_assinatura_mercadopago',return_value=True):
        for _ in range(2):
            r=notificar(ambiente_compra)
            assert r.status_code==200,r.text
            assert r.json()['ocorrencia_financeira']==tipo
    r=confirmar(ambiente_compra,101)
    assert r.json()['ocorrencia_financeira']==tipo and not r.json()['liberou_acesso']
    with ambiente_compra[2]() as db:
        assert db.get(m.ContratacaoCurso,cid).data_fim==fim
        assert db.query(m.PeriodoAcessoPagamento).count()==0
        assert db.get(m.Pagamento,pid).status=='APPROVED'
