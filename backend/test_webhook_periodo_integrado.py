import os

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from dateutil.relativedelta import relativedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.main import webhook_mercadopago


DATABASE_URL_LOCAL = os.environ["DATABASE_URL"]


def test_webhook_registra_periodo_integrado():
    engine = create_engine(DATABASE_URL_LOCAL)

    request = MagicMock()
    request.query_params = {
        "type": "payment",
        "data.id": "mp_ficticio_periodo_002",
    }
    request.json = AsyncMock(
        return_value={
            "type": "payment",
            "data": {"id": "mp_ficticio_periodo_002"},
        }
    )

    resposta_mp = MagicMock()
    resposta_mp.status_code = 200
    resposta_mp.json.return_value = {
        "status": "approved",
        "external_reference": (
            "user:2|curso:1|tempo:1|pagamento:2"
        ),
        "transaction_amount": 49.90,
        "currency_id": "BRL",
    }

    with engine.connect() as conexao:
        transacao = conexao.begin()

        try:
            with Session(
                bind=conexao,
                join_transaction_mode="create_savepoint",
            ) as db:
                with (
                    patch(
                        "app.main.validar_assinatura_mercadopago",
                        return_value=True,
                    ),
                    patch(
                        "app.main.requests.get",
                        return_value=resposta_mp,
                    ),
                    patch(
                        "app.main.mp_headers",
                        return_value={},
                    ),
                ):
                    resultado = asyncio.run(
                        webhook_mercadopago(
                            request=request,
                            db=db,
                        )
                    )

                assert resultado["status"] == "APPROVED"

            periodo = conexao.execute(text("""
                SELECT
                    pagamento_id,
                    usuario_id,
                    curso_id,
                    data_inicio,
                    data_fim
                FROM periodos_acesso_pagamento
                WHERE pagamento_id = 2
            """)).mappings().one()

            assert periodo["usuario_id"] == 2
            assert periodo["curso_id"] == 1
            assert periodo["data_fim"] == (
                periodo["data_inicio"]
                + relativedelta(months=4)
            )

            status = conexao.execute(text("""
                SELECT status
                FROM pagamentos
                WHERE id = 2
            """)).scalar_one()

            assert status == "APPROVED"

        finally:
            transacao.rollback()

    with engine.connect() as conexao:
        status_original = conexao.execute(text("""
            SELECT status
            FROM pagamentos
            WHERE id = 2
        """)).scalar_one()

        quantidade = conexao.execute(text("""
            SELECT COUNT(*)
            FROM periodos_acesso_pagamento
            WHERE pagamento_id = 2
        """)).scalar_one()

    assert status_original == "PENDENTE"
    assert quantidade == 0

    engine.dispose()