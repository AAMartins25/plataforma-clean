import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.main import webhook_mercadopago


def test_segundo_pagamento_nao_prorroga_contrato():
    db = MagicMock()

    pagamento = SimpleNamespace(
        id=156,
        usuario_id=87,
        curso_id=1,
        tempo_acesso_id=1,
        valor_cents=4990,
        tipo_compra="RENOVACAO",
        vencimento_original=datetime(2026, 9, 30),
        oportunidade_id=12,
        ocorrencia_financeira=None,
        mp_payment_id=None,
        aprovado_em=None,
        status="PENDENTE",
    )

    oportunidade = SimpleNamespace(
        id=12,
        concluida_em=datetime(2026, 9, 23),
    )

    db.query.return_value.filter.return_value.with_for_update.return_value.populate_existing.return_value.first.return_value = pagamento

    request = MagicMock()
    request.query_params = {
        "type": "payment",
        "data.id": "mp_segundo_pagamento",
    }
    request.json = AsyncMock(
        return_value={
            "type": "payment",
            "data": {"id": "mp_segundo_pagamento"},
        }
    )

    resposta_mp = MagicMock()
    resposta_mp.status_code = 200
    resposta_mp.json.return_value = {
        "id": "mp_segundo_pagamento",
        "status": "approved",
        "date_approved": "2026-09-24T15:00:00Z",
        "external_reference": "user:87|curso:1|tempo:1|pagamento:156",
        "transaction_amount": 49.90,
        "currency_id": "BRL",
    }

    with (
        patch("app.main.validar_assinatura_mercadopago", return_value=True),
        patch("app.main.requests.get", return_value=resposta_mp),
        patch("app.main.mp_headers", return_value={}),
        patch(
            "app.main.bloquear_oportunidade_pagamento",
            return_value=oportunidade,
        ),
    ):
        resultado = asyncio.run(
            webhook_mercadopago(request=request, db=db)
        )

    assert resultado["liberou_acesso"] is False
    assert resultado["ocorrencia_financeira"] == "COBRANCA_DUPLICADA"
    assert pagamento.ocorrencia_financeira == "COBRANCA_DUPLICADA"
    assert pagamento.status == "APPROVED"
    assert pagamento.aprovado_em == datetime(2026, 9, 24, 15)
    db.add.assert_not_called()
    db.execute.assert_not_called()
    db.commit.assert_called_once()


def test_renovacao_aprovada_fora_do_prazo_nao_libera_acesso():
    db = MagicMock()

    pagamento = SimpleNamespace(
        id=157,
        usuario_id=87,
        curso_id=1,
        tempo_acesso_id=1,
        valor_cents=4990,
        tipo_compra="RENOVACAO",
        vencimento_original=datetime(2026, 9, 23, 15),
        oportunidade_id=13,
        ocorrencia_financeira=None,
        mp_payment_id=None,
        aprovado_em=None,
        status="PENDENTE",
    )

    db.query.return_value.filter.return_value.with_for_update.return_value.populate_existing.return_value.first.return_value = pagamento

    request = MagicMock()
    request.query_params = {
        "type": "payment",
        "data.id": "mp_fora_prazo",
    }
    request.json = AsyncMock(
        return_value={
            "type": "payment",
            "data": {"id": "mp_fora_prazo"},
        }
    )

    resposta_mp = MagicMock()
    resposta_mp.status_code = 200
    resposta_mp.json.return_value = {
        "id": "mp_fora_prazo",
        "status": "approved",
        "date_approved": "2026-09-23T15:00:01Z",
        "external_reference": "user:87|curso:1|tempo:1|pagamento:157",
        "transaction_amount": 49.90,
        "currency_id": "BRL",
    }

    with (
        patch("app.main.validar_assinatura_mercadopago", return_value=True),
        patch("app.main.requests.get", return_value=resposta_mp),
        patch("app.main.mp_headers", return_value={}),
        patch(
            "app.main.bloquear_oportunidade_pagamento",
            return_value=SimpleNamespace(
                id=13,
                concluida_em=None,
            ),
        ),
    ):
        resultado = asyncio.run(
            webhook_mercadopago(request=request, db=db)
        )

    assert resultado["liberou_acesso"] is False
    assert resultado["ocorrencia_financeira"] == "APROVACAO_FORA_PRAZO"
    assert pagamento.ocorrencia_financeira == "APROVACAO_FORA_PRAZO"
    assert pagamento.status == "APPROVED"
    assert pagamento.aprovado_em == datetime(2026, 9, 23, 15, 0, 1)
    db.add.assert_not_called()
    db.execute.assert_not_called()
    db.commit.assert_called_once()


def test_notificacao_repetida_de_cobranca_duplicada():
    db = MagicMock()

    pagamento = SimpleNamespace(
        id=156,
        usuario_id=87,
        curso_id=1,
        tempo_acesso_id=1,
        valor_cents=4990,
        tipo_compra="RENOVACAO",
        vencimento_original=datetime(2026, 9, 30),
        oportunidade_id=12,
        ocorrencia_financeira="COBRANCA_DUPLICADA",
        mp_payment_id="mp_segundo_pagamento",
        aprovado_em=datetime(2026, 9, 24, 15),
        status="APPROVED",
    )

    db.query.return_value.filter.return_value.with_for_update.return_value.populate_existing.return_value.first.return_value = pagamento

    request = MagicMock()
    request.query_params = {
        "type": "payment",
        "data.id": "mp_segundo_pagamento",
    }
    request.json = AsyncMock(
        return_value={
            "type": "payment",
            "data": {"id": "mp_segundo_pagamento"},
        }
    )

    resposta_mp = MagicMock()
    resposta_mp.status_code = 200
    resposta_mp.json.return_value = {
        "id": "mp_segundo_pagamento",
        "status": "approved",
        "date_approved": "2026-09-24T15:00:00Z",
        "external_reference": "user:87|curso:1|tempo:1|pagamento:156",
        "transaction_amount": 49.90,
        "currency_id": "BRL",
    }

    with (
        patch("app.main.validar_assinatura_mercadopago", return_value=True),
        patch("app.main.requests.get", return_value=resposta_mp),
        patch("app.main.mp_headers", return_value={}),
        patch("app.main.bloquear_oportunidade_pagamento") as bloquear,
    ):
        resultado = asyncio.run(
            webhook_mercadopago(request=request, db=db)
        )

    assert resultado["liberou_acesso"] is False
    assert resultado["ocorrencia_financeira"] == "COBRANCA_DUPLICADA"
    assert pagamento.aprovado_em == datetime(2026, 9, 24, 15)
    bloquear.assert_not_called()
    db.add.assert_not_called()
    db.execute.assert_not_called()
    db.flush.assert_not_called()
    db.commit.assert_not_called()


def test_notificacao_repetida_de_aprovacao_fora_do_prazo():
    import inspect

    codigo = inspect.getsource(
        test_notificacao_repetida_de_cobranca_duplicada
    )

    codigo = codigo.replace(
        "test_notificacao_repetida_de_cobranca_duplicada",
        "verificar_notificacao_repetida_fora_do_prazo",
        1,
    ).replace(
        '"COBRANCA_DUPLICADA"',
        '"APROVACAO_FORA_PRAZO"',
    )

    contexto = globals().copy()
    exec(codigo, contexto)
    contexto["verificar_notificacao_repetida_fora_do_prazo"]()
