"""Contrato real da rota pública em banco local descartável, sem banco configurado."""
import os
from pathlib import Path
import subprocess
import threading
import socket
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import models as m
from test_questoes_pratica_patch import carregar_main_isolado

CAMPOS = {'id', 'nome', 'ativo', 'publicado', 'cargo', 'orgao', 'uf', 'ano'}

@pytest.fixture
def catalogo_publico():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    m.Base.metadata.create_all(engine, tables=[m.Usuario.__table__, m.Curso.__table__])
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add_all([
            m.Curso(id=39, nome='RESUMÃO PROF EDUC INFANTIL ALVORADA-RS 26', ativo=True, publicado=True,
                    cargo='Professor de Educação Infantil', orgao='Alvorada', uf='RS', ano=2026,
                    banca='Não expor', produtor_id=99, descricao_publica='Não expor'),
            m.Curso(id=40, nome='Curso parcial', ativo=True, publicado=True, orgao='Órgão confirmado', ano=2027),
            m.Curso(id=41, nome='Curso antigo sem metadados', ativo=True, publicado=True),
            m.Curso(id=42, nome='Outro cargo extenso', ativo=True, publicado=True, uf='SC', ano=2027,
                    cargo='Professor de Educação Infantil e Atendimento Educacional Especializado em Classes de Ensino Integral'),
            m.Curso(id=43, nome='Oculto inativo', ativo=False, publicado=True, cargo='Oculto'),
            m.Curso(id=44, nome='Oculto não publicado', ativo=True, publicado=False, cargo='Oculto'),
            m.Curso(id=45, nome='Oculto inativo e não publicado', ativo=False, publicado=False),
        ])
        db.commit()
    with carregar_main_isolado(factory, engine) as main:
        yield main, factory
        main.app.dependency_overrides.clear()
    engine.dispose()


def test_contrato_http_publico_compativel_e_somente_leitura(catalogo_publico):
    main, factory = catalogo_publico
    with factory() as db:
        antes = db.execute(m.Curso.__table__.select()).all()
    with TestClient(main.app) as client:
        # Sem autenticação: rota pública real, com consulta SQL e serialização FastAPI.
        response = client.get('/cursos-publicos')
        assert response.status_code == 200
        cursos = response.json()
        assert {c['id'] for c in cursos} == {39, 40, 41, 42}
        assert all(set(c) == CAMPOS for c in cursos)
        assert [c['nome'] for c in cursos] == sorted(c['nome'] for c in cursos)
        alvo = next(c for c in cursos if c['id'] == 39)
        assert alvo == dict(id=39, nome='RESUMÃO PROF EDUC INFANTIL ALVORADA-RS 26', ativo=True, publicado=True,
                            cargo='Professor de Educação Infantil', orgao='Alvorada', uf='RS', ano=2026)
        parcial = next(c for c in cursos if c['id'] == 40)
        assert parcial['orgao'] == 'Órgão confirmado' and parcial['ano'] == 2027
        assert parcial['cargo'] is None and parcial['uf'] is None
        antigo = next(c for c in cursos if c['id'] == 41)
        assert all(antigo[k] is None for k in ('cargo', 'orgao', 'uf', 'ano'))
        # O formato legado /cursos permanece inalterado.
        assert all(set(c) == {'id', 'nome', 'ativo'} for c in client.get('/cursos').json())
    with factory() as db:
        assert db.execute(m.Curso.__table__.select()).all() == antes


@pytest.mark.skipif(os.environ.get('PUBLIC_HOME_BROWSER') != '1', reason='Chromium opt-in')
def test_integracao_http_backend_frontend_chromium(catalogo_publico):
    import uvicorn
    from fastapi.staticfiles import StaticFiles
    main, _ = catalogo_publico
    root = Path(__file__).resolve().parents[1]
    main.app.mount('/', StaticFiles(directory=root / 'site-html', html=True), name='home-integracao')
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen()
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(main.app, log_level='warning', lifespan='off'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
    thread.start()
    try:
        for _ in range(200):
            if server.started: break
            time.sleep(.025)
        assert server.started
        result = subprocess.run(['node', str(root / 'site-html/test-home-api-real.cjs')],
            env={**os.environ, 'HOME_REAL_ORIGIN': f'http://127.0.0.1:{port}'},
            text=True, capture_output=True, timeout=150)
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
