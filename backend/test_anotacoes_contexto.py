import os
from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.main import (
    criar_anotacao_questao,
    listar_minhas_anotacoes,
    editar_anotacao_questao,
    excluir_anotacao_questao,
)


def test_anotacoes_isolam_contexto():
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
        # ---------------------------------------------------------
        # 3. Cria uma estrutura mínima para a questão de teste:
        #    disciplina -> assunto -> pasta -> aula -> bateria -> questão.
        # ---------------------------------------------------------
        disciplina_id = db.execute(
            text("""
                INSERT INTO curso_disciplinas_proprias
                    (curso_id, nome, ativo, ordem, disponivel_demonstracao)
                VALUES
                    (1, 'Disciplina Teste Anotacoes Contexto',
                     TRUE, 910, TRUE)
                RETURNING id
            """)
        ).scalar_one()

        assunto_id = db.execute(
            text("""
                INSERT INTO curso_assuntos_proprios
                    (curso_disciplina_propria_id, nome, ativo, ordem)
                VALUES
                    (:disciplina_id,
                     'Assunto Teste Anotacoes Contexto',
                     TRUE, 910)
                RETURNING id
            """),
            {"disciplina_id": disciplina_id}
        ).scalar_one()

        pasta_id = db.execute(
            text("""
                INSERT INTO pastas
                    (nome, tipo, curso_assunto_proprio_id)
                VALUES
                    ('Pasta Teste Anotacoes Contexto',
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
                     'Aula Teste Anotacoes Contexto',
                     910,
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
                     'Bateria Teste Anotacoes Contexto',
                     1,
                     'CONCLUIDA',
                     TRUE)
                RETURNING id
            """),
            {"aula_id": aula_id}
        ).scalar_one()

        questao_id = db.execute(
            text("""
                INSERT INTO questoes
                    (bateria_id, enunciado, tipo, gabarito)
                VALUES
                    (:bateria_id,
                     'Questão teste para isolamento de contexto das anotações.',
                     'CERTO_ERRADO',
                     'CERTO')
                RETURNING id
            """),
            {"bateria_id": bateria_id}
        ).scalar_one()

        # ---------------------------------------------------------
        # 4. Cria anotação no contexto da CONTRATAÇÃO.
        # ---------------------------------------------------------
        anotacao_contratacao = criar_anotacao_questao(
            payload={
                "questao_id": questao_id,
                "bateria_id": bateria_id,
                "texto": "Anotação criada no contexto da contratação.",
                "contratacao_id": contratacao_id,
                "demonstracao_id": None,
            },
            db=db,
            usuario_atual=usuario
        )

        # ---------------------------------------------------------
        # 5. Cria anotação no contexto da DEMONSTRAÇÃO.
        # ---------------------------------------------------------
        anotacao_demonstracao = criar_anotacao_questao(
            payload={
                "questao_id": questao_id,
                "bateria_id": bateria_id,
                "texto": "Anotação criada no contexto da demonstração.",
                "contratacao_id": None,
                "demonstracao_id": demonstracao_id,
            },
            db=db,
            usuario_atual=usuario
        )

        # ---------------------------------------------------------
        # 6. Confirma que cada anotação foi gravada no contexto
        #    correto.
        # ---------------------------------------------------------
        registro_contratacao = db.execute(
            text("""
                SELECT
                    contratacao_id,
                    demonstracao_id
                FROM anotacoes_aluno_questao
                WHERE id = :id
            """),
            {"id": anotacao_contratacao["id"]}
        ).mappings().one()

        assert registro_contratacao["contratacao_id"] == contratacao_id
        assert registro_contratacao["demonstracao_id"] is None

        registro_demonstracao = db.execute(
            text("""
                SELECT
                    contratacao_id,
                    demonstracao_id
                FROM anotacoes_aluno_questao
                WHERE id = :id
            """),
            {"id": anotacao_demonstracao["id"]}
        ).mappings().one()

        assert registro_demonstracao["contratacao_id"] is None
        assert registro_demonstracao["demonstracao_id"] == demonstracao_id

        # ---------------------------------------------------------
        # 7. A listagem da CONTRATAÇÃO deve mostrar somente sua
        #    própria anotação.
        # ---------------------------------------------------------
        lista_contratacao = listar_minhas_anotacoes(
            curso_id=1,
            contratacao_id=contratacao_id,
            demonstracao_id=None,
            db=db,
            usuario_atual=usuario
        )

        ids_contratacao = {
            item["anotacao_id"]
            for item in lista_contratacao
        }

        assert anotacao_contratacao["id"] in ids_contratacao
        assert anotacao_demonstracao["id"] not in ids_contratacao

        # ---------------------------------------------------------
        # 8. A listagem da DEMONSTRAÇÃO deve mostrar somente sua
        #    própria anotação.
        # ---------------------------------------------------------
        lista_demonstracao = listar_minhas_anotacoes(
            curso_id=1,
            contratacao_id=None,
            demonstracao_id=demonstracao_id,
            db=db,
            usuario_atual=usuario
        )

        ids_demonstracao = {
            item["anotacao_id"]
            for item in lista_demonstracao
        }

        assert anotacao_demonstracao["id"] in ids_demonstracao
        assert anotacao_contratacao["id"] not in ids_demonstracao

        # ---------------------------------------------------------
        # 9. A anotação da DEMONSTRAÇÃO não pode ser editada
        #    usando o contexto da CONTRATAÇÃO.
        # ---------------------------------------------------------
        try:
            editar_anotacao_questao(
                anotacao_id=anotacao_demonstracao["id"],
                payload={
                    "texto": "Tentativa indevida de alteração."
                },
                contratacao_id=contratacao_id,
                demonstracao_id=None,
                db=db,
                usuario_atual=usuario
            )
            assert False, (
                "A anotação da demonstração não deveria ser "
                "encontrada no contexto da contratação."
            )
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 404

        # ---------------------------------------------------------
        # 10. A anotação da DEMONSTRAÇÃO não pode ser excluída
        #     usando o contexto da CONTRATAÇÃO.
        # ---------------------------------------------------------
        try:
            excluir_anotacao_questao(
                anotacao_id=anotacao_demonstracao["id"],
                contratacao_id=contratacao_id,
                demonstracao_id=None,
                db=db,
                usuario_atual=usuario
            )
            assert False, (
                "A anotação da demonstração não deveria ser "
                "excluída no contexto da contratação."
            )
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 404

    finally:
        db.close()
        transacao.rollback()
        conexao.close()
        engine.dispose()
