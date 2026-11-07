"""Imagens em SQLite e Storage de memória. Nunca usa banco/Storage configurados."""
import base64
from datetime import datetime, timedelta
from io import BytesIO
import json
import os
from pathlib import Path
import stat
import sys
from types import SimpleNamespace
from unittest.mock import patch
import zipfile

import pytest
from fastapi import HTTPException
from PIL import Image

from app import models as m
from app import imagens as midias
from app import imagens_arquivos as arquivos
from app.imagens_storage import obter_storage_imagens, SupabaseImagens
from test_aulas_admin import ambiente as aulas, infraestrutura


def png(cor="red", tamanho=(90, 40)):
    out = BytesIO(); Image.new("RGB", tamanho, cor).save(out, format="PNG")
    return out.getvalue()


def zip_bytes(itens):
    out = BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as z:
        for nome, valor in itens.items():
            z.writestr(nome, valor)
    return out.getvalue()


class StorageMemoria:
    def __init__(self):
        self.objetos = {}
        self.assinadas = []
        self.falhar = False
        self.envios = 0

    def enviar(self, chave, dados, mime):
        self.envios += 1
        if self.falhar and self.envios % 2 == 0:
            raise HTTPException(502, "Falha simulada no segundo arquivo.")
        self.objetos[chave] = (dados, mime)

    def excluir(self, chave):
        self.objetos.pop(chave, None)

    def assinar(self, chave):
        if chave not in self.objetos:
            raise HTTPException(502, "Objeto de teste ausente.")
        self.assinadas.append(chave)
        return "/__imagens/" + chave + "?assinatura=simulada"


@pytest.fixture
def ambiente_imagens(aulas):
    main, client, factory, perfil = aulas
    tabelas = [m.ImagemTeoria.__table__, m.ImagemTeoriaMaterial.__table__,
               m.QuestaoPraticaAssunto.__table__, m.QuestaoPraticaAlternativa.__table__]
    m.Base.metadata.create_all(factory.kw["bind"], tables=tabelas)
    storage = StorageMemoria()
    main.app.dependency_overrides[obter_storage_imagens] = lambda: storage
    try:
        yield main, client, factory, perfil, storage
    finally:
        main.app.dependency_overrides.pop(obter_storage_imagens, None)
        m.Base.metadata.drop_all(factory.kw["bind"], tables=list(reversed(tabelas)))


def enviar(client, *dados):
    r = client.post("/admin/imagens/arquivos", files=[("arquivos", (f"imagem{i}.png", d, "image/png")) for i, d in enumerate(dados or [png()])])
    assert r.status_code == 200, r.text
    return r.json()["imagens"]


def salvar(client, imagem, **kw):
    return client.post("/materiais", json={"aula_id": 1, "tipo": "TEXTO", "titulo": "Imagem",
        "conteudo_formato": "html_v1", "conteudo": '<figure class="image"><img src="' + imagem["src"] + '" alt="Figura"></figure>', **kw})


def test_upload_gravacao_reabertura_edicao_e_acesso_contextual(ambiente_imagens):
    main, c, factory, perfil, storage = ambiente_imagens
    img = enviar(c)[0]
    r = salvar(c, img); assert r.status_code == 200, r.text
    material = r.json()
    assert material["conteudo_formato"] == "html_v1"
    assert "assinatura" not in material["conteudo"]
    assert c.get("/aulas/1/materiais").json()[-1]["conteudo"] == material["conteudo"]
    with factory() as db:
        assert db.query(m.ImagemTeoriaMaterial).filter_by(material_id=material["id"], imagem_id=img["id"]).count() == 1
    perfil(False)
    url = "/aulas/1/imagens/assinaturas?contratacao_id=1"
    assert c.post(url, json={"ids": [img["id"]]}).status_code == 200
    antes = len(storage.assinadas)
    for errado in ["/aulas/1/imagens/assinaturas", "/aulas/1/imagens/assinaturas?contratacao_id=2",
                    "/aulas/2/imagens/assinaturas?contratacao_id=3"]:
        assert c.post(errado, json={"ids": [img["id"]]}).status_code in {400, 403}
    assert len(storage.assinadas) == antes
    perfil(True)
    r = c.put('/materiais/' + str(material['id']), json={"aula_id": 1, "tipo": "TEXTO", "titulo": "Editado", "conteudo_formato": "html_v1",
              "conteudo": '<p><span class="ro-math-inline">x^2</span></p>' + material["conteudo"]})
    assert r.status_code == 200, r.text
    assert "ro-math-inline" in r.json()["conteudo"]
    with factory() as db:
        db.get(m.Material, material["id"]).ativo = False; db.commit()
    perfil(False)
    assert c.post(url, json={"ids": [img["id"]]}).status_code == 403


def test_imagens_nao_referenciadas_ou_de_outro_autor_nao_sao_liberadas(ambiente_imagens):
    main, c, factory, perfil, storage = ambiente_imagens
    img = enviar(c)[0]
    perfil(False)
    assert c.post("/aulas/1/imagens/assinaturas?contratacao_id=1", json={"ids": [img["id"]]}).status_code == 403
    main.app.dependency_overrides[main.get_usuario_atual] = lambda: SimpleNamespace(id=2, is_admin=True, tipo_admin="admin_geral")
    assert c.post("/admin/imagens/assinaturas", json={"ids": [img["id"]]}).status_code == 404
    assert salvar(c, img).status_code == 422
    assert not storage.assinadas


@pytest.mark.parametrize("tipo,is_admin,status", [("admin_prod",False,200),("admin_geral",True,200),("admin_adm",False,403),(None,False,403)])
def test_upload_respeita_matriz_administrativa(ambiente_imagens, tipo, is_admin, status):
    main, c, _, _, _ = ambiente_imagens
    main.app.dependency_overrides[main.get_usuario_atual] = lambda: SimpleNamespace(id=1,is_admin=is_admin,tipo_admin=tipo)
    assert c.post("/admin/imagens/arquivos", files={"arquivos": ("x.png",png(),"image/png")}).status_code == status


def test_nao_autenticado_nao_envia_nem_assina(ambiente_imagens):
    main, c, _, _, storage = ambiente_imagens
    main.app.dependency_overrides.pop(main.get_usuario_atual)
    assert c.post("/admin/imagens/arquivos",files={"arquivos":("x.png",png(),"image/png")}).status_code == 401
    assert not storage.objetos


def test_falha_parcial_compensa_arquivos_sem_gravar_material(ambiente_imagens):
    _, c, factory, _, storage = ambiente_imagens
    storage.falhar = True
    r = c.post("/admin/imagens/arquivos", files=[("arquivos",("a.png",png(),"image/png")),("arquivos",("b.png",png("blue"),"image/png"))])
    assert r.status_code == 502
    assert not storage.objetos
    with factory() as db:
        assert db.query(m.ImagemTeoria).count() == 0
        assert db.get(m.Material, 1).conteudo == "Conteúdo"


def test_copia_preserva_arquivo_e_exclusao_tem_carencia(ambiente_imagens):
    main, c, factory, _, storage = ambiente_imagens
    img = enviar(c)[0]; material = salvar(c, img).json()
    from app.copias import copiar_assunto_conteudo
    with factory() as db:
        assunto = copiar_assunto_conteudo(db, db.get(m.CursoAssuntoProprio,1),2)
        db.commit()
        copia = db.query(m.Material).join(m.Aula,m.Material.aula_id==m.Aula.id).join(m.Pasta,m.Aula.pasta_id==m.Pasta.id).filter(m.Pasta.curso_assunto_proprio_id==assunto.id,m.Material.titulo=="Imagem").one()
        copia_id = copia.id
        assert copia.conteudo == material["conteudo"]
        assert db.query(m.ImagemTeoriaMaterial).filter_by(imagem_id=img["id"]).count() == 2
        db.get(m.ImagemTeoria,img["id"]).ultima_atividade = datetime.utcnow()-timedelta(days=3); db.commit()
        assert midias.limpar_nao_referenciadas(db,storage) == 0
    assert c.delete('/materiais/'+str(material['id'])).status_code == 200
    with factory() as db:
        assert midias.limpar_nao_referenciadas(db,storage) == 0
    assert c.delete('/materiais/'+str(copia_id)).status_code == 200
    with factory() as db:
        assert midias.limpar_nao_referenciadas(db,storage) == 0
        assert midias.limpar_nao_referenciadas(db,storage,datetime.utcnow()+timedelta(days=2)) == 1
    assert not storage.objetos


def test_zip_valido_com_imagens_nas_posicoes_e_ausencias_recusadas(ambiente_imagens):
    _, c, _, _, storage = ambiente_imagens
    md = '# Título\n\nAntes ![A](imagens/a.png) meio ![B](imagens/b.png) depois.\n\n\\(x^2\\)'
    pacote = zip_bytes({'conteudo.md':md,'imagens/a.png':png(),'imagens/b.png':png('blue')})
    r = c.post('/admin/imagens/zip',files={'arquivo':('material.zip',pacote,'application/zip')})
    assert r.status_code == 200, r.text
    assert r.json()['markdown'] == md
    assert [i['nome'] for i in r.json()['imagens']] == ['imagens/a.png','imagens/b.png']
    assert len(storage.objetos) == 2
    assert c.post('/admin/imagens/zip',files={'arquivo':('bad.zip',zip_bytes({'imagens/a.png':png()}))}).status_code == 422


@pytest.mark.parametrize('nome',['../x.png','/x.png','imagens/../x.png','imagens\\x.png','C:/x.png','imagens/%2e%2e.png','imagens/a.zip','imagens/x.svg','outra/x.png','imagens/sub/x.png'])
def test_zip_recusa_caminhos_e_tipos_inseguros(nome):
    with pytest.raises(HTTPException): arquivos.ler_zip(zip_bytes({'conteudo.md':'Texto',nome:png()}))


def test_zip_recusa_symlink_duplicatas_bomba_e_utf8():
    out=BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        info=zipfile.ZipInfo('imagens/link.png');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16
        z.writestr('conteudo.md','Texto');z.writestr(info,'/etc/passwd')
    with pytest.raises(HTTPException):arquivos.ler_zip(out.getvalue())
    with pytest.raises(HTTPException):arquivos.ler_zip(zip_bytes({'conteudo.md':'Texto','imagens/A.png':png(),'imagens/a.png':png()}))
    with pytest.raises(HTTPException):arquivos.ler_zip(zip_bytes({'conteudo.md':b'\xff'}))
    out=BytesIO()
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:z.writestr('conteudo.md','a'*250000)
    with pytest.raises(HTTPException):arquivos.ler_zip(out.getvalue())


@pytest.mark.parametrize('dados',[b'',b'<svg onload="alert(1)"></svg>',b'<html>imagem.png</html>',b'GIF89axxx',b'x'*(arquivos.MAX_ARQUIVO+1)])
def test_imagens_invalidas(dados):
    with pytest.raises(HTTPException):arquivos.validar_imagem(dados)


def test_dimensoes_metadados_e_animacao():
    out=BytesIO();Image.new('RGB',(4100,4000)).save(out,format='PNG')
    with pytest.raises(HTTPException):arquivos.validar_imagem(out.getvalue())
    imagem=arquivos.validar_imagem(png(tamanho=(3000,20)))
    assert imagem.largura == 2560 and imagem.altura < 20
    assert Image.open(BytesIO(imagem.dados)).info == {}
    out=BytesIO();Image.new('RGB',(20,20),'red').save(out,format='WEBP',save_all=True,append_images=[Image.new('RGB',(20,20),'blue')],duration=100)
    with pytest.raises(HTTPException):arquivos.validar_imagem(out.getvalue())


@pytest.mark.parametrize('ip',['127.0.0.1','10.0.0.2','169.254.169.254','192.168.1.1','::1','::ffff:8.8.8.8','fc00::1'])
def test_ssrf_recusa_destinos_internos(monkeypatch,ip):
    monkeypatch.setenv('IMAGENS_HOSTS_PERMITIDOS','imagens.exemplo')
    monkeypatch.setattr(arquivos.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',(ip,443))])
    with pytest.raises(HTTPException):arquivos.destino_https('https://imagens.exemplo/a.png')


@pytest.mark.parametrize('url',['http://imagens.exemplo/a','https://nao-permitido/a','https://user:pass@imagens.exemplo/a','https://imagens.exemplo:444/a','https://imagens.exemplo/a#frag','https://imagens.exemplo\\@127.0.0.1/a','file:///etc/passwd','data:image/png,abc'])
def test_ssrf_recusa_urls(monkeypatch,url):
    monkeypatch.setenv('IMAGENS_HOSTS_PERMITIDOS','imagens.exemplo')
    with pytest.raises(HTTPException):arquivos.destino_https(url)


def test_download_fixa_ip_e_nao_segue_redirecionamento(monkeypatch):
    monkeypatch.setenv('IMAGENS_HOSTS_PERMITIDOS','imagens.exemplo')
    monkeypatch.setattr(arquivos.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('8.8.8.8',443))])
    chamadas=[]
    class Resposta:
        status=200
        def getheader(self,k,default=None):return default
        def read1(self,n):
            if getattr(self,'lida',False):return b''
            self.lida=True;return png()
    class Conexao:
        def __init__(self,host,ip,t):chamadas.append((host,ip));self.r=Resposta()
        def request(self,*a,**kw):assert 'Authorization' not in kw['headers']
        def getresponse(self):return self.r
        def close(self):pass
    monkeypatch.setattr(arquivos,'_HTTPSFixado',Conexao)
    assert arquivos.baixar_imagem('https://imagens.exemplo/a.png').largura == 90
    assert chamadas == [('imagens.exemplo','8.8.8.8')]
    Resposta.status=302
    with pytest.raises(HTTPException):arquivos.baixar_imagem('https://imagens.exemplo/a.png')


def test_limite_corpo_antes_do_parser_e_referencia_nao_incorporada(ambiente_imagens):
    _,c,factory,_,storage=ambiente_imagens
    assert c.post('/admin/imagens/arquivos',content=b'x',headers={'Content-Length':str(30*1024*1024),'Content-Type':'application/octet-stream'}).status_code == 413
    assert c.post('/admin/imagens/remotas',content=iter([b' ' * 70000,b' '*70000]),headers={'Content-Type':'application/json'}).status_code == 413
    for src in ['https://exemplo/a.png','data:image/png;base64,abc','/midias/imagens/00000000-0000-4000-8000-000000000000']:
        assert salvar(c,{'src':src}).status_code == 422
    assert not storage.objetos
    with factory() as db:assert db.get(m.Material,1).conteudo=='Conteúdo'


def test_configuracao_ausente_falha_fechada(monkeypatch):
    monkeypatch.delenv('SUPABASE_URL',raising=False);monkeypatch.delenv('SUPABASE_SERVICE_ROLE_KEY',raising=False)
    with pytest.raises(HTTPException) as e:SupabaseImagens()
    assert e.value.status_code == 503


def test_contrato_storage_privado_sem_rede(monkeypatch):
    monkeypatch.setenv('SUPABASE_URL','https://projeto-teste.supabase.co')
    chave='eyJhbGciOiJIUzI1NiJ9.'+base64.urlsafe_b64encode(b'{"role":"service_role"}').decode().rstrip('=')+'.assinatura-sintetica'
    monkeypatch.delenv('SUPABASE_SECRET_KEY',raising=False)
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY',chave)
    monkeypatch.setenv('SUPABASE_IMAGENS_BUCKET','teoria-imagens')
    chamadas=[]
    class Sessao:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def request(self,metodo,url,**kwargs):
            assert self.trust_env is False and kwargs['allow_redirects'] is False
            assert kwargs['headers']['Authorization']=='Bearer '+chave
            chamadas.append((metodo,url,kwargs))
            return SimpleNamespace(status_code=200,json=lambda:{'signedURL':'/object/sign/teoria-imagens/id.png?token=simulado'})
    monkeypatch.setattr('app.imagens_storage.requests.Session',Sessao)
    storage=SupabaseImagens();storage.enviar('id.png',b'pixels','image/png')
    url=storage.assinar('id.png');storage.excluir('id.png')
    assert url=='https://projeto-teste.supabase.co/storage/v1/object/sign/teoria-imagens/id.png?token=simulado'
    assert [c[0] for c in chamadas]==['POST','POST','DELETE']
    assert chamadas[0][2]['headers']['x-upsert']=='false'
    assert chamadas[1][2]['json']=={'expiresIn':900}
    assert chamadas[2][2]['json']=={'prefixes':['id.png']}


def test_sanitizacao_de_imagem_preserva_icone_e_remove_atributos_ativos(ambiente_imagens):
    _,c,_,_,_=ambiente_imagens
    img=enviar(c)[0]
    r=salvar(c,img,conteudo='<p>⌨️ 🖥️ 💾</p><img src="'+img['src']+'" onerror="alert(1)" srcset="https://exemplo/x 2x" style="position:fixed" alt="Ícone" width="90" height="40">')
    assert r.status_code==200,r.text
    html=r.json()['conteudo']
    assert '⌨️ 🖥️ 💾' in html and img['src'] in html and 'alt="Ícone"' in html
    assert not any(atributo in html for atributo in ['onerror','srcset','position:fixed'])


def ponte_browser():
    """Ponte de teste HTTP real (ASGI), com perfis e Storage estritamente locais."""
    os.environ['SECRET_KEY']='imagens-teste-chave-sintetica-12345678901234567890'
    infra=infraestrutura.__wrapped__(); fixture_aulas=None;fixture_imagens=None
    try:
        recurso=next(infra);fixture_aulas=aulas.__wrapped__(recurso);recurso_aulas=next(fixture_aulas)
        fixture_imagens=ambiente_imagens.__wrapped__(recurso_aulas)
        main,c,factory,perfil,storage=next(fixture_imagens)
        perfil(True)
        def baixar(url):
            if url not in {'https://imagens.teste/a.png','https://imagens.teste/b.png'}:raise HTTPException(422,'Imagem remota de teste indisponível.')
            return arquivos.validar_imagem(png('blue' if url.endswith('b.png') else 'red'))
        with patch.object(midias,'baixar_imagem',side_effect=baixar):
            print(json.dumps({'ready':True,'png':base64.b64encode(png()).decode(),'png2':base64.b64encode(png('blue')).decode(),
                'zip':base64.b64encode(zip_bytes({'conteudo.md':'# Material completo\n\nAntes ![Figura A](imagens/a.png) meio ![Figura B](imagens/b.png) depois.\n\n\\[\\forall x, P(x) \\Rightarrow Q(x)\\]\n\n| Coluna | Valor |\n|---|---|\n| Teste | 1 |','imagens/a.png':png(),'imagens/b.png':png('blue')})).decode(),
                'zipRuim':base64.b64encode(zip_bytes({'conteudo.md':'Antes ![Ausente](imagens/ausente.png) depois.','imagens/a.png':png()})).decode()}),flush=True)
            for linha in sys.stdin:
                req=json.loads(linha)
                try:
                    if req['path']=='/__perfil':perfil(req.get('admin',True));result={'status':200,'body':{}}
                    elif req['path']=='/__falha':storage.falhar=req['falhar'];storage.envios=0;result={'status':200,'body':{}}
                    elif req['path'].startswith('/__imagens/'):
                        chave=req['path'].split('?',1)[0].rsplit('/',1)[1];dados,mime=storage.objetos[chave]
                        result={'status':200,'base64':base64.b64encode(dados).decode(),'mime':mime}
                    else:
                        resposta=c.request(req['method'],req['path'],content=base64.b64decode(req.get('base64','')),headers=req.get('headers',{}))
                        result={'status':resposta.status_code,'body':resposta.json()}
                    print(json.dumps(result),flush=True)
                except Exception as e:print(json.dumps({'error':str(e)}),flush=True)
    finally:
        if fixture_imagens:fixture_imagens.close()
        if fixture_aulas:fixture_aulas.close()
        infra.close()


if __name__=='__main__' and '--bridge' in sys.argv:ponte_browser()
