import os
from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.main import meus_cursos


def test_visibilidade_renovacao():
    assert os.getenv("AMBIENTE_TESTE") == "1"
    url = os.environ["DATABASE_URL"]
    assert "localhost" in url or "127.0.0.1" in url

    engine = create_engine(url)
    conexao = engine.connect()
    transacao = conexao.begin()
    db = Session(bind=conexao, join_transaction_mode="create_savepoint")

    try:
        usuario = SimpleNamespace(id=2)
        agora = datetime.utcnow()

        def ajustar_vencimento(dias):
            vencimento = agora + timedelta(days=dias)
            db.execute(
                text("UPDATE contratacoes_curso SET data_fim=:fim WHERE id=1"),
                {"fim": vencimento},
            )
            db.execute(
                text(
                    "UPDATE acessos_curso SET data_fim=:fim "
                    "WHERE usuario_id=2 AND curso_id=1"
                ),
                {"fim": vencimento},
            )
            db.flush()
            return vencimento

        # Fora da janela de renovação.
        ajustar_vencimento(30)
        cursos = meus_cursos(db=db, usuario=usuario)
        assert cursos[0].renovacao_disponivel is False

        # Dentro dos últimos 15 dias.
        vencimento = ajustar_vencimento(5)
        cursos = meus_cursos(db=db, usuario=usuario)
        assert cursos[0].renovacao_disponivel is True

        # Uma oportunidade concluída oculta o botão.
        db.execute(
            text("""
                INSERT INTO oportunidades_compra
                    (usuario_id, curso_id, tipo_compra,
                     contratacao_id, vencimento_original,
                     concluida_em, criada_em)
                VALUES
                    (2, 1, 'RENOVACAO', 1, :fim, :agora, :agora)
            """),
            {"fim": vencimento, "agora": agora},
        )
        db.flush()

        cursos = meus_cursos(db=db, usuario=usuario)
        assert cursos[0].renovacao_disponivel is False

    finally:
        db.close()
        transacao.rollback()
        conexao.close()
        engine.dispose()
