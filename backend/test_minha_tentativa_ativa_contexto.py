import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.main import obter_minha_tentativa_ativa


def test_minha_tentativa_ativa_isola_contexto():
    assert os.getenv("AMBIENTE_TESTE") == "1"

    url = os.environ["DATABASE_URL"]
    assert "localhost" in url or "127.0.0.1" in url

    engine = create_engine(url)
    conexao = engine.connect()
    transacao = conexao.begin()
    db = Session(bind=conexao, join_transaction_mode="create_savepoint")

    try:
        usuario_id = 2

        # ---------------------------------------------------------
        # 1. Cria uma demonstração válida para o usuário.
        # ---------------------------------------------------------
        demonstracao_id = db.execute(
            text("""
                INSERT INTO demonstracoes_curso
                    (usuario_id, curso_id, data_inicio, data_fim,
                     liberado_novamente_em, ativo)
                VALUES
                    (
                        :usuario_id,
                        1,
                        NOW() - INTERVAL '1 day',
                        NOW() + INTERVAL '1 day',
                        NOW(),
                        TRUE
                    )
                RETURNING id
            """),
            {"usuario_id": usuario_id}
        ).scalar_one()

        # ---------------------------------------------------------
        # 2. Cria uma contratação válida para o mesmo usuário/curso.
        # ---------------------------------------------------------
        contratacao_id = db.execute(
            text("""
                INSERT INTO contratacoes_curso
                    (usuario_id, curso_id, origem,
                     data_inicio, data_fim)
                VALUES
                    (
                        :usuario_id,
                        1,
                        'ADMIN',
                        NOW() - INTERVAL '1 day',
                        NOW() + INTERVAL '30 days'
                    )
                RETURNING id
            """),
            {"usuario_id": usuario_id}
        ).scalar_one()

        # ---------------------------------------------------------
        # 3. Cria a estrutura mínima:
        # curso -> disciplina -> assunto -> pasta -> aula -> bateria.
        # ---------------------------------------------------------
        disciplina_id = db.execute(
            text("""
                INSERT INTO curso_disciplinas_proprias
                    (curso_id, nome, ordem, ativo, disponivel_demonstracao)
                VALUES
                    (1, 'Disciplina Teste Tentativa Contexto', 901, TRUE, TRUE)
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
                        'Assunto Teste Tentativa Contexto',
                        TRUE,
                        901
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
                        'Pasta Teste Tentativa Contexto',
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
                        'Aula Teste Tentativa Contexto',
                        NULL,
                        901,
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
                        'Sprint Teste Tentativa Contexto',
                        1,
                        'CONCLUIDA',
                        TRUE
                    )
                RETURNING id
            """),
            {"aula_id": aula_id}
        ).scalar_one()

        # ---------------------------------------------------------
        # 4. Cria tentativa ATIVA na contratação.
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
                        :usuario_id,
                        :bateria_id,
                        :contratacao_id,
                        NULL,
                        'EM_ANDAMENTO',
                        80,
                        TRUE
                    )
                RETURNING id
            """),
            {
                "usuario_id": usuario_id,
                "bateria_id": bateria_id,
                "contratacao_id": contratacao_id
            }
        ).scalar_one()

        # ---------------------------------------------------------
        # 5. Cria tentativa ATIVA na demonstração.
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
                        :usuario_id,
                        :bateria_id,
                        NULL,
                        :demonstracao_id,
                        'EM_ANDAMENTO',
                        40,
                        TRUE
                    )
                RETURNING id
            """),
            {
                "usuario_id": usuario_id,
                "bateria_id": bateria_id,
                "demonstracao_id": demonstracao_id
            }
        ).scalar_one()

        usuario = db.execute(
            text("""
                SELECT id
                FROM usuarios
                WHERE id = :usuario_id
            """),
            {"usuario_id": usuario_id}
        ).mappings().first()

        assert usuario is not None

        from app.models import Usuario

        usuario_obj = db.query(Usuario).filter(
            Usuario.id == usuario_id
        ).first()

        assert usuario_obj is not None

        # ---------------------------------------------------------
        # 6. Consulta pelo contexto da CONTRATAÇÃO.
        # ---------------------------------------------------------
        resultado_contratacao = obter_minha_tentativa_ativa(
            bateria_id=bateria_id,
            contratacao_id=contratacao_id,
            demonstracao_id=None,
            db=db,
            usuario_atual=usuario_obj
        )

        assert resultado_contratacao["tentativa"] is not None
        assert resultado_contratacao["tentativa"]["id"] == tentativa_contratacao_id
        assert resultado_contratacao["tentativa"]["id"] != tentativa_demonstracao_id

        # ---------------------------------------------------------
        # 7. Consulta pelo contexto da DEMONSTRAÇÃO.
        # ---------------------------------------------------------
        resultado_demonstracao = obter_minha_tentativa_ativa(
            bateria_id=bateria_id,
            contratacao_id=None,
            demonstracao_id=demonstracao_id,
            db=db,
            usuario_atual=usuario_obj
        )

        assert resultado_demonstracao["tentativa"] is not None
        assert resultado_demonstracao["tentativa"]["id"] == tentativa_demonstracao_id
        assert resultado_demonstracao["tentativa"]["id"] != tentativa_contratacao_id

        # ---------------------------------------------------------
        # 8. Sem contexto: deve ser rejeitado.
        # ---------------------------------------------------------
        try:
            obter_minha_tentativa_ativa(
                bateria_id=bateria_id,
                contratacao_id=None,
                demonstracao_id=None,
                db=db,
                usuario_atual=usuario_obj
            )
            assert False, "A chamada sem contexto deveria ser rejeitada"
        except HTTPException as exc:
            assert exc.status_code == 400
            assert "contexto" in exc.detail.lower()

        # ---------------------------------------------------------
        # 9. Contextos simultâneos: também devem ser rejeitados.
        # ---------------------------------------------------------
        try:
            obter_minha_tentativa_ativa(
                bateria_id=bateria_id,
                contratacao_id=contratacao_id,
                demonstracao_id=demonstracao_id,
                db=db,
                usuario_atual=usuario_obj
            )
            assert False, "A chamada com dois contextos deveria ser rejeitada"
        except HTTPException as exc:
            assert exc.status_code == 400
            assert "contexto" in exc.detail.lower()

    finally:
        db.close()
        transacao.rollback()
        conexao.close()
        engine.dispose()
