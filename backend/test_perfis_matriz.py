"""Matriz definitiva com JWT e banco SQLite efêmero; nenhum serviço externo."""
import re
from datetime import datetime
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB
from app import models as m
from app.auth import criar_token
from app.admin_intermediario import pode_administrar
from test_questoes_pratica_patch import carregar_main_isolado

@compiles(JSONB, 'sqlite')
def jsonb_sqlite(tipo, compiler, **kw):
    return 'JSON'

@pytest.fixture
def ambiente():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    m.Base.metadata.create_all(engine)
    from app.emails_pagamentos import metadata as emails_metadata
    emails_metadata.create_all(engine)
    factory=sessionmaker(bind=engine)
    with factory() as db:
        for uid,tipo in [(1,'admin_geral'),(2,'admin_prod'),(3,'admin_adm'),(4,None),(5,None),(6,'admin_geral')]:
            db.add(m.Usuario(id=uid,nome=f'Usuário {uid}',email=f'u{uid}@example.com',cpf=str(uid),
                telefone='0',senha_hash='hash',ativo=True,is_admin=tipo=='admin_geral',tipo_admin=tipo,perfil_inicial='ALUNO'))
        db.flush()
        db.add(m.Vendedor(id=1,usuario_id=5,nome='Vendedor',ativo=True))
        db.add(m.Curso(id=1,nome='Curso base'))
        db.add(m.Atendimento(id=1,usuario_id=4,assunto='Dúvida',mensagem='Ajuda',status='ABERTO'))
        db.commit()
    with carregar_main_isolado(factory,engine) as main:
        with TestClient(main.app) as client:
            yield main,client,factory
    engine.dispose()


def headers(uid):
    return {'Authorization':'Bearer '+criar_token({'sub':str(uid),'tipo_admin':'admin_geral','is_admin':True})} if uid else {}

@pytest.mark.parametrize('tipo,admin,esperado',[
    ('admin_geral',True,{'geral','producao','alunos'}),('admin_prod',False,{'producao'}),
    ('admin_adm',False,{'alunos'}),(None,False,set()),('admin_prod',True,set()),
    ('admin_geral',False,set()),('root',True,set())])
def test_capacidades(tipo,admin,esperado):
    u=SimpleNamespace(is_admin=admin,tipo_admin=tipo,ativo=True)
    assert {a for a in ['geral','producao','alunos'] if pode_administrar(u,a)}==esperado
    assert not pode_administrar(SimpleNamespace(is_admin=admin,tipo_admin=tipo,ativo=False),'producao')

@pytest.mark.parametrize('uid',[1,2])
def test_fluxo_producao_sem_matricula(ambiente,uid):
    _,c,f=ambiente; h=headers(uid)
    def request(method,url,body=None):
        r=c.request(method,url,headers=h,**({'json':body} if body is not None else {}))
        assert r.status_code==200,(url,r.text)
        return r.json()
    curso=request('POST','/cursos',{'nome':'Novo curso'})['id']
    disc=request('POST',f'/cursos/{curso}/disciplinas-proprias',{'nome':'Disciplina','curso_id':curso})['id']
    assunto=request('POST',f'/disciplinas-proprias/{disc}/assuntos-proprios',{'nome':'Assunto','curso_disciplina_propria_id':disc})['id']
    request('GET',f'/cursos/{curso}/disciplinas-proprias')
    request('GET',f'/disciplinas-proprias/{disc}/assuntos-proprios')
    assert request('GET',f'/admin/cursos/{curso}/disciplinas')[0]['id']==disc
    assert request('GET',f'/admin/cursos/{curso}/disciplinas/{disc}/assuntos')[0]['id']==assunto
    estrutura=request('GET',f'/assuntos-proprios/{assunto}/pasta-teoria')
    pasta,aula=estrutura['id'],estrutura['aula_id']
    material=request('POST','/materiais',{'aula_id':aula,'titulo':'Texto','tipo':'TEXTO','conteudo':'Conteúdo'})['id']
    video=request('POST','/videos',{'aula_id':aula,'titulo':'Vídeo','url':'https://www.youtube.com/watch?v=teste','provedor':'YOUTUBE'})['id']
    bateria=request('POST','/baterias',{'aula_id':aula,'titulo':'Bateria'})['id']
    for url in [f'/pastas/{pasta}/aulas',f'/aulas/{aula}/videos',f'/aulas/{aula}/materiais',
                f'/aulas/{aula}/baterias',f'/baterias/{bateria}/questoes',
                f'/admin/curso-assuntos-proprios/{assunto}/questoes-pratica',f'/admin/cursos/{curso}/config-publica']:
        request('GET',url)
    pratica=request('POST','/admin/questoes-pratica',{'curso_assunto_proprio_id':assunto,
        'tipo':'CERTO_ERRADO','enunciado':'Questão prática','gabarito':'C'})['id']
    request('PUT',f'/admin/questoes-pratica/{pratica}',{'tipo':'CERTO_ERRADO','enunciado':'Editada','gabarito':'E'})
    request('DELETE',f'/admin/questoes-pratica/{pratica}')
    questao=request('POST','/questoes',{'bateria_id':bateria,'tipo':'CERTO_ERRADO',
        'tipo_questao':'CERTO_ERRADO','enunciado':'Questão de bateria','gabarito':'C'})['id']
    request('DELETE',f'/questoes/{questao}')
    request('PUT',f'/admin/cursos/{curso}/config-publica',{'descricao_publica':'Descrição'})
    request('PUT',f'/admin/cursos/{curso}/publicar')
    request('PUT',f'/aulas/{aula}',{'titulo':'Editada','ordem':1,'pasta_id':pasta})
    request('DELETE',f'/materiais/{material}')
    request('DELETE',f'/videos/{video}')
    request('DELETE',f'/baterias/{bateria}')
    request('DELETE',f'/aulas/{aula}')
    with f() as db:
        assert db.get(m.Usuario,2).is_admin is False
        assert db.query(m.AcessoCurso).count()==0

@pytest.mark.parametrize('uid',[1,3])
def test_fluxo_administrativo(ambiente,uid):
    _,c,_=ambiente; h=headers(uid)
    for url in ['/admin/pagamentos','/admin/atendimentos','/admin/mensagens-questoes']:
        r=c.get(url,headers=h);assert r.status_code==200,(url,r.text)
    r=c.post('/admin/atendimentos/1/responder',headers=h,json={'resposta':'Resposta'})
    assert r.status_code==200,r.text
    assert c.post('/admin/atendimentos/1/concluir',headers=h).status_code==200
    assert c.post('/admin/pagamentos/revalidar',headers=h,json={}).status_code==400
    assert c.post('/admin/mensagens-questoes/999/responder',headers=h,json={'texto':'Resposta'}).status_code==404

@pytest.mark.parametrize('uid',[2,3,4,5,None])
def test_comercial_e_perfis_bloqueados(ambiente,uid):
    _,c,f=ambiente;h=headers(uid);status=403 if uid else 401
    operacoes=[('GET','/admin/alunos',None),('POST','/admin/alunos',{}),
      ('POST','/admin/acessos',{'usuario_id':4,'curso_id':1,'ativo':True,'data_fim':'2099-01-01T00:00:00'}),
      ('GET','/admin/vendedores',None),('POST','/admin/vendedores',{'nome':'Novo','senha':'Senha123','email':'novo@example.com','cpf_cnpj':'999'}),
      ('PUT','/admin/vendedores/1',{'ativo':False}),('PUT','/admin/vendedores/1/descredenciar',{}),
      ('PUT','/admin/vendedores/1/reativar',{}),('POST','/admin/usuarios/4/tornar-vendedor',{}),
      ('GET','/admin/emails-pagamentos',None),('POST','/admin/emails-pagamentos/1/pix/reenviar',{}),
      ('GET','/admin/usuarios/perfis?q=Usuário',None),('PUT','/admin/usuarios/4/tipo-admin',{'tipo_admin':'admin_geral'}),
      ('GET','/admin/cupons-desconto',None),('POST','/admin/cupons-desconto/gerar',{'quantidade':1}),
      ('PUT','/admin/cupons-desconto/1/vendedor',{'vendedor_id':None}),('PUT','/admin/cupons-desconto/1/status?ativo=false',{}),
      ('GET','/admin/reembolsos',None),('POST','/admin/reembolsos/1/aprovar',{}),('POST','/admin/reembolsos/1/recusar',{}),
      ('POST','/admin/reembolsos/1/pix-manual',{'valor_cents':100,'referencia_comprovante':'comprovante'}),
      ('POST','/admin/reembolsos/1/pix-manual/confirmar?confirmacao_extrato=true',{}),('GET','/admin/contestacoes',None),
      ('POST','/admin/contestacoes/1/confirmar-devolucao',{'referencia_devolucao':'comprovante','confirmacao_devolucao':True}),
      ('POST','/admin/contestacoes/1/bloquear-acesso',{}),('GET','/admin/financeiro/manutencao',None),
      ('POST','/admin/financeiro/manutencao',{'modo':'PAUSADO','geracao':0,'motivo':'teste'}),
      ('GET','/admin/financeiro/notificacoes',None)]
    for method,url,body in operacoes:
        r=c.request(method,url,headers=h,**({'json':body} if body is not None else {}))
        assert r.status_code==status,(method,url,r.text)
    with f() as db:
        assert db.query(m.AuditoriaPerfilAdmin).count()==0
        assert db.get(m.Vendedor,1).ativo is True
        assert db.query(m.CupomDesconto).count()==0

@pytest.mark.parametrize('uid',[1,6])
def test_gerenciar_trocar_revogar_e_auditar(ambiente,uid):
    _,c,f=ambiente;h=headers(uid)
    assert c.get('/admin/usuarios/perfis?q=u4@example.com',headers=h).json()[0]['id']==4
    anterior=None
    for tipo in ['admin_prod','admin_adm','admin_geral',None]:
        r=c.put('/admin/usuarios/4/tipo-admin',headers=h,json={'tipo_admin':tipo})
        assert r.status_code==200,r.text
        assert r.json()['is_admin']==(tipo=='admin_geral')
        with f() as db:
            a=db.query(m.AuditoriaPerfilAdmin).order_by(m.AuditoriaPerfilAdmin.id.desc()).first()
            assert (a.autor_id,a.usuario_id,a.tipo_anterior,a.tipo_novo)==(uid,4,anterior,tipo)
        anterior=tipo
    assert c.put('/admin/usuarios/4/tipo-admin',headers=h,json={'tipo_admin':None}).status_code==200
    with f() as db: assert db.query(m.AuditoriaPerfilAdmin).count()==4
    for body in [{'tipo_admin':'root'},{'tipo_admin':'admin_prod','is_admin':True},{}]:
        assert c.put('/admin/usuarios/4/tipo-admin',headers=h,json=body).status_code==422


def test_revogacao_token_anterior_e_ultimo_geral(ambiente):
    _,c,f=ambiente
    assert c.put('/admin/usuarios/6/tipo-admin',headers=headers(1),json={'tipo_admin':None}).status_code==200
    assert c.get('/admin/usuarios/perfis?q=teste',headers=headers(6)).status_code==403
    assert c.put('/admin/usuarios/1/tipo-admin',headers=headers(1),json={'tipo_admin':'admin_prod'}).status_code==409
    with f() as db:
        db.get(m.Usuario,2).ativo=False;db.commit()
    assert c.get('/admin/cursos',headers=headers(2)).status_code==401
    assert c.put('/admin/usuarios/2/tipo-admin',headers=headers(1),json={'tipo_admin':'admin_adm'}).status_code==409


def test_vendedores_preservam_usuario_e_prazo(ambiente):
    _,c,f=ambiente;h=headers(1)
    r=c.post('/admin/usuarios/4/tornar-vendedor',headers=h,json={});assert r.status_code==200,r.text
    vid=r.json()['id']
    assert c.put(f'/admin/vendedores/{vid}/descredenciar',headers=h,json={}).status_code==200
    assert c.get('/me',headers=headers(4)).json()['is_vendedor'] is True
    assert c.put(f'/admin/vendedores/{vid}/reativar',headers=h,json={}).status_code==200
    with f() as db:
        assert db.get(m.Usuario,4).tipo_admin is None
        assert db.get(m.Usuario,4).is_admin is False
        assert db.get(m.Vendedor,vid).descredenciado_em is None

@pytest.mark.parametrize('uid',[3,4,5,None])
def test_escritas_producao_negadas(ambiente,uid):
    _,c,_=ambiente;h=headers(uid);status=403 if uid else 401
    casos=[('GET','/admin/cursos',None),('GET','/admin/cursos/1/disciplinas',None),
      ('GET','/admin/cursos/1/disciplinas/1/assuntos',None),
      ('POST','/cursos',{'nome':'Proibido'}),('PUT','/cursos/1',{'nome':'Proibido'}),('DELETE','/cursos/1',None),
      ('POST','/disciplinas',{'nome':'Proibido'}),('POST','/cursos/1/disciplinas/1',{}),
      ('POST','/cursos/1/disciplinas-proprias',{'nome':'Proibido','curso_id':1}),
      ('PUT','/disciplinas-proprias/1',{'nome':'Proibido'}),('DELETE','/disciplinas-proprias/1',None),
      ('POST','/disciplinas-proprias/1/assuntos-proprios',{'nome':'Proibido','curso_disciplina_propria_id':1}),
      ('PUT','/assuntos-proprios/1',{'nome':'Proibido'}),('DELETE','/assuntos-proprios/1',None),
      ('POST','/aulas',{'pasta_id':1,'titulo':'Proibido'}),('POST','/pastas/1/aulas',{'pasta_id':1,'titulo':'Proibido'}),
      ('PUT','/aulas/1',{'pasta_id':1,'titulo':'Proibido'}),('DELETE','/aulas/1',None),
      ('POST','/materiais',{'aula_id':1,'titulo':'Proibido','tipo':'TEXTO','conteudo':'Texto'}),
      ('DELETE','/materiais/1',None),('POST','/videos',{'aula_id':1,'titulo':'Proibido'}),('DELETE','/videos/1',None),
      ('POST','/baterias',{'aula_id':1,'titulo':'Proibido'}),('DELETE','/baterias/1',None),
      ('POST','/questoes',{'bateria_id':1,'enunciado':'Proibido','tipo':'CERTO_ERRADO'}),('DELETE','/questoes/1',None),
      ('GET','/admin/curso-assuntos-proprios/1/questoes-pratica',None),('POST','/admin/questoes-pratica',{'curso_assunto_proprio_id':1,'enunciado':'Proibido','tipo':'CERTO_ERRADO','gabarito':'CERTO'}),
      ('DELETE','/admin/questoes-pratica/1',None),('POST','/admin/cursos/1/duplicar',{'novo_nome':'Cópia'}),
      ('POST','/admin/disciplinas/1/copiar',{'curso_destino_id':1}),
      ('POST','/admin/assuntos/1/copiar',{'disciplina_destino_id':1})]
    for method,url,body in casos:
        r=c.request(method,url,headers=h,**({'json':body} if body is not None else {}))
        assert r.status_code==status,(method,url,r.text)

@pytest.mark.parametrize('uid',[2,4,5,None])
def test_suporte_negado(ambiente,uid):
    _,c,_=ambiente;h=headers(uid);status=403 if uid else 401
    for method,url,body in [('GET','/admin/pagamentos',None),('POST','/admin/pagamentos/revalidar',{}),
      ('GET','/admin/atendimentos',None),('POST','/admin/atendimentos/1/responder',{'resposta':'Proibida'}),
      ('POST','/admin/atendimentos/1/concluir',{}),('GET','/admin/mensagens-questoes',None),
      ('POST','/admin/mensagens-questoes/1/responder',{'texto':'Proibida'}),
      ('GET','/admin/atendimentos',None)]:
        r=c.request(method,url,headers=h,**({'json':body} if body is not None else {}))
        assert r.status_code==status,(method,url,r.text)


def test_criacao_vendedor_login_e_edicao_sem_privilegios(ambiente):
    _,c,f=ambiente;h=headers(1)
    payload={'nome':'Novo vendedor','cpf_cnpj':'999','email':'novo@example.com','telefone':'0',
             'senha':'Senha1234','data_nascimento':'1990-01-01','estado_uf':'SP','cidade':'São Paulo'}
    r=c.post('/admin/vendedores',headers=h,json=payload);assert r.status_code==200,r.text
    vendedor=r.json();uid=vendedor['usuario_id']
    login=c.post('/login',data={'username':'novo@example.com','password':'Senha1234'})
    assert login.status_code==200,login.text
    me=c.get('/me',headers={'Authorization':'Bearer '+login.json()['access_token']}).json()
    assert me['is_vendedor'] is True and me['is_admin'] is False and me['tipo_admin'] is None
    assert c.post('/admin/vendedores',headers=h,json=payload).status_code==409
    r=c.put(f"/admin/vendedores/{vendedor['id']}",headers=h,json={'nome':'Editado','is_admin':True,'tipo_admin':'admin_geral'})
    assert r.status_code==200,r.text
    with f() as db:
        usuario=db.get(m.Usuario,uid)
        assert usuario.is_admin is False and usuario.tipo_admin is None
        assert db.get(m.Vendedor,vendedor['id']).nome=='Editado'
