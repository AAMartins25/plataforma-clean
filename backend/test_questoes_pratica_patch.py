"""Isolated SQLite tests; no production module/database/environment replacement persists."""
import importlib.util
import os
import sys
import types
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app import models, schemas
import app
import dotenv

main = None
engine = None
SessionTest = None


@contextmanager
def carregar_main_isolado(session_factory, test_engine):
    stub = types.ModuleType('app.database')
    stub.SessionLocal = session_factory
    stub.engine = test_engine
    nome = 'app._questoes_pratica_test_main'
    spec = importlib.util.spec_from_file_location(nome, Path(__file__).parent / 'app/main.py')
    modulo = importlib.util.module_from_spec(spec)
    ambiente = dict(os.environ)
    atributos_app = dict(vars(app))
    try:
        with patch.dict(os.environ, {'AMBIENTE_TESTE': '1',
                                     'QUESTOES_PRATICA_SESSION_SECRET': 's' * 48}), \
             patch.dict(sys.modules, {'app.database': stub, nome: modulo}), \
             patch.object(dotenv, 'load_dotenv', return_value=False):
            spec.loader.exec_module(modulo)
        # Restore package attributes too: imports can attach child modules to app.
        vars(app).clear()
        vars(app).update(atributos_app)
        # Patches already undone; the private module retains its own test factory.
        yield modulo
    finally:
        os.environ.clear()
        os.environ.update(ambiente)
        vars(app).clear()
        vars(app).update(atributos_app)


@pytest.fixture(scope='module', autouse=True)
def modulo_isolado():
    global main, engine, SessionTest
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    SessionTest = sessionmaker(bind=engine)
    try:
        with carregar_main_isolado(SessionTest, engine) as modulo:
            main = modulo
            yield
    finally:
        main.app.dependency_overrides.clear()
        engine.dispose()
        main = engine = SessionTest = None

TABLES = [models.Curso.__table__, models.CursoDisciplinaPropria.__table__,
          models.CursoAssuntoProprio.__table__, models.ContratacaoCurso.__table__,
          models.DemonstracaoCurso.__table__, models.QuestaoPraticaAssunto.__table__,
          models.QuestaoPraticaAlternativa.__table__, models.QuestaoPraticaMarcacaoAluno.__table__,
          models.QuestaoPraticaRotatividadeAluno.__table__]

@pytest.fixture
def env():
    models.Base.metadata.drop_all(engine, tables=TABLES)
    models.Base.metadata.create_all(engine, tables=TABLES)
    db = SessionTest()
    now = datetime.utcnow()
    db.add_all([models.Curso(id=1,nome='Curso'),models.Curso(id=2,nome='Outro')])
    db.add_all([models.CursoDisciplinaPropria(id=i,curso_id=1,nome=str(i),ordem=i) for i in range(1,4)])
    db.add_all([models.CursoAssuntoProprio(id=1,curso_disciplina_propria_id=1,nome='Assunto'),
                models.CursoAssuntoProprio(id=2,curso_disciplina_propria_id=1,nome='Outro'),
                models.CursoAssuntoProprio(id=3,curso_disciplina_propria_id=3,nome='Bloqueado')])
    db.add_all([models.DemonstracaoCurso(id=1,usuario_id=1,curso_id=1,data_inicio=now-timedelta(days=1),data_fim=now+timedelta(days=1),liberado_novamente_em=now),
                models.DemonstracaoCurso(id=2,usuario_id=2,curso_id=1,data_inicio=now-timedelta(days=1),data_fim=now+timedelta(days=1),liberado_novamente_em=now),
                models.DemonstracaoCurso(id=3,usuario_id=1,curso_id=1,data_inicio=now-timedelta(days=2),data_fim=now-timedelta(days=1),liberado_novamente_em=now),
                models.ContratacaoCurso(id=1,usuario_id=1,curso_id=1,origem='ADMIN',data_inicio=now-timedelta(days=1))])
    for i in range(1,7):
        db.add(models.QuestaoPraticaAssunto(id=i,curso_assunto_proprio_id=1 if i<5 else 2,
            tipo='CERTO_ERRADO',enunciado='Teste',gabarito='C',ativo=i!=4,comentario='Comentário'))
    db.commit()
    def get_db():
        session=SessionTest()
        try: yield session
        finally: session.close()
    main.app.dependency_overrides[main.get_db]=get_db
    main.app.dependency_overrides[main.get_usuario_atual]=lambda: SimpleNamespace(id=1,is_admin=False)
    try:
        with TestClient(main.app) as client:
            yield client,db
    finally:
        main.app.dependency_overrides.clear()
        # Overrides installed by this fixture are deliberately not retained.
        db.rollback()
        db.close()

def proxima(client, **kwargs):
    return client.post('/curso-assuntos-proprios/1/questoes-pratica/proxima',json={'demonstracao_id':1,**kwargs})

def responder(client, selected, **kwargs):
    return client.post(f"/questoes-pratica/{selected['questao']['id']}/responder",json={
        'demonstracao_id':1,'resposta_marcada':'C','dificuldade_marcada':'FACIL',
        'token_sessao':selected['token_sessao'],**kwargs})

def marcar(db,id,**kwargs):
    db.add(models.QuestaoPraticaMarcacaoAluno(usuario_id=1,questao_id=id,demonstracao_id=1,**kwargs));db.commit()


def somente_questao(db, id):
    for questao in db.query(models.QuestaoPraticaAssunto).filter_by(curso_assunto_proprio_id=1):
        questao.ativo = questao.id == id
    db.commit()

@pytest.mark.parametrize('context,status', [({},400),({'demonstracao_id':1,'contratacao_id':1},400),
    ({'demonstracao_id':2},403),({'demonstracao_id':3},403),({'contratacao_id':999},403),({'contratacao_id':1},200)])
def test_contextos(env,context,status):
    client,_=env
    r=client.get('/curso-assuntos-proprios/1/questoes-pratica/filtros',params=context)
    assert r.status_code==status,r.text

def test_disciplina_bloqueada(env):
    client,_=env
    assert client.get('/curso-assuntos-proprios/3/questoes-pratica/filtros?demonstracao_id=1').status_code==403
    assert client.get('/curso-assuntos-proprios/3/questoes-pratica/filtros?contratacao_id=1').status_code==200

@pytest.mark.parametrize('filtro,ids',[('TODAS',[1,2,3]),('DIFICIL',[1]),('MEDIA',[2]),('FACIL',[3]),('ERREI',[1]),('REVER',[2])])
def test_filtros(env,filtro,ids):
    client,db=env
    marcar(db,1,dificuldade_marcada='DIFICIL',acertou=False)
    marcar(db,2,dificuldade_marcada='MEDIA',acertou=None,nao_soube=True,rever=True)
    marcar(db,3,dificuldade_marcada='FACIL',acertou=True)
    marcar(db,4,dificuldade_marcada='DIFICIL',acertou=False,rever=True)
    r=proxima(client,filtros=[filtro]); assert r.status_code==200,r.text
    assert r.json()['ids_questoes_sessao']==ids
    info=client.get('/curso-assuntos-proprios/1/questoes-pratica/filtros?demonstracao_id=1').json()
    assert info[filtro]['quantidade']==len(ids)

def test_or_chave_todos_filtros(env):
    client,db=env
    marcar(db,1,dificuldade_marcada='FACIL',acertou=True)
    marcar(db,2,dificuldade_marcada='DIFICIL',acertou=False)
    assert proxima(client,filtros=['FACIL','ERREI']).json()['ids_questoes_sessao']==[1,2]
    r=proxima(client,filtros=['DIFICIL','MEDIA','FACIL','ERREI','REVER'])
    assert r.status_code==200 and r.json()['filtro']=='F:31'
    assert len(r.json()['filtro'])<=20

def test_ids_inativos_outro_assunto(env):
    client,_=env
    assert proxima(client,ids_questoes_sessao=[5]).status_code==400
    assert proxima(client,ids_questoes_sessao=[1,4]).json()['ids_questoes_sessao']==[1,2,3]
    assert proxima(client,ids_questoes_sessao=[4]).json()['ids_questoes_sessao']==[1,2,3]

@pytest.mark.parametrize('resposta,acertou,nao_soube',[('C',True,False),('E',False,False),('NAO_SEI',None,True)])
def test_correcao_certo_errado(env,resposta,acertou,nao_soube):
    client,db=env
    somente_questao(db,1)
    selected=proxima(client,ids_questoes_sessao=[1]).json()
    r=responder(client,selected,resposta_marcada=resposta,rever=True)
    assert r.status_code==200,r.text
    assert r.json()['acertou'] is acertou and r.json()['nao_soube']==nao_soube
    assert r.json()['gabarito']=='C' and r.json()['comentario']=='Comentário'
    m=db.query(models.QuestaoPraticaMarcacaoAluno).one()
    assert m.demonstracao_id==1 and m.contratacao_id is None and m.rever
    if nao_soube:
        assert client.get('/curso-assuntos-proprios/1/questoes-pratica/filtros?demonstracao_id=1').json()['ERREI']['quantidade']==0

def test_isolamento_reenvio_e_atualizacao(env):
    client,db=env
    somente_questao(db,1)
    q=proxima(client,ids_questoes_sessao=[1]).json()
    assert responder(client,q).status_code==200
    assert responder(client,q).status_code==409
    r=proxima(client,ids_questoes_sessao=[1]);assert r.json()['ciclo']==2
    assert responder(client,r.json(),resposta_marcada='E').status_code==200
    assert db.query(models.QuestaoPraticaMarcacaoAluno).count()==1
    assert db.query(models.QuestaoPraticaMarcacaoAluno).one().acertou is False
    q2=proxima(client,demonstracao_id=None,contratacao_id=1,ids_questoes_sessao=[1]).json()
    assert q2['ciclo']==1
    assert responder(client,q2,demonstracao_id=None,contratacao_id=1).status_code==200
    assert db.query(models.QuestaoPraticaMarcacaoAluno).count()==2
    info=client.get('/curso-assuntos-proprios/1/questoes-pratica/filtros?contratacao_id=1').json()
    assert info['ERREI']['quantidade']==0

def test_ciclo_filtrado_menor_que_assunto(env):
    client,db=env
    marcar(db,1,dificuldade_marcada='FACIL',acertou=True)
    marcar(db,2,dificuldade_marcada='FACIL',acertou=True)
    ids_seen=[]
    for ciclo in [1,1,2,2,3]:
        q=proxima(client,filtros=['FACIL']).json()
        assert q['ciclo']==ciclo
        ids_seen.append(q['questao']['id'])
        assert responder(client,q,filtros=['FACIL']).status_code==200
    assert len(set(ids_seen[:2]))==2 and len(set(ids_seen[2:4]))==2

def test_token_payload_adulterado_e_sem_gabarito(env):
    client,db=env
    somente_questao(db,1)
    selected=proxima(client,ids_questoes_sessao=[1]).json()
    assert 'gabarito' not in selected['questao']
    assert responder(client,selected,acertou=True).status_code==422
    assert responder(client,selected,token_sessao='invalid').status_code==409
    assert responder(client,selected,demonstracao_id=None,contratacao_id=1).status_code==409
    assert responder(client,selected,filtros=['ERREI']).status_code==409

def test_desativacao_e_elegibilidade_entre_selecao_resposta(env):
    client,db=env
    somente_questao(db,1)
    selected=proxima(client,ids_questoes_sessao=[1]).json()
    q=db.get(models.QuestaoPraticaAssunto,1);q.ativo=False;db.commit()
    assert responder(client,selected).status_code==404
    assert db.query(models.QuestaoPraticaMarcacaoAluno).count()==0

@pytest.mark.parametrize('letras', ['ABCD','ABCDE'])
def test_admin_multipla_cadastro_correcao_rever(env,letras):
    client,db=env
    main.app.dependency_overrides[main.get_usuario_atual]=lambda: SimpleNamespace(id=1,is_admin=True)
    r=client.post('/admin/questoes-pratica',json={'curso_assunto_proprio_id':1,'tipo':'MULTIPLA','enunciado':'Escolha','gabarito':'',
        'alternativas':[{'letra':l,'texto':l,'correta':l==letras[-1]} for l in letras]})
    assert r.status_code==200,r.text
    id=r.json()['id']
    somente_questao(db,id)
    q=proxima(client,ids_questoes_sessao=[id]).json()
    assert len(q['questao']['alternativas'])==len(letras)
    assert all('correta' not in a for a in q['questao']['alternativas'])
    assert responder(client,q,resposta_marcada=letras[-1],rever=True).json()['acertou'] is True
    assert db.query(models.QuestaoPraticaMarcacaoAluno).one().rever

@pytest.mark.parametrize('letras',['ABCE','ABC','AABCD'])
def test_admin_alternativas_invalidas(env,letras):
    client,_=env
    main.app.dependency_overrides[main.get_usuario_atual]=lambda: SimpleNamespace(id=1,is_admin=True)
    r=client.post('/admin/questoes-pratica',json={'curso_assunto_proprio_id':1,'tipo':'MULTIPLA','enunciado':'Escolha','gabarito':'',
        'alternativas':[{'letra':l,'texto':l,'correta':i==0} for i,l in enumerate(letras)]})
    assert r.status_code==400

def test_duplicatas_existentes_bloqueiam(env):
    client,db=env
    somente_questao(db,1)
    marcar(db,1,dificuldade_marcada='FACIL')
    marcar(db,1,dificuldade_marcada='FACIL')
    q=proxima(client,ids_questoes_sessao=[1]).json()
    assert responder(client,q).status_code==409
    assert db.query(models.QuestaoPraticaRotatividadeAluno).count()==0

def test_contexto_curso_usuario_inativo(env):
    client,db=env
    db.get(models.DemonstracaoCurso,1).curso_id=2;db.commit()
    assert proxima(client).status_code==403
    db.get(models.DemonstracaoCurso,1).curso_id=1
    db.get(models.CursoAssuntoProprio,1).ativo=False;db.commit()
    assert proxima(client).status_code==404

def test_conjunto_modificado_e_token_expirado(env):
    from jose import jwt
    client,db=env
    marcar(db,1,dificuldade_marcada='FACIL')
    marcar(db,2,dificuldade_marcada='FACIL')
    q=proxima(client,filtros=['FACIL']).json()
    other=1 if q['questao']['id']==2 else 2
    db.query(models.QuestaoPraticaMarcacaoAluno).filter_by(questao_id=other).one().dificuldade_marcada='DIFICIL';db.commit()
    assert responder(client,q,filtros=['FACIL']).status_code==409
    q=proxima(client).json()
    data=jwt.decode(q['token_sessao'],main.SEGREDO_SESSAO_PRATICA,algorithms=['HS256'])
    data['exp']=int((datetime.utcnow()-timedelta(hours=1)).timestamp())
    expired=jwt.encode(data,main.SEGREDO_SESSAO_PRATICA,algorithm='HS256')
    assert responder(client,q,token_sessao=expired).status_code==409

def test_rollback_da_transacao(env,monkeypatch):
    from sqlalchemy.orm import Session
    client,db=env
    q=proxima(client,ids_questoes_sessao=[1]).json()
    original=Session.commit
    def falhar(session):
        session.flush()
        raise RuntimeError('Falha simulada antes do commit')
    monkeypatch.setattr(Session,'commit',falhar)
    with pytest.raises(RuntimeError): responder(client,q)
    monkeypatch.setattr(Session,'commit',original)
    assert db.query(models.QuestaoPraticaMarcacaoAluno).count()==0
    assert db.query(models.QuestaoPraticaRotatividadeAluno).count()==0

def test_admin_permissao_e_edicao(env):
    client,db=env
    payload={'curso_assunto_proprio_id':1,'tipo':'CERTO_ERRADO','enunciado':'CE','gabarito':'E'}
    assert client.post('/admin/questoes-pratica',json=payload).status_code==403
    main.app.dependency_overrides[main.get_usuario_atual]=lambda: SimpleNamespace(id=1,is_admin=True)
    r=client.post('/admin/questoes-pratica',json=payload);assert r.status_code==200
    id=r.json()['id']
    edit={'tipo':'MULTIPLA','enunciado':'MC','alternativas':[{'letra':l,'texto':l,'correta':l=='B'} for l in 'ABCD']}
    assert client.put(f'/admin/questoes-pratica/{id}',json=edit).status_code==200
    listed=client.get('/admin/curso-assuntos-proprios/1/questoes-pratica').json()
    item=next(q for q in listed if q['id']==id)
    assert item['gabarito']=='B' and len(item['alternativas'])==4
    edit['alternativas'][3]['letra']='E'
    assert client.put(f'/admin/questoes-pratica/{id}',json=edit).status_code==400
    assert client.delete(f'/admin/questoes-pratica/{id}').status_code==200

def test_rever_nao_soube_outro_contexto(env):
    client,db=env
    somente_questao(db,1)
    q=proxima(client,ids_questoes_sessao=[1]).json()
    assert responder(client,q,resposta_marcada='NAO_SEI',rever=True).status_code==200
    assert proxima(client,filtros=['REVER']).json()['ids_questoes_sessao']==[1]
    assert proxima(client,filtros=['ERREI']).status_code==404
    assert proxima(client,demonstracao_id=None,contratacao_id=1,filtros=['REVER']).status_code==404

@pytest.mark.parametrize('resposta',['E','NAO_SEI'])
def test_multipla4_resposta_invalida(env,resposta):
    client,db=env
    somente_questao(db,1)
    q=db.get(models.QuestaoPraticaAssunto,1);q.tipo='MULTIPLA';q.gabarito='B'
    for l in 'ABCD': db.add(models.QuestaoPraticaAlternativa(questao_pratica_id=1,letra=l,texto=l,correta=l=='B'))
    db.commit()
    selected=proxima(client,ids_questoes_sessao=[1]).json()
    assert responder(client,selected,resposta_marcada=resposta).status_code==400


def test_bloqueio_postgresql_chave_contextual():
    calls=[]
    class FakeDB:
        def get_bind(self): return SimpleNamespace(dialect=SimpleNamespace(name='postgresql'))
        def execute(self,statement,params): calls.append((str(statement),params['chave']))
    db=FakeDB()
    main.bloquear_pratica(db,1,1,{'demonstracao_id':1,'contratacao_id':None})
    main.bloquear_pratica(db,1,1,{'demonstracao_id':1,'contratacao_id':None})
    main.bloquear_pratica(db,1,1,{'demonstracao_id':None,'contratacao_id':1})
    assert calls[0]==calls[1] and calls[0][1]!=calls[2][1]
    assert 'pg_advisory_xact_lock' in calls[0][0]


@pytest.mark.parametrize('hint', [[1], [], [4], [1, 4]])
def test_subconjunto_nao_define_ciclo(env, hint):
    client, db = env
    r = proxima(client, ids_questoes_sessao=hint)
    assert r.status_code == 200
    assert r.json()['ids_questoes_sessao'] == [1, 2, 3]
    assert r.json()['ciclo'] == 1


def test_ciclo_incompleto_nao_avanca_nem_pula_questoes(env):
    client, db = env
    primeira = proxima(client).json()
    assert responder(client, primeira).status_code == 200
    for _ in range(8):
        r = proxima(client, ids_questoes_sessao=[primeira['questao']['id']]).json()
        assert r['ciclo'] == 1
        assert r['ids_questoes_sessao'] == [1, 2, 3]
        assert r['questao']['id'] != primeira['questao']['id']
    assert db.query(models.QuestaoPraticaRotatividadeAluno).count() == 1


def test_ciclo_completo_avanca_exatamente_uma_vez(env):
    client, db = env
    vistas = set()
    for _ in range(3):
        r = proxima(client, ids_questoes_sessao=[]).json()
        assert r['ciclo'] == 1 and r['questao']['id'] not in vistas
        vistas.add(r['questao']['id'])
        assert responder(client, r).status_code == 200
    assert vistas == {1, 2, 3}
    assert proxima(client, ids_questoes_sessao=[1]).json()['ciclo'] == 2
    assert proxima(client, ids_questoes_sessao=[]).json()['ciclo'] == 2
    assert responder(client, r).status_code == 409


def test_sessoes_simultaneas_mesma_questao_reenvio(env):
    client, db = env
    somente_questao(db, 1)
    a, b = proxima(client).json(), proxima(client).json()
    assert a['ciclo'] == b['ciclo'] == 1
    assert responder(client, a).status_code == 200
    assert responder(client, b).status_code == 409
    assert db.query(models.QuestaoPraticaRotatividadeAluno).count() == 1


def test_sessoes_simultaneas_questoes_distintas(env, monkeypatch):
    client, db = env
    # Deterministic selections without modifying the server's eligible set.
    from sqlalchemy.orm import Query
    original = Query.first
    escolhida = [1]
    def primeira(query):
        if query.column_descriptions[0].get('entity') is models.QuestaoPraticaAssunto:
            rows = query.all()
            return next((q for q in rows if q.id == escolhida[0]), rows[0] if rows else None)
        return original(query)
    monkeypatch.setattr(Query, 'first', primeira)
    a = proxima(client).json()
    escolhida[0] = 2
    b = proxima(client).json()
    assert a['questao']['id'] == 1 and b['questao']['id'] == 2
    assert responder(client, a).status_code == 200
    assert responder(client, b).status_code == 200
    r = proxima(client).json()
    assert r['ciclo'] == 1 and r['questao']['id'] == 3


def test_ciclo_futuro_assinado_rejeitado(env):
    from jose import jwt
    client, _ = env
    r = proxima(client).json()
    claims = jwt.decode(r['token_sessao'], main.SEGREDO_SESSAO_PRATICA, algorithms=['HS256'])
    claims['ciclo'] = 2
    futuro = jwt.encode(claims, main.SEGREDO_SESSAO_PRATICA, algorithm='HS256')
    assert responder(client, r, token_sessao=futuro).status_code == 409


@pytest.mark.parametrize('secret', ['', 'curto'])
def test_segredo_ausente_ou_fraco_falha_fechada(env, monkeypatch, secret):
    client, db = env
    r = proxima(client).json()
    monkeypatch.setattr(main, 'SEGREDO_SESSAO_PRATICA', secret)
    assert proxima(client).status_code == 503
    assert responder(client, r).status_code == 503
    assert db.query(models.QuestaoPraticaMarcacaoAluno).count() == 0


@pytest.mark.parametrize('campo,valor', [('gabarito','E'), ('enunciado','Texto alterado'), ('comentario','Outro comentário')])
def test_edicao_invalida_sessao_sem_persistir(env, campo, valor):
    client, db = env
    somente_questao(db, 1)
    r = proxima(client).json()
    setattr(db.get(models.QuestaoPraticaAssunto, 1), campo, valor)
    db.commit()
    result = responder(client, r)
    assert result.status_code == 409 and 'alterada' in result.json()['detail']
    assert db.query(models.QuestaoPraticaMarcacaoAluno).count() == 0
    assert db.query(models.QuestaoPraticaRotatividadeAluno).count() == 0
    novo = proxima(client).json()
    assert responder(client, novo).status_code == 200


def test_admin_gabarito_multipla_invalida_sessao(env):
    client, db = env
    somente_questao(db, 1)
    q = db.get(models.QuestaoPraticaAssunto, 1)
    q.tipo = 'MULTIPLA'; q.gabarito = 'B'
    for l in 'ABCD':
        db.add(models.QuestaoPraticaAlternativa(questao_pratica_id=1, letra=l, texto=l, correta=l=='B'))
    db.commit()
    r = proxima(client).json()
    main.app.dependency_overrides[main.get_usuario_atual] = lambda: SimpleNamespace(id=1, is_admin=True)
    payload = {'tipo':'MULTIPLA', 'enunciado':'Teste', 'alternativas':[
        {'letra':l, 'texto':l, 'correta':l=='D'} for l in 'ABCD']}
    assert client.put('/admin/questoes-pratica/1', json=payload).status_code == 200
    assert responder(client, r, resposta_marcada='B').status_code == 409
    novo = proxima(client).json()
    assert responder(client, novo, resposta_marcada='D').json()['acertou'] is True


def test_importacao_isolada_restaura_globais():
    ambiente = dict(os.environ)
    database = sys.modules.get('app.database')
    oficial = sys.modules.get('app.main')
    atributo = getattr(app, 'database', None)
    atributos = dict(vars(app))
    modulos = dict(sys.modules)
    with carregar_main_isolado(SessionTest, engine) as privado:
        assert privado is not oficial
        assert sys.modules.get('app.database') is database
        assert sys.modules.get('app.main') is oficial
        assert dict(os.environ) == ambiente
        assert dict(vars(app)) == atributos
        assert dict(sys.modules) == modulos
    assert sys.modules.get('app.database') is database
    assert sys.modules.get('app.main') is oficial
    assert getattr(app, 'database', None) is atributo
    assert dict(os.environ) == ambiente
