from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import models as m
from app.desempenho import consultar, registrar_rotas
from test_revisoes_assunto import env, enviar
from test_questoes_pratica_patch import carregar_main_isolado


def tentativa(db, tid, data, nota, revisao=None, status='FEITA', cid=None, did=1, usuario=1, completa=True):
    t=m.TentativaBateria(id=tid,usuario_id=usuario,bateria_id=1,status=status,ativo=False,
        contratacao_id=cid,demonstracao_id=did,revisao_id=revisao,percentual_acerto=nota,
        concluida_em=data if revisao else data-timedelta(days=2),
        revisao_concluida_em=None if revisao else data)
    db.add(t);db.flush()
    for i in range(1,11 if completa else 2):
        db.add(m.RespostaAlunoQuestao(usuario_id=usuario,bateria_id=1,questao_id=i,tentativa_id=tid,
            contratacao_id=cid,demonstracao_id=did,resposta_marcada='NAO_SEI',respondida=True))
    db.commit()
    return t


def bateria(db,cid=None,did=1):
    return consultar(db,1,1,cid,did)['disciplinas'][0]['assuntos'][0]['baterias'][0]


def test_ultima_conclusao_ordem_datas_incompleta_refazer(env):
    db,_=env;now=datetime.utcnow()
    tentativa(db,20,now-timedelta(hours=2),80)
    tentativa(db,10,now-timedelta(hours=1),30,revisao=1)
    tentativa(db,30,now,100,status='EM_ANDAMENTO')
    assert bateria(db)['percentual_acerto']==30
    db.get(m.TentativaBateria,30).status='FEITA';db.commit()
    assert bateria(db)['percentual_acerto']==100
    tentativa(db,40,now+timedelta(minutes=1),10,completa=False)
    assert bateria(db)['percentual_acerto']==100


def test_isolamento_e_dados_incompletos(env):
    db,_=env;now=datetime.utcnow()
    tentativa(db,1,now,60)
    tentativa(db,2,now+timedelta(hours=1),20,cid=1,did=None)
    tentativa(db,3,now+timedelta(hours=2),90,usuario=2)
    assert bateria(db)['percentual_acerto']==60
    assert bateria(db,1,None)['percentual_acerto']==20
    db.get(m.TentativaBateria,1).revisao_concluida_em=None;db.commit()
    assert bateria(db)['percentual_acerto'] is None


def test_rotas_expiracao_sem_escrita(env):
    db,_=env;app=FastAPI();actor=SimpleNamespace(id=1)
    with carregar_main_isolado(lambda:db,db.bind) as main:
        registrar_rotas(app,lambda:db,lambda:actor,main.validar_contexto_estudo)
        with TestClient(app) as c:
            assert c.get('/me/cursos/1/desempenho?demonstracao_id=1').status_code==200
            assert c.get('/me/cursos/2/desempenho?demonstracao_id=1').status_code==403
            assert c.get('/me/cursos-expirados/1/desempenho?demonstracao_id=1').status_code==403
            d=db.get(m.DemonstracaoCurso,1);d.data_fim=datetime.utcnow()-timedelta(seconds=1);db.commit()
            before=(d.ativo,d.data_inicio,d.data_fim)
            assert c.get('/me/cursos-expirados/1/desempenho?demonstracao_id=1').status_code==200
            assert c.get('/me/cursos/1/desempenho?demonstracao_id=1').status_code==403
            assert c.get('/me/cursos-expirados/1/desempenho?demonstracao_id=1&contratacao_id=1').status_code==400
            assert len(c.get('/me/desempenho/contextos-expirados').json())==1
            actor.id=2
            assert c.get('/me/cursos-expirados/1/desempenho?demonstracao_id=1').status_code==403
            assert c.get('/me/desempenho/contextos-expirados').json()==[]
            db.refresh(d);assert before==(d.ativo,d.data_inicio,d.data_fim)


@pytest.mark.parametrize('tipo,esperado',[('CERTO_ERRADO',-20),('MULTIPLA',40)])
def test_pontuacao_revisao(env,tipo,esperado):
    db,c=env
    for i in range(1,11):
        db.get(m.Questao,i).tipo=tipo
        if tipo=='MULTIPLA':
            db.get(m.Questao,i).gabarito='A'
            for letra in 'ABCD':db.add(m.Alternativa(questao_id=i,letra=letra,texto=letra))
    db.commit()
    respostas=[{'questao_id':i,'resposta_marcada':('C' if tipo=='CERTO_ERRADO' else 'A') if i<=4 else ('E' if tipo=='CERTO_ERRADO' else 'B')} for i in range(1,11)]
    assert c.post('/me/revisoes/1/baterias/1/respostas?demonstracao_id=1',json={'respostas':respostas}).status_code==200
    db.expire_all();assert db.query(m.TentativaBateria).one().percentual_acerto==esperado


def test_nao_sei_total_revisao(env):
    db,c=env
    assert enviar(c,marcada='NAO_SEI').status_code==200
    db.expire_all();assert db.query(m.TentativaBateria).one().percentual_acerto==0

@pytest.mark.parametrize('tipo,esperado',[('CERTO_ERRADO',10),('MULTIPLA',40)])
def test_pontuacao_normal_com_nao_sei(env,tipo,esperado):
    from app import schemas
    db,_=env
    for i in range(1,11):
        q=db.get(m.Questao,i);q.tipo=tipo;q.gabarito='C' if tipo=='CERTO_ERRADO' else 'A'
    db.commit()
    respostas=[{'questao_id':i,'resposta_marcada':(('C' if tipo=='CERTO_ERRADO' else 'A') if i<=4 else ('E' if tipo=='CERTO_ERRADO' else 'B') if i<=7 else 'NAO_SEI')} for i in range(1,11)]
    with carregar_main_isolado(lambda:db,db.bind) as main:
        result=main.concluir_bateria_aluno(schemas.ConcluirBateriaCreate(bateria_id=1,demonstracao_id=1,respostas=respostas),db,SimpleNamespace(id=1))
        assert result['percentual_acerto']==esperado


def test_pontuacao_ce_revisao_com_nao_sei(env):
    db,c=env
    respostas=[{'questao_id':i,'resposta_marcada':'C' if i<=4 else 'E' if i<=7 else 'NAO_SEI'} for i in range(1,11)]
    assert c.post('/me/revisoes/1/baterias/1/respostas?demonstracao_id=1',json={'respostas':respostas}).status_code==200
    db.expire_all();assert db.query(m.TentativaBateria).one().percentual_acerto==10
