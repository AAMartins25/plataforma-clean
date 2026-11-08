"""Rotas reais, SQLite descartável e MP simulado; sem configuração de produção."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from app import models as m
from test_compras_fluxo import ambiente_compra, motor, contrato, demo

ADMIN = SimpleNamespace(id=2, is_admin=True, tipo_admin='admin_geral')
ALUNO = SimpleNamespace(id=1, email='1@teste.local', is_admin=False)

# Todas as relações consultadas pela proteção, inclusive atividade legada sem
# contratação. A estrutura de conteúdo não é, por si só, vínculo de aluno.
MODELOS = [m.Disciplina, m.Assunto, m.CursoDisciplinaPropria, m.CursoAssuntoProprio,
    m.Pasta, m.Aula, m.Bateria, m.Questao, m.ProgressoAula, m.RevisaoAluno,
    m.TentativaBateria, m.RespostaAlunoQuestao, m.AnotacaoAlunoQuestao,
    m.ConversaQuestaoProfessor, m.QuestaoPraticaAssunto, m.RespostaQuestaoPratica,
    m.QuestaoPraticaMarcacaoAluno, m.QuestaoPraticaRotatividadeAluno, m.AceiteJuridico]

@pytest.fixture
def comercial(ambiente_compra):
    main, client, factory, post, get = ambiente_compra
    with factory() as db:
        tabelas = {x.__table__ for x in MODELOS} | {m.curso_disciplina}
        while True:
            deps = {fk.column.table for t in tabelas for fk in t.foreign_keys}
            if deps <= tabelas: break
            tabelas |= deps
        m.Base.metadata.create_all(db.get_bind(), tables=list(tabelas))
    return ambiente_compra


def ator(ambiente, usuario):
    ambiente[0].app.dependency_overrides[ambiente[0].get_usuario_atual] = lambda: usuario


def conteudo(db, legado=False):
    if legado:
        db.add(m.Disciplina(id=1,nome='Legada'));db.flush()
        db.execute(m.curso_disciplina.insert().values(curso_id=1,disciplina_id=1))
        db.add(m.Assunto(id=1,disciplina_id=1,nome='Assunto legado'));db.flush()
        db.add(m.Pasta(id=1,assunto_id=1,nome='Teoria',tipo='TEORIA'))
    else:
        db.add(m.CursoDisciplinaPropria(id=1,curso_id=1,nome='Disciplina',disponivel_demonstracao=True));db.flush()
        db.add(m.CursoAssuntoProprio(id=1,curso_disciplina_propria_id=1,nome='Assunto'));db.flush()
        db.add(m.Pasta(id=1,curso_assunto_proprio_id=1,nome='Teoria',tipo='TEORIA'))
    db.flush();db.add(m.Aula(id=1,pasta_id=1,titulo='Aula'));db.flush()
    db.add(m.Bateria(id=1,aula_id=1,titulo='Bateria',status='CONCLUIDA'));db.flush()
    db.add(m.Questao(id=1,bateria_id=1,enunciado='Teste',tipo='CERTO_ERRADO',gabarito='C'));db.commit()


def test_catalogo_reativacao_preserva_direitos_revisoes_desempenho(comercial):
    a=comercial;_,c,f,_,_=a
    with f() as db:
        conteudo(db);cid=contrato(db);did=demo(db)
        agora=datetime.utcnow()
        db.add(m.AcessoCurso(usuario_id=1,curso_id=1,ativo=True,data_inicio=agora-timedelta(days=1),data_fim=agora+timedelta(days=30)))
        db.add(m.RevisaoAluno(usuario_id=1,pasta_id=1,aula_id=1,contratacao_id=cid,status='PENDENTE',data_prevista=agora))
        db.add(m.ProgressoAula(usuario_id=1,pasta_id=1,aula_id=1,contratacao_id=cid,concluida=True))
        db.add(m.TentativaBateria(usuario_id=1,bateria_id=1,contratacao_id=cid,status='FEITA',percentual_acerto=100,revisao_concluida_em=agora))
        db.commit()
        tabelas=[m.ContratacaoCurso,m.DemonstracaoCurso,m.AcessoCurso,m.RevisaoAluno,m.ProgressoAula,m.TentativaBateria]
        antes={t.__tablename__:[tuple(x) for x in db.execute(t.__table__.select())] for t in tabelas}
    rotas=['/me/cursos',f'/me/revisoes?contratacao_id={cid}',f'/me/cursos/1/desempenho?contratacao_id={cid}',f'/me/cursos/1/desempenho?demonstracao_id={did}']
    respostas={r:c.get(r).json() for r in rotas}
    for r in rotas: assert c.get(r).status_code==200,r
    assert 1 in [x['id'] for x in c.get('/cursos-publicos').json()]
    ator(a,ADMIN)
    for _ in range(2): assert c.put('/admin/cursos/1/retirar-venda',json={}).status_code==200
    assert 1 not in [x['id'] for x in c.get('/cursos-publicos').json()]
    assert c.get('/public/cursos/1/checkout').json()['publicado'] is False
    with f() as db:
        assert db.get(m.Curso,1).ativo is True
        assert antes=={t.__tablename__:[tuple(x) for x in db.execute(t.__table__.select())] for t in tabelas}
    ator(a,ALUNO)
    for r in rotas: assert c.get(r).json()==respostas[r],r
    ator(a,ADMIN)
    assert c.put('/admin/cursos/1/publicar',json={}).status_code==200
    assert 1 in [x['id'] for x in c.get('/cursos-publicos').json()]
    ator(a,ALUNO)
    assert c.post('/cursos/2/demonstracao').status_code==200


def test_novas_aquisicoes_diretas_bloqueadas_sem_efeito_financeiro(comercial):
    _,c,f,post,_=comercial
    with f() as db:db.get(m.Curso,1).publicado=False;db.commit()
    assert c.post('/cursos/1/demonstracao').status_code==409
    r=c.post('/checkout/mercadopago',json={'tempo_acesso_id':1})
    assert r.status_code==409 and 'venda' in r.json()['detail']
    post.assert_not_called()
    with f() as db:
        for modelo in [m.Pagamento,m.OportunidadeCompra,m.DemonstracaoCurso,m.ContratacaoCurso]:assert db.query(modelo).count()==0
    ator(comercial,ADMIN)
    assert c.put('/admin/cursos/1/publicar',json={}).status_code==200
    ator(comercial,ALUNO)
    assert c.post('/cursos/1/demonstracao').status_code==200
    assert c.post('/checkout/mercadopago',json={'tempo_acesso_id':1}).status_code==200
    assert post.call_count==1


def test_pendente_retoma_e_confirma_apos_retirar_venda(comercial):
    a=comercial;main,c,f,post,get=a
    compra=c.post('/checkout/mercadopago',json={'tempo_acesso_id':1}).json()
    ator(a,ADMIN);assert c.put('/admin/cursos/1/retirar-venda',json={}).status_code==200
    ator(a,ALUNO)
    retomada=c.post('/checkout/mercadopago',json={'tempo_acesso_id':1})
    assert retomada.status_code==200 and retomada.json()['pagamento_id']==compra['pagamento_id']
    assert c.post('/checkout/mercadopago',json={'tempo_acesso_id':2}).status_code==409
    assert post.call_count==1
    with f() as db:identidade=db.get(m.Pagamento,compra['pagamento_id']).checkout_identidade
    get.return_value.json.return_value={'id':'801','status':'approved','date_approved':datetime.utcnow().isoformat()+'Z','transaction_amount':49.90,'currency_id':'BRL','external_reference':'checkout:'+identidade,'collector_id':123456,'live_mode':True}
    from test_pausa_financeira import enviar
    with patch.object(main,'validar_assinatura_mercadopago',return_value=True):
        assert enviar(a,801,'publicacao-pendente').status_code==200
        assert c.post('/pagamentos/confirmar',json={'payment_id':'801','curso_id':1}).status_code==200
    with f() as db:
        assert db.query(m.ContratacaoCurso).count()==1
        assert db.query(m.PeriodoAcessoPagamento).count()==1
        assert db.query(m.AcessoCurso).one().ativo
        assert not db.get(m.Curso,1).publicado


@pytest.mark.parametrize('origem',['ADMIN','PAGAMENTO'])
def test_renovacao_valida_independe_publicacao(comercial,origem):
    _,c,f,post,_=comercial
    with f() as db:cid=contrato(db,origem,10);db.get(m.Curso,1).publicado=False;db.commit()
    assert c.post('/checkout/mercadopago',json={'tempo_acesso_id':1,'tipo_compra':'RENOVACAO','contratacao_id':cid}).status_code==200
    assert post.call_count==1
    assert c.post('/checkout/mercadopago',json={'tempo_acesso_id':1,'tipo_compra':'RENOVACAO','contratacao_id':cid+100}).status_code==409


@pytest.mark.parametrize('vinculo',['acesso','contrato_vigente','contrato_expirado','concessao','demo_expirada','pagamento_pendente','pagamento_cancelado','oportunidade','progresso','revisao','tentativa','resposta','anotacao','pratica','marcacao','rotatividade','legado'])
@pytest.mark.parametrize('metodo',['delete','put'])
def test_exclusao_protege_todos_os_vinculos(comercial,vinculo,metodo):
    a=comercial;_,c,f,_,_=a;ator(a,ADMIN)
    with f() as db:
        agora=datetime.utcnow()
        if vinculo=='acesso':db.add(m.AcessoCurso(usuario_id=1,curso_id=1,ativo=False))
        elif vinculo.startswith('contrato'):contrato(db,dias=-1 if vinculo.endswith('expirado') else 30)
        elif vinculo=='concessao':db.add(m.ConcessaoAcessoAdmin(usuario_id=1,curso_id=1,ativo=False,data_fim=agora-timedelta(days=1)))
        elif vinculo=='demo_expirada':demo(db,dias=-1,ativo=False)
        elif vinculo.startswith('pagamento'):db.add(m.Pagamento(usuario_id=1,curso_id=1,status='PENDENTE' if vinculo.endswith('pendente') else 'CANCELLED',valor_cents=4990))
        elif vinculo=='oportunidade':db.add(m.OportunidadeCompra(usuario_id=1,curso_id=1,tipo_compra='NOVA'))
        else:
            conteudo(db,legado=vinculo=='legado')
            if vinculo in ('progresso','legado'):db.add(m.ProgressoAula(usuario_id=1,pasta_id=1,aula_id=1))
            elif vinculo=='revisao':db.add(m.RevisaoAluno(usuario_id=1,pasta_id=1,aula_id=1,status='CONCLUIDA',data_prevista=agora))
            elif vinculo=='tentativa':db.add(m.TentativaBateria(usuario_id=1,bateria_id=1,status='FEITA',ativo=False,percentual_acerto=100))
            elif vinculo=='resposta':db.add(m.RespostaAlunoQuestao(usuario_id=1,bateria_id=1,questao_id=1,respondida=True))
            elif vinculo=='anotacao':db.add(m.AnotacaoAlunoQuestao(usuario_id=1,bateria_id=1,questao_id=1,texto='Histórico'))
            else:
                db.add(m.QuestaoPraticaAssunto(id=1,curso_assunto_proprio_id=1,tipo='CERTO_ERRADO',enunciado='Prática',gabarito='C'));db.flush()
                if vinculo=='pratica':db.add(m.RespostaQuestaoPratica(usuario_id=1,questao_pratica_id=1,acertou=True))
                elif vinculo=='marcacao':db.add(m.QuestaoPraticaMarcacaoAluno(usuario_id=1,questao_id=1))
                else:db.add(m.QuestaoPraticaRotatividadeAluno(usuario_id=1,questao_id=1,curso_assunto_proprio_id=1))
        db.commit()
    r=c.delete('/cursos/1') if metodo=='delete' else c.put('/cursos/1',json={'nome':'Não mudar','ativo':False})
    assert r.status_code==409,r.text
    assert 'Desativar venda' in r.json()['detail']
    with f() as db:
        curso=db.get(m.Curso,1);assert curso.ativo and curso.publicado and curso.nome=='Curso 1'


@pytest.mark.parametrize('metodo',['delete','put'])
def test_exclusao_sem_vinculos_e_logica_preserva_conteudo(comercial,metodo):
    a=comercial;_,c,f,_,_=a;ator(a,ADMIN)
    with f() as db:conteudo(db)
    r=c.delete('/cursos/1') if metodo=='delete' else c.put('/cursos/1',json={'nome':'Curso 1','ativo':False})
    assert r.status_code==200,r.text
    with f() as db:
        curso=db.get(m.Curso,1);assert not curso.ativo and not curso.publicado
        assert db.query(m.Aula).count()==1 and db.query(m.Questao).count()==1
    assert c.put('/admin/cursos/1/publicar',json={}).status_code==404
    ator(a,ALUNO)
    assert c.post('/cursos/1/demonstracao').status_code==404
    assert c.post('/checkout/mercadopago',json={'tempo_acesso_id':1}).status_code==404
    assert c.get('/public/cursos/1/checkout').status_code==404


def test_editar_nome_preserva_estado_e_historico_expirado(comercial):
    a=comercial;_,c,f,_,_=a
    with f() as db:conteudo(db);cid=contrato(db,dias=-1)
    url=f'/me/cursos-expirados/1/desempenho?contratacao_id={cid}'
    antes=c.get(url);assert antes.status_code==200
    ator(a,ADMIN);assert c.put('/admin/cursos/1/retirar-venda',json={}).status_code==200
    assert c.put('/cursos/1',json={'nome':'Novo nome'}).status_code==200
    with f() as db:assert db.get(m.Curso,1).ativo and not db.get(m.Curso,1).publicado
    ator(a,ALUNO);depois=c.get(url);assert depois.status_code==200
    assert depois.json()['disciplinas']==antes.json()['disciplinas']
    ator(a,ADMIN)
    assert c.delete('/cursos/2').status_code==200
    assert c.put('/cursos/2',json={'nome':'Renomeado inativo'}).json()['ativo'] is False


def test_autorizacao_e_curso_inexistente(comercial):
    a=comercial;_,c,_,_,_=a
    for method,path,body in [('put','/admin/cursos/1/retirar-venda',{}),('put','/admin/cursos/1/publicar',{}),('put','/cursos/1',{'nome':'x','ativo':False}),('delete','/cursos/1',None)]:
        r=c.request(method,path,**({'json':body} if body is not None else {}));assert r.status_code==403,r.text
    ator(a,ADMIN)
    assert c.put('/admin/cursos/999/retirar-venda',json={}).status_code==404
