import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.main import criar_checkout_mp


def test_expiracao_renovacao():
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
        agora = datetime.utcnow()
        vencimento = agora + timedelta(days=5)

        db.execute(text("""
            UPDATE contratacoes_curso
            SET data_fim = :fim
            WHERE id = 1
        """), {"fim": vencimento})

        db.execute(text("""
            UPDATE acessos_curso
            SET data_fim = :fim
            WHERE usuario_id = 2 AND curso_id = 1
        """), {"fim": vencimento})

        resposta_mp = MagicMock()
        resposta_mp.status_code = 201
        resposta_mp.json.return_value = {
            "id": "pref_teste_expiracao",
            "init_point": "https://example.com/checkout-teste",
        }

        usuario = db.execute(text("""
            SELECT id, email
            FROM usuarios
            WHERE id = 2
        """)).one()

        with patch(
            "app.main.requests.post",
            return_value=resposta_mp,
        ) as requisicao:
            resultado = criar_checkout_mp(
                payload={"tempo_acesso_id": 1, "tipo_compra": "RENOVACAO", "contratacao_id": 1},
                db=db,
                user=SimpleNamespace(
                    id=usuario.id,
                    email=usuario.email,
                ),
            )

        enviado = requisicao.call_args.kwargs["json"]

        assert enviado["expires"] is True
        assert datetime.fromisoformat(
            enviado["expiration_date_to"]
        ) == vencimento.replace(
            microsecond=0,
            tzinfo=timezone.utc,
        )
        assert resultado["preference_id"] == "pref_teste_expiracao"

        # O primeiro título já foi gerado. Simulamos mais sete.
        with patch("app.main.requests.post", return_value=resposta_mp) as requisicao:
            for numero in range(2, 9):
                resposta_mp.json.return_value = {
                    "id": f"pref_teste_expiracao_{numero}",
                    "init_point": "https://example.com/checkout-teste",
                }
                criar_checkout_mp(
                    payload={"tempo_acesso_id": 1, "tipo_compra": "RENOVACAO", "contratacao_id": 1},
                    db=db,
                    user=SimpleNamespace(
                        id=usuario.id,
                        email=usuario.email,
                    ),
                )

            assert requisicao.call_count == 7

            # A nona tentativa deve ser bloqueada sem chamar o MP.
            from fastapi import HTTPException

            try:
                criar_checkout_mp(
                    payload={"tempo_acesso_id": 1, "tipo_compra": "RENOVACAO", "contratacao_id": 1},
                    db=db,
                    user=SimpleNamespace(
                        id=usuario.id,
                        email=usuario.email,
                    ),
                )
            except HTTPException as erro:
                assert erro.status_code == 409
                assert "oito títulos" in erro.detail
            else:
                raise AssertionError("A nona tentativa não foi bloqueada.")

            assert requisicao.call_count == 7

    finally:
        db.close()
        transacao.rollback()
        conexao.close()
        engine.dispose()
