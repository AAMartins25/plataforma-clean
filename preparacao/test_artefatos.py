"""Testes offline somente dos pacotes e do ajuste de cache desta etapa."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import pytest
from construir_artefatos import construir, ROOT
from verificar_artefato import verificar


def pacote(nome):
    index=json.loads((ROOT/'artefatos/INDICE.json').read_text())
    return ROOT/'artefatos'/nome,index['pacotes'][nome]


def membros(path):
    with tarfile.open(path) as t:
        return {m.name:t.extractfile(m).read() for m in t.getmembers()}


def test_frontend_aceito_e_recusado_como_backend_ou_recuperacao():
    path,p=pacote('frontend-compativel.tar.gz')
    assert verificar(path,p['sha256'],'frontend')['kind']=='frontend-compativel'
    for uso in ('backend','recuperacao'):
        with pytest.raises(ValueError,match='não é autorizado'):verificar(path,p['sha256'],uso)
    assert all(f.startswith('site-html/') or f=='RELEASE-MANIFEST.json' for f in membros(path))


def test_recuperacao_e_backend_identicos_e_compativeis():
    path,p=pacote('backend-intermediario.tar.gz');rec,r=pacote('recuperacao-intermediario.tar.gz')
    assert path.read_bytes()==rec.read_bytes() and p['sha256']==r['sha256']
    assert verificar(path,p['sha256'],'backend')['base_sha']=='cdba603e9a8d3a3a04a77fc03863ad41c93c1a93'
    assert verificar(rec,r['sha256'],'recuperacao')['kind']=='intermediario-seguro'
    data=membros(path);manifest=json.loads(data['RELEASE-MANIFEST.json'])
    assert manifest['restritos_habilitados'] is False
    approved=json.loads((ROOT/'evidencias/manifesto.json').read_text())
    for f,h in approved['arquivos'].items():assert hashlib.sha256(data[f]).hexdigest()==h
    assert 'backend/app/perfis_admin.py' not in data
    assert not any('.env'==Path(f).name or '.git' in Path(f).parts for f in data)


def test_frontend_das_duas_etapas_e_o_mesmo():
    a,_=pacote('frontend-compativel.tar.gz');b,_=pacote('backend-intermediario.tar.gz')
    fa=membros(a);fb=membros(b)
    for f,v in fa.items():
        if f!='RELEASE-MANIFEST.json':assert fb[f]==v
    asset=json.loads((ROOT/'artefatos/INDICE.json').read_text())['asset']
    assert fa['site-html/js/'+asset]==fa['site-html/js/admin.js']
    refs=[f for f,v in fa.items() if f.startswith('site-html/admin/') and asset.encode() in v]
    assert len(refs)==18


def test_pacotes_reproduziveis():
    a=json.loads((ROOT/'artefatos/INDICE.json').read_text())
    assert construir()==a


def test_sha_externo_incorreto_e_recusado():
    p,_=pacote('backend-intermediario.tar.gz')
    with pytest.raises(ValueError,match='externo divergente'):verificar(p,'0'*64,'backend')


def test_conteudo_modificado_e_recusado(tmp_path):
    p,_=pacote('backend-intermediario.tar.gz');files=membros(p)
    files['backend/app/main.py']+=b'\n# adulterado\n'
    out=tmp_path/'adulterado.tar.gz'
    with tarfile.open(out,'w:gz') as t:
        for name,data in files.items():
            info=tarfile.TarInfo(name);info.size=len(data);t.addfile(info,io.BytesIO(data))
    digest=hashlib.sha256(out.read_bytes()).hexdigest()
    with pytest.raises(ValueError,match='Conteúdo divergente'):verificar(out,digest,'backend')


def test_patches_validos_sem_modificar_o_worktree():
    import subprocess
    for name in ['frontend-primeiro.patch','intermediario-completo.patch']:
        r=subprocess.run(['git','apply','--reverse','--check',str(ROOT/'artefatos'/name)],cwd=ROOT,capture_output=True,text=True)
        assert r.returncode==0,r.stderr
