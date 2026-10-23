"""Chromium real: cache e consumidores antigos/novos contra APIs locais reais."""
import ast
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import subprocess
import socket
import tempfile
import threading
import time
import urllib.request
import websocket
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import schemas
from test_admin_intermediario_seguro import ambiente, headers, ROOT, BASE

BROWSER='/home/codespace/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome'


def test_cache_e_matriz_front_backend(ambiente):
    main,novo,f=ambiente
    original=subprocess.check_output(['git','show',BASE+':backend/app/main.py'],cwd=ROOT,text=True)
    oldjs=subprocess.check_output(['git','show',BASE+':site-html/js/admin.js'],cwd=ROOT,text=True)
    oldschema=subprocess.check_output(['git','show',BASE+':backend/app/schemas.py'],cwd=ROOT,text=True)
    app=FastAPI()
    def get_db():
        with f() as db:yield db
    ns={**vars(schemas),**vars(main),'app':app,'get_db':get_db}
    schema=[n for n in ast.parse(oldschema).body if isinstance(n,ast.ClassDef) and n.name=='UsuarioResponse']
    exec(compile(ast.Module(body=schema,type_ignores=[]),'<schema-publicado>','exec'),ns)
    nomes={'criar_curso','criar_disciplina','criar_assunto','associar_disciplina_ao_curso',
           'me','listar_cursos','listar_disciplinas','listar_disciplinas_do_curso'}
    nodes=[n for n in ast.parse(original).body if isinstance(n,ast.FunctionDef) and n.name in nomes]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'<api-publicada>','exec'),ns)
    antigo=TestClient(app)
    asset=next((ROOT/'site-html/js').glob('admin-intermediario-022.*.js')).name
    state={'js':'antigo','html':'antigo','api':antigo,'records':[],'admin_requests':0,'asset_requests':0}
    lock=threading.Lock()
    token=headers(1)['Authorization'].split(' ',1)[1]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def responder(self,code,body,ctype='text/html',cache='no-store'):
            self.send_response(code);self.send_header('Content-Type',ctype)
            self.send_header('Cache-Control',cache);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def api(self):
            n=int(self.headers.get('Content-Length','0'));body=self.rfile.read(n) if n else None
            with lock:
                r=state['api'].request(self.command,self.path[4:],content=body,
                    headers={k:v for k,v in self.headers.items() if k.lower() in ('authorization','content-type')})
                state['records'].append((self.command,self.path[4:],r.status_code,bool(self.headers.get('Authorization'))))
            self.responder(r.status_code,r.content,'application/json')
        def do_POST(self):self.api()
        def do_GET(self):
            if self.path.startswith('/api/'):return self.api()
            name=self.path.split('?',1)[0]
            if name=='/js/admin.js':
                state['admin_requests']+=1
                body=oldjs if state['js']=='antigo' else (ROOT/'site-html/js/admin.js').read_text()
                return self.responder(200,body.encode(),'text/javascript','public,max-age=3600')
            if name.startswith('/js/'):
                file=ROOT/'site-html'/name.lstrip('/')
                if not file.is_file():return self.responder(404,b'')
                if file.name==asset:state['asset_requests']+=1
                body=file.read_text()
                if name=='/js/app.js':body=re.sub(r'const API_BASE = "[^"]+";',f'const API_BASE = "{base}/api";',body,count=1)
                return self.responder(200,body.encode(),'text/javascript','public,max-age=3600')
            html=f'''<html><body><form id="formCriarCurso"><input id="cursoNome"><input id="cursoAtivo" value="true"></form>
<div id="msgCriar"></div><input id="cursoSelect" value="1"><div id="msgVinculo"></div><div id="listaVinculadas"></div>
<script>localStorage.setItem('access_token',{json.dumps(token)});</script>
<script src="/js/sessao.js"></script><script src="/js/app.js"></script><script src="/js/admin.js"></script></body></html>'''
            if state['html']=='novo':html=html.replace('src="/js/admin.js"','src="/js/'+asset+'"')
            self.responder(200,html.encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);base=f'http://127.0.0.1:{server.server_port}'
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix='intermediario-cache-') as profile:
            sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
            proc=subprocess.Popen([BROWSER,'--headless','--no-sandbox','--disable-dev-shm-usage','--no-first-run',
                '--disable-background-networking','--no-proxy-server','--remote-debugging-port='+str(port),'--remote-allow-origins=*',
                '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1','--user-data-dir='+profile,'about:blank'],
                stdout=subprocess.DEVNULL,stderr=open(ROOT/'evidencias/chromium-homologacao.log','w'))
            ws=None
            try:
                local=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                for _ in range(600):
                    try:
                        local.open(f'http://127.0.0.1:{port}/json/version',timeout=.2).close();break
                    except OSError:time.sleep(.05)
                else:raise AssertionError(f'Chromium não iniciou: exit={proc.poll()}')
                req=urllib.request.Request(f'http://127.0.0.1:{port}/json/new?about:blank',method='PUT')
                page=json.load(local.open(req));ws=websocket.create_connection(page['webSocketDebuggerUrl'],timeout=10,suppress_origin=True)
                seq=0
                def cmd(method,params=None):
                    nonlocal seq
                    seq+=1;ident=seq;ws.send(json.dumps({'id':ident,'method':method,'params':params or {}}))
                    while True:
                        item=json.loads(ws.recv())
                        if item.get('id')==ident:
                            assert 'error' not in item,item.get('error')
                            return item.get('result',{})
                def js(expression):
                    v=cmd('Runtime.evaluate',{'expression':expression,'returnByValue':True,'awaitPromise':True})
                    assert 'exceptionDetails' not in v,v.get('exceptionDetails')
                    return v.get('result',{}).get('value')
                def pronto():
                    for _ in range(100):
                        if js("document.readyState==='complete' && typeof AdminCursos!=='undefined'"):return
                        time.sleep(.05)
                    raise AssertionError('Página não carregou')
                def criar(nome,status,auth):
                    inicio=len(state['records'])
                    js("document.getElementById('cursoNome').value="+json.dumps(nome)+";AdminCursos.bindCriar();document.getElementById('formCriarCurso').dispatchEvent(new Event('submit',{cancelable:true}));true")
                    for _ in range(100):
                        posts=[r for r in state['records'][inicio:] if r[:2]==('POST','/cursos')]
                        if posts:break
                        time.sleep(.05)
                    assert posts and posts[0][2:]==(status,auth),posts
                    time.sleep(.15);pronto()
                cmd('Page.enable');cmd('Network.enable')
                cmd('Network.setCacheDisabled',{'cacheDisabled':False})
                cmd('Network.setBlockedURLs',{'urls':['https://*']})
                cmd('Page.navigate',{'url':base+'/primeira'});pronto()
                assert js("AdminCursos.bindCriar.toString().includes('await apiPost(')")
                criar('Antigo-antigo',200,False)
                carregamentos=state['admin_requests']
                state['js']='novo';state['api']=novo
                cmd('Page.navigate',{'url':base+'/segunda'});pronto()
                assert js("AdminCursos.bindCriar.toString().includes('await apiPost(')")
                assert state['admin_requests']==carregamentos,'Teste não reutilizou o cache'
                criar('Cache-antigo-bloqueado',401,False)
                assert js("!!localStorage.getItem('access_token')"),'401 do consumidor antigo removeu token'
                state['html']='novo'
                cmd('Page.navigate',{'url':base+'/release-versionada'});time.sleep(.15);pronto()
                assert js("AdminCursos.bindCriar.toString().includes('await apiPostAuth(')")
                assert state['admin_requests']==carregamentos
                assert state['asset_requests']==1
                criar('Novo-novo',200,True)
                state['api']=antigo
                criar('Novo-antigo',200,True)
                state['api']=novo
                js("localStorage.setItem('access_token',"+json.dumps(headers(2)['Authorization'].split(' ',1)[1])+")")
                criar('Restrito-bloqueado',403,True)
                # Recarrega para remover os listeners acumulados, com token Geral.
                cmd('Page.reload',{'ignoreCache':True});time.sleep(.15);pronto()
                assert js("(async()=>{await apiPostAuth('/disciplinas',{nome:'Homologada'});await AdminCursoDisciplinas.vincular(1);await apiPostAuth('/assuntos',{nome:'Homologado',disciplina_id:1});return true})()")
                assert any(r==('POST','/cursos/1/disciplinas/1',200,True) for r in state['records'])
            finally:
                if ws:ws.close()
                proc.terminate();proc.wait(timeout=10)
    finally:
        server.shutdown();server.server_close();antigo.close()
