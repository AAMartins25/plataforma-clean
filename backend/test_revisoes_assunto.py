"""Tests exclusively in disposable SQLite; never imports app.database."""
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import models as m
from app.revisoes import registrar_rotas, programar_primeira
from test_questoes_pratica_patch import carregar_main_isolado

TABLES = [m.Curso.__table__, m.CursoDisciplinaPropria.__table__, m.CursoAssuntoProprio.__table__,
          m.DemonstracaoCurso.__table__, m.ContratacaoCurso.__table__, m.Pasta.__table__, m.Aula.__table__, m.Bateria.__table__, m.Questao.__table__,
          m.Alternativa.__table__, m.RevisaoAluno.__table__, m.TentativaBateria.__table__,
          m.RespostaAlunoQuestao.__table__, m.ProgressoAula.__table__]

@pytest.fixture
def env():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    m.Base.metadata.create_all(engine,tables=TABLES)
    factory=sessionmaker(bind=engine, autoflush=False)
    db=factory()
    db.add(m.Curso(id=1,nome='Curso'))
    db.add(m.CursoDisciplinaPropria(id=1,curso_id=1,nome='Disciplina',disponivel_demonstracao=True))
    db.add(m.CursoAssuntoProprio(id=1,curso_disciplina_propria_id=1,nome='Assunto'))
    db.add(m.Pasta(id=1,curso_assunto_proprio_id=1,tipo='TEORIA',nome='Teoria'))
    db.add(m.Aula(id=1,pasta_id=1,titulo='Aula',ativo=True))
    db.add(m.Bateria(id=1,aula_id=1,titulo='Disponível',status='CONCLUIDA',ativo=True))
    db.add(m.Bateria(id=2,aula_id=1,titulo='Preparação',status='EM_ANDAMENTO',ativo=True))
    db.add(m.Bateria(id=3,aula_id=1,titulo='Não liberada',status='CONCLUIDA',ativo=False))
    for i in range(1,11):
        db.add(m.Questao(id=i,bateria_id=1,enunciado='Teste',tipo='CERTO_ERRADO',tipo_questao='CERTO_ERRADO',gabarito='C',ordem=i,ativo=True))
    db.add(m.RevisaoAluno(id=1,usuario_id=1,pasta_id=1,aula_id=1,demonstracao_id=1,etapa=1,status='PENDENTE',data_prevista=datetime.utcnow()-timedelta(days=1)))
    db.add(m.DemonstracaoCurso(id=1,usuario_id=1,curso_id=1,data_inicio=datetime.utcnow()-timedelta(days=1),data_fim=datetime.utcnow()+timedelta(days=1),liberado_novamente_em=datetime.utcnow()))
    db.add(m.ContratacaoCurso(id=1,usuario_id=1,curso_id=1,origem='ADMIN',data_inicio=datetime.utcnow()-timedelta(days=1)))
    db.commit()
    app=FastAPI()
    def get_db():
        session=factory()
        try: yield session
        finally: session.close()
    with carregar_main_isolado(factory,engine) as main:
        registrar_rotas(app,get_db,lambda:SimpleNamespace(id=1),main.validar_contexto_estudo)
        with TestClient(app) as client:
            yield db,client
    db.close();engine.dispose()

Q='?demonstracao_id=1'
def enviar(client, ids=range(1,11), marcada='C'):
    return client.post('/me/revisoes/1/baterias/1/respostas'+Q,json={'respostas':[{'questao_id':i,'resposta_marcada':marcada} for i in ids]})

def test_conclusao_completa_idempotente_e_prazo(env):
    db,c=env
    assert enviar(c).status_code==200
    assert enviar(c).status_code==200
    assert c.put('/me/revisoes/1/concluir'+Q).status_code==200
    assert c.put('/me/revisoes/1/concluir'+Q).status_code==200
    db.expire_all()
    assert db.query(m.TentativaBateria).count()==1
    assert db.query(m.RespostaAlunoQuestao).count()==10
    assert db.query(m.RevisaoAluno).count()==2
    a,b=db.query(m.RevisaoAluno).order_by(m.RevisaoAluno.id).all()
    assert b.data_prevista-a.concluida_em==timedelta(days=15)

def test_incompleta_subconjunto_e_contexto(env):
    db,c=env
    assert enviar(c,[1]).status_code==400
    assert c.put('/me/revisoes/1/concluir'+Q).status_code==409
    assert c.get('/me/revisoes/1?demonstracao_id=2').status_code==404
    assert c.get('/me/revisoes/1?demonstracao_id=1&contratacao_id=1').status_code==400
    assert db.query(m.RespostaAlunoQuestao).count()==0

def test_nao_soube_conta(env):
    db,c=env
    assert enviar(c,marcada='NAO_SEI').status_code==200
    assert c.put('/me/revisoes/1/concluir'+Q).status_code==200
    db.expire_all()
    assert all(r.pulou and not r.acertou for r in db.query(m.RespostaAlunoQuestao))

def test_questao_retirada_e_nova_bateria(env):
    db,c=env
    db.get(m.Questao,10).ativo=False;db.commit()
    assert enviar(c,range(1,10)).status_code==400
    assert enviar(c).status_code==200
    db.add(m.Bateria(id=4,aula_id=1,titulo='Nova',status='CONCLUIDA',ativo=True))
    db.add(m.Questao(id=11,bateria_id=4,enunciado='Nova',tipo='CERTO_ERRADO',gabarito='E',ativo=True));db.commit()
    assert c.put('/me/revisoes/1/concluir'+Q).status_code==409
    db.get(m.Bateria,4).ativo=False;db.commit()
    assert c.put('/me/revisoes/1/concluir'+Q).status_code==200

def test_perda_objeto_cancela_sem_proxima(env):
    db,c=env
    db.get(m.Bateria,1).ativo=False;db.commit()
    assert c.post('/me/revisoes/1/reconciliar'+Q).json()['status']=='CANCELADA'
    assert c.put('/me/revisoes/1/concluir'+Q).json()['status']=='CANCELADA'
    db.expire_all()
    assert db.query(m.RevisaoAluno).count()==1
    assert db.get(m.RevisaoAluno,1).motivo_cancelamento=='PERDA_DE_OBJETO'

def test_futura_e_quarta_etapa(env):
    db,c=env
    db.get(m.RevisaoAluno,1).data_prevista=datetime.utcnow()+timedelta(days=1);db.commit()
    assert enviar(c).status_code==409
    assert c.put('/me/revisoes/1/concluir'+Q).status_code==409
    r=db.get(m.RevisaoAluno,1);r.data_prevista=datetime.utcnow()-timedelta(days=1);r.etapa=4;db.commit()
    assert enviar(c).status_code==200
    assert c.put('/me/revisoes/1/concluir'+Q).status_code==200
    db.expire_all();assert db.query(m.RevisaoAluno).count()==1

def test_estudo_normal_nao_completa_revisao(env):
    db,c=env
    t=m.TentativaBateria(usuario_id=1,bateria_id=1,demonstracao_id=1,status='FEITA',ativo=True)
    db.add(t);db.flush()
    for i in range(1,11): db.add(m.RespostaAlunoQuestao(usuario_id=1,bateria_id=1,questao_id=i,tentativa_id=t.id,demonstracao_id=1,resposta_marcada='C',respondida=True))
    db.commit()
    assert c.put('/me/revisoes/1/concluir'+Q).status_code==409
    programar_primeira(db,1,db.get(m.Aula,1),None,1);db.commit()
    assert db.query(m.RevisaoAluno).count()==1

@pytest.mark.parametrize('etapa,intervalo',[(2,21),(3,28)])
def test_intervalos_restantes(env,etapa,intervalo):
    db,c=env
    db.get(m.RevisaoAluno,1).etapa=etapa;db.commit()
    assert enviar(c).status_code==200
    assert c.put('/me/revisoes/1/concluir'+Q).status_code==200
    db.expire_all()
    a,b=db.query(m.RevisaoAluno).order_by(m.RevisaoAluno.id).all()
    assert b.etapa==etapa+1
    assert b.data_prevista-a.concluida_em==timedelta(days=intervalo)

def test_primeira_revisao_nao_reprograma_apos_quarta(env):
    db,c=env
    r=db.get(m.RevisaoAluno,1);r.status='CONCLUIDA';r.concluida=True;r.etapa=4;db.commit()
    programar_primeira(db,1,db.get(m.Aula,1),None,1);db.commit()
    assert db.query(m.RevisaoAluno).count()==1

def test_get_nao_cancela_e_bateria_indisponivel(env):
    db,c=env
    assert c.get('/me/revisoes/1/baterias/2/questoes'+Q).status_code==404
    assert c.get('/me/revisoes/1/baterias/3/questoes'+Q).status_code==404
    db.get(m.Bateria,1).ativo=False;db.commit()
    assert c.get('/me/revisoes/1'+Q).json()['perda_de_objeto']
    db.expire_all();assert db.get(m.RevisaoAluno,1).status=='PENDENTE'

def test_expiracao_real_e_contratacao_isolada(env):
    db,c=env
    db.add(m.RevisaoAluno(id=2,usuario_id=1,pasta_id=1,aula_id=1,contratacao_id=1,etapa=1,status='PENDENTE',data_prevista=datetime.utcnow()-timedelta(days=1)))
    db.commit()
    assert c.get('/me/revisoes/2?contratacao_id=1').status_code==200
    assert c.get('/me/revisoes/2'+Q).status_code==404
    assert enviar(c).status_code==200
    assert c.put('/me/revisoes/2/concluir?contratacao_id=1').status_code==409
    db.get(m.DemonstracaoCurso,1).data_fim=datetime.utcnow()-timedelta(seconds=1);db.commit()
    assert c.get('/me/revisoes/1'+Q).status_code==403


def test_primeira_programacao_com_respostas_persistidas(env):
    db,c=env
    db.delete(db.get(m.RevisaoAluno,1));db.commit()
    t=m.TentativaBateria(usuario_id=1,bateria_id=1,demonstracao_id=1,status='FEITA',ativo=True,concluida_em=datetime.utcnow())
    db.add(t);db.flush()
    for i in range(1,11): db.add(m.RespostaAlunoQuestao(usuario_id=1,bateria_id=1,questao_id=i,tentativa_id=t.id,demonstracao_id=1,resposta_marcada='C',respondida=True))
    db.commit()
    programar_primeira(db,1,db.get(m.Aula,1),None,1);db.commit()
    programar_primeira(db,1,db.get(m.Aula,1),None,1);db.commit()
    r=db.query(m.RevisaoAluno).one()
    assert r.data_prevista-t.concluida_em==timedelta(days=7)
    assert db.query(m.ProgressoAula).one().concluida


def tentativa_normal(db, status='FEITA', quantidade=10, ativa=True, contexto_id=1):
    t=m.TentativaBateria(usuario_id=1,bateria_id=1,demonstracao_id=contexto_id,
                         revisao_id=None,status=status,ativo=ativa,concluida_em=datetime.utcnow())
    db.add(t);db.flush()
    for i in range(1,quantidade+1):
        db.add(m.RespostaAlunoQuestao(usuario_id=1,bateria_id=1,questao_id=i,
            tentativa_id=t.id,demonstracao_id=contexto_id,resposta_marcada='NAO_SEI',respondida=True,pulou=True))
    db.commit()
    return t


def test_anterior_completa_valida_posterior_incompleta(env):
    db,_=env
    db.delete(db.get(m.RevisaoAluno,1));db.commit()
    antiga=tentativa_normal(db,ativa=False)
    tentativa_normal(db,status='EM_ANDAMENTO',quantidade=3)
    programar_primeira(db,1,db.get(m.Aula,1),None,1);db.commit()
    assert db.query(m.RevisaoAluno).one().data_prevista==antiga.concluida_em+timedelta(days=7)


def test_nova_completa_substitui_anterior_com_autoflush_false(env):
    db,_=env
    db.delete(db.get(m.RevisaoAluno,1));db.commit()
    tentativa_normal(db,ativa=False)
    nova=tentativa_normal(db,status='EM_ANDAMENTO')
    nova.status='FEITA'  # Ainda não persistida. programar_primeira deve fazer flush.
    programar_primeira(db,1,db.get(m.Aula,1),None,1);db.commit()
    assert db.query(m.RevisaoAluno).one().data_prevista==nova.concluida_em+timedelta(days=7)


def test_feita_sem_todas_respostas_nao_substitui_completa(env):
    db,_=env
    db.delete(db.get(m.RevisaoAluno,1));db.commit()
    antiga=tentativa_normal(db)
    tentativa_normal(db,quantidade=2)
    programar_primeira(db,1,db.get(m.Aula,1),None,1);db.commit()
    assert db.query(m.RevisaoAluno).one().data_prevista==antiga.concluida_em+timedelta(days=7)


def test_cancelada_perda_objeto_nova_agenda_sem_reabrir(env):
    db,c=env
    db.get(m.Bateria,1).ativo=False;db.commit()
    assert c.post('/me/revisoes/1/reconciliar'+Q).json()['status']=='CANCELADA'
    db.get(m.Bateria,1).ativo=True;db.commit()
    assert c.get('/me/revisoes/1'+Q).json()['status']=='CANCELADA'
    assert db.query(m.RevisaoAluno).count()==1
    programar_primeira(db,1,db.get(m.Aula,1),None,1);db.commit()
    assert db.query(m.RevisaoAluno).count()==1  # Falta comprovar estudo normal.
    tentativa_normal(db)
    programar_primeira(db,1,db.get(m.Aula,1),None,1);db.commit()
    programar_primeira(db,1,db.get(m.Aula,1),None,1);db.commit()
    revisoes=db.query(m.RevisaoAluno).order_by(m.RevisaoAluno.id).all()
    assert len(revisoes)==2
    assert revisoes[0].status=='CANCELADA'
    assert revisoes[0].motivo_cancelamento=='PERDA_DE_OBJETO'
    assert revisoes[1].status=='PENDENTE' and revisoes[1].etapa==1


def test_contexto_errado_nao_programa_primeira(env):
    db,_=env
    db.delete(db.get(m.RevisaoAluno,1));db.commit()
    tentativa_normal(db,contexto_id=2)
    programar_primeira(db,1,db.get(m.Aula,1),None,1);db.commit()
    assert db.query(m.RevisaoAluno).count()==0


def test_finalizacao_real_considera_feita_sem_autoflush(env):
    db,_=env
    db.delete(db.get(m.RevisaoAluno,1));db.commit()
    t=tentativa_normal(db,status='EM_ANDAMENTO')
    with carregar_main_isolado(lambda: db,db.bind) as main:
        result=main.finalizar_revisao_tentativa(t.id,db,SimpleNamespace(id=1))
    assert result['status']=='FEITA'
    assert db.query(m.RevisaoAluno).one().etapa==1


def test_todas_baterias_disponiveis_precisam_respostas(env):
    db,_=env
    db.delete(db.get(m.RevisaoAluno,1));db.commit()
    tentativa_normal(db)
    db.get(m.Bateria,2).status='CONCLUIDA'
    db.add(m.Questao(id=11,bateria_id=2,enunciado='Nova bateria',tipo='CERTO_ERRADO',gabarito='C',ativo=True));db.commit()
    programar_primeira(db,1,db.get(m.Aula,1),None,1);db.commit()
    assert db.query(m.RevisaoAluno).count()==0
    t=m.TentativaBateria(usuario_id=1,bateria_id=2,demonstracao_id=1,status='FEITA',ativo=True,concluida_em=datetime.utcnow())
    db.add(t);db.flush()
    db.add(m.RespostaAlunoQuestao(usuario_id=1,bateria_id=2,questao_id=11,tentativa_id=t.id,demonstracao_id=1,resposta_marcada='NAO_SEI',pulou=True,respondida=True));db.commit()
    programar_primeira(db,1,db.get(m.Aula,1),None,1);db.commit()
    assert db.query(m.RevisaoAluno).count()==1
