import os
from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.main import concluir_aula, listar_meu_progresso


def test_progresso_isola_contexto():
    assert os.getenv("AMBIENTE_TESTE") == "1"

    url = os.environ["DATABASE_URL"]
    assert "localhost" in url or "127.0.0.1" in url

    engine = create_engine(url)
    conexao = engine.connect()
    transacao = conexao.begin()
    db = Session(
        bind=conexao,
        join_transaction_mode="create_savepoint"
    )

    try:
        usuario = SimpleNamespace(id=2)
        agora = datetime.utcnow()

        # ---------------------------------------------------------
        # 1. Busca uma contratação existente do usuário.
        # ---------------------------------------------------------
        contratacao_id = db.execute(
            text("""
                SELECT id
                FROM contratacoes_curso
                WHERE usuario_id = 2
                  AND curso_id = 1
                ORDER BY id
                LIMIT 1
            """)
        ).scalar()

        assert contratacao_id is not None, (
            "O banco de teste precisa possuir uma contratação "
            "do usuário 2 para o curso 1."
        )

        # ---------------------------------------------------------
        # 2. Cria uma demonstração para o mesmo usuário/curso.
        # ---------------------------------------------------------
        demonstracao_id = db.execute(
            text("""
                INSERT INTO demonstracoes_curso
                    (usuario_id, curso_id, data_inicio, data_fim,
                     liberado_novamente_em, ativo)
                VALUES
                    (2, 1, :inicio, :fim, :liberado, TRUE)
                RETURNING id
            """),
            {
                "inicio": agora - timedelta(days=1),
                "fim": agora + timedelta(days=10),
                "liberado": agora + timedelta(days=11),
            }
        ).scalar_one()

        # ---------------------------------------------------------
        # 3. Cria estrutura mínima:
        #    disciplina -> assunto -> pasta -> aula.
        # ---------------------------------------------------------
        disciplina_id = db.execute(
            text("""
                INSERT INTO curso_disciplinas_proprias
                    (curso_id, nome, ativo, ordem, disponivel_demonstracao)
                VALUES
                    (1, 'Disciplina Teste Progresso Contexto',
                     TRUE, 901, TRUE)
                RETURNING id
            """)
        ).scalar_one()

        assunto_id = db.execute(
            text("""
                INSERT INTO curso_assuntos_proprios
                    (curso_disciplina_propria_id, nome, ativo, ordem)
                VALUES
                    (:disciplina_id,
                     'Assunto Teste Progresso Contexto',
                     TRUE, 901)
                RETURNING id
            """),
            {"disciplina_id": disciplina_id}
        ).scalar_one()

        pasta_id = db.execute(
            text("""
                INSERT INTO pastas
                    (nome, tipo, curso_assunto_proprio_id)
                VALUES
                    ('Pasta Teste Progresso Contexto',
                     'TEORIA',
                     :assunto_id)
                RETURNING id
            """),
            {"assunto_id": assunto_id}
        ).scalar_one()

        aula_id = db.execute(
            text("""
                INSERT INTO aulas
                    (pasta_id, titulo, ordem, ativo)
                VALUES
                    (:pasta_id,
                     'Aula Teste Progresso Contexto',
                     901,
                     TRUE)
                RETURNING id
            """),
            {"pasta_id": pasta_id}
        ).scalar_one()

        db.flush()

        # ---------------------------------------------------------
        # 4. Não existe progresso inicialmente em nenhum contexto.
        # ---------------------------------------------------------
        registros = db.execute(
            text("""
                SELECT
                    contratacao_id,
                    demonstracao_id,
                    concluida
                FROM progresso_aulas
                WHERE usuario_id = 2
                  AND aula_id = :aula_id
            """),
            {"aula_id": aula_id}
        ).mappings().all()

        assert registros == []

        # ---------------------------------------------------------
        # 5. Conclui a aula no contexto da CONTRATAÇÃO.
        # ---------------------------------------------------------
        resultado_contratacao = concluir_aula(
            aula_id=aula_id,
            contratacao_id=contratacao_id,
            demonstracao_id=None,
            db=db,
            usuario=usuario
        )

        assert resultado_contratacao.contratacao_id == contratacao_id
        assert resultado_contratacao.demonstracao_id is None
        assert resultado_contratacao.concluida is True

        # ---------------------------------------------------------
        # 6. A contratação possui progresso.
        #    A demonstração NÃO possui.
        # ---------------------------------------------------------
        progresso_contratacao = db.execute(
            text("""
                SELECT
                    contratacao_id,
                    demonstracao_id,
                    concluida
                FROM progresso_aulas
                WHERE usuario_id = 2
                  AND aula_id = :aula_id
                  AND contratacao_id = :contratacao_id
                  AND demonstracao_id IS NULL
            """),
            {
                "aula_id": aula_id,
                "contratacao_id": contratacao_id
            }
        ).mappings().first()

        assert progresso_contratacao is not None
        assert progresso_contratacao["contratacao_id"] == contratacao_id
        assert progresso_contratacao["demonstracao_id"] is None
        assert progresso_contratacao["concluida"] is True

        progresso_demonstracao = db.execute(
            text("""
                SELECT id
                FROM progresso_aulas
                WHERE usuario_id = 2
                  AND aula_id = :aula_id
                  AND contratacao_id IS NULL
                  AND demonstracao_id = :demonstracao_id
            """),
            {
                "aula_id": aula_id,
                "demonstracao_id": demonstracao_id
            }
        ).first()

        assert progresso_demonstracao is None

        # ---------------------------------------------------------
        # 7. O endpoint de listagem também deve enxergar somente
        #    o contexto da CONTRATAÇÃO.
        # ---------------------------------------------------------
        lista_contratacao = listar_meu_progresso(
            pasta_id=pasta_id,
            contratacao_id=contratacao_id,
            demonstracao_id=None,
            db=db,
            usuario=usuario
        )

        assert len(lista_contratacao) == 1
        assert lista_contratacao[0]["aula_id"] == aula_id

        # ---------------------------------------------------------
        # 8. O contexto da DEMONSTRAÇÃO continua sem progresso.
        # ---------------------------------------------------------
        lista_demonstracao = listar_meu_progresso(
            pasta_id=pasta_id,
            contratacao_id=None,
            demonstracao_id=demonstracao_id,
            db=db,
            usuario=usuario
        )

        assert lista_demonstracao == []

        # ---------------------------------------------------------
        # 9. Agora conclui a mesma aula no contexto da DEMONSTRAÇÃO.
        # ---------------------------------------------------------
        resultado_demonstracao = concluir_aula(
            aula_id=aula_id,
            contratacao_id=None,
            demonstracao_id=demonstracao_id,
            db=db,
            usuario=usuario
        )

        assert resultado_demonstracao.contratacao_id is None
        assert resultado_demonstracao.demonstracao_id == demonstracao_id
        assert resultado_demonstracao.concluida is True

        # ---------------------------------------------------------
        # 10. Agora existem DOIS progressos independentes.
        # ---------------------------------------------------------
        progressos = db.execute(
            text("""
                SELECT
                    contratacao_id,
                    demonstracao_id,
                    concluida
                FROM progresso_aulas
                WHERE usuario_id = 2
                  AND aula_id = :aula_id
                ORDER BY id
            """),
            {"aula_id": aula_id}
        ).mappings().all()

        assert len(progressos) == 2

        contextos = {
            (
                p["contratacao_id"],
                p["demonstracao_id"]
            )
            for p in progressos
        }

        assert (
            contratacao_id,
            None
        ) in contextos

        assert (
            None,
            demonstracao_id
        ) in contextos

        # ---------------------------------------------------------
        # 11. Cada contexto deve enxergar somente o seu próprio
        #     progresso.
        # ---------------------------------------------------------
        lista_contratacao = listar_meu_progresso(
            pasta_id=pasta_id,
            contratacao_id=contratacao_id,
            demonstracao_id=None,
            db=db,
            usuario=usuario
        )

        assert len(lista_contratacao) == 1
        assert lista_contratacao[0]["aula_id"] == aula_id

        lista_demonstracao = listar_meu_progresso(
            pasta_id=pasta_id,
            contratacao_id=None,
            demonstracao_id=demonstracao_id,
            db=db,
            usuario=usuario
        )

        assert len(lista_demonstracao) == 1
        assert lista_demonstracao[0]["aula_id"] == aula_id

    finally:
        db.close()
        transacao.rollback()
        conexao.close()
        engine.dispose()
