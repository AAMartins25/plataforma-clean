"""Concorrência em PostgreSQL descartável sem rede; não executa migrações."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
import pytest
import psycopg
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from fastapi import FastAPI
from app import models as m
from app.auth import criar_token
from app import perfis_admin
from test_questoes_pratica_patch import carregar_main_isolado

SOCKET='/tmp/resumao-perfis-matriz-pg'

@pytest.fixture
def ambiente_pg():
    if os.environ.get('RESUMAO_PERFIS_PG_SOCKET') != SOCKET:
        pytest.skip('Requer socket exclusivo do PostgreSQL descartável de perfis')
    nome='perfis_matriz_'+uuid.uuid4().hex
    with psycopg.connect(host=SOCKET,user='postgres',dbname='postgres',autocommit=True) as c:
        c.execute(psycopg.sql.SQL('CREATE DATABASE {}').format(psycopg.sql.Identifier(nome)))
    engine=create_engine('postgresql+psycopg://postgres@/'+nome+'?host='+SOCKET,
                         connect_args={'connect_timeout':5},pool_size=5)
    try:
        # Apenas cria o esquema de teste vazio; nenhum arquivo de migração é usado.
        m.Base.metadata.create_all(engine,tables=[m.Usuario.__table__,m.Vendedor.__table__,m.AuditoriaPerfilAdmin.__table__])
        from app.pausa_financeira import metadata,controle,agora
        metadata.create_all(engine)
        with engine.begin() as c:
            c.execute(controle.insert().values(id=1,modo='NORMAL',geracao=0,alterado_em=agora(),motivo='teste isolado'))
        f=sessionmaker(bind=engine,autoflush=False)
        with f() as db:
            for uid,tipo in [(1,'admin_geral'),(2,'admin_geral'),(3,None)]:
                db.add(m.Usuario(id=uid,nome=str(uid),email=f'{uid}@example.com',cpf=str(uid),telefone='0',senha_hash='hash',
                                 ativo=True,is_admin=tipo=='admin_geral',tipo_admin=tipo))
            db.commit()
        with carregar_main_isolado(f,engine) as main:
            # Usa as dependências reais de identidade e os handlers de perfil,
            # sem inicializar serviços financeiros alheios ao teste.
            app=FastAPI()
            perfis_admin.registrar_rotas(app,main.get_db,main.get_usuario_atual)
            with TestClient(app) as client:
                yield client,f
    finally:
        engine.dispose()
        with psycopg.connect(host=SOCKET,user='postgres',dbname='postgres',autocommit=True) as c:
            c.execute(psycopg.sql.SQL('DROP DATABASE {} WITH (FORCE)').format(psycopg.sql.Identifier(nome)))


def headers(uid):
    return {'Authorization':'Bearer '+criar_token({'sub':str(uid)})}


def test_duas_revogacoes_preservam_ultimo_geral(ambiente_pg):
    c,f=ambiente_pg;b=Barrier(2)
    def revogar(autor,alvo):
        b.wait(5)
        return c.put(f'/admin/usuarios/{alvo}/tipo-admin',headers=headers(autor),json={'tipo_admin':None}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(revogar,1,2);b1=pool.submit(revogar,2,1)
        assert sorted([a.result(10),b1.result(10)])==[200,403]
    with f() as db:
        assert db.query(m.Usuario).filter_by(is_admin=True,tipo_admin='admin_geral',ativo=True).count()==1
        assert db.query(m.AuditoriaPerfilAdmin).count()==1


@pytest.mark.parametrize('inativar',[False,True])
def test_autor_revalidado_apos_leitura_inicial(ambiente_pg,monkeypatch,inativar):
    c,f=ambiente_pg;lido=Event();continuar=Event();original=perfis_admin.revalidar_geral
    def aguardar(db,uid):
        lido.set();assert continuar.wait(5)
        return original(db,uid)
    monkeypatch.setattr(perfis_admin,'revalidar_geral',aguardar)
    with ThreadPoolExecutor(max_workers=1) as pool:
        resposta=pool.submit(c.put,'/admin/usuarios/3/tipo-admin',headers=headers(1),json={'tipo_admin':'admin_geral'})
        try:
            assert lido.wait(5)
            with f() as db:
                u=db.get(m.Usuario,1)
                if inativar:u.ativo=False
                else:u.is_admin=False;u.tipo_admin='admin_prod'
                db.commit()
        finally:
            continuar.set()
        assert resposta.result(10).status_code==403
    with f() as db:
        assert db.get(m.Usuario,3).tipo_admin is None
        assert db.query(m.AuditoriaPerfilAdmin).count()==0
