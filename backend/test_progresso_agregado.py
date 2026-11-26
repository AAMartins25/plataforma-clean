"""Paridade do percentual e limite de consultas em SQLite descartável."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models as m
from test_questoes_pratica_patch import carregar_main_isolado


@pytest.fixture
def ambiente():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    # As verificações de acesso consultam também o histórico financeiro.
    # BTRIM é usado em uma restrição PostgreSQL reproduzida no SQLite isolado.
    with engine.connect() as conexao:
        conexao.connection.driver_connection.create_function(
            "BTRIM", 1, lambda valor: valor.strip() if valor is not None else None)
    m.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    agora = datetime.utcnow()
    with factory() as db:
        db.add_all([m.Curso(id=1, nome="Curso"), m.Curso(id=2, nome="Outro curso")])
        db.add_all([m.CursoDisciplinaPropria(id=i, curso_id=1, nome=str(i), ordem=i)
                    for i in range(1, 4)])
        db.add_all([m.CursoAssuntoProprio(id=i, curso_disciplina_propria_id=1 if i < 3 else 2,
                                          nome=str(i), ordem=i) for i in range(1, 4)])
        db.add_all([m.Pasta(id=i, curso_assunto_proprio_id=i, tipo="TEORIA", nome=str(i))
                    for i in range(1, 4)])
        db.add_all([m.Aula(id=i, pasta_id=1 if i < 3 else 2, titulo=str(i), ativo=True)
                    for i in range(1, 4)])
        db.add_all([m.Bateria(id=i, aula_id=i, titulo=str(i), status="CONCLUIDA", ativo=True)
                    for i in range(1, 4)])
        db.add_all([m.Bateria(id=8, aula_id=1, titulo="Rascunho", status="EM_ANDAMENTO", ativo=True),
                    m.Bateria(id=9, aula_id=1, titulo="Inativa", status="CONCLUIDA", ativo=False)])
        db.add_all([m.ContratacaoCurso(id=1, usuario_id=1, curso_id=1, origem="ADMIN",
                                      data_inicio=agora-timedelta(days=1)),
                    m.ContratacaoCurso(id=2, usuario_id=2, curso_id=1, origem="ADMIN",
                                      data_inicio=agora-timedelta(days=1)),
                    m.ContratacaoCurso(id=3, usuario_id=1, curso_id=1, origem="ADMIN",
                                      data_inicio=agora-timedelta(days=2),
                                      data_fim=agora-timedelta(days=1)),
                    m.ContratacaoCurso(id=4, usuario_id=1, curso_id=2, origem="ADMIN",
                                      data_inicio=agora-timedelta(days=1)),
                    m.DemonstracaoCurso(id=1, usuario_id=1, curso_id=1, ativo=True,
                                        data_inicio=agora-timedelta(days=1),
                                        data_fim=agora+timedelta(days=1),
                                        liberado_novamente_em=agora),
                    m.DemonstracaoCurso(id=2, usuario_id=1, curso_id=1, ativo=True,
                                        data_inicio=agora-timedelta(days=2),
                                        data_fim=agora-timedelta(days=1),
                                        liberado_novamente_em=agora),
                    m.DemonstracaoCurso(id=3, usuario_id=2, curso_id=1, ativo=True,
                                        data_inicio=agora-timedelta(days=1),
                                        data_fim=agora+timedelta(days=1),
                                        liberado_novamente_em=agora),
                    m.AcessoCurso(id=1, usuario_id=1, curso_id=1, ativo=True)])
        db.add_all([
            m.TentativaBateria(id=1, usuario_id=1, bateria_id=1, contratacao_id=1, status="FEITA", ativo=True),
            m.TentativaBateria(id=2, usuario_id=1, bateria_id=2, contratacao_id=1, status="FEITA", ativo=True),
            m.TentativaBateria(id=3, usuario_id=1, bateria_id=2, contratacao_id=1, status="EM_ANDAMENTO", ativo=True),
            m.TentativaBateria(id=4, usuario_id=1, bateria_id=3, contratacao_id=1, revisao_id=4, status="FEITA", ativo=True),
            m.TentativaBateria(id=5, usuario_id=2, bateria_id=3, contratacao_id=2, status="FEITA", ativo=True),
            m.TentativaBateria(id=6, usuario_id=1, bateria_id=3, demonstracao_id=1, status="FEITA", ativo=True),
            m.TentativaBateria(id=7, usuario_id=1, bateria_id=2, contratacao_id=1, status="FEITA", ativo=False),
        ])
        db.commit()
    with carregar_main_isolado(factory, engine) as main:
        yield main, engine, factory, SimpleNamespace(id=1, is_admin=False)
    engine.dispose()


@pytest.mark.parametrize("contexto,assuntos_esperados,disciplina_esperada", [
    ({"contratacao_id": 1}, [100, 0], 67),
    ({"demonstracao_id": 1}, [0, 100], 33),
])
def test_progresso_preserva_conclusoes_por_contexto(ambiente, contexto, assuntos_esperados, disciplina_esperada):
    main, _, factory, usuario = ambiente
    with factory() as db:
        assuntos = main.progresso_assuntos_agregado(1, db=db, usuario=usuario, **contexto)
        assert [x["percentual"] for x in assuntos["percentuais"]] == assuntos_esperados
        curso = main.progresso_disciplinas_agregado(1, db=db, usuario=usuario, **contexto)
        assert [x["percentual"] for x in curso["percentuais"]] == [disciplina_esperada, 0, 0]


def test_contexto_permissoes_e_demo_bloqueada(ambiente):
    main, _, factory, usuario = ambiente
    with factory() as db:
        for contexto, codigo in (({}, 400), ({"contratacao_id": 1, "demonstracao_id": 1}, 400),
                                 ({"contratacao_id": 2}, 403), ({"contratacao_id": 3}, 403),
                                 ({"contratacao_id": 4}, 403), ({"demonstracao_id": 2}, 403),
                                 ({"demonstracao_id": 3}, 403)):
            with pytest.raises(HTTPException) as erro:
                main.progresso_assuntos_agregado(1, db=db, usuario=usuario, **contexto)
            assert erro.value.status_code == codigo
        with pytest.raises(HTTPException) as erro:
            main.progresso_assuntos_agregado(3, demonstracao_id=1, db=db, usuario=usuario)
        assert erro.value.status_code == 403
        resposta = main.progresso_disciplinas_agregado(1, demonstracao_id=1, db=db, usuario=usuario)
        assert resposta["percentuais"][-1] == {"disciplina_id": 3, "percentual": 0}


@pytest.mark.parametrize("tipo_admin,is_admin", [("admin_geral", True), ("admin_prod", False)])
def test_administrador_de_producao_so_ve_progresso_do_proprio_contexto(
    ambiente, tipo_admin, is_admin
):
    main, _, factory, _ = ambiente
    usuario = SimpleNamespace(id=1, is_admin=is_admin, tipo_admin=tipo_admin, ativo=True)
    rotas = ((main.progresso_disciplinas_agregado, 1),
             (main.progresso_assuntos_agregado, 1))
    with factory() as db:
        for rota, identificador in rotas:
            for contexto in ({"contratacao_id": 2}, {"contratacao_id": 4},
                             {"demonstracao_id": 2}, {"demonstracao_id": 3}):
                with pytest.raises(HTTPException) as erro:
                    rota(identificador, db=db, usuario=usuario, **contexto)
                assert erro.value.status_code == 403
            sem_contexto = rota(identificador, db=db, usuario=usuario)
            assert all(item["percentual"] == 0 for item in sem_contexto["percentuais"])
            proprio = rota(identificador, contratacao_id=1, db=db, usuario=usuario)
            assert any(item["percentual"] > 0 for item in proprio["percentuais"])
            demo_propria = rota(identificador, demonstracao_id=1, db=db, usuario=usuario)
            assert any(item["percentual"] > 0 for item in demo_propria["percentuais"])


@pytest.mark.parametrize("tipo_admin,is_admin", [("admin_adm", False), ("admin_prod", True)])
def test_perfil_sem_permissao_de_producao_nao_ignora_contexto(ambiente, tipo_admin, is_admin):
    main, _, factory, _ = ambiente
    usuario = SimpleNamespace(id=1, is_admin=is_admin, tipo_admin=tipo_admin, ativo=True)
    with factory() as db:
        for rota in (main.progresso_disciplinas_agregado, main.progresso_assuntos_agregado):
            for contexto, esperado in (({}, 400), ({"contratacao_id": 2}, 403)):
                with pytest.raises(HTTPException) as erro:
                    rota(1, db=db, usuario=usuario, **contexto)
                assert erro.value.status_code == esperado


def test_numero_de_selects_nao_cresce_com_conteudo(ambiente):
    main, engine, factory, usuario = ambiente
    sql = []
    def observar(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().lower().startswith(("select", "with")):
            sql.append(statement)
    event.listen(engine, "before_cursor_execute", observar)
    try:
        with factory() as db:
            main.progresso_disciplinas_agregado(1, contratacao_id=1, db=db, usuario=usuario)
        base = len(sql)
        sql.clear()
        with factory() as db:
            for i in range(10, 35):
                db.add(m.CursoAssuntoProprio(id=i, curso_disciplina_propria_id=1, nome=str(i)))
                db.add(m.Pasta(id=i, curso_assunto_proprio_id=i, tipo="TEORIA", nome=str(i)))
                db.add(m.Aula(id=i, pasta_id=i, titulo=str(i)))
                db.add(m.Bateria(id=i, aula_id=i, titulo=str(i), status="CONCLUIDA"))
            db.commit()
        with factory() as db:
            main.progresso_disciplinas_agregado(1, contratacao_id=1, db=db, usuario=usuario)
        assert len(sql) == base
        assert base <= 7
        assert not any("FROM questoes" in consulta for consulta in sql)
    finally:
        event.remove(engine, "before_cursor_execute", observar)


def test_http_rotas_exigem_autenticacao_e_contexto(ambiente):
    main, _, _, usuario = ambiente
    client = TestClient(main.app)
    caminho = "/me/cursos/1/progresso-disciplinas"
    assert client.get(caminho, params={"contratacao_id": 1}).status_code == 401
    main.app.dependency_overrides[main.get_usuario_atual] = lambda: usuario
    try:
        resposta = client.get(caminho, params={"contratacao_id": 1})
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["percentuais"][0]["percentual"] == 67
        resposta = client.get("/me/disciplinas-proprias/1/progresso-assuntos",
                             params={"demonstracao_id": 1})
        assert resposta.status_code == 200, resposta.text
        assert [item["percentual"] for item in resposta.json()["percentuais"]] == [0, 100]
    finally:
        main.app.dependency_overrides.clear()


def test_http_admin_prod_nao_consulta_progresso_de_outro_aluno(ambiente):
    main, _, _, _ = ambiente
    usuario = SimpleNamespace(id=1, is_admin=False, tipo_admin="admin_prod", ativo=True)
    client = TestClient(main.app)
    main.app.dependency_overrides[main.get_usuario_atual] = lambda: usuario
    try:
        for caminho in ("/me/cursos/1/progresso-disciplinas",
                        "/me/disciplinas-proprias/1/progresso-assuntos"):
            assert client.get(caminho, params={"contratacao_id": 2}).status_code == 403
            assert client.get(caminho, params={"demonstracao_id": 3}).status_code == 403
            assert client.get(caminho, params={"contratacao_id": 1}).status_code == 200
            sem_contexto = client.get(caminho)
            assert sem_contexto.status_code == 200
            assert all(item["percentual"] == 0
                       for item in sem_contexto.json()["percentuais"])
    finally:
        main.app.dependency_overrides.clear()
