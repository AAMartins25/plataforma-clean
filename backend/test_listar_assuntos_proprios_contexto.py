import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.main import listar_assuntos_proprios


def test_listar_assuntos_proprios_isola_contexto():
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
        # 1. Contratação do curso 1.
        # ---------------------------------------------------------
        contratacao_id = db.execute(
            text("""
                INSERT INTO contratacoes_curso
                    (
                        usuario_id,
                        curso_id,
                        data_inicio,
                        data_fim,
                        origem
                    )
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
        # 2. Demonstração do curso 1.
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
        # 3. Disciplina 1 do curso 1.
        # ---------------------------------------------------------
        disciplina_1_id = db.execute(
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
                        'Disciplina Teste Assuntos Contexto 1',
                        991,
                        TRUE,
                        TRUE
                    )
                RETURNING id
            """)
        ).scalar_one()

        # ---------------------------------------------------------
        # 4. Disciplina 2 do curso 1.
        # ---------------------------------------------------------
        disciplina_2_id = db.execute(
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
                        'Disciplina Teste Assuntos Contexto 2',
                        992,
                        TRUE,
                        TRUE
                    )
                RETURNING id
            """)
        ).scalar_one()

        # ---------------------------------------------------------
        # 5. Disciplina 3 do curso 1.
        #    Deve ficar fora da demonstração.
        # ---------------------------------------------------------
        disciplina_3_id = db.execute(
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
                        'Disciplina Teste Assuntos Contexto 3',
                        993,
                        TRUE,
                        TRUE
                    )
                RETURNING id
            """)
        ).scalar_one()

        # ---------------------------------------------------------
        # 6. Assunto da disciplina 1.
        # ---------------------------------------------------------
        assunto_1_id = db.execute(
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
                        'Assunto Teste Contexto 1',
                        991,
                        TRUE
                    )
                RETURNING id
            """),
            {"disciplina_id": disciplina_1_id}
        ).scalar_one()

        # ---------------------------------------------------------
        # 7. Assunto da disciplina 2.
        # ---------------------------------------------------------
        assunto_2_id = db.execute(
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
                        'Assunto Teste Contexto 2',
                        992,
                        TRUE
                    )
                RETURNING id
            """),
            {"disciplina_id": disciplina_2_id}
        ).scalar_one()

        # ---------------------------------------------------------
        # 8. Assunto da disciplina 3.
        # ---------------------------------------------------------
        assunto_3_id = db.execute(
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
                        'Assunto Teste Contexto 3',
                        993,
                        TRUE
                    )
                RETURNING id
            """),
            {"disciplina_id": disciplina_3_id}
        ).scalar_one()

        # ---------------------------------------------------------
        # 9. Contexto de contratação:
        #    deve listar o assunto da disciplina 3 também.
        # ---------------------------------------------------------
        resultado_contratacao = listar_assuntos_proprios(
            disciplina_id=disciplina_3_id,
            contratacao_id=contratacao_id,
            demonstracao_id=None,
            db=db,
            usuario=usuario
        )

        ids_contratacao = {
            assunto.id
            for assunto in resultado_contratacao
        }

        assert assunto_3_id in ids_contratacao

        # ---------------------------------------------------------
        # 10. Contexto de demonstração:
        #     disciplina 1 deve ser acessível.
        # ---------------------------------------------------------
        resultado_demonstracao = listar_assuntos_proprios(
            disciplina_id=disciplina_1_id,
            contratacao_id=None,
            demonstracao_id=demonstracao_id,
            db=db,
            usuario=usuario
        )

        ids_demonstracao = {
            assunto.id
            for assunto in resultado_demonstracao
        }

        assert assunto_1_id in ids_demonstracao

        # ---------------------------------------------------------
        # 11. Contexto de demonstração:
        #     disciplina 3 deve ser bloqueada.
        # ---------------------------------------------------------
        try:
            listar_assuntos_proprios(
                disciplina_id=disciplina_3_id,
                contratacao_id=None,
                demonstracao_id=demonstracao_id,
                db=db,
                usuario=usuario
            )
            assert False, "Era esperado bloqueio da disciplina na demonstração"
        except HTTPException as exc:
            assert exc.status_code == 403

        # ---------------------------------------------------------
        # 12. Cria um segundo curso para testar isolamento de contexto.
        # ---------------------------------------------------------
        outro_curso_id = db.execute(
            text("""
                INSERT INTO cursos
                    (nome, ativo, publicado)
                VALUES
                    (
                        'Curso Teste Outro Contexto',
                        TRUE,
                        FALSE
                    )
                RETURNING id
            """
            )
        ).scalar_one()

        # ---------------------------------------------------------
        # 13. Contratação de outro curso não pode ser usada.
        # ---------------------------------------------------------
        contratacao_outro_curso_id = db.execute(
            text("""
                INSERT INTO contratacoes_curso
                    (
                        usuario_id,
                        curso_id,
                        data_inicio,
                        data_fim,
                        origem
                    )
                VALUES
                    (
                        2,
                        :outro_curso_id,
                        NOW() - INTERVAL '1 day',
                        NOW() + INTERVAL '30 days',
                        'ADMIN'
                    )
                RETURNING id
            """),
            {"outro_curso_id": outro_curso_id}
        ).scalar_one()

        try:
            listar_assuntos_proprios(
                disciplina_id=disciplina_1_id,
                contratacao_id=contratacao_outro_curso_id,
                demonstracao_id=None,
                db=db,
                usuario=usuario
            )
            assert False, "Era esperado bloqueio por contexto de outro curso"
        except HTTPException as exc:
            assert exc.status_code == 403

        # ---------------------------------------------------------
        # 13. Sem contexto.
        # ---------------------------------------------------------
        try:
            listar_assuntos_proprios(
                disciplina_id=disciplina_1_id,
                contratacao_id=None,
                demonstracao_id=None,
                db=db,
                usuario=usuario
            )
            assert False, "Era esperado erro sem contexto"
        except HTTPException as exc:
            assert exc.status_code == 400

        # ---------------------------------------------------------
        # 14. Dois contextos simultaneamente.
        # ---------------------------------------------------------
        try:
            listar_assuntos_proprios(
                disciplina_id=disciplina_1_id,
                contratacao_id=contratacao_id,
                demonstracao_id=demonstracao_id,
                db=db,
                usuario=usuario
            )
            assert False, "Era esperado erro com dois contextos"
        except HTTPException as exc:
            assert exc.status_code == 400

    finally:
        db.close()
        transacao.rollback()
        conexao.close()
        engine.dispose()
