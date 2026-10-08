"""Listagem de assuntos com contexto real em SQLite descartável em memória."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models as m
from test_questoes_pratica_patch import carregar_main_isolado


@pytest.fixture
def ambiente():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    tabelas = [m.Curso.__table__, m.CursoDisciplinaPropria.__table__,
               m.CursoAssuntoProprio.__table__, m.ContratacaoCurso.__table__,
               m.DemonstracaoCurso.__table__]
    m.Base.metadata.create_all(engine, tables=tabelas)
    factory = sessionmaker(bind=engine)
    agora = datetime.utcnow()
    with factory() as db:
        db.add_all([m.Curso(id=1, nome="Original"), m.Curso(id=2, nome="Cópia")])
        db.add_all([
            m.CursoDisciplinaPropria(id=i, curso_id=1 if i < 4 else 2,
                                    nome=str(i), ordem=i)
            for i in range(1, 5)
        ])
        db.add_all([
            m.CursoAssuntoProprio(id=1, curso_disciplina_propria_id=1, nome="B", ordem=2),
            m.CursoAssuntoProprio(id=2, curso_disciplina_propria_id=1, nome="A", ordem=1),
            m.CursoAssuntoProprio(id=3, curso_disciplina_propria_id=1, nome="Inativo", ativo=False),
            m.CursoAssuntoProprio(id=4, curso_disciplina_propria_id=3, nome="Terceira"),
            m.CursoAssuntoProprio(id=5, curso_disciplina_propria_id=4, nome="Outro curso"),
        ])
        for modelo in (m.ContratacaoCurso, m.DemonstracaoCurso):
            for i, usuario_id, curso_id, expirado in (
                (1, 1, 1, False), (2, 2, 1, False),
                (3, 1, 2, False), (4, 1, 1, True)
            ):
                extras = ({"origem": "ADMIN"} if modelo is m.ContratacaoCurso
                          else {"liberado_novamente_em": agora, "ativo": True})
                db.add(modelo(
                    id=i, usuario_id=usuario_id, curso_id=curso_id,
                    data_inicio=agora - timedelta(days=2),
                    data_fim=agora + timedelta(days=-1 if expirado else 1), **extras
                ))
        db.commit()

    with carregar_main_isolado(factory, engine) as main:
        main.app.dependency_overrides[main.get_usuario_atual] = lambda: SimpleNamespace(
            id=1, is_admin=False
        )
        try:
            with TestClient(main.app) as client:
                yield main, client
        finally:
            main.app.dependency_overrides.clear()
            engine.dispose()


@pytest.mark.parametrize("disciplina_id,ids", [(1, [2, 1]), (4, [5])])
def test_admin_sem_contexto_dispensa_validador(ambiente, disciplina_id, ids):
    main, client = ambiente
    main.app.dependency_overrides[main.get_usuario_atual] = lambda: SimpleNamespace(
        id=1, is_admin=True
    )
    with patch.object(main, "validar_contexto_estudo", side_effect=AssertionError("Validador chamado")):
        resposta = client.get(f"/disciplinas-proprias/{disciplina_id}/assuntos-proprios")
    assert resposta.status_code == 200, resposta.text
    assert [item["id"] for item in resposta.json()] == ids
    assert set(resposta.json()[0]) == {
        "id", "curso_disciplina_propria_id", "nome", "descricao", "ativo", "ordem"
    }


@pytest.mark.parametrize("contexto", ["contratacao_id", "demonstracao_id"])
@pytest.mark.parametrize("identificador,status", [(1, 200), (2, 403), (3, 403), (4, 403), (999, 403)])
def test_aluno_valida_identidade_curso_vigencia(ambiente, contexto, identificador, status):
    _, client = ambiente
    resposta = client.get("/disciplinas-proprias/1/assuntos-proprios",
                          params={contexto: identificador})
    assert resposta.status_code == status, resposta.text
    if status == 200:
        assert [item["id"] for item in resposta.json()] == [2, 1]


@pytest.mark.parametrize("params", [{}, {"contratacao_id": 1, "demonstracao_id": 1}])
def test_aluno_exige_exatamente_um_contexto(ambiente, params):
    _, client = ambiente
    resposta = client.get("/disciplinas-proprias/1/assuntos-proprios", params=params)
    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Informe exatamente um contexto de acesso ao curso."


@pytest.mark.parametrize("contexto,status", [("contratacao_id", 200), ("demonstracao_id", 403)])
def test_terceira_disciplina_bloqueada_apenas_na_demonstracao(ambiente, contexto, status):
    _, client = ambiente
    resposta = client.get("/disciplinas-proprias/3/assuntos-proprios", params={contexto: 1})
    assert resposta.status_code == status, resposta.text


def test_admin_preserva_disciplina_inexistente(ambiente):
    main, client = ambiente
    main.app.dependency_overrides[main.get_usuario_atual] = lambda: SimpleNamespace(is_admin=True)
    resposta = client.get("/disciplinas-proprias/999/assuntos-proprios")
    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "Disciplina não encontrada"
