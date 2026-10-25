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
    for table in [m.Usuario.__table__,m.AnotacaoAlunoQuestao.__table__,m.ConversaQuestaoProfessor.__table__,m.MensagemConversaQuestao.__table__,m.ReformulacaoConversaOperacao.__table__]:table.create(db.bind)
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
        main.app.state.main_module=main
        with TestClient(main.app) as c:yield db,c,actor

def iniciar(c,tid=1,**kw):
    body=dict(questao_id=1,bateria_id=1,tentativa_id=tid,demonstracao_id=1,texto='Dúvida')
    body.update(kw)
    return c.post('/me/mensagens-prof',json=body)

def test_tentativas_nao_soube_e_revisao(api):
    db,c,a=api
    assert iniciar(c).status_code==200
    assert iniciar(c).status_code==409
    assert iniciar(c,2).status_code==409
    assert iniciar(c,3).status_code==404
    assert iniciar(c,999).status_code==404
    assert db.query(m.ConversaQuestaoProfessor).count()==1
    assert db.query(m.ConversaQuestaoProfessor).one().tentativa_id==1


def _dados_reformulacao(c, rid, operacao_id="123e4567-e89b-42d3-a456-426614174000", **override):
    estado=c.get("/me/mensagens-prof?demonstracao_id=1").json()[0]["estado_conversa"]
    body={"texto":"Nova pergunta", "operacao_id":operacao_id,
          "estado_conversa":estado, "confirmado":True}
    body.update(override)
    return body


def test_reformular_exclui_e_idempotencia_http(api):
    db,c,_=api
    rid=iniciar(c).json()["conversa_id"]
    # SQLite pode reutilizar o maior ROWID após DELETE; usar um ID alto para
    # testar que a conversa substituta tem outra identidade também nesse dialeto.
    db.query(m.ConversaQuestaoProfessor).filter_by(id=rid).update({m.ConversaQuestaoProfessor.id: 100})
    db.query(m.MensagemConversaQuestao).filter_by(conversa_id=rid).update({m.MensagemConversaQuestao.conversa_id: 100})
    db.commit()
    rid=100
    body=_dados_reformulacao(c,rid)
    url=f"/me/mensagens-prof/{rid}/reformular?demonstracao_id=1"
    resposta=c.post(url,json=body)
    assert resposta.status_code==200,resposta.text
    nova_id=resposta.json()["conversa_id"]
    assert nova_id!=rid and resposta.json()["status"]=="ABERTA"
    assert db.get(m.ConversaQuestaoProfessor,rid) is None
    assert db.query(m.MensagemConversaQuestao).filter_by(conversa_id=rid).count()==0
    assert [x.texto for x in db.query(m.MensagemConversaQuestao).filter_by(conversa_id=nova_id)]==["Nova pergunta"]
    repetida=c.post(url,json=body)
    assert repetida.status_code==200 and repetida.json()["conversa_id"]==nova_id
    assert db.query(m.ConversaQuestaoProfessor).count()==1
    assert db.query(m.MensagemConversaQuestao).count()==1
    assert db.query(m.ReformulacaoConversaOperacao).count()==1
    assert c.post(url,json={**body,"texto":"Parâmetros diferentes"}).status_code==409


def test_reformular_cancelamento_validacao_e_titularidade(api):
    db,c,actor=api
    rid=iniciar(c).json()["conversa_id"]
    body=_dados_reformulacao(c,rid)
    assert c.post(f"/me/mensagens-prof/{rid}/reformular?demonstracao_id=1",json={**body,"confirmado":False}).status_code==422
    actor.id=2
    assert c.post(f"/me/mensagens-prof/{rid}/reformular?demonstracao_id=1",json=body).status_code==404
    actor.id=1
    assert db.get(m.ConversaQuestaoProfessor,rid) is not None
    assert db.query(m.MensagemConversaQuestao).filter_by(conversa_id=rid).count()==1


def test_reformular_rollback_antes_do_commit(api,monkeypatch):
    db,c,_=api
    rid=iniciar(c).json()["conversa_id"]
    body=_dados_reformulacao(c,rid)
    main=c.app.state.main_module
    original=main._resultado_conversa
    def falhar_antes_do_commit(*args,**kwargs):
        raise RuntimeError("falha simulada antes do commit")
    monkeypatch.setattr(main,"_resultado_conversa",falhar_antes_do_commit)
    with pytest.raises(RuntimeError,match="falha simulada"):
        c.post(f"/me/mensagens-prof/{rid}/reformular?demonstracao_id=1",json=body)
    monkeypatch.setattr(main,"_resultado_conversa",original)
    db.expire_all()
    assert db.get(m.ConversaQuestaoProfessor,rid) is not None
    assert db.query(m.MensagemConversaQuestao).filter_by(conversa_id=rid).count()==1
    assert db.query(m.ReformulacaoConversaOperacao).count()==0


@pytest.mark.parametrize("fase", ["ABERTA", "RESPONDIDA", "ENCERRADA"])
def test_reformular_estados_e_preserva_historico_de_estudo(api, fase):
    db,c,actor=api
    rid=iniciar(c).json()["conversa_id"]
    db.query(m.ConversaQuestaoProfessor).filter_by(id=rid).update({m.ConversaQuestaoProfessor.id: 100})
    db.query(m.MensagemConversaQuestao).filter_by(conversa_id=rid).update({m.MensagemConversaQuestao.conversa_id: 100})
    db.commit()
    rid=100
    if fase in {"RESPONDIDA", "ENCERRADA"}:
        actor.is_admin=True; actor.tipo_admin="admin_geral"
        assert c.post(f"/admin/mensagens-questoes/{rid}/responder",json={"texto":"Resposta do professor"}).status_code==200
        actor.is_admin=False; actor.tipo_admin=None
        if fase == "ENCERRADA":
            assert c.post(f"/me/mensagens-prof/{rid}/responder?demonstracao_id=1",json={"texto":"Complemento"}).status_code==200
            actor.is_admin=True; actor.tipo_admin="admin_geral"
            assert c.post(f"/admin/mensagens-questoes/{rid}/responder",json={"texto":"Resposta final"}).status_code==200
            actor.is_admin=False; actor.tipo_admin=None
    db.add(m.AnotacaoAlunoQuestao(usuario_id=1,questao_id=1,bateria_id=1,tentativa_id=1,
        demonstracao_id=1,texto="Anotação preservada")); db.commit()
    antes_tentativas=db.query(m.TentativaBateria).count()
    antes_respostas=db.query(m.RespostaAlunoQuestao).count()
    antes_anotacoes=db.query(m.AnotacaoAlunoQuestao).count()
    estado=_dados_reformulacao(c,rid)
    resposta=c.post(f"/me/mensagens-prof/{rid}/reformular?demonstracao_id=1",json=estado)
    assert resposta.status_code==200,resposta.text
    nova_id=resposta.json()["conversa_id"]
    assert resposta.json()["status"]=="ABERTA"
    assert resposta.json()["questao_id"]==1 and resposta.json()["bateria_id"]==1
    assert [x.autor for x in db.query(m.MensagemConversaQuestao).filter_by(conversa_id=nova_id)]==["ALUNO"]
    assert db.query(m.MensagemConversaQuestao).filter_by(conversa_id=rid).count()==0
    assert db.query(m.TentativaBateria).count()==antes_tentativas
    assert db.query(m.RespostaAlunoQuestao).count()==antes_respostas
    assert db.query(m.AnotacaoAlunoQuestao).count()==antes_anotacoes


def test_resposta_professor_invalida_confirmacao_antiga(api):
    db,c,actor=api
    rid=iniciar(c).json()["conversa_id"]
    dados=_dados_reformulacao(c,rid)
    actor.is_admin=True; actor.tipo_admin="admin_geral"
    assert c.post(f"/admin/mensagens-questoes/{rid}/responder",json={"texto":"Resposta nova"}).status_code==200
    actor.is_admin=False; actor.tipo_admin=None
    resposta=c.post(f"/me/mensagens-prof/{rid}/reformular?demonstracao_id=1",json=dados)
    assert resposta.status_code==409
    assert db.get(m.ConversaQuestaoProfessor,rid) is not None
    assert db.query(m.MensagemConversaQuestao).filter_by(conversa_id=rid).count()==2


def test_reformular_com_acesso_expirado_preserva_conversa(api):
    db,c,_=api
    rid=iniciar(c).json()["conversa_id"]
    dados=_dados_reformulacao(c,rid)
    db.get(m.DemonstracaoCurso,1).data_fim=datetime.utcnow()-timedelta(seconds=1)
    db.commit()
    resposta=c.post(f"/me/mensagens-prof/{rid}/reformular?demonstracao_id=1",json=dados)
    assert resposta.status_code==403
    assert db.get(m.ConversaQuestaoProfessor,rid) is not None
    assert db.query(m.MensagemConversaQuestao).filter_by(conversa_id=rid).count()==1
    assert db.query(m.ReformulacaoConversaOperacao).count()==0


def test_fila_admin_ignora_legada_sem_contexto(api):
    from sqlalchemy import text
    db,c,actor=api
    contextual=iniciar(c).json()["conversa_id"]
    db.execute(text("PRAGMA ignore_check_constraints=ON"))
    legado=m.ConversaQuestaoProfessor(usuario_id=1,questao_id=1,bateria_id=1,status="ABERTA")
    db.add(legado);db.flush()
    db.add(m.MensagemConversaQuestao(conversa_id=legado.id,autor="ALUNO",texto="Legado"));db.commit()
    actor.is_admin=True; actor.tipo_admin="admin_geral"
    filas=c.get("/admin/mensagens-questoes")
    assert filas.status_code==200,filas.text
    assert [r["conversa_id"] for r in filas.json()]==[contextual]
    assert db.get(m.ConversaQuestaoProfessor,legado.id) is not None

def test_alternancia_limite_encerramento_imutavel(api):
    db,c,a=api
    rid=iniciar(c).json()['conversa_id']
    student=f'/me/mensagens-prof/{rid}/responder?demonstracao_id=1'
    admin=f'/admin/mensagens-questoes/{rid}/responder'
    assert c.post(student,json={'texto':'x'}).status_code==409
    assert c.post(admin,json={'texto':'x'}).status_code==403
    for i in range(3):
        a.is_admin=True; a.tipo_admin="admin_geral"
        assert c.post(admin,json={'texto':'Resposta'}).status_code==200
        assert c.post(admin,json={'texto':'extra'}).status_code==409
        a.is_admin=False; a.tipo_admin=None
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
    assert c.get('/me/cursos-expirados/1/mensagens-prof').status_code==400

def test_expiracao_historico_admin_e_indice(api):
    db,c,a=api
    rid=iniciar(c).json()['conversa_id']
    db.get(m.DemonstracaoCurso,1).data_fim=datetime.utcnow()-timedelta(seconds=1)
    db.get(m.ConversaQuestaoProfessor,rid).criado_em=datetime.utcnow()-timedelta(minutes=1);db.commit()
    assert c.get('/me/mensagens-prof?demonstracao_id=1').status_code==403
    contrato=db.get(m.ContratacaoCurso,1)
    contrato.data_fim=db.get(m.DemonstracaoCurso,1).data_fim
    conversa=db.get(m.ConversaQuestaoProfessor,rid)
    conversa.contratacao_id=1; conversa.demonstracao_id=None; db.commit()
    assert len(c.get('/me/cursos-expirados/1/mensagens-prof?contratacao_id=1').json())==1
    assert c.get('/me/cursos-expirados/2/mensagens-prof?contratacao_id=1').status_code==403
    a.is_admin=True; a.tipo_admin="admin_geral"
    assert c.post(f'/admin/mensagens-questoes/{rid}/responder',json={'texto':'Resposta histórica'}).status_code==200
    assert c.get('/admin/mensagens-questoes').status_code==200
    db.add(m.ConversaQuestaoProfessor(usuario_id=1,questao_id=1,bateria_id=1,tentativa_id=1,demonstracao_id=1,status='ABERTA'))
    with pytest.raises(IntegrityError):db.commit()
    db.rollback()

def test_historico_expirado_ignora_legada_e_preserva_contextual(api):
    from sqlalchemy import text
    db,c,_=api
    rid=iniciar(c).json()["conversa_id"]
    db.get(m.DemonstracaoCurso,1).data_fim=datetime.utcnow()-timedelta(seconds=1)
    db.get(m.ConversaQuestaoProfessor,rid).criado_em=datetime.utcnow()-timedelta(minutes=1)
    db.execute(text("PRAGMA ignore_check_constraints=ON"))
    legado=m.ConversaQuestaoProfessor(usuario_id=1,questao_id=1,bateria_id=1,
        tentativa_id=None,contratacao_id=None,demonstracao_id=None,status="ABERTA")
    db.add(legado);db.commit()

    contrato=db.get(m.ContratacaoCurso,1)
    contrato.data_fim=db.get(m.DemonstracaoCurso,1).data_fim
    conversa=db.get(m.ConversaQuestaoProfessor,rid)
    conversa.contratacao_id=1; conversa.demonstracao_id=None; db.commit()
    resposta=c.get('/me/cursos-expirados/1/mensagens-prof?contratacao_id=1')
    assert resposta.status_code==200,resposta.text
    assert [item['conversa_id'] for item in resposta.json()]==[rid]
    assert db.get(m.ConversaQuestaoProfessor,legado.id) is not None

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
