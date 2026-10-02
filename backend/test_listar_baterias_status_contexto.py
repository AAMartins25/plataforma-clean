import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.main import listar_baterias_com_status_do_aluno


def test_listar_baterias_status_isola_contexto():
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
        # 1. Estrutura mínima de curso.
        # ---------------------------------------------------------
        disciplina_id = db.execute(
            text("""
                INSERT INTO curso_disciplinas_proprias
                    (curso_id, nome, ativo, ordem, disponivel_demonstracao)
                VALUES
                    (1, 'Disciplina Teste Status Contexto', TRUE, 900, TRUE)
                RETURNING id
            """)
        ).scalar_one()

        assunto_id = db.execute(
            text("""
                INSERT INTO curso_assuntos_proprios
                    (curso_disciplina_propria_id, nome, ativo, ordem)
                VALUES
                    (
                        :disciplina_id,
                        'Assunto Teste Status Contexto',
                        TRUE,
                        900
                    )
                RETURNING id
            """),
            {"disciplina_id": disciplina_id}
        ).scalar_one()

        pasta_id = db.execute(
            text("""
                INSERT INTO pastas
                    (nome, tipo, curso_assunto_proprio_id)
                VALUES
                    (
                        'Pasta Teste Status Contexto',
                        'TEORIA',
                        :assunto_id
                    )
                RETURNING id
            """),
            {"assunto_id": assunto_id}
        ).scalar_one()

        aula_id = db.execute(
            text("""
                INSERT INTO aulas
                    (pasta_id, titulo, descricao, ordem, ativo)
                VALUES
                    (
                        :pasta_id,
                        'Aula Teste Status Contexto',
                        'Aula criada exclusivamente para o teste',
                        900,
                        TRUE
                    )
                RETURNING id
            """),
            {"pasta_id": pasta_id}
        ).scalar_one()

        bateria_id = db.execute(
            text("""
                INSERT INTO baterias
                    (aula_id, titulo, ordem, status, ativo)
                VALUES
                    (
                        :aula_id,
                        'Sprint Teste Status Contexto',
                        1,
                        'CONCLUIDA',
                        TRUE
                    )
                RETURNING id
            """),
            {"aula_id": aula_id}
        ).scalar_one()

        # ---------------------------------------------------------
        # 2. Localiza a contratação do usuário para o curso.
        # ---------------------------------------------------------
        contratacao = db.execute(
            text("""
                SELECT id
                FROM contratacoes_curso
                WHERE usuario_id = 2
                  AND curso_id = 1
                  AND origem IN ('PAGAMENTO', 'ADMIN')
                ORDER BY id
                LIMIT 1
            """)
        ).mappings().first()

        assert contratacao is not None, (
            "Nenhuma contratação disponível para o usuário/curso do teste"
        )

        contratacao_id = contratacao["id"]

        # ---------------------------------------------------------
        # 3. Cria uma demonstração para o mesmo usuário/curso.
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
        # 4. Cria uma tentativa no contexto da contratação.
        # ---------------------------------------------------------
        tentativa_contratacao = db.execute(
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
                        'FEITA',
                        80,
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
        # 5. Cria uma tentativa no contexto da demonstração.
        # ---------------------------------------------------------
        tentativa_demonstracao = db.execute(
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
                        'FEITA',
                        40,
                        TRUE
                    )
                RETURNING id
            """),
            {
                "bateria_id": bateria_id,
                "demonstracao_id": demonstracao_id
            }
        ).scalar_one()

        usuario_teste = type(
            "UsuarioTeste",
            (),
            {"id": 2}
        )()

        # ---------------------------------------------------------
        # 6. Consulta no contexto da contratação.
        # ---------------------------------------------------------
        resultado_contratacao = listar_baterias_com_status_do_aluno(
            aula_id=aula_id,
            contratacao_id=contratacao_id,
            demonstracao_id=None,
            db=db,
            usuario_atual=usuario_teste
        )

        bateria_resultado = next(
            item for item in resultado_contratacao
            if item["id"] == bateria_id
        )

        assert bateria_resultado["tentativa_id"] == tentativa_contratacao
        assert bateria_resultado["percentual_acerto"] == 80

        # ---------------------------------------------------------
        # 7. Consulta no contexto da demonstração.
        # ---------------------------------------------------------
        resultado_demonstracao = listar_baterias_com_status_do_aluno(
            aula_id=aula_id,
            contratacao_id=None,
            demonstracao_id=demonstracao_id,
            db=db,
            usuario_atual=usuario_teste
        )

        bateria_resultado = next(
            item for item in resultado_demonstracao
            if item["id"] == bateria_id
        )

        assert bateria_resultado["tentativa_id"] == tentativa_demonstracao
        assert bateria_resultado["percentual_acerto"] == 40

        # ---------------------------------------------------------
        # 8. Sem contexto deve ser rejeitado.
        # ---------------------------------------------------------
        try:
            listar_baterias_com_status_do_aluno(
                aula_id=aula_id,
                contratacao_id=None,
                demonstracao_id=None,
                db=db,
                usuario_atual=usuario_teste
            )

            assert False, "A consulta sem contexto deveria ser rejeitada"

        except HTTPException as exc:
            assert exc.status_code == 400
            assert "contexto" in exc.detail.lower()

    finally:
        db.close()
        transacao.rollback()
        conexao.close()
        engine.dispose()
