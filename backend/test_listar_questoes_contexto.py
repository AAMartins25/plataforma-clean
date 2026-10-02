import os
from datetime import datetime, timedelta
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.main import listar_questoes_da_bateria


def preparar_estrutura(db):
    disciplina_id = db.execute(
        text("""
            INSERT INTO curso_disciplinas_proprias
                (curso_id, nome, ativo, ordem, disponivel_demonstracao)
            VALUES
                (1, 'Disciplina Teste Questões Contexto', TRUE, 1, TRUE)
            RETURNING id
        """)
    ).scalar_one()

    assunto_id = db.execute(
        text("""
            INSERT INTO curso_assuntos_proprios
                (curso_disciplina_propria_id, nome, ativo, ordem)
            VALUES
                (:disciplina_id, 'Assunto Teste Questões Contexto', TRUE, 1)
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
                (:pasta_id, 'Aula Teste Questões Contexto', 1, TRUE)
            RETURNING id
        """),
        {"pasta_id": pasta_id},
    ).scalar_one()

    bateria_id = db.execute(
        text("""
            INSERT INTO baterias
                (aula_id, titulo, ordem, status, ativo)
            VALUES
                (:aula_id, 'Bateria Teste Questões Contexto', 1,
                 'EM_ANDAMENTO', TRUE)
            RETURNING id
        """),
        {"aula_id": aula_id},
    ).scalar_one()

    questao_id = db.execute(
        text("""
            INSERT INTO questoes
                (bateria_id, enunciado, tipo, ordem, ativo,
                 tipo_questao, quantidade_alternativas, gabarito)
            VALUES
                (:bateria_id, 'Questão de teste', 'CERTO_ERRADO', 1, TRUE,
                 'CERTO_ERRADO', NULL, 'CERTO')
            RETURNING id
        """),
        {"bateria_id": bateria_id},
    ).scalar_one()

    return bateria_id, questao_id


def criar_db():
    url = os.environ["DATABASE_URL"]
    assert "localhost" in url or "127.0.0.1" in url

    engine = create_engine(url)
    conexao = engine.connect()
    transacao = conexao.begin()
    db = Session(bind=conexao, join_transaction_mode="create_savepoint")

    return engine, conexao, transacao, db


def test_listar_questoes_com_contratacao():
    assert os.getenv("AMBIENTE_TESTE") == "1"

    engine, conexao, transacao, db = criar_db()

    try:
        bateria_id, questao_id = preparar_estrutura(db)

        usuario = SimpleNamespace(id=2)

        resultado = listar_questoes_da_bateria(
            bateria_id=bateria_id,
            contratacao_id=1,
            demonstracao_id=None,
            db=db,
            usuario_atual=usuario,
        )

        assert len(resultado) == 1
        assert resultado[0]["id"] == questao_id
        assert resultado[0]["bateria_id"] == bateria_id
        assert resultado[0]["enunciado"] == "Questão de teste"

    finally:
        db.close()
        transacao.rollback()
        conexao.close()
        engine.dispose()


def test_listar_questoes_com_demonstracao():
    assert os.getenv("AMBIENTE_TESTE") == "1"

    engine, conexao, transacao, db = criar_db()

    try:
        bateria_id, questao_id = preparar_estrutura(db)

        usuario = SimpleNamespace(id=2)
        agora = datetime.utcnow()

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
                "inicio": agora - timedelta(minutes=1),
                "fim": agora + timedelta(hours=1),
                "liberado": agora + timedelta(days=30),
            },
        ).scalar_one()

        resultado = listar_questoes_da_bateria(
            bateria_id=bateria_id,
            contratacao_id=None,
            demonstracao_id=demonstracao_id,
            db=db,
            usuario_atual=usuario,
        )

        assert len(resultado) == 1
        assert resultado[0]["id"] == questao_id
        assert resultado[0]["bateria_id"] == bateria_id

    finally:
        db.close()
        transacao.rollback()
        conexao.close()
        engine.dispose()


def test_listar_questoes_sem_contexto():
    assert os.getenv("AMBIENTE_TESTE") == "1"

    engine, conexao, transacao, db = criar_db()

    try:
        bateria_id, _ = preparar_estrutura(db)

        usuario = SimpleNamespace(id=2)

        try:
            listar_questoes_da_bateria(
                bateria_id=bateria_id,
                contratacao_id=None,
                demonstracao_id=None,
                db=db,
                usuario_atual=usuario,
            )
            assert False, "Era esperada rejeição por falta de contexto"

        except HTTPException as exc:
            assert exc.status_code == 400
            assert "contexto" in exc.detail.lower()

    finally:
        db.close()
        transacao.rollback()
        conexao.close()
        engine.dispose()
