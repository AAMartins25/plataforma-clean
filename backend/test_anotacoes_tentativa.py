"""Integração HTTP em SQLite descartável; nunca utiliza o banco local/oficial."""
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from app import models as m
from test_revisoes_assunto import env
from test_questoes_pratica_patch import carregar_main_isolado

@pytest.fixture
def api(env):
    db,_=env
    m.AnotacaoAlunoQuestao.__table__.create(db.bind)
    for tid in (1,2):
        db.add(m.TentativaBateria(id=tid,usuario_id=1,bateria_id=1,demonstracao_id=1,status='FEITA'))
        db.flush()
        db.add(m.RespostaAlunoQuestao(tentativa_id=tid,usuario_id=1,bateria_id=1,questao_id=1,demonstracao_id=1,respondida=True,resposta_marcada='C'))
    db.commit()
    with carregar_main_isolado(lambda:db,db.bind) as main:
        main.app.dependency_overrides[main.get_db]=lambda:db
        main.app.dependency_overrides[main.get_usuario_atual]=lambda:SimpleNamespace(id=1)
        with TestClient(main.app) as client:
            yield db,client

def criar(c,tid=1,**extra):
    payload=dict(questao_id=1,bateria_id=1,tentativa_id=tid,demonstracao_id=1,texto='Anotação teste')
    payload.update(extra)
    return c.post('/me/anotacoes-questoes',json=payload)

def test_duplicata_e_nova_tentativa(api):
    db,c=api
    assert criar(c).status_code==200
    assert criar(c).status_code==409
    assert criar(c,2).status_code==200
    assert db.query(m.AnotacaoAlunoQuestao).count()==2
    rows=c.get('/me/minhas-anotacoes?demonstracao_id=1&curso_id=1').json()
    assert {r['tentativa_id'] for r in rows}=={1,2}

def test_contexto_edicao_exclusao_e_validacao(api):
    db,c=api
    assert criar(c,999).status_code==404
    assert criar(c,texto=' ').status_code==422
    assert criar(c,demonstracao_id=2).status_code==403
    aid=criar(c).json()['id']
    assert c.put(f'/me/anotacoes-questoes/{aid}',json={'texto':'editada'}).status_code==400
    assert c.put(f'/me/anotacoes-questoes/{aid}?demonstracao_id=1',json={'texto':'editada'}).status_code==200
    assert c.delete(f'/me/anotacoes-questoes/{aid}?demonstracao_id=2').status_code==404
    assert c.delete(f'/me/anotacoes-questoes/{aid}?demonstracao_id=1').status_code==200

def test_expirado_historico_legado_e_isolamento(api):
    db,c=api
    criar(c)
    db.add(m.AnotacaoAlunoQuestao(usuario_id=1,questao_id=1,bateria_id=1,demonstracao_id=1,texto='legado'))
    db.add(m.AnotacaoAlunoQuestao(usuario_id=2,questao_id=1,bateria_id=1,demonstracao_id=1,texto='outro aluno'))
    db.commit()
    acesso=db.get(m.DemonstracaoCurso,1)
    acesso.data_fim=datetime.utcnow()-timedelta(seconds=1)
    for a in db.query(m.AnotacaoAlunoQuestao): a.criado_em=acesso.data_fim-timedelta(minutes=1)
    db.commit()
    assert c.get('/me/minhas-anotacoes?demonstracao_id=1').status_code==403
    rows=c.get('/me/cursos-expirados/1/anotacoes').json()
    assert len(rows)==2 and any(r['tentativa_id'] is None for r in rows)
    assert c.get('/me/cursos-expirados/2/anotacoes').json()==[]
    aid=rows[0]['anotacao_id']
    assert c.delete(f'/me/anotacoes-questoes/{aid}?demonstracao_id=1').status_code==403
    assert c.put(f'/me/anotacoes-questoes/{aid}?demonstracao_id=1',json={'texto':'x'}).status_code==403

def test_indice_unico_e_legados_sem_tentativa(api):
    from sqlalchemy.exc import IntegrityError
    db,c=api
    criar(c)
    db.add(m.AnotacaoAlunoQuestao(usuario_id=1,questao_id=1,bateria_id=1,demonstracao_id=1,tentativa_id=1,texto='duplicada'))
    with pytest.raises(IntegrityError): db.commit()
    db.rollback()
    for _ in range(2): db.add(m.AnotacaoAlunoQuestao(usuario_id=1,questao_id=1,bateria_id=1,demonstracao_id=1,texto='legado'))
    db.commit()
    assert db.query(m.AnotacaoAlunoQuestao).count()==3

def test_tentativa_revisao_e_nao_expor_texto_fora_da_vigencia(api):
    db,c=api
    db.get(m.TentativaBateria,2).revisao_id=1
    db.commit()
    assert criar(c,2).status_code==200
    assert criar(c,2).status_code==409
    acesso=db.get(m.DemonstracaoCurso,1)
    acesso.data_fim=datetime.utcnow()-timedelta(seconds=1)
    db.commit()
    assert c.get('/me/cursos-expirados/1/anotacoes').json()==[]
