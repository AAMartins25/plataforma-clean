import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.main import listar_disciplinas_proprias
from app.models import Usuario


def test_listar_disciplinas_proprias_isola_contexto():
    assert os.getenv("AMBIENTE_TESTE") == "1"

    url = os.environ["DATABASE_URL"]
    assert "localhost" in url or "127.0.0.1" in url

    engine = create_engine(url)
    conexao = engine.connect()
    transacao = conexao.begin()
    db = Session(bind=conexao, join_transaction_mode="create_savepoint")

    try:
        usuario_row = db.execute(
            text("""
                SELECT id
                FROM usuarios
                WHERE id = 2
            """)
        ).mappings().first()

        assert usuario_row is not None

        usuario = db.query(Usuario).filter(
            Usuario.id == 2
        ).first()

        assert usuario is not None

        # ---------------------------------------------------------
        # 1. Contratação ativa para o curso 1.
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
        # 2. Demonstração ativa para o curso 1.
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
        # 3. Disciplinas próprias do curso 1.
        #
        # Criamos três para verificar também a regra de
        # bloqueio na demonstração a partir da terceira.
        # ---------------------------------------------------------
        disciplina_ids = []

        for ordem, nome in [
            (991, "Disciplina Contexto 1"),
            (992, "Disciplina Contexto 2"),
            (993, "Disciplina Contexto 3"),
        ]:
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
                            :nome,
                            :ordem,
                            TRUE,
                            TRUE
                        )
                    RETURNING id
                """),
                {
                    "nome": nome,
                    "ordem": ordem
                }
            ).scalar_one()

            disciplina_ids.append(disciplina_id)

        db.flush()

        # ---------------------------------------------------------
        # 4. Contratação: deve retornar as três disciplinas e
        # nenhuma delas deve estar bloqueada.
        # ---------------------------------------------------------
        resultado_contratacao = listar_disciplinas_proprias(
            curso_id=1,
            contratacao_id=contratacao_id,
            demonstracao_id=None,
            db=db,
            usuario=usuario
        )

        disciplinas_contratacao = [
            d for d in resultado_contratacao
            if d["id"] in disciplina_ids
        ]

        assert len(disciplinas_contratacao) == 3

        assert all(
            d["bloqueada"] is False
            for d in disciplinas_contratacao
        )

        # ---------------------------------------------------------
        # 5. Demonstração: deve retornar as três disciplinas,
        # mas a partir da terceira a disciplina fica bloqueada.
        # ---------------------------------------------------------
        resultado_demonstracao = listar_disciplinas_proprias(
            curso_id=1,
            contratacao_id=None,
            demonstracao_id=demonstracao_id,
            db=db,
            usuario=usuario
        )

        disciplinas_demonstracao = [
            d for d in resultado_demonstracao
            if d["id"] in disciplina_ids
        ]

        assert len(disciplinas_demonstracao) == 3

        disciplinas_demonstracao.sort(key=lambda d: d["ordem"])

        assert disciplinas_demonstracao[0]["bloqueada"] is False
        assert disciplinas_demonstracao[1]["bloqueada"] is False
        assert disciplinas_demonstracao[2]["bloqueada"] is True

        # ---------------------------------------------------------
        # 6. Não pode informar os dois contextos simultaneamente.
        # ---------------------------------------------------------
        try:
            listar_disciplinas_proprias(
                curso_id=1,
                contratacao_id=contratacao_id,
                demonstracao_id=demonstracao_id,
                db=db,
                usuario=usuario
            )
            assert False, "Era esperado HTTP 400"
        except HTTPException as exc:
            assert exc.status_code == 400

        # ---------------------------------------------------------
        # 7. Não pode omitir o contexto.
        # ---------------------------------------------------------
        try:
            listar_disciplinas_proprias(
                curso_id=1,
                contratacao_id=None,
                demonstracao_id=None,
                db=db,
                usuario=usuario
            )
            assert False, "Era esperado HTTP 400"
        except HTTPException as exc:
            assert exc.status_code == 400

        # ---------------------------------------------------------
        # 8. Um curso diferente do curso do contexto deve ser
        # rejeitado.
        #
        # A contratação criada pertence ao curso 1.
        # ---------------------------------------------------------
        try:
            listar_disciplinas_proprias(
                curso_id=999999,
                contratacao_id=contratacao_id,
                demonstracao_id=None,
                db=db,
                usuario=usuario
            )
            assert False, "Era esperado HTTP 403"
        except HTTPException as exc:
            assert exc.status_code == 403

    finally:
        db.close()
        transacao.rollback()
        conexao.close()
        engine.dispose()
