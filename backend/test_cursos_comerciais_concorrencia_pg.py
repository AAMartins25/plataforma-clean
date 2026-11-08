"""Locks reais em PostgreSQL descartável, sem migrações ou rede/produção."""
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event, current_thread
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from app import models as m
from app.schemas import CursoUpdate, AcessoCursoCreate
from app.pausa_financeira import metadata, controle, agora
from test_questoes_pratica_patch import carregar_main_isolado

ADMIN=SimpleNamespace(id=2,is_admin=True,tipo_admin='admin_geral')
ALUNO=SimpleNamespace(id=1,email='1@teste.local',is_admin=False)

@pytest.fixture
def pg(monkeypatch):
    url=os.environ.get('VENDAS_TEST_PG_DSN')
    if not url:pytest.skip('Defina VENDAS_TEST_PG_DSN para PostgreSQL exclusivo dos testes de venda')
    parsed=make_url(url)
    assert parsed.get_backend_name()=='postgresql'
    assert parsed.database=='compras_test_venda_20261108'
    assert parsed.host is None and parsed.query.get('host')=='/tmp/resumao-venda-pgsocket-final'
    base=create_engine(url)
    schema='vendas_'+uuid.uuid4().hex
    with base.begin() as c:c.execute(text(f'CREATE SCHEMA {schema}'))
    engine=create_engine(url,connect_args={'options':f'-csearch_path={schema} -clock_timeout=5000 -cstatement_timeout=15000'})
    factory=sessionmaker(bind=engine,autoflush=False)
    monkeypatch.setenv('MP_COLLECTOR_ID','123456')
    try:
        # Apenas modelos em schema novo; nenhum script de migração é executado.
        m.Base.metadata.create_all(engine);metadata.create_all(engine)
        with engine.begin() as c:
            c.execute(text('CREATE UNIQUE INDEX test_acesso_unico ON acessos_curso(usuario_id,curso_id)'))
            c.execute(controle.insert().values(id=1,modo='NORMAL',geracao=0,alterado_em=agora(),motivo='teste de concorrência exclusivo'))
        with factory() as db:
            db.add_all([m.Usuario(id=1,nome='Aluno',email='1@teste.local',senha_hash='teste',cpf='1',telefone='0'),m.Usuario(id=2,nome='ADM',email='2@teste.local',senha_hash='teste',cpf='2',telefone='0',is_admin=True,tipo_admin='admin_geral'),m.Curso(id=1,nome='Curso',ativo=True,publicado=True)])
            db.flush();db.add(m.TempoAcessoCurso(id=1,curso_id=1,meses=4,valor_cents=4990,ativo=True));db.commit()
        with carregar_main_isolado(factory,engine) as main:
            main.MP_ACCESS_TOKEN='simulado-sem-validade'
            response=Mock(status_code=201);response.json.return_value={'id':'pref_teste','init_point':'https://example.com/simulado','collector_id':123456}
            with patch.object(main.requests,'post',return_value=response) as post:
                yield main,factory,engine,post
    finally:
        engine.dispose()
        with base.begin() as c:c.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        base.dispose()


def disputar(pg,primeiro,segundo):
    main,factory,engine,_=pg
    bloqueado=Event();soltar=Event();tentando=Event();real=main.bloquear_curso
    identificadores={}
    def lock(db,*args,**kwargs):
        nome=current_thread().name
        identificadores[nome]=db.execute(text('SELECT pg_backend_pid()')).scalar_one()
        if nome=='segundo':tentando.set()
        curso=real(db,*args,**kwargs)
        if nome=='primeiro':
            bloqueado.set();assert soltar.wait(10)
        return curso
    def executar(nome,func):
        current_thread().name=nome
        with factory() as db:
            try:return func(main,db)
            except HTTPException as e:db.rollback();return e.status_code
    with patch.object(main,'bloquear_curso',side_effect=lock),ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(executar,'primeiro',primeiro)
        try:
            assert bloqueado.wait(5),'primeira operação não bloqueou o curso'
            b=pool.submit(executar,'segundo',segundo)
            assert tentando.wait(5)
            limite=time.monotonic()+4
            espera_real=False
            while time.monotonic()<limite:
                with engine.connect() as c:
                    espera_real=bool(c.execute(text('SELECT cardinality(pg_blocking_pids(:pid)) > 0'),{'pid':identificadores['segundo']}).scalar_one())
                if espera_real:break
                Event().wait(.02)
            assert espera_real,'segunda transação não aguardou o lock real do PostgreSQL'
            assert not b.done()
        finally:soltar.set()
        return a.result(timeout=10),b.result(timeout=10)


def adquirir(tipo):
    def executar(main,db):
        if tipo=='demo':return main.iniciar_demonstracao_curso(1,db,ALUNO)
        if tipo=='compra':return main.criar_checkout_mp({'tempo_acesso_id':1},db,ALUNO)
        return main.admin_criar_acesso(AcessoCursoCreate(usuario_id=1,curso_id=1,data_fim=datetime.utcnow()+timedelta(days=30)),db,ADMIN)
    return executar


@pytest.mark.parametrize('tipo',['demo','compra','admin'])
@pytest.mark.parametrize('metodo',['delete','put'])
@pytest.mark.parametrize('exclusao_primeiro',[True,False])
def test_exclusao_e_aquisicao_serializadas(pg,tipo,metodo,exclusao_primeiro):
    main,factory,_,post=pg
    def excluir(main,db):
        return main.excluir_curso(1,db,ADMIN) if metodo=='delete' else main.editar_curso(1,CursoUpdate(nome='Curso',ativo=False),db,ADMIN)
    compra=adquirir(tipo)
    a,b=disputar(pg,excluir if exclusao_primeiro else compra,compra if exclusao_primeiro else excluir)
    assert isinstance(a,dict)
    assert b==(404 if exclusao_primeiro else 409),(a,b)
    with factory() as db:
        assert db.get(m.Curso,1).ativo is (not exclusao_primeiro)
        modelo={'demo':m.DemonstracaoCurso,'compra':m.Pagamento,'admin':m.ContratacaoCurso}[tipo]
        assert db.query(modelo).count()==int(not exclusao_primeiro)
    assert post.call_count==int(tipo=='compra' and not exclusao_primeiro)


@pytest.mark.parametrize('tipo',['demo','compra'])
@pytest.mark.parametrize('retirada_primeiro',[True,False])
def test_retirada_e_aquisicao_serializadas(pg,tipo,retirada_primeiro):
    def retirar(main,db):return main.retirar_curso_venda(1,db,ADMIN)
    compra=adquirir(tipo)
    a,b=disputar(pg,retirar if retirada_primeiro else compra,compra if retirada_primeiro else retirar)
    assert isinstance(a,dict)
    assert b==409 if retirada_primeiro else isinstance(b,dict)
    with pg[1]() as db:
        curso=db.get(m.Curso,1);assert curso.ativo and not curso.publicado
        assert db.query(m.DemonstracaoCurso if tipo=='demo' else m.Pagamento).count()==int(not retirada_primeiro)


def test_dois_alunos_podem_adquirir_mesmo_curso_sem_espera_mutua(pg):
    main,factory,_,_=pg
    primeiro_bloqueado=Event();soltar=Event();real=main.bloquear_curso
    def lock(db,*args,**kwargs):
        curso=real(db,*args,**kwargs)
        if current_thread().name=='primeiro':
            primeiro_bloqueado.set();assert soltar.wait(10)
        return curso
    def executar(nome,usuario):
        current_thread().name=nome
        with factory() as db:return main.iniciar_demonstracao_curso(1,db,usuario)
    with patch.object(main,'bloquear_curso',side_effect=lock),ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(executar,'primeiro',ALUNO)
        try:
            assert primeiro_bloqueado.wait(5)
            b=pool.submit(executar,'segundo',ADMIN)
            assert b.result(timeout=4)['ok']
            assert not a.done()
        finally:soltar.set()
        assert a.result(timeout=5)['ok']
    with factory() as db:assert db.query(m.DemonstracaoCurso).count()==2
