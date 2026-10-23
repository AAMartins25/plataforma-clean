"""HTTP real com SQLite em memória; nunca importa app.database configurado."""
import ast
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import models as m
from app.auth import criar_token, hash_senha
from app.admin_intermediario import exigir_geral
from test_questoes_pratica_patch import carregar_main_isolado

BASE='cdba603e9a8d3a3a04a77fc03863ad41c93c1a93'
ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def ambiente(monkeypatch):
    monkeypatch.setenv('ADMIN_RESTRITOS_HABILITADOS','1')
    monkeypatch.setenv('ADMIN_DATABASE_ROLE_LEGADO','nao_utilizado')
    e=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    # Emula apenas o cast de DATE aceito pelo PostgreSQL publicado.
    # A aplicação mantém seu tratamento original; SQLite exige date em Python.
    @event.listens_for(e, 'before_execute', retval=True)
    def datas_sqlite(conn, clause, multiparams, params, options):
        from datetime import date
        def ajustar(p):
            if isinstance(p, dict) and isinstance(p.get('data_nascimento'), str):
                return {**p, 'data_nascimento': date.fromisoformat(p['data_nascimento'])}
            return p
        return clause, [ajustar(p) for p in multiparams], ajustar(params)
    f=sessionmaker(bind=e,autoflush=False)
    tabelas=[m.Usuario,m.AuditoriaPerfilAdmin,m.Curso,m.Disciplina,m.Assunto,m.Pasta,m.Vendedor,m.AcessoCurso,m.Atendimento]
    m.Base.metadata.create_all(e,tables=[t.__table__ for t in tabelas]+[m.curso_disciplina])
    with f() as db:
        for i,tipo in enumerate(['admin_geral','admin_prod','admin_adm',None,None],1):
            db.add(m.Usuario(id=i,nome=f'Usuário {i}',email=f'u{i}@example.com',cpf=str(i),telefone='0',
                senha_hash='simulado',is_admin=tipo=='admin_geral',tipo_admin=tipo,perfil_inicial='ALUNO',ativo=True))
        db.add(m.Curso(id=1,nome='Base'));db.add(m.Disciplina(id=1,nome='Base'));db.flush()
        db.add(m.Vendedor(id=1,usuario_id=5,nome='Vendedor',ativo=True));db.commit()
    with carregar_main_isolado(f,e) as main:
        def db_atual():
            with f() as db:yield db
        main.app.dependency_overrides[main.get_db]=db_atual
        with TestClient(main.app) as client:yield main,client,f
    e.dispose()

def headers(i):
    return {'Authorization':'Bearer '+criar_token({'sub':str(i),'is_admin':True,'tipo_admin':'admin_geral'})} if i else {}

GRAVACOES=[('/cursos',{'nome':'Novo'}),('/disciplinas',{'nome':'Nova'}),
           ('/cursos/1/disciplinas/1',{}),('/assuntos',{'nome':'Novo','disciplina_id':1})]

@pytest.mark.parametrize('i',[1,2,3,4,5,None])
def test_quatro_gravacoes(ambiente,i):
    _,c,f=ambiente
    for url,p in GRAVACOES:
        r=c.post(url,json=p,headers=headers(i))
        assert r.status_code==(200 if i==1 else 403 if i else 401),(url,r.text)
    with f() as db:
        assert db.query(m.Curso).count()==(2 if i==1 else 1)
        assert db.query(m.Disciplina).count()==(2 if i==1 else 1)
        assert db.query(m.Assunto).count()==(1 if i==1 else 0)
        assert len(db.execute(m.curso_disciplina.select()).all())==int(i==1)

@pytest.mark.parametrize('i',[2,3,4,5,None])
def test_leituras_administrativas_negadas(ambiente,i):
    main,c,_=ambiente
    for route in main.app.routes:
        if route.path.startswith('/admin/') and 'GET' in route.methods:
            url=re.sub(r'\{[^}]+\}','1',route.path)+'?q=Teste'
            r=c.get(url,headers=headers(i));assert r.status_code==(403 if i else 401),(url,r.text)

@pytest.mark.parametrize('i',[1,2,3,4,5])
def test_me_jwt_antigo_e_perfis_acumulados(ambiente,i):
    _,c,f=ambiente
    r=c.get('/me',headers=headers(i));assert r.status_code==200
    assert (r.json()['is_admin'],r.json()['tipo_admin'])==(i==1,{1:'admin_geral',2:'admin_prod',3:'admin_adm'}.get(i))
    assert r.json()['is_aluno'] is True
    assert r.json()['is_vendedor']==(i==5)

@pytest.mark.parametrize('i',[1,2,3])
def test_login_real(ambiente,i):
    _,c,f=ambiente
    with f() as db:db.get(m.Usuario,i).senha_hash=hash_senha('Teste123');db.commit()
    r=c.post('/login',data={'username':f'u{i}@example.com','password':'Teste123'});assert r.status_code==200
    h={'Authorization':'Bearer '+r.json()['access_token']}
    assert c.get('/me',headers=h).json()['is_admin']==(i==1)
    assert c.post('/cursos',json={'nome':'Login'},headers=h).status_code==(200 if i==1 else 403)

@pytest.mark.parametrize('i',[2,3,4,5,None])
def test_escalada_e_endpoint_ausente(ambiente,i):
    _,c,_=ambiente
    assert c.post('/admin/alunos',json={'is_admin':True,'tipo_admin':'admin_geral'},headers=headers(i)).status_code==(403 if i else 401)
    assert c.put('/admin/usuarios/4/tipo-admin',json={'tipo_admin':'admin_geral'},headers=headers(i)).status_code==404

def test_criacao_geral_auditoria_e_payload(ambiente):
    _,c,f=ambiente
    p={'nome':'Novo','cpf':'999','data_nascimento':'1990-01-01','telefone':'0','email':'novo@example.com','senha':'Teste123','is_admin':True}
    for extra in [{'tipo_admin':'admin_prod'},{'is_admin':'false'}]:
        assert c.post('/admin/alunos',json={**p,**extra},headers=headers(1)).status_code==422
    r=c.post('/admin/alunos',json=p,headers=headers(1));assert r.status_code==200,r.text
    with f() as db:
        u=db.query(m.Usuario).filter_by(cpf='999').one();a=db.query(m.AuditoriaPerfilAdmin).one()
        assert (u.is_admin,u.tipo_admin)==(True,'admin_geral')
        assert (a.autor_id,a.usuario_id,a.tipo_novo)==(1,u.id,'admin_geral')

def test_publico_e_revogacao_com_jwt_anterior(ambiente):
    _,c,f=ambiente
    r=c.post('/register',json={'nome':'Teste','cpf':'999','telefone':'0','email':'novo@example.com','senha':'Teste123','is_admin':True,'tipo_admin':'admin_geral'})
    assert r.status_code==200
    assert (r.json()['is_admin'],r.json()['tipo_admin'])==(False,None)
    h=headers(1)
    with f() as db:u=db.get(m.Usuario,1);u.is_admin=False;u.tipo_admin='admin_prod';db.commit()
    assert c.post('/cursos',json={'nome':'Novo'},headers=h).status_code==403
    with f() as db:db.get(m.Usuario,1).ativo=False;db.commit()
    assert c.get('/me',headers=h).status_code==401

@pytest.mark.parametrize('admin,tipo',[(True,None),(True,'admin_prod'),(True,'admin_adm'),(False,'admin_geral'),(False,'root')])
def test_combinacoes_invalidas(ambiente,admin,tipo):
    from app.schemas import UsuarioResponse
    from pydantic import ValidationError
    _,_,f=ambiente
    with f() as db:
        u=db.get(m.Usuario,4);u.is_admin=admin;u.tipo_admin=tipo
        with pytest.raises(IntegrityError):db.commit()
    with pytest.raises(HTTPException):exigir_geral(SimpleNamespace(is_admin=admin,tipo_admin=tipo))
    with pytest.raises(ValidationError):
        UsuarioResponse(id=1,nome='Teste',email='teste@example.com',cpf='1',telefone='0',ativo=True,
            is_admin=admin,tipo_admin=tipo,perfil_inicial='ALUNO')

def test_handlers_publicados_aceitam_frontend_novo(ambiente):
    main,_,f=ambiente
    source=subprocess.check_output(['git','show',BASE+':backend/app/main.py'],cwd=ROOT,text=True)
    nomes={'criar_curso','criar_disciplina','associar_disciplina_ao_curso','criar_assunto'}
    nodes=[n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name in nomes]
    app=FastAPI()
    def db_atual():
        with f() as db:yield db
    ns={**vars(main),'app':app,'get_db':db_atual}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'<handlers-publicados>','exec'),ns)
    with TestClient(app) as c:
        for url,p in GRAVACOES:assert c.post(url,json=p,headers=headers(1)).status_code==200

@pytest.mark.parametrize('i',[2,3])
def test_restritos_sem_competencia_em_escritas_das_quatro_secoes(ambiente,i):
    _,c,f=ambiente
    operacoes=[('/quiz-ia',{}),('/cartoes-ia',{}),('/questoes-ia',{}),
      ('/admin/acessos',{'usuario_id':4,'curso_id':1,'ativo':True,'data_fim':'2030-01-01T00:00:00'}),
      ('/admin/pagamentos/revalidar',{}),('/admin/atendimentos/1/responder',{'resposta':'Resposta'}),
      ('/admin/mensagens-questoes/1/responder',{'texto':'Resposta'}),
      ('/admin/cupons-desconto/gerar',{'quantidade':1}),
      ('/admin/financeiro/manutencao',{'modo':'PAUSADO','geracao':0,'motivo':'Teste'}),
      ('/admin/emails-pagamentos/1/pix/reenviar',{})]
    for url,p in operacoes:
        r=c.post(url,json=p,headers=headers(i));assert r.status_code==403,(url,r.text)
    with f() as db:
        assert db.query(m.AuditoriaPerfilAdmin).count()==0
        assert db.get(m.Usuario,i).is_admin is False


def test_falha_da_auditoria_nao_persiste_novo_administrador(ambiente):
    from sqlalchemy.exc import SQLAlchemyError
    _,c,f=ambiente
    # Simula indisponibilidade da tabela somente no SQLite efêmero da fixture.
    m.AuditoriaPerfilAdmin.__table__.drop(f.kw['bind'])
    with pytest.raises(SQLAlchemyError):
        c.post('/admin/alunos',headers=headers(1),json={'nome':'Novo','cpf':'999',
            'data_nascimento':'1990-01-01','telefone':'0','email':'novo@example.com',
            'senha':'Teste123','is_admin':True})
    with f() as db:
        assert db.query(m.Usuario).count()==5
        assert db.query(m.Usuario).filter_by(cpf='999').count()==0
