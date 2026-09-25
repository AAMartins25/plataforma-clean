import os

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.main import webhook_mercadopago


DATABASE_URL_LOCAL = os.environ["DATABASE_URL"]


def test_webhook_idempotencia_integrado():
    engine = create_engine(DATABASE_URL_LOCAL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Registra o estado original do pagamento e do acesso.
        pagamento_antes = db.execute(
            text("""
                SELECT status, mp_payment_id, aprovado_em
                FROM pagamentos
                WHERE id = 1
            """)
        ).one()

        acesso_antes = db.execute(
            text("""
                SELECT ativo, data_inicio, data_fim
                FROM acessos_curso
                WHERE usuario_id = 2 AND curso_id = 1
            """)
        ).one()

        assert pagamento_antes.status == "APPROVED"
        assert pagamento_antes.mp_payment_id == (
            "mp_teste_integrado_001"
        )

        request = MagicMock()
        request.query_params = {
            "type": "payment",
            "data.id": "mp_teste_integrado_001",
        }
        request.json = AsyncMock(
            return_value={
                "type": "payment",
                "data": {"id": "mp_teste_integrado_001"},
            }
        )

        resposta_mp = MagicMock()
        resposta_mp.status_code = 200
        resposta_mp.json.return_value = {
            "status": "approved",
            "external_reference": (
                "user:2|curso:1|tempo:1|pagamento:1"
            ),
            "transaction_amount": 49.90,
            "currency_id": "BRL",
        }

        # Impede uma nova concessão de acesso.
        execute_original = db.execute

        def verificar_execute(statement, *args, **kwargs):
            if "INSERT INTO acessos_curso" in str(statement):
                raise AssertionError(
                    "Webhook tentou conceder acesso novamente"
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
            patch("app.main.mp_headers", return_value={}),
            patch.object(
                db,
                "execute",
                side_effect=verificar_execute,
            ),
        ):
            resultado = asyncio.run(
                webhook_mercadopago(request=request, db=db)
            )

        assert resultado["ok"] is True
        assert resultado["status"] == "APPROVED"

        # Consulta novamente os registros no banco.
        pagamento_depois = db.execute(
            text("""
                SELECT status, mp_payment_id, aprovado_em
                FROM pagamentos
                WHERE id = 1
            """)
        ).one()

        acesso_depois = db.execute(
            text("""
                SELECT ativo, data_inicio, data_fim
                FROM acessos_curso
                WHERE usuario_id = 2 AND curso_id = 1
            """)
        ).one()

        assert pagamento_depois == pagamento_antes
        assert acesso_depois == acesso_antes

        # Uma notificação repetida não pode criar
        # um novo período de acesso.
        periodos = db.execute(
            text("""
                SELECT COUNT(*)
                FROM periodos_acesso_pagamento
                WHERE pagamento_id = 1
            """)
        ).scalar_one()

        assert periodos == 0

    finally:
        db.close()
        engine.dispose()
