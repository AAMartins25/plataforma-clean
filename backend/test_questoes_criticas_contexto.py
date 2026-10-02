import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.main import listar_questoes_criticas


def test_questoes_criticas_isola_contexto():
    assert os.getenv("AMBIENTE_TESTE") == "1"

    url = os.environ["DATABASE_URL"]
    assert "localhost" in url or "127.0.0.1" in url

    engine = create_engine(url)
    conexao = engine.connect()
    transacao = conexao.begin()
    db = Session(bind=conexao, join_transaction_mode="create_savepoint")

    try:
        usuario = db.execute(
            text("""
                SELECT id
                FROM usuarios
                WHERE id = 2
            """)
        ).mappings().first()

        assert usuario is not None

        # ---------------------------------------------------------
        # 1. Contratação.
        # ---------------------------------------------------------
        contratacao_id = db.execute(
            text("""
                INSERT INTO contratacoes_curso
                    (usuario_id, curso_id, data_inicio, data_fim, origem)
                VALUES
                    (
                        2,
                        1,
                        NOW() - INTERVAL '1 day',
                        NOW() + INTERVAL '30 days',
                        'ADMIN'
                    )
                RETURNING id
            """)
        ).scalar_one()

        # ---------------------------------------------------------
        # 2. Demonstração.
        # ---------------------------------------------------------
        demonstracao_id = db.execute(
            text("""
                INSERT INTO demonstracoes_curso
                    (
                        usuario_id,
                        curso_id,
                        data_inicio,
                        data_fim,
                        liberado_novamente_em,
                        ativo
                    )
                VALUES
                    (
                        2,
                        1,
                        NOW() - INTERVAL '1 day',
                        NOW() + INTERVAL '1 day',
                        NOW(),
                        TRUE
                    )
                RETURNING id
            """)
        ).scalar_one()

        # ---------------------------------------------------------
        # 3. Disciplina própria.
        # ---------------------------------------------------------
        disciplina_id = db.execute(
            text("""
                INSERT INTO curso_disciplinas_proprias
                    (
                        curso_id,
                        nome,
                        ordem,
                        ativo,
                        disponivel_demonstracao
                    )
                VALUES
                    (
                        1,
                        'Disciplina Teste Questões Críticas Contexto',
                        990,
                        TRUE,
                        TRUE
                    )
                RETURNING id
            """)
        ).scalar_one()

        # ---------------------------------------------------------
        # 4. Assunto próprio.
        # ---------------------------------------------------------
        assunto_id = db.execute(
            text("""
                INSERT INTO curso_assuntos_proprios
                    (
                        curso_disciplina_propria_id,
                        nome,
                        ordem,
                        ativo
                    )
                VALUES
                    (
                        :disciplina_id,
                        'Assunto Teste Questões Críticas Contexto',
                        990,
                        TRUE
                    )
                RETURNING id
            """),
            {"disciplina_id": disciplina_id}
        ).scalar_one()

        # ---------------------------------------------------------
        # 5. Pasta.
        # ---------------------------------------------------------
        pasta_id = db.execute(
            text("""
                INSERT INTO pastas
                    (
                        curso_assunto_proprio_id,
                        tipo,
                        nome
                    )
                VALUES
                    (
                        :assunto_id,
                        'TEORIA',
                        'Pasta Teste Questões Críticas Contexto'
                    )
                RETURNING id
            """),
            {"assunto_id": assunto_id}
        ).scalar_one()

        # ---------------------------------------------------------
        # 6. Aula.
        # ---------------------------------------------------------
        aula_id = db.execute(
            text("""
                INSERT INTO aulas
                    (
                        pasta_id,
                        titulo,
                        descricao,
                        ordem,
                        ativo
                    )
                VALUES
                    (
                        :pasta_id,
                        'Aula Teste Questões Críticas Contexto',
                        'Aula utilizada no teste de isolamento.',
                        990,
                        TRUE
                    )
                RETURNING id
            """),
            {"pasta_id": pasta_id}
        ).scalar_one()

        # ---------------------------------------------------------
        # 7. Bateria.
        # ---------------------------------------------------------
        bateria_id = db.execute(
            text("""
                INSERT INTO baterias
                    (
                        aula_id,
                        titulo,
                        ordem,
                        status,
                        ativo
                    )
                VALUES
                    (
                        :aula_id,
                        'Bateria Teste Questões Críticas Contexto',
                        1,
                        'CONCLUIDA',
                        TRUE
                    )
                RETURNING id
            """),
            {"aula_id": aula_id}
        ).scalar_one()

        # ---------------------------------------------------------
        # 8. Questão.
        # ---------------------------------------------------------
        questao_id = db.execute(
            text("""
                INSERT INTO questoes
                    (
                        bateria_id,
                        enunciado,
                        tipo,
                        ordem,
                        ativo,
                        tipo_questao,
                        quantidade_alternativas,
                        gabarito,
                        comentario
                    )
                VALUES
                    (
                        :bateria_id,
                        'Questão crítica de teste de isolamento.',
                        'MULTIPLA',
                        1,
                        TRUE,
                        'MULTIPLA',
                        4,
                        'A',
                        'Comentário da questão crítica.'
                    )
                RETURNING id
            """),
            {"bateria_id": bateria_id}
        ).scalar_one()

        # ---------------------------------------------------------
        # 9. Alternativas.
        # ---------------------------------------------------------
        for letra in ("A", "B", "C", "D"):
            db.execute(
                text("""
                    INSERT INTO alternativas
                        (
                            questao_id,
                            letra,
                            texto
                        )
                    VALUES
                        (
                            :questao_id,
                            :letra,
                            :texto
                        )
                """),
                {
                    "questao_id": questao_id,
                    "letra": letra,
                    "texto": f"Alternativa {letra}"
                }
            )

        # ---------------------------------------------------------
        # 10. Tentativa da contratação.
        # ---------------------------------------------------------
        tentativa_contratacao_id = db.execute(
            text("""
                INSERT INTO tentativas_bateria
                    (
                        usuario_id,
                        bateria_id,
                        contratacao_id,
                        demonstracao_id,
                        status,
                        percentual_acerto,
                        ativo
                    )
                VALUES
                    (
                        2,
                        :bateria_id,
                        :contratacao_id,
                        NULL,
                        'CONCLUIDA',
                        0,
                        TRUE
                    )
                RETURNING id
            """),
            {
                "bateria_id": bateria_id,
                "contratacao_id": contratacao_id
            }
        ).scalar_one()

        # ---------------------------------------------------------
        # 11. Resposta crítica da contratação.
        #
        # Errou e marcou como difícil/rever.
        # ---------------------------------------------------------
        resposta_contratacao_id = db.execute(
            text("""
                INSERT INTO respostas_aluno_questoes
                    (
                        tentativa_id,
                        usuario_id,
                        questao_id,
                        bateria_id,
                        contratacao_id,
                        demonstracao_id,
                        resposta_marcada,
                        gabarito,
                        dificuldade,
                        acertou,
                        pulou,
                        rever,
                        respondida,
                        finalizada
                    )
                VALUES
                    (
                        :tentativa_id,
                        2,
                        :questao_id,
                        :bateria_id,
                        :contratacao_id,
                        NULL,
                        'B',
                        'A',
                        'DIFICIL',
                        FALSE,
                        FALSE,
                        TRUE,
                        TRUE,
                        TRUE
                    )
                RETURNING id
            """),
            {
                "tentativa_id": tentativa_contratacao_id,
                "questao_id": questao_id,
                "bateria_id": bateria_id,
                "contratacao_id": contratacao_id
            }
        ).scalar_one()

        # ---------------------------------------------------------
        # 12. Tentativa da demonstração.
        # ---------------------------------------------------------
        tentativa_demonstracao_id = db.execute(
            text("""
                INSERT INTO tentativas_bateria
                    (
                        usuario_id,
                        bateria_id,
                        contratacao_id,
                        demonstracao_id,
                        status,
                        percentual_acerto,
                        ativo
                    )
                VALUES
                    (
                        2,
                        :bateria_id,
                        NULL,
                        :demonstracao_id,
                        'CONCLUIDA',
                        0,
                        TRUE
                    )
                RETURNING id
            """),
            {
                "bateria_id": bateria_id,
                "demonstracao_id": demonstracao_id
            }
        ).scalar_one()

        # ---------------------------------------------------------
        # 13. Resposta crítica da demonstração.
        # ---------------------------------------------------------
        resposta_demonstracao_id = db.execute(
            text("""
                INSERT INTO respostas_aluno_questoes
                    (
                        tentativa_id,
                        usuario_id,
                        questao_id,
                        bateria_id,
                        contratacao_id,
                        demonstracao_id,
                        resposta_marcada,
                        gabarito,
                        dificuldade,
                        acertou,
                        pulou,
                        rever,
                        respondida,
                        finalizada
                    )
                VALUES
                    (
                        :tentativa_id,
                        2,
                        :questao_id,
                        :bateria_id,
                        NULL,
                        :demonstracao_id,
                        'C',
                        'A',
                        'DIFICIL',
                        FALSE,
                        FALSE,
                        TRUE,
                        TRUE,
                        TRUE
                    )
                RETURNING id
            """),
            {
                "tentativa_id": tentativa_demonstracao_id,
                "questao_id": questao_id,
                "bateria_id": bateria_id,
                "demonstracao_id": demonstracao_id
            }
        ).scalar_one()

        db.flush()

        # ---------------------------------------------------------
        # 14. Usuário utilizado pelo endpoint.
        # ---------------------------------------------------------
        usuario_atual = db.execute(
            text("""
                SELECT id
                FROM usuarios
                WHERE id = 2
            """)
        ).mappings().first()

        class UsuarioTeste:
            pass

        usuario = UsuarioTeste()
        usuario.id = usuario_atual["id"]

        # ---------------------------------------------------------
        # 15. Consulta na CONTRATAÇÃO.
        #
        # Deve considerar somente a resposta da contratação.
        # ---------------------------------------------------------
        resultado_contratacao = listar_questoes_criticas(
            curso_id=1,
            contratacao_id=contratacao_id,
            demonstracao_id=None,
            db=db,
            usuario_atual=usuario
        )

        assert len(resultado_contratacao) == 1

        item_contratacao = resultado_contratacao[0]

        assert item_contratacao["questao_id"] == questao_id
        assert item_contratacao["resposta_id"] == resposta_contratacao_id
        assert item_contratacao["bateria_id"] == bateria_id
        assert item_contratacao["erro"] is True
        assert item_contratacao["dificil"] is True
        assert item_contratacao["para_rever"] is True

        # ---------------------------------------------------------
        # 16. Consulta na DEMONSTRAÇÃO.
        #
        # Deve considerar somente a resposta da demonstração.
        # ---------------------------------------------------------
        resultado_demonstracao = listar_questoes_criticas(
            curso_id=1,
            contratacao_id=None,
            demonstracao_id=demonstracao_id,
            db=db,
            usuario_atual=usuario
        )

        assert len(resultado_demonstracao) == 1

        item_demonstracao = resultado_demonstracao[0]

        assert item_demonstracao["questao_id"] == questao_id
        assert item_demonstracao["resposta_id"] == resposta_demonstracao_id
        assert item_demonstracao["bateria_id"] == bateria_id
        assert item_demonstracao["erro"] is True
        assert item_demonstracao["dificil"] is True
        assert item_demonstracao["para_rever"] is True

        # ---------------------------------------------------------
        # 17. Os IDs das respostas devem estar isolados.
        # ---------------------------------------------------------
        assert (
            item_contratacao["resposta_id"]
            != item_demonstracao["resposta_id"]
        )

        # ---------------------------------------------------------
        # 18. Nenhum contexto informado.
        # ---------------------------------------------------------
        try:
            listar_questoes_criticas(
                curso_id=1,
                contratacao_id=None,
                demonstracao_id=None,
                db=db,
                usuario_atual=usuario
            )
        except HTTPException as exc:
            assert exc.status_code == 400
            assert "contratacao_id" in exc.detail.lower()
        else:
            raise AssertionError(
                "A consulta sem contexto deveria ser rejeitada"
            )

        # ---------------------------------------------------------
        # 19. Dois contextos informados simultaneamente.
        # ---------------------------------------------------------
        try:
            listar_questoes_criticas(
                curso_id=1,
                contratacao_id=contratacao_id,
                demonstracao_id=demonstracao_id,
                db=db,
                usuario_atual=usuario
            )
        except HTTPException as exc:
            assert exc.status_code == 400
            assert "apenas um contexto" in exc.detail.lower()
        else:
            raise AssertionError(
                "A consulta com dois contextos deveria ser rejeitada"
            )

    finally:
        db.close()
        transacao.rollback()
        conexao.close()
        engine.dispose()
