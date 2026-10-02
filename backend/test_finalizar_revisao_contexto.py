import os
from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.main import (
    finalizar_revisao_tentativa,
    listar_minhas_revisoes,
    concluir_revisao,
)


def test_finalizar_revisao_isola_contexto():
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
        # 3. Cria uma estrutura mínima:
        #    disciplina -> assunto -> pasta -> aula -> 2 baterias.
        # ---------------------------------------------------------
        disciplina_id = db.execute(
            text("""
                INSERT INTO curso_disciplinas_proprias
                    (curso_id, nome, ativo, ordem, disponivel_demonstracao)
                VALUES
                    (1, 'Disciplina Teste Finalizacao Contexto',
                     TRUE, 900, TRUE)
                RETURNING id
            """)
        ).scalar_one()

        assunto_id = db.execute(
            text("""
                INSERT INTO curso_assuntos_proprios
                    (curso_disciplina_propria_id, nome, ativo, ordem)
                VALUES
                    (:disciplina_id,
                     'Assunto Teste Finalizacao Contexto',
                     TRUE, 900)
                RETURNING id
            """),
            {"disciplina_id": disciplina_id}
        ).scalar_one()

        pasta_id = db.execute(
            text("""
                INSERT INTO pastas
                    (nome, tipo, curso_assunto_proprio_id)
                VALUES
                    ('Pasta Teste Finalizacao Contexto', 'TEORIA', :assunto_id)
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
                     'Aula Teste Finalizacao Contexto',
                     900, TRUE)
                RETURNING id
            """),
            {"pasta_id": pasta_id}
        ).scalar_one()

        bateria_1_id = db.execute(
            text("""
                INSERT INTO baterias
                    (aula_id, titulo, ordem, status, ativo)
                VALUES
                    (:aula_id, 'Bateria 1 Teste', 1,
                     'CONCLUIDA', TRUE)
                RETURNING id
            """),
            {"aula_id": aula_id}
        ).scalar_one()

        bateria_2_id = db.execute(
            text("""
                INSERT INTO baterias
                    (aula_id, titulo, ordem, status, ativo)
                VALUES
                    (:aula_id, 'Bateria 2 Teste', 2,
                     'CONCLUIDA', TRUE)
                RETURNING id
            """),
            {"aula_id": aula_id}
        ).scalar_one()

        # ---------------------------------------------------------
        # 4. Tentativa da bateria 1:
        #    feita no contexto da CONTRATAÇÃO.
        # ---------------------------------------------------------
        tentativa_contratacao_id = db.execute(
            text("""
                INSERT INTO tentativas_bateria
                    (usuario_id, bateria_id,
                     contratacao_id, demonstracao_id,
                     status, percentual_acerto, ativo)
                VALUES
                    (2, :bateria_id,
                     :contratacao_id, NULL,
                     'FEITA', 100, TRUE)
                RETURNING id
            """),
            {
                "bateria_id": bateria_1_id,
                "contratacao_id": contratacao_id,
            }
        ).scalar_one()

        # ---------------------------------------------------------
        # 5. Tentativa da bateria 2:
        #    ainda em andamento no contexto da DEMONSTRAÇÃO.
        # ---------------------------------------------------------
        tentativa_demonstracao_id = db.execute(
            text("""
                INSERT INTO tentativas_bateria
                    (usuario_id, bateria_id,
                     contratacao_id, demonstracao_id,
                     status, percentual_acerto, ativo)
                VALUES
                    (2, :bateria_id,
                     NULL, :demonstracao_id,
                     'EM_ANDAMENTO', 0, TRUE)
                RETURNING id
            """),
            {
                "bateria_id": bateria_2_id,
                "demonstracao_id": demonstracao_id,
            }
        ).scalar_one()

        db.flush()

        # ---------------------------------------------------------
        # 6. Finaliza a bateria 2.
        # ---------------------------------------------------------
        resultado = finalizar_revisao_tentativa(
            tentativa_id=tentativa_demonstracao_id,
            db=db,
            usuario_atual=usuario
        )

        assert resultado["id"] == tentativa_demonstracao_id
        assert resultado["status"] == "FEITA"

        # ---------------------------------------------------------
        # 7. A contratação NÃO pode contaminar a demonstração.
        #
        # Neste momento:
        # - bateria 1 = FEITA na contratação;
        # - bateria 2 = FEITA na demonstração;
        #
        # Portanto, a aula ainda NÃO deve estar concluída
        # no contexto da demonstração.
        # ---------------------------------------------------------
        progresso = db.execute(
            text("""
                SELECT
                    contratacao_id,
                    demonstracao_id,
                    concluida
                FROM progresso_aulas
                WHERE usuario_id = 2
                  AND aula_id = :aula_id
                  AND demonstracao_id = :demonstracao_id
                ORDER BY id DESC
                LIMIT 1
            """),
            {
                "aula_id": aula_id,
                "demonstracao_id": demonstracao_id
            }
        ).mappings().first()

        assert progresso is None

        # ---------------------------------------------------------
        # 8. Agora cria a conclusão da bateria 1 também no contexto
        #    da demonstração.
        # ---------------------------------------------------------
        tentativa_bateria_1_demonstracao_id = db.execute(
            text("""
                INSERT INTO tentativas_bateria
                    (usuario_id, bateria_id,
                     contratacao_id, demonstracao_id,
                     status, percentual_acerto, ativo)
                VALUES
                    (2, :bateria_id,
                     NULL, :demonstracao_id,
                     'FEITA', 100, TRUE)
                RETURNING id
            """),
            {
                "bateria_id": bateria_1_id,
                "demonstracao_id": demonstracao_id
            }
        ).scalar_one()

        db.flush()

        # ---------------------------------------------------------
        # 9. Finaliza a revisão da bateria 1 no contexto da
        #    demonstração.
        # ---------------------------------------------------------
        resultado_bateria_1 = finalizar_revisao_tentativa(
            tentativa_id=tentativa_bateria_1_demonstracao_id,
            db=db,
            usuario_atual=usuario
        )

        assert resultado_bateria_1["id"] == tentativa_bateria_1_demonstracao_id
        assert resultado_bateria_1["status"] == "FEITA"

        # ---------------------------------------------------------
        # 10. Agora as duas baterias estão feitas na demonstração.
        #     A aula deve ser concluída nesse contexto.
        # ---------------------------------------------------------
        progresso = db.execute(
            text("""
                SELECT
                    contratacao_id,
                    demonstracao_id,
                    concluida
                FROM progresso_aulas
                WHERE usuario_id = 2
                  AND aula_id = :aula_id
                  AND demonstracao_id = :demonstracao_id
                ORDER BY id DESC
                LIMIT 1
            """),
            {
                "aula_id": aula_id,
                "demonstracao_id": demonstracao_id
            }
        ).mappings().first()

        assert progresso is not None

        assert progresso["demonstracao_id"] == demonstracao_id
        assert progresso["contratacao_id"] is None
        assert progresso["concluida"] is True

        # ---------------------------------------------------------
        # 11. Verifica a revisão criada no mesmo contexto.
        # ---------------------------------------------------------
        revisao = db.execute(
            text("""
                SELECT
                    id,
                    contratacao_id,
                    demonstracao_id,
                    aula_id,
                    etapa
                FROM revisoes_aluno
                WHERE usuario_id = 2
                AND aula_id = :aula_id
                AND demonstracao_id = :demonstracao_id
                ORDER BY id DESC
                LIMIT 1
            """),
            {
                "aula_id": aula_id,
                "demonstracao_id": demonstracao_id
            }
        ).mappings().first()

        assert revisao is not None

        assert revisao["demonstracao_id"] == demonstracao_id
        assert revisao["contratacao_id"] is None
        assert revisao["etapa"] == 1

        # ---------------------------------------------------------
        # 12. Cria uma revisão pendente no contexto da CONTRATAÇÃO.
        # ---------------------------------------------------------
        revisao_contratacao_id = db.execute(
            text("""
                INSERT INTO revisoes_aluno
                    (usuario_id, aula_id, pasta_id,
                     contratacao_id, demonstracao_id,
                     etapa, data_prevista, concluida)
                VALUES
                    (2, :aula_id, :pasta_id,
                     :contratacao_id, NULL,
                     1, :data_prevista, FALSE)
                RETURNING id
            """),
            {
                "aula_id": aula_id,
                "pasta_id": pasta_id,
                "contratacao_id": contratacao_id,
                "data_prevista": agora
            }
        ).scalar_one()

        # ---------------------------------------------------------
        # 13. Lista revisões no contexto da CONTRATAÇÃO.
        #     Deve aparecer somente a revisão da contratação.
        # ---------------------------------------------------------
        revisoes_contratacao = listar_minhas_revisoes(
            contratacao_id=contratacao_id,
            demonstracao_id=None,
            db=db,
            usuario_atual=usuario
        )

        ids_contratacao = {
            r["id"]
            for r in revisoes_contratacao
        }

        assert revisao_contratacao_id in ids_contratacao

        for r in revisoes_contratacao:
            revisao_db = db.execute(
                text("""
                    SELECT contratacao_id, demonstracao_id
                    FROM revisoes_aluno
                    WHERE id = :id
                """),
                {"id": r["id"]}
            ).mappings().one()

            assert revisao_db["contratacao_id"] == contratacao_id
            assert revisao_db["demonstracao_id"] is None

        # ---------------------------------------------------------
        # 14. Lista revisões no contexto da DEMONSTRAÇÃO.
        #     Não pode aparecer a revisão da contratação.
        # ---------------------------------------------------------
        revisoes_demonstracao = listar_minhas_revisoes(
            contratacao_id=None,
            demonstracao_id=demonstracao_id,
            db=db,
            usuario_atual=usuario
        )

        ids_demonstracao = {
            r["id"]
            for r in revisoes_demonstracao
        }

        assert revisao_contratacao_id not in ids_demonstracao

        for r in revisoes_demonstracao:
            revisao_db = db.execute(
                text("""
                    SELECT contratacao_id, demonstracao_id
                    FROM revisoes_aluno
                    WHERE id = :id
                """),
                {"id": r["id"]}
            ).mappings().one()

            assert revisao_db["contratacao_id"] is None
            assert revisao_db["demonstracao_id"] == demonstracao_id

        # ---------------------------------------------------------
        # 15. Conclui a revisão da DEMONSTRAÇÃO.
        # ---------------------------------------------------------
        resultado_revisao = concluir_revisao(
            revisao_id=revisao["id"],
            contratacao_id=None,
            demonstracao_id=demonstracao_id,
            db=db,
            usuario_atual=usuario
        )

        assert resultado_revisao["ok"] is True

        # ---------------------------------------------------------
        # 16. A revisão original da demonstração deve estar
        #     concluída.
        # ---------------------------------------------------------
        revisao_concluida = db.execute(
            text("""
                SELECT
                    concluida,
                    contratacao_id,
                    demonstracao_id,
                    etapa
                FROM revisoes_aluno
                WHERE id = :id
            """),
            {"id": revisao["id"]}
        ).mappings().one()

        assert revisao_concluida["concluida"] is True
        assert revisao_concluida["contratacao_id"] is None
        assert revisao_concluida["demonstracao_id"] == demonstracao_id
        assert revisao_concluida["etapa"] == 1

        # ---------------------------------------------------------
        # 17. A próxima etapa deve permanecer no contexto da
        #     DEMONSTRAÇÃO.
        # ---------------------------------------------------------
        proxima_revisao = db.execute(
            text("""
                SELECT
                    contratacao_id,
                    demonstracao_id,
                    etapa,
                    concluida
                FROM revisoes_aluno
                WHERE usuario_id = 2
                  AND aula_id = :aula_id
                  AND demonstracao_id = :demonstracao_id
                  AND etapa = 2
                ORDER BY id DESC
                LIMIT 1
            """),
            {
                "aula_id": aula_id,
                "demonstracao_id": demonstracao_id
            }
        ).mappings().first()

        assert proxima_revisao is not None
        assert proxima_revisao["contratacao_id"] is None
        assert proxima_revisao["demonstracao_id"] == demonstracao_id
        assert proxima_revisao["etapa"] == 2
        assert proxima_revisao["concluida"] is False

        # ---------------------------------------------------------
        # 18. Não pode concluir essa revisão usando o contexto
        #     da CONTRATAÇÃO.
        # ---------------------------------------------------------
        try:
            concluir_revisao(
                revisao_id=revisao["id"],
                contratacao_id=contratacao_id,
                demonstracao_id=None,
                db=db,
                usuario_atual=usuario
            )
            assert False, (
                "A revisão da demonstração não deveria ser "
                "encontrada no contexto da contratação."
            )
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 404

    finally:
        db.close()
        transacao.rollback()
        conexao.close()
        engine.dispose()
