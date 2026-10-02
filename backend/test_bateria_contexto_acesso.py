import os
from types import SimpleNamespace

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.main import concluir_bateria_aluno
from app.schemas import ConcluirBateriaCreate, RespostaQuestaoAlunoCreate


def test_concluir_bateria_grava_contexto_contratacao():
    assert os.getenv("AMBIENTE_TESTE") == "1"
    url = os.environ["DATABASE_URL"]
    assert "localhost" in url or "127.0.0.1" in url

    engine = create_engine(url)
    conexao = engine.connect()
    transacao = conexao.begin()
    db = Session(bind=conexao, join_transaction_mode="create_savepoint")

    try:
        usuario = SimpleNamespace(id=2)

        disciplina_id = db.execute(
            text("""
                INSERT INTO curso_disciplinas_proprias
                    (curso_id, nome, ativo, ordem, disponivel_demonstracao)
                VALUES
                    (1, 'Disciplina Teste Contexto', TRUE, 1, TRUE)
                RETURNING id
            """)
        ).scalar_one()

        assunto_id = db.execute(
            text("""
                INSERT INTO curso_assuntos_proprios
                    (curso_disciplina_propria_id, nome, ativo, ordem)
                VALUES
                    (:disciplina_id, 'Assunto Teste Contexto', TRUE, 1)
                RETURNING id
            """),
            {"disciplina_id": disciplina_id},
        ).scalar_one()

        pasta_id = db.execute(
            text("""
                INSERT INTO pastas
                    (curso_assunto_proprio_id, tipo, nome)
                VALUES
                    (:assunto_id, 'TEORIA', 'Teoria + Questões')
                RETURNING id
            """),
            {"assunto_id": assunto_id},
        ).scalar_one()

        aula_id = db.execute(
            text("""
                INSERT INTO aulas
                    (pasta_id, titulo, ordem, ativo)
                VALUES
                    (:pasta_id, 'Aula Teste Contexto', 1, TRUE)
                RETURNING id
            """),
            {"pasta_id": pasta_id},
        ).scalar_one()

        bateria_id = db.execute(
            text("""
                INSERT INTO baterias
                    (aula_id, titulo, ordem, status, ativo)
                VALUES
                    (:aula_id, 'Bateria Teste Contexto', 1, 'EM_ANDAMENTO', TRUE)
                RETURNING id
            """),
            {"aula_id": aula_id},
        ).scalar_one()

        questoes_ids = []

        for ordem in range(1, 11):
            questao_id = db.execute(
                text("""
                    INSERT INTO questoes
                        (bateria_id, enunciado, tipo, ordem, ativo, gabarito)
                    VALUES
                        (:bateria_id, :enunciado, 'MULTIPLA', :ordem, TRUE, 'A')
                    RETURNING id
                """),
                {
                    "bateria_id": bateria_id,
                    "enunciado": f"Questão de teste {ordem}",
                    "ordem": ordem,
                },
            ).scalar_one()

            questoes_ids.append(questao_id)

        db.flush()

        dados = ConcluirBateriaCreate(
            bateria_id=bateria_id,
            contratacao_id=1,
            demonstracao_id=None,
            respostas=[
                RespostaQuestaoAlunoCreate(
                    questao_id=questao_id,
                    resposta_marcada="A",
                    dificuldade="MEDIA",
                    rever=False,
                )
                for questao_id in questoes_ids
            ],
        )

        resultado = concluir_bateria_aluno(
            dados=dados,
            db=db,
            usuario_atual=usuario,
        )

        assert resultado["bateria_id"] == bateria_id
        assert resultado["usuario_id"] == 2
        assert resultado["percentual_acerto"] == 100

        tentativa = db.execute(
            text("""
                SELECT contratacao_id, demonstracao_id
                FROM tentativas_bateria
                WHERE id = :tentativa_id
            """),
            {"tentativa_id": resultado["id"]},
        ).mappings().one()

        assert tentativa["contratacao_id"] == 1
        assert tentativa["demonstracao_id"] is None

        respostas = db.execute(
            text("""
                SELECT contratacao_id, demonstracao_id
                FROM respostas_aluno_questoes
                WHERE tentativa_id = :tentativa_id
                ORDER BY id
            """),
            {"tentativa_id": resultado["id"]},
        ).mappings().all()

        assert len(respostas) == 10
        assert all(r["contratacao_id"] == 1 for r in respostas)
        assert all(r["demonstracao_id"] is None for r in respostas)

    finally:
        db.close()
        transacao.rollback()
        conexao.close()
        engine.dispose()
