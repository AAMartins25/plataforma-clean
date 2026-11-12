"""Chromium via CDP, assets reais e API simulada. Sem pacotes novos de browser.
Iniciar Chromium com --remote-debugging-port=9347 --remote-allow-origins=http://127.0.0.1:9347.
Executar a partir da raiz da worktree: python site-html/test-gestao-cursos-browser.py
"""
import base64, functools, http.server, json, pathlib, threading, time, urllib.request
import websocket
ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/'auditorias/gestao-cursos-20261112'
OUT.mkdir(parents=True,exist_ok=True)
MOCK=r'''
window.dadosCursos = [
 {id:1,nome:'zebra Legado',ativo:true},
 {id:2,nome:'alfa Professor Infantil',ativo:true,banca:'Instituto',cargo:'Professor',orgao:'Prefeitura',ano:2026,uf:'RO',produtor_id:7,produtor_nome:'Ana'},
 {id:3,nome:'Beta Professor',ativo:true,banca:'Instituto',cargo:'Professor',orgao:'Estado',ano:2025,uf:'SP',produtor_id:8,produtor_nome:'Bruno'},
 {id:4,nome:'ALFA Guarda',ativo:true,banca:'Outra',cargo:'Guarda',orgao:'Prefeitura',ano:2026,uf:'RO',produtor_id:7,produtor_nome:'Ana'},
 {id:5,nome:'Inativo',ativo:false},
 {id:6,nome:'<img src=x onerror=window.injetado=true>',ativo:true}
];
window.chamadas=[];window.alertas=[];window.falhaLista=false;window.falhaSalvar=false;
window.alert=x=>alertas.push(x);window.confirm=()=>true;window.prompt=()=> 'Curso duplicado';
window.requireAdmin=async()=>true;
window.apiGetAuth=async url=>{
 chamadas.push(['GET',url]);
 if(url==='/admin/cursos') {if(falhaLista)throw Error('Falha simulada');return structuredClone(dadosCursos);}
 if(url.endsWith('/config-publica'))return {publicado:false,descricao_publica:'',tempos_acesso:[]};
 if(url.includes('disciplinas-proprias'))return [];
 return [];
};
window.apiPostAuth=async(url,dados)=>{
 chamadas.push(['POST',url,dados]);
 if(falhaSalvar)throw Error('Falha simulada');
 if(url==='/cursos') {const c={...dados,id:20,produtor_id:7};dadosCursos.push(c);return c;}
 if(url.endsWith('/duplicar')) {let c={...dadosCursos.find(c=>c.id===Number(url.split('/')[3])),id:21,nome:dados.novo_nome,produtor_id:7};dadosCursos.push(c);return {novo_curso_id:21,novo_curso_nome:c.nome};}
 return {};
};
window.apiPutAuth=async(url,dados)=>{chamadas.push(['PUT',url,dados]);if(falhaSalvar)throw Error('Falha simulada');let c=dadosCursos.find(c=>c.id===Number(url.split('/')[2]));Object.assign(c,dados);return structuredClone(c);};
window.apiDeleteAuth=async url=>{chamadas.push(['DELETE',url]);let c=dadosCursos.find(c=>c.id===Number(url.split('/')[2]));if(c)c.ativo=false;return {};};
'''
class Handler(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args): pass
 def do_GET(self):
  path=self.path.split('?')[0]
  content=None
  if path.endswith('/js/app.js'):content=MOCK
  elif path.endswith('/js/admin.js'):content=(ROOT/'site-html/js/admin.js').read_text()+'\n'+MOCK
  elif path.endswith(('/js/sessao.js','/js/admin-acesso.js')):content=''
  elif path.endswith('/js/editor-descricao-publica.js'):content='window.DescricaoPublicaEditor={carregar:async()=>{},bloquear:()=>{},obter:()=>""};'
  if content is not None:
   self.send_response(200);self.send_header('Content-Type','application/javascript');self.end_headers();self.wfile.write(content.encode());return
  super().do_GET()
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT/'site-html')))
threading.Thread(target=server.serve_forever,daemon=True).start()
targets=json.load(urllib.request.urlopen('http://127.0.0.1:9347/json'))
ws=websocket.create_connection(next(t['webSocketDebuggerUrl'] for t in targets if t['type']=='page'),origin='http://127.0.0.1:9347',timeout=20)
seq=0;errors=[]
def cdp(method,params=None):
 global seq
 seq+=1;n=seq;ws.send(json.dumps({'id':n,'method':method,'params':params or {}}))
 while True:
  r=json.loads(ws.recv())
  if r.get('method')=='Runtime.exceptionThrown':errors.append(r['params'])
  if r.get('id')==n:
   assert 'error' not in r,r
   return r.get('result',{})
def js(code):
 r=cdp('Runtime.evaluate',{'expression':code,'awaitPromise':True,'returnByValue':True})
 assert 'exceptionDetails' not in r,r
 return r.get('result',{}).get('value')
def check(code):assert js(code),code
def settle():js('new Promise(r=>setTimeout(r,100))')
def screenshot(name):
 b=cdp('Page.captureScreenshot',{'format':'png','captureBeyondViewport':True})['data'];(OUT/name).write_bytes(base64.b64decode(b))
try:
 cdp('Runtime.enable');cdp('Page.enable')
 cdp('Page.navigate',{'url':f'http://127.0.0.1:{server.server_port}/admin/criar-curso-completo.html'})
 for _ in range(400):
  if js('document.readyState==="complete" && typeof GestaoCursos!=="undefined" && window.chamadas?.some(c=>c[1]==="/admin/cursos")'):break
  time.sleep(.05)
 check('typeof GestaoCursos!=="undefined"')
 # Only authorized admin endpoint supplies the list; text is never rendered as HTML.
 check('chamadas.some(c=>c[1]==="/admin/cursos") && !chamadas.some(c=>c[1]==="/cursos")')
 check('!window.injetado && !document.querySelector("#cursoExistenteSelect img")')
 check('JSON.stringify([...cursoExistenteSelect.options].slice(1).map(o=>o.value))===JSON.stringify(["6","4","2","3","1"])')
 for width in (320,390,768,1366):
  cdp('Emulation.setDeviceMetricsOverride',{'width':width,'height':900,'deviceScaleFactor':1,'mobile':False})
  settle()
  check('document.documentElement.scrollWidth<=innerWidth && document.body.scrollWidth<=innerWidth')
  screenshot(f'cursos-{width}.png')
  js('cursoExistenteSelect.value="2";btnEditarCurso.click()')
  check('!formEditarCurso.hidden && document.querySelector("#editar-cargo").value==="Professor"')
  check('document.documentElement.scrollWidth<=innerWidth && document.body.scrollWidth<=innerWidth')
  screenshot(f'editar-{width}.png')
  js('cancelarEdicaoCurso.click()')
 # Six simultaneous filters and multiple partial keywords, including accent folding.
 js('''for(const [k,v] of Object.entries({banca:'Instituto',cargo:'Professor',orgao:'Prefeitura',ano:'2026',uf:'RO',produtor_id:'7'})){let e=document.getElementById('filtro-'+k);e.value=v;e.dispatchEvent(new Event('change'));} cursoPesquisa.value='ALF infant';cursoPesquisa.dispatchEvent(new Event('input'));''')
 check('cursoExistenteSelect.options.length===2 && cursoExistenteSelect.options[1].value==="2"')
 js('cursoPesquisa.value="inexistente";cursoPesquisa.dispatchEvent(new Event("input"))')
 check('cursoExistenteSelect.options.length===1 && resultadoCursos.textContent.includes("Nenhum curso")')
 js('limparFiltrosCursos.click();cursoPesquisa.value="legad";cursoPesquisa.dispatchEvent(new Event("input"))')
 check('cursoExistenteSelect.options.length===2 && cursoExistenteSelect.options[1].value==="1"')
 js('limparFiltrosCursos.click();cursoExistenteSelect.value="1";btnEditarCurso.click()')
 check('document.querySelector("#editar-banca").value==="" && !document.querySelector("#editar-banca").required')
 # Existing course can still be renamed without retroactive metadata.
 js('document.querySelector("#editar-nome").value="Legado editado";formEditarCurso.requestSubmit()');settle()
 check('formEditarCurso.hidden && dadosCursos[0].nome==="Legado editado" && dadosCursos[0].ano===null')
 # Editing persists metadata, preserves producer, handles errors, and selects a renamed course outside prior filters.
 js('cursoExistenteSelect.value="2";btnEditarCurso.click();document.querySelector("#editar-nome").value="Nome alterado";document.querySelector("#editar-cargo").value="Professor novo";falhaSalvar=true;formEditarCurso.requestSubmit()');settle()
 check('!formEditarCurso.hidden && erroEditarCurso.textContent.includes("Falha simulada")')
 js('falhaSalvar=false;formEditarCurso.requestSubmit()');settle()
 check('formEditarCurso.hidden && dadosCursos[1].cargo==="Professor novo" && dadosCursos[1].produtor_id===7 && cursoExistenteSelect.value==="2"')
 # Native and explicit frontend validation prevent incomplete creation.
 js('formCurso.requestSubmit()');settle()
 check('!chamadas.some(c=>c[0]==="POST" && c[1]==="/cursos")')
 js('''cursoNome.value='Novo criado';for(const [k,v] of Object.entries({banca:'Banca',cargo:'Professor',orgao:'Município',ano:2027,uf:'AC'}))document.getElementById('novo-'+k).value=v;formCurso.requestSubmit();''');settle()
 check('chamadas.some(c=>c[0]==="POST" && c[1]==="/cursos" && c[2].uf==="AC" && c[2].ano===2027 && !("produtor_id" in c[2]))')
 check('cursoExistenteSelect.value==="20" && msgCurso.textContent.includes("sucesso")')
 # Selection still loads disciplines/configuration.
 js('btnUsarCursoExistente.click()');settle()
 check('chamadas.some(c=>c[1]==="/cursos/20/disciplinas-proprias")')
 # Duplicate remains selectable even with a restrictive name search.
 js('cursoPesquisa.value="Nome alterado";cursoPesquisa.dispatchEvent(new Event("input"));cursoExistenteSelect.value="2";btnDuplicarCurso.click()');settle()
 check('cursoExistenteSelect.value==="21" && msgCurso.textContent.includes("sucesso")')
 js('btnExcluirCurso.click()');settle()
 check('chamadas.some(c=>c[0]==="DELETE" && c[1]==="/cursos/21")')
 # Load failure removes any stale options and allows retry.
 js('falhaLista=true;GestaoCursos.carregar().catch(()=>{})');settle()
 check('cursoExistenteSelect.options.length===1 && cursoExistenteSelect.options[0].text.includes("Erro")')
 js('falhaLista=false;GestaoCursos.carregar()');settle()
 check('cursoExistenteSelect.options.length>1')
 assert not errors,errors
 result={'status':'OK','larguras':[320,390,768,1366],'transbordamento_horizontal':False,'capturas':8,'fluxos':['criação','edição','curso legado','produtor imutável','filtros combinados','pesquisa parcial','ordenação','limpar','seleção','duplicação','exclusão','erros de edição/lista','texto sem HTML'],'api':'simulada; permissões reais testadas na suíte HTTP'}
 (OUT/'browser.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
except Exception:
 print("ERROS BROWSER",json.dumps(errors,ensure_ascii=False));print("CHAMADAS",js("JSON.stringify(window.chamadas)"));print("DOC",js("JSON.stringify({ready:document.readyState,scripts:[...document.scripts].map(s=>s.src),main:typeof window.voltarParaListaVideos,resources:performance.getEntriesByType('resource').map(r=>[r.name,r.responseStatus,r.duration])})"));raise
finally:
 ws.close();server.shutdown()
