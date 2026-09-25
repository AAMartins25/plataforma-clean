from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
import pytest
from fastapi import HTTPException

from app.main import webhook_mercadopago


def test_webhook_rejeita_valor_divergente():
    db = MagicMock()

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

    request = MagicMock()
    request.query_params = {
        "type": "payment",
        "data.id": "mp_teste_webhook_001",
    }
    request.json = AsyncMock(
        return_value={
            "type": "payment",
            "data": {"id": "mp_teste_webhook_001"},
        }
    )

    resposta_mp = MagicMock()
    resposta_mp.status_code = 200
    resposta_mp.json.return_value = {
        "status": "approved",
        "external_reference": "user:87|curso:1|tempo:1|pagamento:155",
        "transaction_amount": 39.90,
        "currency_id": "BRL",
    }

    with (
        patch(
            "app.main.validar_assinatura_mercadopago",
            return_value=True,
        ),
        patch("app.main.requests.get", return_value=resposta_mp),
        patch("app.main.mp_headers", return_value={}),
    ):
        with pytest.raises(HTTPException) as erro:
            asyncio.run(webhook_mercadopago(request=request, db=db))

    assert erro.value.status_code == 409
    assert pagamento.status == "PENDENTE"
    assert pagamento.aprovado_em is None

    db.execute.assert_not_called()
    db.commit.assert_not_called()


def test_webhook_rejeita_moeda_divergente():
    db = MagicMock()

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

    request = MagicMock()
    request.query_params = {
        "type": "payment",
        "data.id": "mp_teste_moeda",
    }
    request.json = AsyncMock(
        return_value={
            "type": "payment",
            "data": {"id": "mp_teste_moeda"},
        }
    )

    resposta_mp = MagicMock()
    resposta_mp.status_code = 200
    resposta_mp.json.return_value = {
        "status": "approved",
        "external_reference": "user:87|curso:1|tempo:1|pagamento:155",
        "transaction_amount": 49.90,
        "currency_id": "USD",
    }

    with (
        patch(
            "app.main.validar_assinatura_mercadopago",
            return_value=True,
        ),
        patch("app.main.requests.get", return_value=resposta_mp),
        patch("app.main.mp_headers", return_value={}),
    ):
        with pytest.raises(HTTPException) as erro:
            asyncio.run(webhook_mercadopago(request=request, db=db))

    assert erro.value.status_code == 409
    assert pagamento.status == "PENDENTE"
    assert pagamento.aprovado_em is None

    db.execute.assert_not_called()
    db.commit.assert_not_called()


def test_webhook_rejeita_periodo_divergente():
    db = MagicMock()

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

    request = MagicMock()
    request.query_params = {
        "type": "payment",
        "data.id": "mp_teste_periodo",
    }
    request.json = AsyncMock(
        return_value={
            "type": "payment",
            "data": {"id": "mp_teste_periodo"},
        }
    )

    resposta_mp = MagicMock()
    resposta_mp.status_code = 200
    resposta_mp.json.return_value = {
        "status": "approved",
        "external_reference": "user:87|curso:1|tempo:2|pagamento:155",
        "transaction_amount": 49.90,
        "currency_id": "BRL",
    }

    with (
        patch(
            "app.main.validar_assinatura_mercadopago",
            return_value=True,
        ),
        patch("app.main.requests.get", return_value=resposta_mp),
        patch("app.main.mp_headers", return_value={}),
    ):
        with pytest.raises(HTTPException) as erro:
            asyncio.run(webhook_mercadopago(request=request, db=db))

    assert erro.value.status_code == 409
    assert pagamento.status == "PENDENTE"
    assert pagamento.mp_payment_id is None
    assert pagamento.aprovado_em is None

    db.execute.assert_not_called()
    db.commit.assert_not_called()


def test_webhook_aprova_pagamento_e_libera_acesso():
    db = MagicMock()

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

    request = MagicMock()
    request.query_params = {
        "type": "payment",
        "data.id": "mp_teste_webhook_aprovado",
    }
    request.json = AsyncMock(
        return_value={
            "type": "payment",
            "data": {"id": "mp_teste_webhook_aprovado"},
        }
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
        patch(
            "app.main.validar_assinatura_mercadopago",
            return_value=True,
        ),
        patch("app.main.requests.get", return_value=resposta_mp),
        patch("app.main.mp_headers", return_value={}),
    ):
        resultado = asyncio.run(
            webhook_mercadopago(request=request, db=db)
        )

    assert resultado["ok"] is True
    assert resultado["status"] == "APPROVED"

    assert pagamento.status == "APPROVED"
    assert pagamento.mp_payment_id == "mp_teste_webhook_aprovado"
    assert pagamento.aprovado_em is not None

    db.execute.assert_called_once()
    assert "INSERT INTO acessos_curso" in str(
        db.execute.call_args.args[0]
    )
    db.commit.assert_called_once()


def test_webhook_falha_na_concessao_desfaz_pagamento():
    db = MagicMock()

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

    request = MagicMock()
    request.query_params = {
        "type": "payment",
        "data.id": "mp_teste_webhook_rollback",
    }
    request.json = AsyncMock(
        return_value={
            "type": "payment",
            "data": {"id": "mp_teste_webhook_rollback"},
        }
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
        patch(
            "app.main.validar_assinatura_mercadopago",
            return_value=True,
        ),
        patch("app.main.requests.get", return_value=resposta_mp),
        patch("app.main.mp_headers", return_value={}),
    ):
        with pytest.raises(
            RuntimeError,
            match="Falha simulada"
        ):
            asyncio.run(
                webhook_mercadopago(request=request, db=db)
            )

    db.execute.assert_called_once()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_webhook_aprovacao_repetida_nao_duplica_acesso():
    from datetime import datetime

    db = MagicMock()

    aprovacao_original = datetime(2026, 9, 23, 15, 58, 6)

    pagamento = SimpleNamespace(
        id=155,
        usuario_id=87,
        curso_id=1,
        tempo_acesso_id=1,
        valor_cents=4990,
        mp_payment_id="mp_teste_repetido",
        aprovado_em=aprovacao_original,
        status="APPROVED",
        atualizado_em=aprovacao_original,
    )

    db.query.return_value.filter.return_value.first.return_value = pagamento

    request = MagicMock()
    request.query_params = {
        "type": "payment",
        "data.id": "mp_teste_repetido",
    }
    request.json = AsyncMock(
        return_value={
            "type": "payment",
            "data": {"id": "mp_teste_repetido"},
        }
    )

    resposta_mp = MagicMock()
    resposta_mp.status_code = 200
    resposta_mp.json.return_value = {
        "status": "approved",
        "external_reference": (
            "user:87|curso:1|tempo:1|pagamento:155"
        ),
        "transaction_amount": 49.90,
        "currency_id": "BRL",
    }

    with (
        patch(
            "app.main.validar_assinatura_mercadopago",
            return_value=True,
        ),
        patch(
            "app.main.requests.get",
            return_value=resposta_mp,
        ),
        patch("app.main.mp_headers", return_value={}),
    ):
        resultado = asyncio.run(
            webhook_mercadopago(request=request, db=db)
        )

    assert resultado["ok"] is True
    assert resultado["status"] == "APPROVED"

    assert pagamento.status == "APPROVED"
    assert pagamento.mp_payment_id == "mp_teste_repetido"
    assert pagamento.aprovado_em == aprovacao_original

    # Não pode executar novamente a concessão de acesso.
    db.execute.assert_not_called()

    # O código atual confirma o processamento da notificação.
    db.commit.assert_called_once()


def test_webhook_ignora_pending_apos_aprovacao():
    from datetime import datetime

    db = MagicMock()
    aprovacao_original = datetime(2026, 9, 23, 15, 58, 6)

    pagamento = SimpleNamespace(
        id=155,
        usuario_id=87,
        curso_id=1,
        tempo_acesso_id=1,
        valor_cents=4990,
        mp_payment_id="mp_teste_pending_tardio",
        aprovado_em=aprovacao_original,
        status="APPROVED",
        atualizado_em=aprovacao_original,
    )

    db.query.return_value.filter.return_value.first.return_value = pagamento

    request = MagicMock()
    request.query_params = {
        "type": "payment",
        "data.id": "mp_teste_pending_tardio",
    }
    request.json = AsyncMock(
        return_value={
            "type": "payment",
            "data": {"id": "mp_teste_pending_tardio"},
        }
    )

    resposta_mp = MagicMock()
    resposta_mp.status_code = 200
    resposta_mp.json.return_value = {
        "status": "pending",
        "external_reference": (
            "user:87|curso:1|tempo:1|pagamento:155"
        ),
        "transaction_amount": 49.90,
        "currency_id": "BRL",
    }

    with (
        patch(
            "app.main.validar_assinatura_mercadopago",
            return_value=True,
        ),
        patch("app.main.requests.get", return_value=resposta_mp),
        patch("app.main.mp_headers", return_value={}),
    ):
        resultado = asyncio.run(
            webhook_mercadopago(request=request, db=db)
        )

    assert resultado["ok"] is True
    assert resultado["ignored"] is True

    assert pagamento.status == "APPROVED"
    assert pagamento.aprovado_em == aprovacao_original
    assert pagamento.mp_payment_id == "mp_teste_pending_tardio"

    db.execute.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize("status_tardio", ["pending", "rejected"])
def test_webhook_ignora_status_tardio_apos_aprovacao(
    status_tardio,
):
    from datetime import datetime

    db = MagicMock()
    aprovacao_original = datetime(2026, 9, 23, 15, 58, 6)

    pagamento = SimpleNamespace(
        id=155,
        usuario_id=87,
        curso_id=1,
        tempo_acesso_id=1,
        valor_cents=4990,
        mp_payment_id="mp_teste_status_tardio",
        aprovado_em=aprovacao_original,
        status="APPROVED",
        atualizado_em=aprovacao_original,
    )

    db.query.return_value.filter.return_value.first.return_value = pagamento

    request = MagicMock()
    request.query_params = {
        "type": "payment",
        "data.id": "mp_teste_status_tardio",
    }
    request.json = AsyncMock(
        return_value={
            "type": "payment",
            "data": {"id": "mp_teste_status_tardio"},
        }
    )

    resposta_mp = MagicMock()
    resposta_mp.status_code = 200
    resposta_mp.json.return_value = {
        "status": status_tardio,
        "external_reference": (
            "user:87|curso:1|tempo:1|pagamento:155"
        ),
        "transaction_amount": 49.90,
        "currency_id": "BRL",
    }

    with (
        patch(
            "app.main.validar_assinatura_mercadopago",
            return_value=True,
        ),
        patch("app.main.requests.get", return_value=resposta_mp),
        patch("app.main.mp_headers", return_value={}),
    ):
        resultado = asyncio.run(
            webhook_mercadopago(request=request, db=db)
        )

    assert resultado["ok"] is True
    assert resultado["ignored"] is True

    assert pagamento.status == "APPROVED"
    assert pagamento.aprovado_em == aprovacao_original
    assert pagamento.mp_payment_id == "mp_teste_status_tardio"

    db.execute.assert_not_called()
    db.commit.assert_not_called()
