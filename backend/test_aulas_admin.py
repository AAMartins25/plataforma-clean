"""CRUD de Aulas em SQLite descartável, com FKs; sem importar o banco configurado."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models as m
from test_questoes_pratica_patch import carregar_main_isolado

MODELOS = [m.Usuario, m.Curso, m.Disciplina, m.Assunto, m.CursoDisciplinaPropria,
           m.CursoAssuntoProprio, m.ContratacaoCurso, m.DemonstracaoCurso,
           m.Pasta, m.Aula, m.Material, m.Video, m.Bateria, m.Questao,
           m.Alternativa, m.Comentario, m.RevisaoAluno, m.TentativaBateria,
           m.RespostaAlunoQuestao, m.AnotacaoAlunoQuestao,
           m.ConversaQuestaoProfessor, m.MensagemConversaQuestao, m.ProgressoAula]


@pytest.fixture(scope="module")
def infraestrutura():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    @event.listens_for(engine, 'connect')
    def ativar_fk(conexao, _):
        conexao.execute('PRAGMA foreign_keys=ON')
    factory = sessionmaker(bind=engine, autoflush=False)
    with carregar_main_isolado(factory, engine) as main:
        try:
            yield main, engine, factory
        finally:
            main.app.dependency_overrides.clear()
            engine.dispose()


@pytest.fixture
def ambiente(infraestrutura):
    main, engine, factory = infraestrutura
    m.Base.metadata.drop_all(engine, tables=[modelo.__table__ for modelo in MODELOS])
    m.Base.metadata.create_all(engine, tables=[modelo.__table__ for modelo in MODELOS])
    agora = datetime.utcnow()
    with factory() as db:
        db.add_all([m.Usuario(id=i, nome=str(i), email=f'{i}@teste.local', senha_hash='teste',
                             cpf=str(i), telefone='0') for i in (1, 2)])
        db.add_all([m.Curso(id=i, nome=str(i)) for i in (1, 2)])
        db.flush()
        db.add_all([m.CursoDisciplinaPropria(id=i, curso_id=i, nome=str(i)) for i in (1, 2)])
        db.flush()
        db.add_all([m.CursoAssuntoProprio(id=i, curso_disciplina_propria_id=i, nome=str(i)) for i in (1, 2)])
        db.flush()
        db.add_all([m.Pasta(id=i, curso_assunto_proprio_id=i, tipo='TEORIA', nome='Teoria') for i in (1, 2)])
        db.flush()
        db.add_all([m.Aula(id=i, pasta_id=i, titulo='Aula') for i in (1, 2)])
        db.flush()
        db.add_all([m.Bateria(id=i, aula_id=1, titulo=str(i), ordem=i,
                             status='CONCLUIDA' if i == 2 else 'EM_ANDAMENTO') for i in (1, 2)])
        db.add(m.Material(id=1, aula_id=1, titulo='Texto', tipo='TEXTO', conteudo='Conteúdo', ordem=3))
        db.add(m.Material(id=2, aula_id=1, titulo='PDF', tipo='PDF', url='https://teste.local/pdf', ordem=8, ativo=False))
        db.add(m.Video(id=1, aula_id=1, titulo='Vídeo', url='https://youtu.be/teste', ordem=4,
                       duracao_segundos=123, transcricao='Transcrição', ativo=False))
        for modelo in (m.ContratacaoCurso, m.DemonstracaoCurso):
            for i, usuario_id, curso_id, expirado in ((1,1,1,False),(2,2,1,False),(3,1,2,False),(4,1,1,True)):
                extra = {'origem':'ADMIN'} if modelo is m.ContratacaoCurso else {'liberado_novamente_em':agora}
                db.add(modelo(id=i, usuario_id=usuario_id, curso_id=curso_id,
                              data_inicio=agora-timedelta(days=2), data_fim=agora+timedelta(days=-1 if expirado else 1), **extra))
        db.flush()
        db.add(m.Questao(id=1, bateria_id=2, enunciado='Concluída', tipo='CERTO_ERRADO',
                         tipo_questao='CERTO_ERRADO', gabarito='C', ordem=1))
        db.commit()
    def perfil(admin):
        main.app.dependency_overrides[main.get_usuario_atual] = lambda: SimpleNamespace(id=1,is_admin=admin)
    perfil(True)
    try:
        with TestClient(main.app) as client:
            yield main, client, factory, perfil
    finally:
        main.app.dependency_overrides.clear()


def texto(**extras):
    return {'aula_id':1,'tipo':'TEXTO','titulo':'Novo','conteudo':'Conteúdo',**extras}


def video(**extras):
    return {'aula_id':1,'titulo':'Novo','url':'https://youtu.be/teste',**extras}


def questao(tipo='MULTIPLA_4', **extras):
    letras = list('ABCDE' if tipo == 'MULTIPLA_5' else 'ABCD')
    return {'bateria_id':1,'enunciado':'Enunciado','tipo':'CERTO_ERRADO' if tipo=='CERTO_ERRADO' else 'MULTIPLA',
            'tipo_questao':tipo,'gabarito':'C' if tipo=='CERTO_ERRADO' else 'A','comentario':'Comentário',
            'alternativas':[] if tipo=='CERTO_ERRADO' else [{'letra':l,'texto':l} for l in letras],**extras}


GESTAO = [
    ('post','/materiais',texto()), ('put','/materiais/1',texto()), ('delete','/materiais/1',None),
    ('post','/videos',video()), ('put','/videos/1',video()), ('delete','/videos/1',None),
    ('post','/baterias',{'aula_id':1,'titulo':'Nova'}), ('put','/baterias/1',{'aula_id':1,'titulo':'Novo'}),
    ('delete','/baterias/1',None), ('put','/baterias/1/concluir',{}),
    ('post','/questoes',questao()), ('put','/questoes/1',questao('CERTO_ERRADO',bateria_id=2)),
    ('delete','/questoes/1',None), ('post','/questoes/1/alternativas',{'letra':'A','texto':'A'}),
    ('post','/questoes/1/comentario-geral',{'texto':'Comentário'}),
    ('post','/baterias/1/gerar-10-questoes',{'bateria_id':1,'tipo':'MULTIPLA'}),
]


@pytest.mark.parametrize('metodo,url,payload',GESTAO)
@pytest.mark.parametrize('autenticado,status',[(False,401),(True,403)])
def test_gestao_exige_admin(ambiente,metodo,url,payload,autenticado,status):
    main,c,factory,perfil=ambiente
    if autenticado:
        perfil(False)
    else:
        main.app.dependency_overrides.pop(main.get_usuario_atual)
    with factory() as db:
        antes={modelo.__tablename__:list(db.execute(select(modelo.__table__))) for modelo in MODELOS}
    r=c.request(metodo,url,json=payload)
    assert r.status_code==status,r.text
    with factory() as db:
        assert antes=={modelo.__tablename__:list(db.execute(select(modelo.__table__))) for modelo in MODELOS}


LEITURAS=['/aulas/1/materiais','/aulas/1/videos','/aulas/1/baterias','/baterias/2/questoes']


@pytest.mark.parametrize('url',LEITURAS+['/baterias/1/questoes'])
def test_admin_lista_sem_contexto(ambiente,url):
    main,c,_,_=ambiente
    with patch.object(main,'validar_contexto_estudo',side_effect=AssertionError('Contexto de aluno invocado')):
        r=c.get(url)
    assert r.status_code==200,r.text
    if url=='/baterias/1/questoes': assert r.json()==[]
    if url=='/aulas/1/materiais': assert [x['id'] for x in r.json()]==[1,2]


@pytest.mark.parametrize('url',LEITURAS)
@pytest.mark.parametrize('parametros,status',[
    ({},400),({'contratacao_id':1,'demonstracao_id':1},400),
    ({'contratacao_id':1},200),({'demonstracao_id':1},200),
    *[({contexto:i},403) for contexto in ('contratacao_id','demonstracao_id') for i in (2,3,4,999)]])
def test_leituras_preservam_contexto_aluno(ambiente,url,parametros,status):
    _,c,_,perfil=ambiente;perfil(False)
    r=c.get(url,params=parametros)
    assert r.status_code==status,r.text
    if status==200 and url=='/aulas/1/materiais':assert [x['id'] for x in r.json()]==[1]
    if status==200 and url=='/aulas/1/videos':assert r.json()==[]


@pytest.mark.parametrize('contexto',['contratacao_id','demonstracao_id'])
def test_rascunho_indisponivel_aluno(ambiente,contexto):
    _,c,_,perfil=ambiente;perfil(False)
    assert c.get('/baterias/1/questoes',params={contexto:1}).status_code==404


@pytest.mark.parametrize('url,payload,ordem',[('/materiais',texto(),9),('/videos',video(),5),('/baterias',{'aula_id':1,'titulo':'Nova'},3)])
def test_crud_e_ordem_com_lacunas(ambiente,url,payload,ordem):
    _,c,_,_=ambiente
    r=c.post(url,json=payload);assert r.status_code==200,r.text
    dado=r.json();assert dado['ordem']==ordem
    assert c.post(url,json={**payload,'ordem':ordem}).status_code==409
    assert c.put(f"{url}/{dado['id']}",json={**payload,'titulo':'Editado'}).json()['titulo']=='Editado'
    assert c.delete(f"{url}/{dado['id']}").status_code==200
    assert c.delete(f"{url}/{dado['id']}").status_code==404
    assert c.post(url,json=payload).json()['ordem']==ordem


@pytest.mark.parametrize('url,payload',[('/materiais/1',texto(ordem=8)),('/videos/1',video(aula_id=2)),('/baterias/1',{'aula_id':2,'titulo':'Mudança'})])
def test_edicao_nao_transfere_vinculo_ou_colide_ordem(ambiente,url,payload):
    _,c,_,_=ambiente
    assert c.put(url,json=payload).status_code in (400,409)


def test_edicao_video_preserva_metadados_e_alteracao_expressa(ambiente):
    _,c,_,_=ambiente
    r=c.put('/videos/1',json=video(titulo='Editado'));assert r.status_code==200,r.text
    assert (r.json()['duracao_segundos'],r.json()['transcricao'],r.json()['ativo'],r.json()['ordem'])==(123,'Transcrição',False,4)
    r=c.put('/videos/1',json=video(duracao_segundos=9,transcricao=None,ativo=True))
    assert (r.json()['duracao_segundos'],r.json()['transcricao'],r.json()['ativo'])==(9,None,True)


def test_titulo_bateria_preserva_status_e_ativo(ambiente):
    _,c,factory,_=ambiente
    with factory() as db:
        db.get(m.Bateria,2).ativo=False;db.commit()
    r=c.put('/baterias/2',json={'aula_id':1,'titulo':'Editado'})
    assert r.status_code==200,r.text
    assert (r.json()['status'],r.json()['ativo'],r.json()['ordem'])==('CONCLUIDA',False,2)


@pytest.mark.parametrize('provedor,extras',[('YOUTUBE',{'url':'https://youtu.be/teste'}),('CLOUDFLARE',{'url':'','cloudflare_uid':'uid-teste'})])
def test_videos_provedores_criacao_edicao(ambiente,provedor,extras):
    _,c,_,_=ambiente
    r=c.post('/videos',json=video(provedor=provedor,**extras));assert r.status_code==200,r.text
    id=r.json()['id']
    r=c.put(f'/videos/{id}',json=video(provedor=provedor,**extras));assert r.status_code==200,r.text
    assert r.json()['provedor']==provedor
    assert c.delete(f'/videos/{id}').status_code==200


@pytest.mark.parametrize('extras',[{'provedor':'OUTRO'},{'url':''},{'provedor':'CLOUDFLARE','url':'','cloudflare_uid':''}])
def test_video_invalido_nao_grava(ambiente,extras):
    _,c,factory,_=ambiente
    assert c.post('/videos',json=video(**extras)).status_code==400
    with factory() as db:assert db.query(m.Video).count()==1


@pytest.mark.parametrize('tipo',['MULTIPLA_4','MULTIPLA_5','CERTO_ERRADO'])
def test_questoes_crud_atomico_e_edicao_alternativas(ambiente,tipo):
    _,c,factory,_=ambiente
    r=c.post('/questoes',json=questao(tipo));assert r.status_code==200,r.text
    id=r.json()['id']
    with factory() as db:
        ids={a.letra:a.id for a in db.query(m.Alternativa).filter_by(questao_id=id)}
    payload=questao(tipo,enunciado='Editado')
    for a in payload['alternativas']:a['texto']='Editado '+a['letra']
    assert c.put(f'/questoes/{id}',json=payload).status_code==200
    qs=c.get('/baterias/1/questoes').json();assert qs[0]['enunciado']=='Editado'
    assert all(a['texto']=='Editado '+a['letra'] for a in qs[0]['alternativas'])
    assert {a['letra']:a['id'] for a in qs[0]['alternativas']}==ids
    assert c.delete(f'/questoes/{id}').status_code==200
    with factory() as db:
        assert db.query(m.Alternativa).filter_by(questao_id=id).count()==0


def test_mudanca_tipo_remove_apenas_alternativas_de_conteudo(ambiente):
    _,c,factory,_=ambiente
    id=c.post('/questoes',json=questao('MULTIPLA_5')).json()['id']
    with factory() as db:
        alt=db.query(m.Alternativa).filter_by(questao_id=id,letra='E').one()
        db.add(m.Comentario(questao_id=id,alternativa_id=alt.id,texto='Comentário da alternativa'));db.commit()
    for tipo,numero in [('MULTIPLA_4',4),('CERTO_ERRADO',0),('MULTIPLA_5',5)]:
        r=c.put(f'/questoes/{id}',json=questao(tipo));assert r.status_code==200,r.text
        assert len(c.get('/baterias/1/questoes').json()[0]['alternativas'])==numero
    with factory() as db:assert db.query(m.Comentario).count()==0


@pytest.mark.parametrize('alternativas',[[{'letra':'A','texto':'A'}],[{'letra':'A','texto':'A'}]*4,
                                         [{'letra':l,'texto':'' if l=='D' else l} for l in 'ABCD']])
def test_alternativas_invalidas_nao_deixam_questao_parcial(ambiente,alternativas):
    _,c,factory,_=ambiente
    assert c.post('/questoes',json=questao(alternativas=alternativas)).status_code==400
    with factory() as db:assert db.query(m.Questao).filter_by(bateria_id=1).count()==0


@pytest.mark.parametrize('url,payload',[('/questoes',questao()),('/materiais',texto()),('/videos',video())])
def test_falha_commit_desfaz_criacao_inteira(ambiente,url,payload):
    _,c,factory,_=ambiente
    def falhar(_):raise IntegrityError('Falha simulada',{},Exception('constraint'))
    event.listen(factory.class_,'before_commit',falhar)
    try: assert c.post(url,json=payload).status_code==409
    finally:event.remove(factory.class_,'before_commit',falhar)
    with factory() as db:
        assert db.query(m.Material).count()==2
        assert db.query(m.Video).count()==1
        assert db.query(m.Questao).count()==1
        assert db.query(m.Alternativa).count()==0


def test_falha_commit_desfaz_edicao_de_questao_e_alternativas(ambiente):
    _,c,factory,_=ambiente
    id=c.post('/questoes',json=questao()).json()['id']
    def falhar(_):raise IntegrityError('Falha simulada',{},Exception('constraint'))
    event.listen(factory.class_,'before_commit',falhar)
    try:assert c.put(f'/questoes/{id}',json=questao('MULTIPLA_5',enunciado='Não gravar')).status_code==409
    finally:event.remove(factory.class_,'before_commit',falhar)
    with factory() as db:
        q=db.get(m.Questao,id);assert (q.enunciado,q.tipo_questao)==('Enunciado','MULTIPLA_4')
        assert [a.letra for a in db.query(m.Alternativa).filter_by(questao_id=id).order_by(m.Alternativa.letra)]==list('ABCD')


def test_conclusao_rascunho_e_rename_nao_afetam_estudo(ambiente):
    _,c,_,perfil=ambiente
    assert c.put('/baterias/1/concluir',json={}).status_code==400
    for _ in range(10):assert c.post('/questoes',json=questao('CERTO_ERRADO')).status_code==200
    assert c.post('/questoes',json=questao()).status_code==400
    assert c.put('/baterias/1/concluir',json={}).json()['status']=='CONCLUIDA'
    assert c.put('/baterias/1',json={'aula_id':1,'titulo':'Renomeada'}).json()['status']=='CONCLUIDA'
    perfil(False)
    assert len(c.get('/baterias/1/questoes?contratacao_id=1').json())==10


def test_nao_conclui_questao_incremental_incompleta(ambiente):
    _,c,_,_=ambiente
    for _ in range(10):assert c.post('/questoes',json=questao(alternativas=None)).status_code==200
    assert c.put('/baterias/1/concluir',json={}).status_code==400


def inserir_historico(db,tipo):
    if tipo=='revisao':
        db.add(m.RevisaoAluno(id=1,usuario_id=1,aula_id=1,pasta_id=1,contratacao_id=1,
                             data_prevista=datetime.utcnow()+timedelta(days=7)))
    elif tipo=='tentativa':
        db.add(m.TentativaBateria(id=1,usuario_id=1,bateria_id=2,contratacao_id=1,ativo=False))
    elif tipo=='resposta':
        db.add(m.RespostaAlunoQuestao(usuario_id=1,questao_id=1,bateria_id=2,contratacao_id=1,resposta_marcada='C'))
    elif tipo=='anotacao':
        db.add(m.AnotacaoAlunoQuestao(usuario_id=1,questao_id=1,bateria_id=2,contratacao_id=1,texto='Preservar'))
    elif tipo=='mensagem':
        db.add(m.ConversaQuestaoProfessor(id=1,usuario_id=1,questao_id=1,bateria_id=2,contratacao_id=1))
        db.flush()
        db.add(m.MensagemConversaQuestao(conversa_id=1,autor='ALUNO',texto='Preservar'))
    db.commit()


@pytest.mark.parametrize('tipo',['revisao','tentativa','resposta','anotacao','mensagem'])
@pytest.mark.parametrize('url',['/questoes/1','/baterias/2'])
def test_exclusao_com_historico_bloqueada_sem_alterar_registros(ambiente,tipo,url):
    _,c,factory,_=ambiente
    with factory() as db:
        inserir_historico(db,tipo)
        antes={modelo.__tablename__:list(db.execute(select(modelo.__table__))) for modelo in MODELOS}
    r=c.delete(url);assert r.status_code==409,r.text
    assert 'preservados' in r.json()['detail']
    with factory() as db:
        assert antes=={modelo.__tablename__:list(db.execute(select(modelo.__table__))) for modelo in MODELOS}


def test_mudanca_tipo_com_historico_bloqueada(ambiente):
    _,c,factory,_=ambiente
    with factory() as db:inserir_historico(db,'resposta')
    assert c.put('/questoes/1',json=questao(bateria_id=2)).status_code==409
    with factory() as db:assert db.get(m.Questao,1).tipo_questao=='CERTO_ERRADO'


def test_exclusao_bateria_limpa_comentarios_e_alternativas_sem_historico(ambiente):
    _,c,factory,_=ambiente
    id=c.post('/questoes',json=questao()).json()['id']
    with factory() as db:
        alt=db.query(m.Alternativa).filter_by(questao_id=id).first()
        db.add(m.Comentario(questao_id=id,alternativa_id=alt.id,texto='Comentário'));db.commit()
    assert c.delete('/baterias/1').status_code==200
    with factory() as db:
        assert db.get(m.Bateria,1) is None
        assert db.query(m.Questao).filter_by(bateria_id=1).count()==0
        assert db.query(m.Alternativa).count()==db.query(m.Comentario).count()==0


def test_playback_cloudflare_preserva_contextos_sem_chamada_externa(ambiente):
    main,c,_,perfil=ambiente
    id=c.post('/videos',json=video(provedor='CLOUDFLARE',url='',cloudflare_uid='uid')).json()['id']
    perfil(False)
    resposta=SimpleNamespace(ok=True,json=lambda:{'result':{'token':'token-isolado'}})
    with patch.object(main,'CLOUDFLARE_ACCOUNT_ID','conta-teste'),patch.object(main,'CLOUDFLARE_STREAM_API_TOKEN','segredo-teste'),patch.object(main.requests,'post',return_value=resposta) as chamada:
        assert c.get(f'/videos/{id}/playback').status_code==400
        chamada.assert_not_called()
        for contexto in ('contratacao_id','demonstracao_id'):
            r=c.get(f'/videos/{id}/playback',params={contexto:1})
            assert r.status_code==200 and r.json()['token']=='token-isolado'
    assert c.get('/videos/1/playback?contratacao_id=1').status_code==404  # Vídeo inativo.


@pytest.mark.parametrize('url',LEITURAS)
def test_leituras_exigem_login(ambiente,url):
    main,c,_,_=ambiente
    main.app.dependency_overrides.pop(main.get_usuario_atual)
    assert c.get(url).status_code==401


def test_edicao_somente_titulo_video_cloudflare_preserva_provedor_e_uid(ambiente):
    _,c,_,_=ambiente
    id=c.post('/videos',json=video(provedor='CLOUDFLARE',url='',cloudflare_uid='uid')).json()['id']
    r=c.put(f'/videos/{id}',json={'aula_id':1,'titulo':'Renomeado'})
    assert r.status_code==200,r.text
    assert (r.json()['provedor'],r.json()['cloudflare_uid'],r.json()['url'])==('CLOUDFLARE','uid','')


def test_edicao_material_preserva_ativo_e_conteudo_omitidos(ambiente):
    _,c,_,_=ambiente
    r=c.put('/materiais/2',json={'aula_id':1,'tipo':'PDF','titulo':'Renomeado'})
    assert r.status_code==200,r.text
    assert (r.json()['ativo'],r.json()['url'],r.json()['ordem'])==(False,'https://teste.local/pdf',8)


@pytest.mark.parametrize('url,payload',[('/materiais',texto(aula_id=999)),('/videos',video(aula_id=999)),
                                       ('/baterias',{'aula_id':999,'titulo':'Nova'}),('/questoes',questao(bateria_id=999))])
def test_criacao_rejeita_pai_inexistente(ambiente,url,payload):
    _,c,_,_=ambiente
    assert c.post(url,json=payload).status_code==404


def test_bateria_nao_pode_nascer_concluida(ambiente):
    _,c,_,_=ambiente
    assert c.post('/baterias',json={'aula_id':1,'titulo':'Inválida','status':'CONCLUIDA'}).status_code==400


def test_ordem_questoes_apos_exclusao_nao_colide(ambiente):
    _,c,_,_=ambiente
    ids=[c.post('/questoes',json=questao('CERTO_ERRADO')).json()['id'] for _ in range(3)]
    assert c.delete(f'/questoes/{ids[1]}').status_code==200
    assert c.post('/questoes',json=questao('CERTO_ERRADO')).json()['ordem']==4
    assert [q['ordem'] for q in c.get('/baterias/1/questoes').json()]==[1,3,4]


@pytest.mark.parametrize('url,payload,modelo',[('/materiais',texto(),m.Material),('/videos',video(),m.Video),
                                            ('/baterias',{'aula_id':1,'titulo':'Nova'},m.Bateria)])
def test_limites_existentes_de_20_conteudos(ambiente,url,payload,modelo):
    _,c,factory,_=ambiente
    with factory() as db:
        for ordem in range(1,21):
            valores={**payload,'aula_id':2,'ordem':ordem}
            db.add(modelo(**valores))
        db.commit()
    r=c.post(url,json={**payload,'aula_id':2})
    assert 'Limite de 20' in r.json()['erro']
    with factory() as db:assert db.query(modelo).filter_by(aula_id=2).count()==20


def test_alternativas_invalidas_na_edicao_preservam_questao_original(ambiente):
    _,c,factory,_=ambiente
    id=c.post('/questoes',json=questao()).json()['id']
    assert c.put(f'/questoes/{id}',json=questao(enunciado='Não salvar',alternativas=[])).status_code==400
    with factory() as db:
        assert db.get(m.Questao,id).enunciado=='Enunciado'
        assert db.query(m.Alternativa).filter_by(questao_id=id).count()==4


def test_geracao_legada_atomica_e_sem_historico_removivel(ambiente):
    _,c,factory,_=ambiente
    r=c.post('/baterias/1/gerar-10-questoes',json={'bateria_id':1,'tipo':'MULTIPLA'})
    assert r.status_code==200 and r.json()['questoes_criadas']==10
    with factory() as db:
        assert db.query(m.Alternativa).count()==db.query(m.Comentario).count()==50
    assert c.delete('/baterias/1').status_code==200


def test_falha_geracao_legada_reverte_questoes_alternativas_comentarios(ambiente):
    _,c,factory,_=ambiente
    def falhar(_):raise IntegrityError('Falha simulada',{},Exception('constraint'))
    event.listen(factory.class_,'before_commit',falhar)
    try:
        assert c.post('/baterias/1/gerar-10-questoes',json={'bateria_id':1,'tipo':'MULTIPLA'}).status_code==409
    finally:event.remove(factory.class_,'before_commit',falhar)
    with factory() as db:
        assert db.query(m.Questao).filter_by(bateria_id=1).count()==0
        assert db.query(m.Alternativa).count()==db.query(m.Comentario).count()==0
