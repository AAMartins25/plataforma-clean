import asyncio
import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.main import webhook_mercadopago


def test_dois_pagamentos_mesma_oportunidade():
    assert os.getenv("AMBIENTE_TESTE") == "1"
    url = os.environ["DATABASE_URL"]
    assert "localhost" in url or "127.0.0.1" in url

    engine = create_engine(url)
    conexao = engine.connect()
    transacao = conexao.begin()
    db = Session(
        bind=conexao,
        join_transaction_mode="create_savepoint",
    )

    try:
        contrato = db.execute(text("""
            SELECT id, data_fim
            FROM contratacoes_curso
            WHERE usuario_id = 2
              AND curso_id = 1
              AND origem = 'ADMIN'
            ORDER BY id
            LIMIT 1
        """)).one()

        vencimento_original = contrato.data_fim

        oportunidade_id = db.execute(text("""
            INSERT INTO oportunidades_compra (
                usuario_id, curso_id, tipo_compra,
                contratacao_id, vencimento_original
            )
            VALUES (2, 1, 'RENOVACAO', :contrato, :vencimento)
            RETURNING id
        """), {
            "contrato": contrato.id,
            "vencimento": vencimento_original,
        }).scalar_one()


        pagamentos = []

        for numero in (1, 2):
            pagamento_id = db.execute(text("""
                INSERT INTO pagamentos (
                    usuario_id, curso_id, status,
                    valor_cents, provedor, moeda,
                    tempo_acesso_id, tipo_compra,
                    vencimento_original, contratacao_id,
                    oportunidade_id, mp_preference_id
                )
                VALUES (
                    2, 1, 'PENDENTE',
                    4990, 'mercadopago', 'BRL',
                    1, 'RENOVACAO',
                    :vencimento, :contrato,
                    :oportunidade, :preferencia
                )
                RETURNING id
            """), {
                "vencimento": vencimento_original,
                "contrato": contrato.id,
                "oportunidade": oportunidade_id,
                "preferencia": f"pref_teste_{numero}",
            }).scalar_one()

            pagamentos.append(pagamento_id)

        assert len(pagamentos) == 2
        assert pagamentos[0] != pagamentos[1]


        def notificar(pagamento_id, numero):
            payment_id = f"mp_integrado_{numero}_{pagamento_id}"

            request = MagicMock()
            request.query_params = {
                "type": "payment",
                "data.id": payment_id,
            }
            request.json = AsyncMock(return_value={
                "type": "payment",
                "data": {"id": payment_id},
            })

            resposta_mp = MagicMock()
            resposta_mp.status_code = 200
            resposta_mp.json.return_value = {
                "id": payment_id,
                "status": "approved",
                "date_approved": "2026-09-24T15:00:00Z",
                "external_reference": (
                    f"user:2|curso:1|tempo:1|pagamento:{pagamento_id}"
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
                return asyncio.run(
                    webhook_mercadopago(request=request, db=db)
                )

        primeira = notificar(pagamentos[0], 1)
        assert primeira["status"] == "APPROVED"

        vencimento_renovado = db.execute(text("""
            SELECT data_fim
            FROM contratacoes_curso
            WHERE id = :contrato
        """), {"contrato": contrato.id}).scalar_one()

        assert vencimento_renovado > vencimento_original

        segunda = notificar(pagamentos[1], 2)
        assert segunda["liberou_acesso"] is False
        assert segunda["ocorrencia_financeira"] == "COBRANCA_DUPLICADA"

        vencimento_final = db.execute(text("""
            SELECT data_fim
            FROM contratacoes_curso
            WHERE id = :contrato
        """), {"contrato": contrato.id}).scalar_one()

        assert vencimento_final == vencimento_renovado

        periodos = db.execute(text("""
            SELECT pagamento_id
            FROM periodos_acesso_pagamento
            WHERE pagamento_id IN (:primeiro, :segundo)
        """), {
            "primeiro": pagamentos[0],
            "segundo": pagamentos[1],
        }).scalars().all()

        assert periodos == [pagamentos[0]]

        ocorrencias = db.execute(text("""
            SELECT id, ocorrencia_financeira
            FROM pagamentos
            WHERE id IN (:primeiro, :segundo)
            ORDER BY id
        """), {
            "primeiro": pagamentos[0],
            "segundo": pagamentos[1],
        }).all()

        assert ocorrencias[0].ocorrencia_financeira is None
        assert ocorrencias[1].ocorrencia_financeira == "COBRANCA_DUPLICADA"

    finally:
        db.close()
        transacao.rollback()
        conexao.close()
        engine.dispose()



def test_aprovacao_apos_vencimento_nao_prorroga():
    assert os.getenv("AMBIENTE_TESTE") == "1"
    url = os.environ["DATABASE_URL"]
    assert "localhost" in url or "127.0.0.1" in url

    engine = create_engine(url)
    conexao = engine.connect()
    transacao = conexao.begin()
    db = Session(
        bind=conexao,
        join_transaction_mode="create_savepoint",
    )

    try:
        contrato = db.execute(text("""
            SELECT id, data_fim
            FROM contratacoes_curso
            WHERE usuario_id = 2
              AND curso_id = 1
              AND origem = 'ADMIN'
            ORDER BY id
            LIMIT 1
        """)).one()

        vencimento_original = contrato.data_fim

        oportunidade_id = db.execute(text("""
            INSERT INTO oportunidades_compra (
                usuario_id, curso_id, tipo_compra,
                contratacao_id, vencimento_original
            )
            VALUES (2, 1, 'RENOVACAO', :contrato, :vencimento)
            RETURNING id
        """), {
            "contrato": contrato.id,
            "vencimento": vencimento_original,
        }).scalar_one()


        pagamentos = []

        for numero in (1, 2):
            pagamento_id = db.execute(text("""
                INSERT INTO pagamentos (
                    usuario_id, curso_id, status,
                    valor_cents, provedor, moeda,
                    tempo_acesso_id, tipo_compra,
                    vencimento_original, contratacao_id,
                    oportunidade_id, mp_preference_id
                )
                VALUES (
                    2, 1, 'PENDENTE',
                    4990, 'mercadopago', 'BRL',
                    1, 'RENOVACAO',
                    :vencimento, :contrato,
                    :oportunidade, :preferencia
                )
                RETURNING id
            """), {
                "vencimento": vencimento_original,
                "contrato": contrato.id,
                "oportunidade": oportunidade_id,
                "preferencia": f"pref_teste_{numero}",
            }).scalar_one()

            pagamentos.append(pagamento_id)

        assert len(pagamentos) == 2
        assert pagamentos[0] != pagamentos[1]


        def notificar(pagamento_id, numero):
            payment_id = f"mp_integrado_{numero}_{pagamento_id}"

            request = MagicMock()
            request.query_params = {
                "type": "payment",
                "data.id": payment_id,
            }
            request.json = AsyncMock(return_value={
                "type": "payment",
                "data": {"id": payment_id},
            })

            resposta_mp = MagicMock()
            resposta_mp.status_code = 200
            resposta_mp.json.return_value = {
                "id": payment_id,
                "status": "approved",
                "date_approved": (vencimento_original + timedelta(seconds=1)).isoformat() + "Z",
                "external_reference": (
                    f"user:2|curso:1|tempo:1|pagamento:{pagamento_id}"
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
                return asyncio.run(
                    webhook_mercadopago(request=request, db=db)
                )


        vencimento_antes = db.execute(text("""
            SELECT data_fim
            FROM contratacoes_curso
            WHERE id = :contrato
        """), {"contrato": contrato.id}).scalar_one()

        # A aprovação simulada ocorrerá um segundo após o vencimento.
        # A data será ajustada na função notificar antes da execução.


        resultado = notificar(pagamentos[0], 1)

        assert resultado["status"] == "APPROVED"
        assert resultado["liberou_acesso"] is False
        assert resultado["ocorrencia_financeira"] == "APROVACAO_FORA_PRAZO"

        vencimento_depois = db.execute(text("""
            SELECT data_fim
            FROM contratacoes_curso
            WHERE id = :contrato
        """), {"contrato": contrato.id}).scalar_one()

        assert vencimento_depois == vencimento_antes

        quantidade_periodos = db.execute(text("""
            SELECT COUNT(*)
            FROM periodos_acesso_pagamento
            WHERE pagamento_id = :pagamento
        """), {"pagamento": pagamentos[0]}).scalar_one()

        assert quantidade_periodos == 0

        ocorrencia = db.execute(text("""
            SELECT ocorrencia_financeira
            FROM pagamentos
            WHERE id = :pagamento
        """), {"pagamento": pagamentos[0]}).scalar_one()

        assert ocorrencia == "APROVACAO_FORA_PRAZO"

    finally:
        db.close()
        transacao.rollback()
        conexao.close()
        engine.dispose()


def test_webhook_tardio_com_aprovacao_dentro_do_prazo():
    assert os.getenv("AMBIENTE_TESTE") == "1"
    url = os.environ["DATABASE_URL"]
    assert "localhost" in url or "127.0.0.1" in url

    engine = create_engine(url)
    conexao = engine.connect()
    transacao = conexao.begin()
    db = Session(
        bind=conexao,
        join_transaction_mode="create_savepoint",
    )

    try:
        contrato = db.execute(text("""
            SELECT id, data_fim
            FROM contratacoes_curso
            WHERE usuario_id = 2
              AND curso_id = 1
              AND origem = 'ADMIN'
            ORDER BY id
            LIMIT 1
        """)).one()

        vencimento_original = datetime(2026, 9, 20, 15, 0)
        db.execute(text("""
            UPDATE contratacoes_curso
            SET data_inicio = :vencimento - INTERVAL '4 months',
                data_fim = :vencimento
            WHERE id = :contrato
        """), {
            "vencimento": vencimento_original,
            "contrato": contrato.id,
        })

        oportunidade_id = db.execute(text("""
            INSERT INTO oportunidades_compra (
                usuario_id, curso_id, tipo_compra,
                contratacao_id, vencimento_original
            )
            VALUES (2, 1, 'RENOVACAO', :contrato, :vencimento)
            RETURNING id
        """), {
            "contrato": contrato.id,
            "vencimento": vencimento_original,
        }).scalar_one()


        pagamentos = []

        for numero in (1, 2):
            pagamento_id = db.execute(text("""
                INSERT INTO pagamentos (
                    usuario_id, curso_id, status,
                    valor_cents, provedor, moeda,
                    tempo_acesso_id, tipo_compra,
                    vencimento_original, contratacao_id,
                    oportunidade_id, mp_preference_id
                )
                VALUES (
                    2, 1, 'PENDENTE',
                    4990, 'mercadopago', 'BRL',
                    1, 'RENOVACAO',
                    :vencimento, :contrato,
                    :oportunidade, :preferencia
                )
                RETURNING id
            """), {
                "vencimento": vencimento_original,
                "contrato": contrato.id,
                "oportunidade": oportunidade_id,
                "preferencia": f"pref_teste_{numero}",
            }).scalar_one()

            pagamentos.append(pagamento_id)

        assert len(pagamentos) == 2
        assert pagamentos[0] != pagamentos[1]


        def notificar(pagamento_id, numero):
            payment_id = f"mp_integrado_{numero}_{pagamento_id}"

            request = MagicMock()
            request.query_params = {
                "type": "payment",
                "data.id": payment_id,
            }
            request.json = AsyncMock(return_value={
                "type": "payment",
                "data": {"id": payment_id},
            })

            resposta_mp = MagicMock()
            resposta_mp.status_code = 200
            resposta_mp.json.return_value = {
                "id": payment_id,
                "status": "approved",
                "date_approved": (vencimento_original - timedelta(seconds=1)).isoformat() + "Z",
                "external_reference": (
                    f"user:2|curso:1|tempo:1|pagamento:{pagamento_id}"
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
                return asyncio.run(
                    webhook_mercadopago(request=request, db=db)
                )


        vencimento_antes = db.execute(text("""
            SELECT data_fim
            FROM contratacoes_curso
            WHERE id = :contrato
        """), {"contrato": contrato.id}).scalar_one()


        resultado = notificar(pagamentos[0], 1)
        assert resultado["status"] == "APPROVED"

        vencimento_depois = db.execute(text("""
            SELECT data_fim
            FROM contratacoes_curso
            WHERE id = :contrato
        """), {"contrato": contrato.id}).scalar_one()

        assert vencimento_depois > vencimento_antes

        quantidade_periodos = db.execute(text("""
            SELECT COUNT(*)
            FROM periodos_acesso_pagamento
            WHERE pagamento_id = :pagamento
        """), {"pagamento": pagamentos[0]}).scalar_one()

        assert quantidade_periodos == 1

        ocorrencia = db.execute(text("""
            SELECT ocorrencia_financeira
            FROM pagamentos
            WHERE id = :pagamento
        """), {"pagamento": pagamentos[0]}).scalar_one()

        assert ocorrencia is None

    finally:
        db.close()
        transacao.rollback()
        conexao.close()
        engine.dispose()
