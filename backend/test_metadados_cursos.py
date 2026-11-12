"""Contrato HTTP da gestão; SQLite descartável, sem importar banco configurado."""
from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from app import models as m, schemas
from test_admin_intermediario_seguro import ambiente, headers

DADOS = dict(nome='Curso novo', banca='Instituto', cargo='Professor', orgao='Prefeitura', ano=2026, uf='RO')

@pytest.mark.parametrize('campo',list(DADOS))
@pytest.mark.parametrize('valor',[None, ''])
def test_nova_criacao_requer_seis_campos(campo,valor):
    with pytest.raises(ValidationError): schemas.CursoCreate(**{**DADOS,campo:valor})

@pytest.mark.parametrize('valor',[999,10000,2026.5,True,'2026'])
def test_ano_invalido(valor):
    with pytest.raises(ValidationError): schemas.CursoCreate(**{**DADOS,'ano':valor})

@pytest.mark.parametrize('campo,valor',[('uf','XX'),('uf','ro'),('nome','   '),('banca','  '),('cargo','x'*256),('orgao','x'*256),('nome','x'*256)])
def test_campos_invalidos(campo,valor):
    with pytest.raises(ValidationError): schemas.CursoCreate(**{**DADOS,campo:valor})

@pytest.mark.parametrize('id',[1,2])
def test_criacao_edicao_produtor_persistente_e_listagem(ambiente,id):
    _,c,f=ambiente
    r=c.post('/cursos',json=DADOS,headers=headers(id));assert r.status_code==200,r.text
    cid=r.json()['id']
    with f() as db:
        curso=db.get(m.Curso,cid)
        assert curso.produtor_id==id and curso.uf=='RO' and curso.cargo=='Professor'
    r=c.get('/admin/cursos',headers=headers(id));assert r.status_code==200,r.text
    novo=next(x for x in r.json() if x['id']==cid)
    assert novo['produtor_nome']==f'Usuário {id}' and novo['banca']=='Instituto'
    antigo=next(x for x in r.json() if x['id']==1)
    assert antigo['ano'] is None and antigo['produtor_id'] is None
    # PUT antigo preserva os metadados e o produtor.
    assert c.put(f'/cursos/{cid}',json={'nome':'Renomeado'},headers=headers(1)).status_code==200
    assert c.put('/cursos/1',json={**DADOS,'nome':'Legado preenchido'},headers=headers(id)).status_code==200
    with f() as db:
        assert db.get(m.Curso,cid).banca=='Instituto'
        assert db.get(m.Curso,cid).produtor_id==id
        assert db.get(m.Curso,1).uf=='RO' and db.get(m.Curso,1).produtor_id is None
    # Nenhum metadado ou identidade de produtor na listagem pública legada.
    assert all(set(x)=={'id','nome','ativo'} for x in c.get('/cursos').json())

@pytest.mark.parametrize('id',[3,4,5,None])
def test_permissoes_nao_revelam_lista_nem_permitem_escrita(ambiente,id):
    _,c,_=ambiente
    esperado=403 if id else 401
    assert c.get('/admin/cursos',headers=headers(id)).status_code==esperado
    assert c.post('/cursos',json=DADOS,headers=headers(id)).status_code==esperado
    assert c.put('/cursos/1',json=DADOS,headers=headers(id)).status_code==esperado

@pytest.mark.parametrize('campo',['produtor_id','produtor_nome'])
def test_produtor_nao_pode_ser_enviado_pelo_cliente(ambiente,campo):
    _,c,f=ambiente
    for metodo,url in [('post','/cursos'),('put','/cursos/1')]:
        r=getattr(c,metodo)(url,json={**DADOS,campo:2},headers=headers(1))
        assert r.status_code==422,r.text
    with f() as db: assert db.query(m.Curso).count()==1


def test_edicao_invalida_inexistente_e_falha_commit(ambiente,monkeypatch):
    _,c,f=ambiente
    assert c.put('/cursos/999',json=DADOS,headers=headers(1)).status_code==404
    for dados in [{**DADOS,'uf':'XX'},{**DADOS,'ano':2026.5},{**DADOS,'nome':'  '}]:
        assert c.put('/cursos/1',json=dados,headers=headers(1)).status_code==422
    from sqlalchemy.orm import Session
    def falhar(self): raise RuntimeError('Falha de banco simulada')
    with monkeypatch.context() as mp:
        mp.setattr(Session,'commit',falhar)
        with pytest.raises(RuntimeError): c.put('/cursos/1',json=DADOS,headers=headers(1))
    with f() as db: assert db.get(m.Curso,1).nome=='Base'
