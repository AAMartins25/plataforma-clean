/* Chromium real, API inteiramente interceptada; nunca acessa Render. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const http=require('node:http');
const {spawn}=require('node:child_process');
const chrome=process.env.RESUMAO_TEST_CHROMIUM || '/home/codespace/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell';
const root=__dirname;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function executar(){
 const server=http.createServer((req,res)=>{
  const filename=path.join(root,new URL(req.url,'http://localhost').pathname);
  if(!filename.startsWith(root+path.sep)){res.writeHead(403).end();return;}
  fs.readFile(filename,(err,data)=>{
   if(err){res.writeHead(404).end();return;}
   res.setHeader('Content-Type',filename.endsWith('.js')?'application/javascript':filename.endsWith('.css')?'text/css':'text/html');res.end(data);
  });
 });
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const origin=`http://127.0.0.1:${server.address().port}`;
 const profile=fs.mkdtempSync(path.join(os.tmpdir(),'resumao-perfis-browser-'));
 const proc=spawn(chrome,['--headless','--no-sandbox','--disable-dev-shm-usage','--disable-background-networking','--no-first-run','--remote-debugging-pipe',`--user-data-dir=${profile}`],{stdio:['ignore','ignore','pipe','pipe','pipe']});
 let nextId=0,buffer='',tipo='admin_geral';const alteracoes=[];
 let usuario={id:4,nome:'Usuário local',email:'u4@example.com',cpf:'4',ativo:true,is_admin:false,tipo_admin:null,is_aluno:true,is_vendedor:false};const pending=new Map();const listeners=new Map();
 let stderr='';proc.stderr.on('data',b=>stderr+=b);
 function send(method,params={},sessionId){return new Promise((resolve,reject)=>{
  const id=++nextId;const timer=setTimeout(()=>{pending.delete(id);reject(Error(`Timeout ${method}: ${stderr.slice(-300)}`));},15000);
  pending.set(id,{resolve,reject,timer});proc.stdio[3].write(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})})+'\0');
 });}
 proc.stdio[4].on('data',b=>{
  buffer+=b;let end;
  while((end=buffer.indexOf('\0'))>=0){
   const packet=JSON.parse(buffer.slice(0,end));buffer=buffer.slice(end+1);
   if(packet.id){const p=pending.get(packet.id);if(p){clearTimeout(p.timer);pending.delete(packet.id);packet.error?p.reject(Error(JSON.stringify(packet.error))):p.resolve(packet.result);}}
   else for(const f of listeners.get(packet.method)||[])f(packet.params,packet.sessionId);
  }
 });
 const on=(event,f)=>listeners.set(event,[...(listeners.get(event)||[]),f]);
 let checks=0;
 try{
  const {targetId}=await send('Target.createTarget',{url:'about:blank'});
  const {sessionId}=await send('Target.attachToTarget',{targetId,flatten:true});
  const cdp=(method,params)=>send(method,params,sessionId);
  await cdp('Page.enable');await cdp('Runtime.enable');await cdp('Fetch.enable',{patterns:[{urlPattern:'*'}]});
  on('Fetch.requestPaused',async p=>{
   try{
    const u=new URL(p.request.url);
    if(u.origin===origin){await cdp('Fetch.continueRequest',{requestId:p.requestId});return;}
    const me={id:1,nome:'Teste local',email:'local@example.com',ativo:true,is_admin:tipo==='admin_geral',tipo_admin:tipo,is_aluno:true,is_vendedor:false,tem_cursos:false,perfil_inicial:'ALUNO'};
    if (u.pathname==='/admin/usuarios/4/tipo-admin' && p.request.method==='PUT') {
     const dados=JSON.parse(p.request.postData);alteracoes.push(dados.tipo_admin);usuario={...usuario,tipo_admin:dados.tipo_admin,is_admin:dados.tipo_admin==='admin_geral'};
    }
    const payload=u.pathname==='/me'?me:u.pathname==='/admin/usuarios/perfis'?[usuario]:u.pathname==='/admin/usuarios/4/tipo-admin'?usuario:u.pathname.endsWith('/contestacoes')?{contestacoes:[],pendencias:[]}:[];
    await cdp('Fetch.fulfillRequest',{requestId:p.requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:'application/json'},{name:'Access-Control-Allow-Origin',value:'*'},{name:'Access-Control-Allow-Headers',value:'Authorization, Content-Type'},{name:'Access-Control-Allow-Methods',value:'GET, POST, PUT, DELETE, OPTIONS'}],body:Buffer.from(JSON.stringify(payload)).toString('base64')});
   }catch(e){if(!String(e).includes('Invalid InterceptionId'))throw e;}
  });
  on('Page.javascriptDialogOpening',()=>cdp('Page.handleJavaScriptDialog',{accept:true}));
  await cdp('Page.addScriptToEvaluateOnNewDocument',{source:`localStorage.setItem('access_token','token-local');localStorage.setItem('auth_generation','teste');localStorage.removeItem('me_cache');`});
  const producao=['criar-curso-completo.html','admin-questoes-aluno.html','admin-questoes-pratica.html','cursos.html','curso-disciplinas.html','disciplinas.html','assuntos.html','aulas.html','aula-conteudo.html'];
  const alunos=['pagamentos.html','atendimento.html','admin-mensagens-questoes.html'];
  const geral=['alunos.html','vendedores.html','cupons.html','reembolsos.html','contestacoes.html','perfis.html'];
  for(tipo of ['admin_geral','admin_prod','admin_adm',null]){
   for(const pagina of ['index.html',...producao,...alunos,...geral]){
    const allowed=tipo==='admin_geral'||tipo==='admin_prod'&&producao.includes(pagina)||tipo==='admin_adm'&&alunos.includes(pagina)||pagina==='index.html'&&!!tipo;
    await cdp('Page.navigate',{url:`${origin}/admin/${pagina}`});
    let state;
    for(let i=0;i<100;i++){
     await sleep(30);
     const r=await cdp('Runtime.evaluate',{expression:`JSON.stringify({url:location.pathname,ready:document.readyState,hidden:document.documentElement.classList.contains('admin-validando'),sections:Array.from(document.querySelectorAll('[data-admin-area]')).map(e=>!e.hidden)})`,returnByValue:true});
     if(!r.result.value)continue;state=JSON.parse(r.result.value);
     if(allowed&&state.url===`/admin/${pagina}`&&state.ready==='complete'&&!state.hidden)break;
     if(!allowed&&!state.url.startsWith('/admin/')&&state.ready==='complete')break;
    }
    assert(state,`${tipo}: ${pagina}`);
    if(allowed){assert.equal(state.url,`/admin/${pagina}`);assert.equal(state.hidden,false,`${tipo}: ${pagina}`);}
    else assert(!state.url.startsWith('/admin/'),`${tipo}: ${pagina}: ${JSON.stringify(state)}`);
    if(pagina==='index.html'&&allowed)assert.deepEqual(state.sections,tipo==='admin_geral'?[true,true,true,true]:tipo==='admin_prod'?[true,false,false,false]:[false,true,false,false]);
    checks++;
   }
  }
  // Exercita o formulário real de atribuição, troca e revogação.
  tipo='admin_geral';
  await cdp('Page.navigate',{url:`${origin}/admin/perfis.html`});
  async function evaluate(expression){return (await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true})).result.value;}
  async function esperar(expression){for(let i=0;i<100;i++){await sleep(30);if(await evaluate(expression))return;}throw Error('Não ocorreu: '+expression);}
  await esperar("document.readyState==='complete' && !document.documentElement.classList.contains('admin-validando')");
  await evaluate("document.getElementById('buscaPerfilUsuario').value='local';document.getElementById('btnBuscarPerfilUsuario').click()");
  await esperar("!!document.querySelector('[data-usuario-id=\"4\"]')");
  await evaluate("document.querySelector('[data-usuario-id=\"4\"]').click()");
  for(const novo of ['admin_prod','admin_adm','admin_geral',null]){
   await evaluate(`document.getElementById('tipoAdminUsuario').value=${JSON.stringify(novo||'')};document.getElementById('btnAlterarPerfilAdmin').click()`);
   await esperar(`document.getElementById('tipoAdminUsuario')?.value===${JSON.stringify(novo||'')} && !document.getElementById('btnAlterarPerfilAdmin').disabled`);
  }
  assert.deepEqual(alteracoes,['admin_prod','admin_adm','admin_geral',null]);
  console.log('Chromium: formulário real de atribuição, troca e revogação aprovado.');
  console.log(`Chromium: ${checks} navegações por URL direta e menus aprovadas; API interceptada, sem acesso externo.`);
 }finally{
  proc.kill('SIGTERM');server.close();
  for(const p of pending.values()){clearTimeout(p.timer);p.reject(Error('Browser encerrado'));}
  await new Promise(r=>proc.exitCode!==null?r():proc.once('exit',r));
  fs.rmSync(profile,{recursive:true,force:true});
 }
}
executar().catch(e=>{console.error(e);process.exitCode=1;});
