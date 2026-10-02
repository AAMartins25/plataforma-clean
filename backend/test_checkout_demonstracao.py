import os
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.main import criar_checkout_mp


def test_validacao_demonstracao_no_checkout():
    assert os.getenv("AMBIENTE_TESTE") == "1"
    url = os.environ["DATABASE_URL"]
    assert "localhost" in url or "127.0.0.1" in url

    engine = create_engine(url)
    conexao = engine.connect()
    transacao = conexao.begin()
    db = Session(bind=conexao, join_transaction_mode="create_savepoint")

    try:
        usuario = db.execute(
            text("SELECT id, email FROM usuarios WHERE id = 2")
        ).one()
        aluno = SimpleNamespace(id=usuario.id, email=usuario.email)
        agora = datetime.utcnow()

        # Criamos uma demonstração temporária para o aluno.
        demo_id = db.execute(
            text("""
                INSERT INTO demonstracoes_curso
                    (usuario_id, curso_id, data_inicio, data_fim,
                     liberado_novamente_em, ativo)
                VALUES
                    (2, 1, :inicio, :fim, :liberado, TRUE)
                RETURNING id
            """),
            {
                "inicio": agora - timedelta(minutes=1),
                "fim": agora + timedelta(hours=23),
                "liberado": agora + timedelta(days=30),
            },
        ).scalar_one()
        db.flush()

        resposta_mp = MagicMock()
        resposta_mp.status_code = 201
        resposta_mp.json.return_value = {
            "id": "pref_teste_demo_valida",
            "init_point": "https://example.com/checkout-teste",
        }

        with patch(
            "app.main.requests.post", return_value=resposta_mp
        ) as requisicao:
            resultado = criar_checkout_mp(
                payload={
                    "tempo_acesso_id": 1,
                    "tipo_compra": "NOVA",
                    "demonstracao_id": demo_id,
                },
                db=db,
                user=aluno,
            )
            assert resultado["preference_id"] == "pref_teste_demo_valida"
            assert requisicao.call_count == 1

        # Um identificador inexistente deve ser rejeitado.
        with patch("app.main.requests.post") as requisicao:
            with pytest.raises(HTTPException) as erro:
                criar_checkout_mp(
                    payload={
                        "tempo_acesso_id": 1,
                        "tipo_compra": "NOVA",
                        "demonstracao_id": 999999999,
                    },
                    db=db,
                    user=aluno,
                )
            assert erro.value.status_code == 409
            requisicao.assert_not_called()

        # Outro aluno não pode utilizar a demonstração criada.
        outro = db.execute(
            text("SELECT id, email FROM usuarios WHERE id = 1")
        ).one()
        with patch("app.main.requests.post") as requisicao:
            with pytest.raises(HTTPException) as erro:
                criar_checkout_mp(
                    payload={
                        "tempo_acesso_id": 1,
                        "tipo_compra": "NOVA",
                        "demonstracao_id": demo_id,
                    },
                    db=db,
                    user=SimpleNamespace(
                        id=outro.id, email=outro.email
                    ),
                )
            assert erro.value.status_code == 409
            requisicao.assert_not_called()

    finally:
        db.close()
        transacao.rollback()
        conexao.close()
        engine.dispose()
