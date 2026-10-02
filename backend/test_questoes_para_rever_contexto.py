import os
from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.main import listar_questoes_para_rever


def test_questoes_para_rever_isolam_contexto():
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
        #    disciplina -> assunto -> pasta -> aula -> bateria
        #    -> questão -> alternativa.
        # ---------------------------------------------------------
        disciplina_id = db.execute(
            text("""
                INSERT INTO curso_disciplinas_proprias
                    (curso_id, nome, ativo, ordem, disponivel_demonstracao)
                VALUES
                    (1, 'Disciplina Teste Questões Rever Contexto',
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
                     'Assunto Teste Questões Rever Contexto',
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
                    ('Pasta Teste Questões Rever Contexto',
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
                     'Aula Teste Questões Rever Contexto',
                     920, TRUE)
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
                     'Bateria Teste Questões Rever Contexto',
                     1, 'CONCLUIDA', TRUE)
                RETURNING id
            """),
            {"aula_id": aula_id}
        ).scalar_one()

        questao_id = db.execute(
            text("""
                INSERT INTO questoes
                    (bateria_id, enunciado, comentario, ordem,
                     tipo, tipo_questao, gabarito)
                VALUES
                    (:bateria_id,
                     'Questão teste para isolamento de contexto.',
                     'Comentário da questão de teste.',
                     1,
                     'MULTIPLA',
                     'MULTIPLA',
                     'A')
                RETURNING id
            """),
            {"bateria_id": bateria_id}
        ).scalar_one()

        db.execute(
            text("""
                INSERT INTO alternativas
                    (questao_id, letra, texto)
                VALUES
                    (:questao_id, 'A', 'Alternativa A'),
                    (:questao_id, 'B', 'Alternativa B')
            """),
            {"questao_id": questao_id}
        )

        # ---------------------------------------------------------
        # 4. Cria resposta marcada para REVER no contexto da
        #    CONTRATAÇÃO.
        # ---------------------------------------------------------
        resposta_contratacao_id = db.execute(
            text("""
                INSERT INTO respostas_aluno_questoes
                    (usuario_id, questao_id, bateria_id,
                     contratacao_id, demonstracao_id,
                     resposta_marcada, gabarito, acertou,
                     pulou, rever, dificuldade)
                VALUES
                    (2, :questao_id, :bateria_id,
                     :contratacao_id, NULL,
                     'A', 'A', TRUE,
                     FALSE, TRUE, 'FACIL')
                RETURNING id
            """),
            {
                "questao_id": questao_id,
                "bateria_id": bateria_id,
                "contratacao_id": contratacao_id
            }
        ).scalar_one()

        # ---------------------------------------------------------
        # 5. Cria resposta marcada para REVER no contexto da
        #    DEMONSTRAÇÃO.
        #
        #    É a mesma questão, mas uma resposta/contexto diferente.
        # ---------------------------------------------------------
        resposta_demonstracao_id = db.execute(
            text("""
                INSERT INTO respostas_aluno_questoes
                    (usuario_id, questao_id, bateria_id,
                     contratacao_id, demonstracao_id,
                     resposta_marcada, gabarito, acertou,
                     pulou, rever, dificuldade)
                VALUES
                    (2, :questao_id, :bateria_id,
                     NULL, :demonstracao_id,
                     'B', 'A', FALSE,
                     FALSE, TRUE, 'DIFICIL')
                RETURNING id
            """),
            {
                "questao_id": questao_id,
                "bateria_id": bateria_id,
                "demonstracao_id": demonstracao_id
            }
        ).scalar_one()

        db.flush()

        # ---------------------------------------------------------
        # 6. Listagem no contexto da CONTRATAÇÃO.
        # ---------------------------------------------------------
        lista_contratacao = listar_questoes_para_rever(
            contratacao_id=contratacao_id,
            demonstracao_id=None,
            db=db,
            usuario_atual=usuario
        )

        ids_contratacao = {
            item["resposta_id"]
            for item in lista_contratacao
        }

        assert resposta_contratacao_id in ids_contratacao
        assert resposta_demonstracao_id not in ids_contratacao

        # ---------------------------------------------------------
        # 7. Listagem no contexto da DEMONSTRAÇÃO.
        # ---------------------------------------------------------
        lista_demonstracao = listar_questoes_para_rever(
            contratacao_id=None,
            demonstracao_id=demonstracao_id,
            db=db,
            usuario_atual=usuario
        )

        ids_demonstracao = {
            item["resposta_id"]
            for item in lista_demonstracao
        }

        assert resposta_demonstracao_id in ids_demonstracao
        assert resposta_contratacao_id not in ids_demonstracao

        # ---------------------------------------------------------
        # 8. Não pode consultar sem contexto.
        # ---------------------------------------------------------
        try:
            listar_questoes_para_rever(
                contratacao_id=None,
                demonstracao_id=None,
                db=db,
                usuario_atual=usuario
            )
            assert False, (
                "A consulta deveria exigir um contexto de estudo."
            )
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 400

        # ---------------------------------------------------------
        # 9. Não pode informar os dois contextos simultaneamente.
        # ---------------------------------------------------------
        try:
            listar_questoes_para_rever(
                contratacao_id=contratacao_id,
                demonstracao_id=demonstracao_id,
                db=db,
                usuario_atual=usuario
            )
            assert False, (
                "A consulta não deveria aceitar contratação e "
                "demonstração simultaneamente."
            )
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 400

    finally:
        db.close()
        transacao.rollback()
        conexao.close()
        engine.dispose()
