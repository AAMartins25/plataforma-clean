from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from datetime import datetime
from dateutil.relativedelta import relativedelta
from app.models import PeriodoAcessoPagamento
import pytest
from fastapi import HTTPException

from app.main import confirmar_pagamento


def test_rejeita_pagamento_de_outro_usuario():
    db = MagicMock()
    usuario = SimpleNamespace(id=87)

    resposta_mp = MagicMock()
    resposta_mp.status_code = 200
    resposta_mp.json.return_value = {
        "status": "approved",
        "external_reference": "user:99|curso:1|tempo:1|pagamento:155",
        "transaction_amount": 49.90,
        "currency_id": "BRL",
    }

    with (
        patch("app.main.requests.get", return_value=resposta_mp),
        patch("app.main.mp_headers", return_value={}),
    ):
        with pytest.raises(HTTPException) as erro:
            confirmar_pagamento(
                payload={"payment_id": "mp_teste_123", "curso_id": 1},
                db=db,
                user=usuario,
            )

    assert erro.value.status_code == 403
    db.commit.assert_not_called()
    db.execute.assert_not_called()


def test_rejeita_pagamento_com_valor_divergente():
    db = MagicMock()
    usuario = SimpleNamespace(id=87)

    pagamento = SimpleNamespace(
        id=155,
        usuario_id=87,
        curso_id=1,
        valor_cents=4990,
        mp_payment_id=None,
        aprovado_em=None,
        tempo_acesso_id=1
    )

    db.query.return_value.filter.return_value.first.return_value = pagamento

    resposta_mp = MagicMock()
    resposta_mp.status_code = 200
    resposta_mp.json.return_value = {
        "status": "approved",
        "external_reference": "user:87|curso:1|tempo:1|pagamento:155",
        "transaction_amount": 39.90,
        "currency_id": "BRL",
    }

    with (
        patch("app.main.requests.get", return_value=resposta_mp),
        patch("app.main.mp_headers", return_value={}),
    ):
        with pytest.raises(HTTPException) as erro:
            confirmar_pagamento(
                payload={"payment_id": "mp_teste_456", "curso_id": 1},
                db=db,
                user=usuario,
            )

    assert erro.value.status_code == 409
    assert pagamento.aprovado_em is None
    db.commit.assert_not_called()
    db.execute.assert_not_called()

def test_pagamento_valido_libera_acesso():
    db = MagicMock()
    usuario = SimpleNamespace(id=87)

    pagamento = SimpleNamespace(
        id=155,
        usuario_id=87,
        curso_id=1,
        tempo_acesso_id=1,
        valor_cents=4990,
        mp_payment_id=None,
        aprovado_em=None,
        status="PENDENTE",
        atualizado_em=None,
    )

    db.query.return_value.filter.return_value.first.side_effect = [
        pagamento,
        SimpleNamespace(meses=4),
    ]

    resposta_mp = MagicMock()
    resposta_mp.status_code = 200
    resposta_mp.json.return_value = {
        "status": "approved",
        "external_reference": "user:87|curso:1|tempo:1|pagamento:155",
        "transaction_amount": 49.90,
        "currency_id": "BRL",
    }

    with (
        patch("app.main.requests.get", return_value=resposta_mp),
        patch("app.main.mp_headers", return_value={}),
    ):
        resultado = confirmar_pagamento(
            payload={"payment_id": "mp_teste_789", "curso_id": 1},
            db=db,
            user=usuario,
        )

    assert resultado["status"] == "APPROVED"
    assert resultado["liberou_acesso"] is True
    assert pagamento.mp_payment_id == "mp_teste_789"
    assert pagamento.aprovado_em is not None

    db.add.assert_called_once()

    periodo = db.add.call_args.args[0]

    assert isinstance(periodo, PeriodoAcessoPagamento)
    assert periodo.pagamento_id == 155
    assert periodo.usuario_id == 87
    assert periodo.curso_id == 1
    assert periodo.data_fim == (
        periodo.data_inicio + relativedelta(months=4)
    )

    db.execute.assert_called_once()
    assert "INSERT INTO acessos_curso" in str(
        db.execute.call_args.args[0]
    )
    db.commit.assert_called_once()

def test_falha_na_concessao_nao_confirma_pagamento():
    db = MagicMock()
    usuario = SimpleNamespace(id=87)

    pagamento = SimpleNamespace(
        id=155,
        usuario_id=87,
        curso_id=1,
        tempo_acesso_id=1,
        valor_cents=4990,
        mp_payment_id=None,
        aprovado_em=None,
        status="PENDENTE",
        atualizado_em=None,
    )

    db.query.return_value.filter.return_value.first.side_effect = [
        pagamento,
        SimpleNamespace(meses=4),
    ]

    db.execute.side_effect = RuntimeError(
        "Falha simulada ao gravar o acesso"
    )

    resposta_mp = MagicMock()
    resposta_mp.status_code = 200
    resposta_mp.json.return_value = {
        "status": "approved",
        "external_reference": "user:87|curso:1|tempo:1|pagamento:155",
        "transaction_amount": 49.90,
        "currency_id": "BRL",
    }

    with (
        patch("app.main.requests.get", return_value=resposta_mp),
        patch("app.main.mp_headers", return_value={}),
    ):
        with pytest.raises(
            RuntimeError,
            match="Falha simulada"
        ):
            confirmar_pagamento(
                payload={
                    "payment_id": "mp_teste_falha",
                    "curso_id": 1,
                },
                db=db,
                user=usuario,
            )

    db.commit.assert_not_called()
    db.execute.assert_called_once()
    db.rollback.assert_called_once()

def test_rejeita_pagamento_com_periodo_divergente():
    db = MagicMock()
    usuario = SimpleNamespace(id=87)

    pagamento = SimpleNamespace(
        id=155,
        usuario_id=87,
        curso_id=1,
        tempo_acesso_id=1,
        valor_cents=4990,
        mp_payment_id=None,
        aprovado_em=None,
        status="PENDENTE",
    )

    db.query.return_value.filter.return_value.first.return_value = pagamento

    resposta_mp = MagicMock()
    resposta_mp.status_code = 200
    resposta_mp.json.return_value = {
        "status": "approved",
        "external_reference": "user:87|curso:1|tempo:2|pagamento:155",
        "transaction_amount": 49.90,
        "currency_id": "BRL",
    }

    with (
        patch("app.main.requests.get", return_value=resposta_mp),
        patch("app.main.mp_headers", return_value={}),
    ):
        with pytest.raises(HTTPException) as erro:
            confirmar_pagamento(
                payload={"payment_id": "mp_teste_periodo", "curso_id": 1},
                db=db,
                user=usuario,
            )

    assert erro.value.status_code == 409
    assert pagamento.status == "PENDENTE"
    assert pagamento.mp_payment_id is None
    assert pagamento.aprovado_em is None

    db.execute.assert_not_called()
    db.commit.assert_not_called()

@pytest.mark.parametrize("status_mp", ["pending", "rejected"])
def test_pagamento_aprovado_nao_regride(status_mp):
    db = MagicMock()
    usuario = SimpleNamespace(id=87)

    data_aprovacao = datetime(2026, 9, 23, 15, 0, 0)

    pagamento = SimpleNamespace(
        id=155,
        usuario_id=87,
        curso_id=1,
        tempo_acesso_id=1,
        valor_cents=4990,
        mp_payment_id="mp_teste_aprovado",
        aprovado_em=data_aprovacao,
        status="APPROVED",
        atualizado_em=data_aprovacao,
    )

    db.query.return_value.filter.return_value.first.return_value = pagamento

    resposta_mp = MagicMock()
    resposta_mp.status_code = 200
    resposta_mp.json.return_value = {
        "status": status_mp,
        "external_reference": "user:87|curso:1|tempo:1|pagamento:155",
        "transaction_amount": 49.90,
        "currency_id": "BRL",
    }

    with (
        patch("app.main.requests.get", return_value=resposta_mp),
        patch("app.main.mp_headers", return_value={}),
    ):
        resultado = confirmar_pagamento(
            payload={
                "payment_id": "mp_teste_aprovado",
                "curso_id": 1,
            },
            db=db,
            user=usuario,
        )

    assert resultado["status"] == "APPROVED"
    assert resultado["liberou_acesso"] is False
    assert pagamento.status == "APPROVED"
    assert pagamento.aprovado_em == data_aprovacao

    db.execute.assert_not_called()
    db.commit.assert_not_called()