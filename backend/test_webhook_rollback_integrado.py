import os

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import webhook_mercadopago


DATABASE_URL_LOCAL = os.environ["DATABASE_URL"]


def test_webhook_rollback_integrado():
    engine = create_engine(DATABASE_URL_LOCAL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        request = MagicMock()
        request.query_params = {
            "type": "payment",
            "data.id": "mp_teste_rollback_integrado",
        }
        request.json = AsyncMock(
            return_value={
                "type": "payment",
                "data": {"id": "mp_teste_rollback_integrado"},
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

        execute_original = db.execute

        def executar_com_falha(statement, *args, **kwargs):
            if "INSERT INTO acessos_curso" in str(statement):
                raise RuntimeError(
                    "Falha simulada na concessão do acesso"
                )

            return execute_original(statement, *args, **kwargs)

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
            patch.object(
                db,
                "execute",
                side_effect=executar_com_falha,
            ),
        ):
            with pytest.raises(
                RuntimeError,
                match="Falha simulada",
            ):
                asyncio.run(
                    webhook_mercadopago(
                        request=request,
                        db=db,
                    )
                )

    finally:
        db.close()
        engine.dispose()
