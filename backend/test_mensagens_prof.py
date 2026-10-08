"""Testes HTTP isolados; nunca utiliza banco de produção."""
from datetime import datetime,timedelta
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from app import models as m
from test_revisoes_assunto import env
from test_questoes_pratica_patch import carregar_main_isolado

@pytest.fixture
def api(env):
    db,_=env
    for table in [m.Usuario.__table__,m.ConversaQuestaoProfessor.__table__,m.MensagemConversaQuestao.__table__]:table.create(db.bind)
    db.add(m.Usuario(id=1,nome='Aluno',email='teste@example.com',cpf='00000000000',telefone='0',senha_hash='teste'))
    for i in (1,2,3):
        t=m.TentativaBateria(id=i,usuario_id=1,bateria_id=1,demonstracao_id=1,status='FEITA',revisao_id=1 if i==2 else None)
        db.add(t);db.flush()
        if i!=3:db.add(m.RespostaAlunoQuestao(usuario_id=1,bateria_id=1,questao_id=1,tentativa_id=i,demonstracao_id=1,respondida=True,resposta_marcada='NAO_SEI',pulou=True))
    db.commit()
    with carregar_main_isolado(lambda:db,db.bind) as main:
        actor=SimpleNamespace(id=1,is_admin=False)
        main.app.dependency_overrides[main.get_db]=lambda:db
        main.app.dependency_overrides[main.get_usuario_atual]=lambda:actor
        with TestClient(main.app) as c:yield db,c,actor

def iniciar(c,tid=1,**kw):
    body=dict(questao_id=1,bateria_id=1,tentativa_id=tid,demonstracao_id=1,texto='Dúvida')
    body.update(kw)
    return c.post('/me/mensagens-prof',json=body)

def test_tentativas_nao_soube_e_revisao(api):
    db,c,a=api
    assert iniciar(c).status_code==200
    assert iniciar(c).status_code==409
    assert iniciar(c,2).status_code==200
    assert iniciar(c,3).status_code==404
    assert iniciar(c,999).status_code==404
    assert db.query(m.ConversaQuestaoProfessor).count()==2

def test_alternancia_limite_encerramento_imutavel(api):
    db,c,a=api
    rid=iniciar(c).json()['conversa_id']
    student=f'/me/mensagens-prof/{rid}/responder?demonstracao_id=1'
    admin=f'/admin/mensagens-questoes/{rid}/responder'
    assert c.post(student,json={'texto':'x'}).status_code==409
    assert c.post(admin,json={'texto':'x'}).status_code==403
    for i in range(3):
        a.is_admin=True
        assert c.post(admin,json={'texto':'Resposta'}).status_code==200
        assert c.post(admin,json={'texto':'extra'}).status_code==409
        a.is_admin=False
        assert c.post(student,json={'texto':'continua'}).status_code==(200 if i<2 else 409)
    assert db.query(m.MensagemConversaQuestao).count()==6
    assert db.get(m.ConversaQuestaoProfessor,rid).status=='ENCERRADA'
    assert c.put(student,json={'texto':'editar'}).status_code==405

def test_contexto_usuario_curso_e_palavras(api):
    db,c,a=api
    assert iniciar(c,texto=' ').status_code==422
    assert iniciar(c,texto='palavra '*301).status_code==422
    assert iniciar(c,contratacao_id=1).status_code==400
    assert iniciar(c,demonstracao_id=2).status_code==403
    rid=iniciar(c).json()['conversa_id']
    assert c.get('/me/mensagens-prof?demonstracao_id=1&curso_id=2').status_code==403
    assert c.get('/me/mensagens-prof').status_code==400
    assert c.post(f'/me/mensagens-prof/{rid}/responder?contratacao_id=1',json={'texto':'x'}).status_code==404
    a.id=2
    assert c.get('/me/mensagens-prof?demonstracao_id=1').status_code==403
    assert c.get('/me/cursos-expirados/1/mensagens-prof').json()==[]

def test_expiracao_historico_admin_e_indice(api):
    db,c,a=api
    rid=iniciar(c).json()['conversa_id']
    db.get(m.DemonstracaoCurso,1).data_fim=datetime.utcnow()-timedelta(seconds=1)
    db.get(m.ConversaQuestaoProfessor,rid).criado_em=datetime.utcnow()-timedelta(minutes=1);db.commit()
    assert c.get('/me/mensagens-prof?demonstracao_id=1').status_code==403
    assert len(c.get('/me/cursos-expirados/1/mensagens-prof').json())==1
    assert c.get('/me/cursos-expirados/2/mensagens-prof').json()==[]
    a.is_admin=True
    assert c.post(f'/admin/mensagens-questoes/{rid}/responder',json={'texto':'Resposta histórica'}).status_code==200
    assert c.get('/admin/mensagens-questoes').status_code==200
    db.add(m.ConversaQuestaoProfessor(usuario_id=1,questao_id=1,bateria_id=1,tentativa_id=1,demonstracao_id=1,status='ABERTA'))
    with pytest.raises(IntegrityError):db.commit()
    db.rollback()

def test_contratacao_isolada_da_demonstracao(api):
    db,c,a=api
    db.add(m.TentativaBateria(id=4,usuario_id=1,bateria_id=1,contratacao_id=1,status='FEITA'))
    db.flush()
    db.add(m.RespostaAlunoQuestao(usuario_id=1,bateria_id=1,questao_id=1,tentativa_id=4,contratacao_id=1,respondida=True,resposta_marcada='C'))
    db.commit()
    demo=iniciar(c).json()['conversa_id']
    contract=iniciar(c,4,demonstracao_id=None,contratacao_id=1)
    assert contract.status_code==200
    rid=contract.json()['conversa_id']
    assert {r['conversa_id'] for r in c.get('/me/mensagens-prof?contratacao_id=1').json()}=={rid}
    assert {r['conversa_id'] for r in c.get('/me/mensagens-prof?demonstracao_id=1').json()}=={demo}
    assert c.post(f'/me/mensagens-prof/{rid}/responder?demonstracao_id=1',json={'texto':'x'}).status_code==404
