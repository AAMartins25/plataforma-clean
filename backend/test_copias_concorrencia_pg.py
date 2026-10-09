"""Concorrência real: exige PostgreSQL local descartável com nome copias_test_*."""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app import models as m, schemas
from test_aulas_admin import ambiente
from test_copiar_conteudo import copia, snapshot, HISTORICO
from test_questoes_pratica_patch import carregar_main_isolado


@pytest.fixture(scope='module')
def infraestrutura():
    endereco=os.getenv('COPIAS_TEST_DATABASE_URL')
    if not endereco:
        pytest.skip('Defina COPIAS_TEST_DATABASE_URL para um PostgreSQL descartável local')
    url=make_url(endereco)
    assert url.host in ('localhost','127.0.0.1') and url.database.startswith('copias_test_')
    assert url.get_backend_name()=='postgresql'
    engine=create_engine(url,connect_args={'options':'-c lock_timeout=10000 -c statement_timeout=20000'})
    factory=sessionmaker(bind=engine,autoflush=False)
    with carregar_main_isolado(factory,engine) as main:
        try:yield main,engine,factory
        finally:
            main.app.dependency_overrides.clear()
            engine.dispose()


def copiar(main,factory,tipo,origem=1,destino=2,barreira=None):
    if barreira:barreira.wait(timeout=10)
    with factory() as db:
        usuario=SimpleNamespace(id=1,is_admin=True)
        if tipo=='disciplina':
            return main.copiar_disciplina_entre_cursos(origem,schemas.CopiarDisciplinaRequest(curso_destino_id=destino),db,usuario)
        return main.copiar_assunto_entre_disciplinas(origem,schemas.CopiarAssuntoRequest(disciplina_destino_id=destino),db,usuario)


@pytest.mark.parametrize('tipo',['disciplina','assunto'])
@pytest.mark.parametrize('destino_vazio',[False,True])
def test_copias_simultaneas_mesmo_destino_sem_ordens_repetidas(copia,tipo,destino_vazio):
    main,_,factory,_=copia
    with factory() as db:
        if destino_vazio:
            # Remove somente a semente do destino no banco descartável.
            db.query(m.Aula).filter_by(pasta_id=2).delete()
            db.query(m.Pasta).filter_by(id=2).delete()
            db.query(m.CursoAssuntoProprio).filter_by(id=2).delete()
            if tipo=='disciplina':db.query(m.CursoDisciplinaPropria).filter_by(id=2).delete()
            db.commit()
        historico=snapshot(db,HISTORICO)
        tabela,pai=('curso_disciplinas_proprias','curso_id') if tipo=='disciplina' else ('curso_assuntos_proprios','curso_disciplina_propria_id')
        # Constraint apenas no banco descartável: detecta também colisão durante o INSERT.
        db.execute(text(f'CREATE UNIQUE INDEX test_ordem_copia ON {tabela} ({pai}, ordem)'))
        db.commit()
    barreira=Barrier(4)
    with ThreadPoolExecutor(max_workers=4) as executor:
        futuros=[executor.submit(copiar,main,factory,tipo,barreira=barreira) for _ in range(4)]
        resultados=[f.result(timeout=25) for f in futuros]
    with factory() as db:
        if tipo=='disciplina':
            ids=[r['nova_disciplina_id'] for r in resultados]
            ordens=[db.get(m.CursoDisciplinaPropria,id).ordem for id in ids]
            assert sorted(ordens)==([1,2,3,4] if destino_vazio else [10,11,12,13])
        else:
            ids=[r['novo_assunto_id'] for r in resultados]
            ordens=[db.get(m.CursoAssuntoProprio,id).ordem for id in ids]
            assert sorted(ordens)==([1,2,3,4] if destino_vazio else [18,19,20,21])
        assert len(set(ids))==4
        assert snapshot(db,HISTORICO)==historico


@pytest.mark.parametrize('tipo',['disciplina','assunto'])
def test_copias_em_sentidos_opostos_sem_deadlock(copia,tipo):
    main,_,factory,_=copia
    barreira=Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futuros=[executor.submit(copiar,main,factory,tipo,origem,destino,barreira)
                 for origem,destino in [(1,2),(2,1)]]
        resultados=[f.result(timeout=25) for f in futuros]
    assert all(r['ok'] for r in resultados)
    assert {r['curso_destino_id'] for r in resultados}=={1,2}


def test_lock_destino_mantido_ate_commit_e_leitura_da_ordem_atual(copia):
    main,_,factory,_=copia
    aguardando_lock=Event()
    with factory() as bloqueador:
        destino=bloqueador.query(m.Curso).filter_by(id=2).with_for_update().one()
        assert destino.id==2
        def detectar_lock(conexao,cursor,sql,parametros,contexto,muitos):
            if 'FROM cursos' in sql and 'FOR UPDATE' in sql:
                aguardando_lock.set()
        event.listen(bloqueador.bind,'before_cursor_execute',detectar_lock)
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                futuro=executor.submit(copiar,main,factory,'disciplina')
                try:
                    assert aguardando_lock.wait(timeout=5)
                    assert not futuro.done()
                    bloqueador.add(m.CursoDisciplinaPropria(curso_id=2,nome='Inserida sob lock',ordem=30))
                    bloqueador.commit()
                finally:
                    bloqueador.rollback()  # Libera o lock mesmo se a asserção falhar.
                resultado=futuro.result(timeout=25)
        finally:
            event.remove(bloqueador.bind,'before_cursor_execute',detectar_lock)
    with factory() as db:assert db.get(m.CursoDisciplinaPropria,resultado['nova_disciplina_id']).ordem==31
