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


@pytest.mark.parametrize('origem', ['PAGAMENTO', 'ADMIN'])
def test_demo_com_atividades_so_aparece_apos_direito_posterior_expirar(historico, origem):
    db,c=historico; agora=datetime.utcnow()
    db.add(m.Curso(id=3,nome='Somente demonstração'))
    db.add(m.CursoDisciplinaPropria(id=3,curso_id=3,nome='Disciplina'))
    db.add(m.CursoAssuntoProprio(id=3,curso_disciplina_propria_id=3,nome='Assunto'))
    db.add(m.Pasta(id=3,curso_assunto_proprio_id=3,tipo='TEORIA',nome='Teoria'))
    db.add(m.Aula(id=3,pasta_id=3,titulo='Aula'))
    db.add(m.Bateria(id=10,aula_id=3,titulo='Bateria',status='CONCLUIDA'))
    db.add(m.Questao(id=20,bateria_id=10,enunciado='Questão',tipo='CERTO_ERRADO',gabarito='C'))
    db.add(m.DemonstracaoCurso(id=10,usuario_id=1,curso_id=3,
        data_inicio=agora-timedelta(days=10),data_fim=agora-timedelta(days=9),
        liberado_novamente_em=agora))
    db.add(m.TentativaBateria(id=20,usuario_id=1,bateria_id=10,demonstracao_id=10,
        status='FEITA',percentual_acerto=100,concluida_em=agora-timedelta(days=9)))
    db.add(m.RespostaAlunoQuestao(id=20,usuario_id=1,bateria_id=10,questao_id=20,
        tentativa_id=20,demonstracao_id=10,resposta_marcada='C',acertou=True))
    db.add(m.AnotacaoAlunoQuestao(id=120,usuario_id=1,bateria_id=10,questao_id=20,
        tentativa_id=20,demonstracao_id=10,texto='Anotação da demonstração'))
    db.add(m.ConversaQuestaoProfessor(id=120,usuario_id=1,bateria_id=10,questao_id=20,
        tentativa_id=20,demonstracao_id=10,status='ABERTA'))
    db.add(m.MensagemConversaQuestao(id=120,conversa_id=120,autor='ALUNO',texto='Mensagem preservada'))
    db.commit()
    tabelas=[m.DemonstracaoCurso,m.TentativaBateria,m.RespostaAlunoQuestao,
             m.AnotacaoAlunoQuestao,m.ConversaQuestaoProfessor,m.MensagemConversaQuestao,m.Pagamento]
    def snapshot():
        return {t.__tablename__:db.execute(t.__table__.select().order_by(t.__table__.c.id)).all() for t in tabelas}
    antes=snapshot()
    def itens():
        resposta=c.get('/me/desempenho/contextos-expirados')
        assert resposta.status_code==200
        return [x for x in resposta.json() if x['curso_id']==3]
    assert itens()==[]
    db.add(m.ContratacaoCurso(id=30,usuario_id=1,curso_id=3,origem=origem,
        data_inicio=agora-timedelta(days=8),data_fim=agora+timedelta(days=1)))
    db.commit()
    assert itens()==[]
    contrato=db.get(m.ContratacaoCurso,30);contrato.data_fim=agora-timedelta(days=1);db.commit()
    linhas=itens()
    assert len(linhas)==1 and linhas[0]['contratacao_id']==30
    assert 'demonstracao_id' not in linhas[0]
    assert snapshot()==antes
    assert db.get(m.ContratacaoCurso,30).origem==origem
