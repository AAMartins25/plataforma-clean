"""PostgreSQL 17 descartável sem rede; opt-in por socket exclusivo do intermediário."""
import multiprocessing

import os

from pathlib import Path

import uuid

import pytest

import psycopg

from sqlalchemy import create_engine, text

from sqlalchemy.orm import sessionmaker

SOCKET = '/tmp/resumao-intermediario-pg-socket'

@pytest.fixture
def banco_pg():
    if os.getenv('RESUMAO_INTERMEDIARIO_PG_SOCKET') != SOCKET:
        pytest.skip('Exige PostgreSQL descartável no socket exclusivo admin022')
    nome = 'admin022_' + uuid.uuid4().hex
    with psycopg.connect(host=SOCKET, user='postgres', dbname='postgres', autocommit=True) as c:
        c.execute(psycopg.sql.SQL('CREATE DATABASE {}').format(psycopg.sql.Identifier(nome)))
    try:
        yield nome
    finally:
        with psycopg.connect(host=SOCKET, user='postgres', dbname='postgres', autocommit=True) as c:
            c.execute(psycopg.sql.SQL('DROP DATABASE {} WITH (FORCE)').format(psycopg.sql.Identifier(nome)))

def motor(nome):
    assert nome.startswith('admin022_')
    return create_engine('postgresql+psycopg://postgres@/' + nome + '?host=' + SOCKET,
                         pool_size=2, max_overflow=0, pool_timeout=3, pool_pre_ping=True,
                         connect_args={'prepare_threshold': None, 'connect_timeout': 5})

def test_migracao_pg_backfill_reaplicacao_e_falha_atomica(banco_pg):
    migration = (Path(__file__).parent/'migrations/022_tipos_administrador.sql').read_text()
    with psycopg.connect(host=SOCKET, user='postgres', dbname=banco_pg, autocommit=True) as c:
        c.execute('CREATE TABLE usuarios(id serial PRIMARY KEY, is_admin boolean, nome text)')
        c.execute("INSERT INTO usuarios(is_admin,nome) VALUES(true,'Geral'),(false,'Aluno'),(NULL,'Legado')")
        c.execute(migration)
        assert c.execute('SELECT is_admin,tipo_admin FROM usuarios ORDER BY id').fetchall() == [(True,'admin_geral'),(False,None),(False,None)]
        c.execute("UPDATE usuarios SET tipo_admin='admin_prod' WHERE id=2")
        c.execute(migration)
        assert c.execute('SELECT is_admin,tipo_admin FROM usuarios WHERE id=2').fetchone() == (False,'admin_prod')
        for admin, tipo in [(True,None),(True,'admin_prod'),(True,'admin_adm'),(False,'admin_geral'),(False,'root')]:
            with pytest.raises(psycopg.errors.CheckViolation):
                c.execute('UPDATE usuarios SET is_admin=%s,tipo_admin=%s WHERE id=3',(admin,tipo))
        # Simula dados inválidos anteriores; a migração deve recusar sem promovê-los.
        c.execute('ALTER TABLE usuarios DROP CONSTRAINT ck_usuarios_tipo_admin')
        c.execute("UPDATE usuarios SET is_admin=true,tipo_admin='admin_prod' WHERE id=2")
        with pytest.raises(psycopg.errors.RaiseException): c.execute(migration)
        c.execute('ROLLBACK')
        assert c.execute('SELECT is_admin,tipo_admin FROM usuarios WHERE id=2').fetchone() == (True,'admin_prod')

def test_session_pool_reutilizacao_e_lock_transacional(banco_pg):
    # Exercita o contrato de sessões PostgreSQL com o pool SQLAlchemy local.
    # Não equivale a um ensaio no serviço Supavisor.
    engine = motor(banco_pg)
    outro = motor(banco_pg)
    lock = "hashtextextended('resumao:perfis-admin', 0)"
    try:
        with engine.connect() as a, outro.connect() as b:
            pid = a.execute(text('SELECT pg_backend_pid()')).scalar_one()
            assert pid != b.execute(text('SELECT pg_backend_pid()')).scalar_one()
            a.execute(text(f'SELECT pg_advisory_xact_lock({lock})'))
            assert b.execute(text(f'SELECT pg_try_advisory_xact_lock({lock})')).scalar_one() is False
            b.rollback()
            a.commit()
            assert b.execute(text(f'SELECT pg_try_advisory_xact_lock({lock})')).scalar_one() is True
            b.rollback()
            a.execute(text(f'SELECT pg_advisory_xact_lock({lock})'))
            # Devolução ao pool sem commit precisa liberar o lock por rollback.
        with outro.connect() as b:
            assert b.execute(text(f'SELECT pg_try_advisory_xact_lock({lock})')).scalar_one() is True
        with engine.connect() as a:
            assert a.execute(text('SELECT pg_backend_pid()')).scalar_one() == pid
            assert a.execute(text('SELECT current_user=session_user')).scalar_one() is True
    finally:
        engine.dispose(); outro.dispose()


def preparar(nome):
    from app.models import Base,Usuario,AuditoriaPerfilAdmin
    e=motor(nome)
    Base.metadata.create_all(e,tables=[Usuario.__table__,AuditoriaPerfilAdmin.__table__])
    with sessionmaker(bind=e)() as db:
        db.add(Usuario(nome='Geral',email='geral@example.com',cpf='1',telefone='0',senha_hash='teste',
            is_admin=True,tipo_admin='admin_geral',ativo=True));db.commit()
    e.dispose()


def criar(nome,cpf,barreira,lido,continuar,saida):
    from fastapi import HTTPException
    from app.models import Usuario
    from test_questoes_pratica_patch import carregar_main_isolado
    e=motor(nome);f=sessionmaker(bind=e,autoflush=False)
    try:
        with carregar_main_isolado(f,e) as main,f() as db:
            autor=db.get(Usuario,1)
            if lido is not None:lido.set();assert continuar.wait(20)
            if barreira is not None:barreira.wait(20)
            try:
                main.admin_criar_aluno({'nome':'Novo','cpf':cpf,'data_nascimento':'1990-01-01',
                    'telefone':'0','email':cpf+'@example.com','senha':'Teste123','is_admin':True},db,autor)
                saida.put((200,os.getpid()))
            except HTTPException as exc:
                db.rollback();saida.put((exc.status_code,os.getpid()))
    finally:e.dispose()


def revogar(nome,lido,continuar,inativar):
    from app.models import Usuario
    e=motor(nome)
    try:
        assert lido.wait(20)
        with sessionmaker(bind=e)() as db:
            db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('resumao:perfis-admin', 0))"))
            u=db.get(Usuario,1)
            if inativar:u.ativo=False
            else:u.is_admin=False;u.tipo_admin='admin_prod'
            db.commit()
        continuar.set()
    finally:e.dispose()


def executar(processos):
    try:
        for p in processos:p.start()
        for p in processos:p.join(35);assert p.exitcode==0,(p.pid,p.exitcode)
    finally:
        for p in processos:
            if p.is_alive():p.terminate();p.join(5)


@pytest.mark.parametrize('inativar',[False,True])
def test_revalidacao_entre_processos(banco_pg,inativar):
    preparar(banco_pg);ctx=multiprocessing.get_context('spawn')
    lido,continuar,q=ctx.Event(),ctx.Event(),ctx.Queue()
    executar([ctx.Process(target=criar,args=(banco_pg,'2',None,lido,continuar,q)),
              ctx.Process(target=revogar,args=(banco_pg,lido,continuar,inativar))])
    assert q.get(timeout=5)[0]==403
    e=motor(banco_pg)
    try:
        with e.connect() as c:
            assert c.execute(text('SELECT count(*) FROM usuarios')).scalar_one()==1
            assert c.execute(text('SELECT count(*) FROM auditoria_perfis_admin')).scalar_one()==0
    finally:e.dispose()


def test_criacoes_concorrentes_auditadas(banco_pg):
    preparar(banco_pg);ctx=multiprocessing.get_context('spawn');b=ctx.Barrier(2);q=ctx.Queue()
    executar([ctx.Process(target=criar,args=(banco_pg,str(i),b,None,None,q)) for i in (2,3)])
    resultados=[q.get(timeout=5) for _ in range(2)]
    assert [s for s,p in resultados]==[200,200] and len({p for s,p in resultados})==2
    e=motor(banco_pg)
    try:
        with e.connect() as c:
            assert c.execute(text("SELECT count(*) FROM usuarios WHERE ativo AND is_admin AND tipo_admin='admin_geral'")).scalar_one()==3
            assert c.execute(text('SELECT count(*) FROM auditoria_perfis_admin WHERE autor_id=1')).scalar_one()==2
            assert c.execute(text('SHOW transaction_isolation')).scalar_one()=='read committed'
    finally:e.dispose()


def test_migracao_cinco_gerais_e_vinculos_preservados(banco_pg):
    migration=(Path(__file__).parent/'migrations/022_tipos_administrador.sql').read_text()
    with psycopg.connect(host=SOCKET,user='postgres',dbname=banco_pg,autocommit=True) as c:
        c.execute('CREATE TABLE usuarios(id int PRIMARY KEY, nome text, senha_hash text, ativo boolean, is_admin boolean, perfil_inicial text)')
        c.execute("INSERT INTO usuarios SELECT i,'Fictício '||i,'hash-ficticio-'||i,true,i>=56,CASE WHEN i>=56 THEN 'ADMIN' WHEN i>=54 THEN 'VENDEDOR' ELSE 'ALUNO' END FROM generate_series(1,60) i")
        c.execute('CREATE TABLE vendedores(id int PRIMARY KEY,usuario_id int REFERENCES usuarios(id),ativo boolean)')
        c.execute('INSERT INTO vendedores VALUES(1,54,true),(2,55,true)')
        c.execute('CREATE TABLE acessos_curso(usuario_id int REFERENCES usuarios(id),curso_id int,ativo boolean)')
        c.execute('INSERT INTO acessos_curso SELECT i,1,true FROM generate_series(1,53) i')
        c.execute('CREATE TABLE pagamentos(id int PRIMARY KEY,usuario_id int REFERENCES usuarios(id),valor_cents int)')
        c.execute('INSERT INTO pagamentos VALUES(1,1,100),(2,53,200),(3,56,300)')
        antes=c.execute('SELECT id,nome,senha_hash,ativo,is_admin,perfil_inicial FROM usuarios ORDER BY id').fetchall()
        vinculos={t:c.execute('SELECT * FROM '+t+' ORDER BY 1').fetchall() for t in ['vendedores','acessos_curso','pagamentos']}
        c.execute(migration)
        assert c.execute("SELECT count(*) FROM usuarios WHERE ativo AND is_admin AND tipo_admin='admin_geral'").fetchone()[0]==5
        assert c.execute('SELECT count(*) FROM usuarios WHERE NOT is_admin AND tipo_admin IS NULL').fetchone()[0]==55
        assert c.execute('SELECT id,nome,senha_hash,ativo,is_admin,perfil_inicial FROM usuarios ORDER BY id').fetchall()==antes
        for t,linhas in vinculos.items():assert c.execute('SELECT * FROM '+t+' ORDER BY 1').fetchall()==linhas
