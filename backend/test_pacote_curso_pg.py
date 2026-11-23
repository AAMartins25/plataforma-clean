"""Executar somente com o PostgreSQL descartável e sem rede deste teste."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import os
import uuid
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app import models as m
from app.pacote_curso import importar_pacote
from test_importacao_cursos import documento
from test_pacote_curso import Storage, preparar_fluxo


@pytest.fixture
def pg_zip():
    socket = os.environ.get('ZIP_TEST_SOCKET', '/tmp/resumao-zip-pg-socket')
    if not os.path.exists(socket + '/.s.PGSQL.5432'):
        pytest.skip('PostgreSQL descartável não está disponível')
    url = 'postgresql+psycopg://postgres@/resumao_zip_test?host=' + socket
    base = create_engine(url)
    esquema = 'zip_' + uuid.uuid4().hex
    with base.begin() as conn:
        conn.execute(text('CREATE SCHEMA ' + esquema))
    engine = create_engine(url, connect_args={'options': '-csearch_path=' + esquema + ' -clock_timeout=10000'})
    factory = sessionmaker(bind=engine, autoflush=False)
    try:
        m.Base.metadata.create_all(engine)
        with factory() as db:
            db.add(m.Usuario(id=1, nome='Admin', email='admin@teste.local', senha_hash='teste', cpf='1', telefone='0'))
            db.commit()
        yield factory
    finally:
        engine.dispose()
        with base.begin() as conn:
            conn.execute(text('DROP SCHEMA ' + esquema + ' CASCADE'))
        base.dispose()


def test_duas_importacoes_concorrentes_sao_idempotentes(pg_zip, documento):
    bruto, convertido = preparar_fluxo(documento)
    storage = Storage()
    barreira = Barrier(2)
    def executar():
        with pg_zip() as db:
            barreira.wait(timeout=10)
            return importar_pacote(db, 1, 'chaveconcorrente123456', bruto, convertido, storage)
    with ThreadPoolExecutor(max_workers=2) as executor:
        resultados = list(executor.map(lambda _: executar(), range(2)))
    assert sorted(x['repetida'] for x in resultados) == [False, True]
    assert resultados[0]['curso_id'] == resultados[1]['curso_id']
    assert len(storage.objetos) == 1
    with pg_zip() as db:
        assert db.query(m.Curso).count() == 1
        assert db.query(m.ImagemTeoria).count() == 1
        assert db.query(m.ImagemTeoriaMaterial).count() == 1
        assert db.query(m.ImagemQuestao).count() == 1


def test_http_preparar_importar_e_autorizacao(pg_zip, documento, monkeypatch):
    import asyncio
    import json
    import httpx2 as httpx
    from types import SimpleNamespace
    from test_questoes_pratica_patch import carregar_main_isolado
    import app.imagens_storage
    from app.imagens import obter_storage_imagens as dependencia_storage
    from app.pausa_financeira import metadata, controle, agora

    bruto, convertido = preparar_fluxo(documento)
    storage = Storage()
    monkeypatch.setattr(app.imagens_storage, 'obter_storage_imagens', lambda: storage)
    engine = pg_zip.kw['bind']
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(controle.insert().values(id=1, modo='NORMAL', geracao=0, alterado_em=agora(), motivo='teste'))
    with carregar_main_isolado(pg_zip, engine) as main:
        main.app.dependency_overrides[dependencia_storage] = lambda: storage
        main.app.dependency_overrides[main.get_usuario_atual] = lambda: SimpleNamespace(id=1, is_admin=True, tipo_admin='admin_geral')
        monkeypatch.setattr(main, 'validar_aceite', lambda *args: None)
        monkeypatch.setattr(main.requests, 'post', lambda *args, **kwargs: pytest.fail('Checkout chamou serviço externo'))
        async def teste():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://local') as client:
                r = await client.post('/admin/importacoes/cursos/pacote/preparar', files={'arquivo': ('curso.zip', bruto, 'application/zip')})
                assert r.status_code == 200, r.text
                assert r.json()['original']['curso']['nome'] == documento['curso']['nome']
                r = await client.post('/admin/importacoes/cursos/pacote/importar', data={'chave':'1234567890abcdef'}, files={
                    'arquivo': ('curso.zip', bruto, 'application/zip'),
                    'convertido': ('convertido.json', json.dumps(convertido), 'application/json')})
                assert r.status_code == 200, r.text
                assert not r.json()['repetida']
                curso_id = r.json()['curso_id']
                publicacao = await client.put(f'/admin/cursos/{curso_id}/publicar', json={})
                assert publicacao.status_code == 409
                from datetime import datetime, timedelta
                with pg_zip() as db:
                    curso = db.get(m.Curso, curso_id)
                    assert not curso.publicado and curso.precos_provisorios
                    assert [(x.meses, x.valor_cents) for x in db.query(m.TempoAcessoCurso).filter_by(curso_id=curso_id).order_by(m.TempoAcessoCurso.meses)] == [(4,4),(8,8),(12,12)]
                    tempo_id = db.query(m.TempoAcessoCurso.id).filter_by(curso_id=curso_id, meses=4).one()[0]
                    assert db.query(m.ContratacaoCurso).count() == 0
                    db.add(m.Usuario(id=2, nome='Aluno', email='aluno@teste.local', senha_hash='teste', cpf='2', telefone='0'))
                    contrato = m.ContratacaoCurso(usuario_id=2, curso_id=curso_id, origem='ADMIN',
                        data_inicio=datetime.utcnow()-timedelta(days=1), data_fim=datetime.utcnow()+timedelta(days=1))
                    db.add(contrato); db.flush()
                    contrato_id = contrato.id
                    aula_id = db.query(m.Aula.id).one()[0]
                    bateria_id = db.query(m.Bateria.id).order_by(m.Bateria.id).first()[0]
                    imagem_id = db.query(m.ImagemTeoria.id).one()[0]
                    db.commit()
                main.app.dependency_overrides[main.get_usuario_atual] = lambda: SimpleNamespace(id=2, email='aluno@teste.local', is_admin=False, tipo_admin=None)
                checkout = await client.post('/checkout/mercadopago', json={'tempo_acesso_id':tempo_id})
                assert checkout.status_code == 409 and 'provisórios' in checkout.text
                for path in (f'/aulas/{aula_id}/imagens/assinaturas', f'/baterias/{bateria_id}/imagens/assinaturas'):
                    liberada = await client.post(path, params={'contratacao_id':contrato_id}, json={'ids':[imagem_id]})
                    assert liberada.status_code == 200, liberada.text
                    negada = await client.post(path, json={'ids':[imagem_id]})
                    assert negada.status_code in (400, 403)
                main.app.dependency_overrides[main.get_usuario_atual] = lambda: SimpleNamespace(id=1, is_admin=False, tipo_admin=None)
                r = await client.post('/admin/importacoes/cursos/pacote/preparar', files={'arquivo': ('curso.zip', bruto, 'application/zip')})
                assert r.status_code == 403
        asyncio.run(teste())
