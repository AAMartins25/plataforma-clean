import os
from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.main import meus_cursos


def test_contrato_e_demonstracao_mesmo_curso():
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

        # Contrato vigente dentro da janela de renovação.
        vencimento_contrato = agora + timedelta(days=5)

        db.execute(
            text("""
                UPDATE contratacoes_curso
                SET data_fim = :fim
                WHERE id = 1
                  AND usuario_id = 2
                  AND curso_id = 1
            """),
            {"fim": vencimento_contrato},
        )

        db.execute(
            text("""
                UPDATE acessos_curso
                SET ativo = TRUE,
                    data_fim = :fim
                WHERE usuario_id = 2
                  AND curso_id = 1
            """),
            {"fim": vencimento_contrato},
        )

        # Demonstração simultânea do mesmo curso.
        vencimento_demo = agora + timedelta(hours=23)

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
                "fim": vencimento_demo,
                "liberado": agora + timedelta(days=30),
            },
        ).scalar_one()

        db.flush()

        cursos = meus_cursos(db=db, usuario=usuario)

        curso = next(c for c in cursos if c.curso_id == 1)

        assert len(curso.contratacoes) == 1
        assert curso.contratacoes[0]["id"] == 1
        assert curso.contratacoes[0]["renovacao_disponivel"] is True
        assert curso.contratacoes[0]["data_fim"] == vencimento_contrato

        assert len(curso.demonstracoes) == 1
        assert curso.demonstracoes[0]["id"] == demo_id
        assert curso.demonstracoes[0]["aquisicao_disponivel"] is True
        assert curso.demonstracoes[0]["data_fim"] == vencimento_demo

    finally:
        db.close()
        transacao.rollback()
        conexao.close()
        engine.dispose()
