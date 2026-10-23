"""Homologação adicional: PostgreSQL efêmero, falha parcial e recuperação.
Reutiliza somente factories/socket seguros dos testes anteriores.
"""
import multiprocessing
from pathlib import Path
import time
import pytest
import psycopg
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from app import models as m
from app.auth import criar_token
from test_admin_intermediario_pg import banco_pg, motor, SOCKET
from test_questoes_pratica_patch import carregar_main_isolado
from fastapi.testclient import TestClient


def preparar_estrutura(nome):
    e=motor(nome)
    m.Base.metadata.create_all(e)
    with e.connect() as c:
        for f in ['016_pausa_financeira_webhooks.sql','014_pagamentos_multiplas_transacoes.sql',
                  '015_reembolsos_manual_auditoria.sql','017_checkout_identidade_segura.sql',
                  '018_isolamento_notificacoes_historicas.sql']:
            c.connection.driver_connection.execute((Path(__file__).parent/'migrations'/f).read_text())
    with e.begin() as c:
        c.execute(text("INSERT INTO usuarios(nome,email,cpf,telefone,senha_hash,ativo,is_admin,tipo_admin,perfil_inicial,tentativas_login,bloqueado_login) SELECT 'Fictício '||i,'u'||i||'@example.com',i::text,'0','hash-ficticio',true,i>=56,CASE WHEN i>=56 THEN 'admin_geral' ELSE NULL END,'ALUNO',0,false FROM generate_series(1,60) i"))
    with sessionmaker(bind=e)() as db:
        db.add(m.Curso(nome='Base',ativo=True));db.flush()
        db.add(m.Vendedor(nome='Vendedor',ativo=True,usuario_id=54))
        db.add(m.AcessoCurso(usuario_id=1,curso_id=1,ativo=True));db.commit()
    return e


def criar_interrompido(nome,pronto):
    e=motor(nome);f=sessionmaker(bind=e,autoflush=False)
    with carregar_main_isolado(f,e) as main,f() as db:
        autor=db.get(m.Usuario,56)
        def interromper():
            # Flush da auditoria para provar rollback das duas gravações reais.
            db.flush();pronto.set();time.sleep(30)
        db.commit=interromper
        main.admin_criar_aluno({'nome':'Não deve persistir','email':'crash@example.com','cpf':'crash',
           'telefone':'0','data_nascimento':'1990-01-01','senha':'Teste123','is_admin':True},db,autor)


def processo_reiniciado(nome,fila):
    # Processo novo: novo import de main, engine/pool e startup/shutdown reais.
    e=motor(nome);f=sessionmaker(bind=e,autoflush=False)
    with carregar_main_isolado(f,e) as main,TestClient(main.app) as c:
        h={'Authorization':'Bearer '+criar_token({'sub':'56'})}
        me=c.get('/me',headers=h)
        r=c.post('/cursos',headers=h,json={'nome':'Após reinício'})
        fila.put((me.status_code,me.json().get('tipo_admin'),r.status_code))
    e.dispose()


def test_migracao_interrompida_e_recuperacao_so_intermediario(banco_pg,monkeypatch):
    monkeypatch.setenv('EMAILS_PAGAMENTOS_ATIVOS','false')
    e=preparar_estrutura(banco_pg)
    # Converte somente o banco descartável em schema legado para ensaiar 022.
    with e.begin() as c:
        c.execute(text('DROP TABLE auditoria_perfis_admin'))
        c.execute(text('ALTER TABLE usuarios DROP COLUMN tipo_admin CASCADE'))
    sql=(Path(__file__).parent/'migrations/022_tipos_administrador.sql').read_text()
    with e.connect() as c:
        usuarios=c.execute(text('SELECT id,nome,email,cpf,senha_hash,is_admin FROM usuarios ORDER BY id')).all()
        acessos=c.execute(text('SELECT usuario_id,curso_id,ativo FROM acessos_curso')).all()
        vendedores=c.execute(text('SELECT id,usuario_id,ativo FROM vendedores')).all()
    # Cliente cai antes de COMMIT: encerramento da conexão deve desfazer o DDL.
    c=psycopg.connect(host=SOCKET,user='postgres',dbname=banco_pg,autocommit=True)
    c.execute(sql.rsplit('COMMIT;',1)[0]);c.close()
    with e.connect() as c:
        assert not c.execute(text("SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='usuarios' AND column_name='tipo_admin')")).scalar_one()
        assert c.execute(text("SELECT to_regclass('public.auditoria_perfis_admin')")).scalar_one() is None
        assert c.execute(text('SELECT id,nome,email,cpf,senha_hash,is_admin FROM usuarios ORDER BY id')).all()==usuarios
    with psycopg.connect(host=SOCKET,user='postgres',dbname=banco_pg,autocommit=True) as c:c.execute(sql)
    with e.connect() as c:
        assert c.execute(text("SELECT count(*) FROM usuarios WHERE is_admin AND tipo_admin='admin_geral'")).scalar_one()==5
        assert c.execute(text('SELECT usuario_id,curso_id,ativo FROM acessos_curso')).all()==acessos
        assert c.execute(text('SELECT id,usuario_id,ativo FROM vendedores')).all()==vendedores
    ctx=multiprocessing.get_context('spawn');pronto=ctx.Event()
    p=ctx.Process(target=criar_interrompido,args=(banco_pg,pronto));p.start()
    try:
        assert pronto.wait(20)
        p.terminate();p.join(10);assert not p.is_alive()
        with e.connect() as c:
            assert c.execute(text('SELECT count(*) FROM usuarios')).scalar_one()==60
            assert c.execute(text('SELECT count(*) FROM auditoria_perfis_admin')).scalar_one()==0
        fila=ctx.Queue();novo=ctx.Process(target=processo_reiniciado,args=(banco_pg,fila))
        novo.start();novo.join(25)
        if novo.is_alive():novo.terminate();novo.join(5)
        assert novo.exitcode==0
        assert fila.get(timeout=5)==(200,'admin_geral',200)
        # Flag ligada ainda não concede poderes a um restrito após recuperação.
        with e.begin() as c:c.execute(text("UPDATE usuarios SET tipo_admin='admin_prod' WHERE id=2"))
        f=sessionmaker(bind=e,autoflush=False)
        with carregar_main_isolado(f,e) as main,TestClient(main.app) as cliente:
            monkeypatch.setenv('ADMIN_RESTRITOS_HABILITADOS','1')
            assert cliente.post('/cursos',json={'nome':'Proibido'},headers={'Authorization':'Bearer '+criar_token({'sub':'2'})}).status_code==403
    finally:
        if p.is_alive():p.terminate();p.join(5)
        e.dispose()
