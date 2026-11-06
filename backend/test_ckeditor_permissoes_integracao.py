from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from test_aulas_admin import infraestrutura

@pytest.mark.parametrize('is_admin,tipo_admin,expected',[(True,'admin_geral',200),(False,'admin_prod',200),(False,'admin_adm',403),(False,None,403),(True,None,403),(True,'admin_prod',403)])
def test_chave_respeita_matriz_atual(infraestrutura,monkeypatch,is_admin,tipo_admin,expected):
    main,_,_=infraestrutura
    monkeypatch.setenv('CKEDITOR_LICENSE_KEY','somente-chave-sintetica-de-teste')
    main.app.dependency_overrides[main.get_usuario_atual]=lambda:SimpleNamespace(id=1,is_admin=is_admin,tipo_admin=tipo_admin)
    try:
        with TestClient(main.app) as client:r=client.get('/admin/ckeditor-chave')
        assert r.status_code==expected
        if expected==200:assert r.json()=={'licenseKey':'somente-chave-sintetica-de-teste'}
        else:assert 'licenseKey' not in r.json()
    finally:main.app.dependency_overrides.clear()

def test_chave_sem_sessao_nao_expoe_chave(infraestrutura,monkeypatch):
    main,_,_=infraestrutura
    monkeypatch.setenv('CKEDITOR_LICENSE_KEY','somente-chave-sintetica-de-teste')
    def sem_sessao():raise HTTPException(401,'Não autenticado')
    main.app.dependency_overrides[main.get_usuario_atual]=sem_sessao
    try:
        with TestClient(main.app) as client:r=client.get('/admin/ckeditor-chave')
        assert r.status_code==401 and 'licenseKey' not in r.json()
    finally:main.app.dependency_overrides.clear()
