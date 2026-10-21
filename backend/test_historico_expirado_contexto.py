"""Históricos independentes em SQLite descartável; nenhuma conexão de produção."""
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from app import models as m
from test_revisoes_assunto import env
from test_questoes_pratica_patch import carregar_main_isolado

ROTAS = ['disciplinas', 'anotacoes', 'mensagens-prof', 'desempenho']

@pytest.fixture
def historico(env):
    db, _ = env
    m.Base.metadata.create_all(db.bind, tables=[m.Usuario.__table__, m.AnotacaoAlunoQuestao.__table__,
        m.ConversaQuestaoProfessor.__table__, m.MensagemConversaQuestao.__table__])
    now = datetime.utcnow()
    db.add(m.Curso(id=2,nome="Outro curso"))
    for cid, origem, uid, curso, fim in [(2,'PAGAMENTO',1,1,-2),(3,'ADMIN',1,1,-1),
            (4,'PAGAMENTO',2,1,-1),(5,'ADMIN',1,2,-1),(6,'PAGAMENTO',1,1,2),
            (7,'OUTRA',1,1,-1)]:
        db.add(m.ContratacaoCurso(id=cid, usuario_id=uid, curso_id=curso, origem=origem,
            data_inicio=now-timedelta(days=10), data_fim=now+timedelta(days=fim)))
    db.add(m.DemonstracaoCurso(id=2,usuario_id=1,curso_id=1,data_inicio=now-timedelta(days=10),
        data_fim=now-timedelta(days=1),liberado_novamente_em=now))
    for cid in [2,3,4,6]:
        for ident, data in [(cid, now-timedelta(days=5)),(cid+10,now)]:
            db.add(m.AnotacaoAlunoQuestao(id=ident,usuario_id=2 if cid==4 else 1,
                questao_id=1,bateria_id=1,contratacao_id=cid,texto=f'Nota {ident}',criado_em=data))
            db.add(m.ConversaQuestaoProfessor(id=ident,usuario_id=2 if cid==4 else 1,
                questao_id=1,bateria_id=1,contratacao_id=cid,status='ABERTA',criado_em=data))
            db.add(m.MensagemConversaQuestao(conversa_id=ident,autor='ALUNO',texto=f'Mensagem {ident}'))
    db.add(m.AnotacaoAlunoQuestao(id=99,usuario_id=1,questao_id=1,bateria_id=1,
        demonstracao_id=2,texto='Teste gratuito',criado_em=now-timedelta(days=5)))
    db.commit()
    with carregar_main_isolado(lambda: db, db.bind) as main:
        main.app.dependency_overrides[main.get_db] = lambda: db
        main.app.dependency_overrides[main.get_usuario_atual] = lambda: SimpleNamespace(id=1)
        with TestClient(main.app) as client:
            yield db, client

@pytest.mark.parametrize('rota', ROTAS)
@pytest.mark.parametrize('query,status', [('',400),('contratacao_id=2&demonstracao_id=2',400),
    ('demonstracao_id=2',403),('demonstracao_id=1',403),('contratacao_id=1',403),
    ('contratacao_id=4',403),('contratacao_id=5',403),('contratacao_id=6',403),
    ('contratacao_id=7',403),('contratacao_id=999',403)])
def test_recusa_contextos(historico, rota, query, status):
    _, c = historico
    assert c.get(f'/me/cursos-expirados/1/{rota}?{query}').status_code == status

@pytest.mark.parametrize('cid', [2,3])
def test_compras_admin_multiplos_historicos(historico,cid):
    db,c=historico
    before = [(t.id,t.data_inicio,t.data_fim,t.origem) for t in db.query(m.ContratacaoCurso)]
    for rota in ROTAS:
        r=c.get(f'/me/cursos-expirados/1/{rota}?contratacao_id={cid}')
        assert r.status_code == 200, r.text
        if rota=='anotacoes': assert [x['anotacao_id'] for x in r.json()]==[cid]
        if rota=='mensagens-prof': assert [x['conversa_id'] for x in r.json()]==[cid]
    assert before==[(t.id,t.data_inicio,t.data_fim,t.origem) for t in db.query(m.ContratacaoCurso)]


def test_listagem_exclui_teste_gratuito_e_preserva_recompras(historico):
    _,c=historico
    rows=c.get('/me/desempenho/contextos-expirados').json()
    assert sorted(r['contratacao_id'] for r in rows)==[2,3,5]
    assert all('demonstracao_id' not in r for r in rows)
    assert len([r for r in rows if r['curso_id']==1])==2


def test_demonstracao_ativa_continua_autorizada(historico):
    _,c=historico
    assert c.get('/me/cursos/1/desempenho?demonstracao_id=1').status_code==200
    assert c.get('/me/cursos/1/desempenho?demonstracao_id=2').status_code==403
