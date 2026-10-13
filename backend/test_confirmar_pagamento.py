"""Regressões de confirmação com banco isolado e API simulada."""
from unittest.mock import patch
import pytest
from app import models as m
from test_compras_fluxo import ambiente_compra, motor
from test_transacoes_mp import preparar, confirmar

@pytest.mark.parametrize('campo,valor,codigo', [
    ('transaction_amount', 39.90, 409), ('currency_id', 'USD', 409),
    ('external_reference', 'user:99|curso:1|tempo:1|pagamento:{pid}', 403),
    ('external_reference', 'user:1|curso:1|tempo:2|pagamento:{pid}', 409),
])
def test_rejeita_pagamento_incompativel(ambiente_compra,campo,valor,codigo):
    pid,_,tx,_=preparar(ambiente_compra, legado=True)
    tx['101'][campo]=valor.format(pid=pid) if isinstance(valor,str) else valor
    assert confirmar(ambiente_compra,101).status_code==codigo
    with ambiente_compra[2]() as db:
        assert db.query(m.ContratacaoCurso).count()==0
        assert db.get(m.Pagamento,pid).mp_payment_id is None

def test_pagamento_valido_libera_acesso(ambiente_compra):
    _,dados,tx,_=preparar(ambiente_compra)
    tx['101']=dados(101,'approved')
    assert confirmar(ambiente_compra,101).json()['liberou_acesso']
    with ambiente_compra[2]() as db:
        assert db.query(m.PeriodoAcessoPagamento).count()==1

@pytest.mark.parametrize('status',['pending','rejected'])
def test_pagamento_aprovado_nao_regride(ambiente_compra,status):
    pid,dados,tx,_=preparar(ambiente_compra)
    tx['101']=dados(101,'approved');confirmar(ambiente_compra,101)
    tx['101']=dados(101,status)
    assert confirmar(ambiente_compra,101).json()['status']=='APPROVED'
    with ambiente_compra[2]() as db:
        assert db.get(m.Pagamento,pid).status=='APPROVED'
        assert db.query(m.PeriodoAcessoPagamento).count()==1

def test_falha_na_concessao_nao_confirma_pagamento(ambiente_compra):
    pid,dados,tx,_=preparar(ambiente_compra)
    tx['101']=dados(101,'approved')
    with patch.object(ambiente_compra[0],'registrar_contratacao',side_effect=RuntimeError('Falha simulada')):
        with pytest.raises(RuntimeError): confirmar(ambiente_compra,101)
    with ambiente_compra[2]() as db:
        assert db.get(m.Pagamento,pid).mp_payment_id is None
        assert db.get(m.Pagamento,pid).aprovado_em is None
        assert db.query(m.ContratacaoCurso).count()==0
