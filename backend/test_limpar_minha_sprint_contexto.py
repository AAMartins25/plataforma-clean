import os
from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.main import limpar_minha_sprint


def test_limpar_minha_sprint_isola_contexto():
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
        # 1. Busca uma contratação existente do usuário 2 no curso 1.
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
        # 3. Cria uma estrutura mínima para a bateria:
        #    disciplina -> assunto -> pasta -> aula -> bateria.
        # ---------------------------------------------------------
        disciplina_id = db.execute(
            text("""
                INSERT INTO curso_disciplinas_proprias
                    (curso_id, nome, ativo, ordem, disponivel_demonstracao)
                VALUES
                    (1, 'Disciplina Teste Limpar Sprint',
                     TRUE, 920, TRUE)
                RETURNING id
            """)
        ).scalar_one()

        assunto_id = db.execute(
            text("""
                INSERT INTO curso_assuntos_proprios
                    (curso_disciplina_propria_id, nome, ativo, ordem)
                VALUES
                    (:disciplina_id,
                     'Assunto Teste Limpar Sprint',
                     TRUE, 920)
                RETURNING id
            """),
            {"disciplina_id": disciplina_id}
        ).scalar_one()

        pasta_id = db.execute(
            text("""
                INSERT INTO pastas
                    (nome, tipo, curso_assunto_proprio_id)
                VALUES
                    ('Pasta Teste Limpar Sprint',
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
                     'Aula Teste Limpar Sprint',
                     920,
                     TRUE)
                RETURNING id
            """),
            {"pasta_id": pasta_id}
        ).scalar_one()

        bateria_id = db.execute(
            text("""
                INSERT INTO baterias
                    (aula_id, titulo, ordem, status, ativo)
                VALUES
                    (:aula_id,
                     'Bateria Teste Limpar Sprint',
                     920,
                     'CONCLUIDA',
                     TRUE)
                RETURNING id
            """),
            {"aula_id": aula_id}
        ).scalar_one()

        # ---------------------------------------------------------
        # 4. Cria uma tentativa ATIVA no contexto da contratação.
        # ---------------------------------------------------------
        tentativa_contratacao_id = db.execute(
            text("""
                INSERT INTO tentativas_bateria
                    (usuario_id, bateria_id, contratacao_id,
                     demonstracao_id, status, percentual_acerto,
                     ativo)
                VALUES
                    (2, :bateria_id, :contratacao_id, NULL,
                     'CONCLUIDA', 80, TRUE)
                RETURNING id
            """),
            {
                "bateria_id": bateria_id,
                "contratacao_id": contratacao_id
            }
        ).scalar_one()

        # ---------------------------------------------------------
        # 5. Cria uma tentativa ATIVA no contexto da demonstração.
        # ---------------------------------------------------------
        tentativa_demonstracao_id = db.execute(
            text("""
                INSERT INTO tentativas_bateria
                    (usuario_id, bateria_id, contratacao_id,
                     demonstracao_id, status, percentual_acerto,
                     ativo)
                VALUES
                    (2, :bateria_id, NULL, :demonstracao_id,
                     'CONCLUIDA', 60, TRUE)
                RETURNING id
            """),
            {
                "bateria_id": bateria_id,
                "demonstracao_id": demonstracao_id
            }
        ).scalar_one()

        db.flush()

        # ---------------------------------------------------------
        # 6. Limpa a sprint no contexto da CONTRATAÇÃO.
        # ---------------------------------------------------------
        resultado = limpar_minha_sprint(
            bateria_id=bateria_id,
            contratacao_id=contratacao_id,
            demonstracao_id=None,
            db=db,
            usuario_atual=usuario
        )

        assert resultado["mensagem"] == (
            "Sprint liberada para ser refeita."
        )

        # ---------------------------------------------------------
        # 7. A tentativa da contratação deve ter sido desativada.
        # ---------------------------------------------------------
        ativo_contratacao = db.execute(
            text("""
                SELECT ativo
                FROM tentativas_bateria
                WHERE id = :id
            """),
            {"id": tentativa_contratacao_id}
        ).scalar_one()

        assert ativo_contratacao is False

        # ---------------------------------------------------------
        # 8. A tentativa da demonstração deve continuar ativa.
        # ---------------------------------------------------------
        ativo_demonstracao = db.execute(
            text("""
                SELECT ativo
                FROM tentativas_bateria
                WHERE id = :id
            """),
            {"id": tentativa_demonstracao_id}
        ).scalar_one()

        assert ativo_demonstracao is True

        # ---------------------------------------------------------
        # 9. Reativa a tentativa da contratação apenas para testar
        #    o sentido inverso.
        # ---------------------------------------------------------
        db.execute(
            text("""
                UPDATE tentativas_bateria
                SET ativo = TRUE
                WHERE id = :id
            """),
            {"id": tentativa_contratacao_id}
        )

        db.flush()

        # ---------------------------------------------------------
        # 10. Limpa agora no contexto da DEMONSTRAÇÃO.
        # ---------------------------------------------------------
        resultado = limpar_minha_sprint(
            bateria_id=bateria_id,
            contratacao_id=None,
            demonstracao_id=demonstracao_id,
            db=db,
            usuario_atual=usuario
        )

        assert resultado["mensagem"] == (
            "Sprint liberada para ser refeita."
        )

        # ---------------------------------------------------------
        # 11. A tentativa da demonstração deve estar desativada.
        # ---------------------------------------------------------
        ativo_demonstracao = db.execute(
            text("""
                SELECT ativo
                FROM tentativas_bateria
                WHERE id = :id
            """),
            {"id": tentativa_demonstracao_id}
        ).scalar_one()

        assert ativo_demonstracao is False

        # ---------------------------------------------------------
        # 12. A tentativa da contratação deve continuar ativa.
        # ---------------------------------------------------------
        ativo_contratacao = db.execute(
            text("""
                SELECT ativo
                FROM tentativas_bateria
                WHERE id = :id
            """),
            {"id": tentativa_contratacao_id}
        ).scalar_one()

        assert ativo_contratacao is True

    finally:
        db.close()
        transacao.rollback()
        conexao.close()
        engine.dispose()
