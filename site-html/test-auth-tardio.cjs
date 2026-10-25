const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return{promise,resolve,reject}};
function ambiente(tipo='login',store=new Map()) {
 const fields={},timers=[],calls=[],events={};let identity='IDENTIDADE ATUAL';
 for(const id of ['formLogin','formRegister','msg','email','senha','confirmarSenha','nome','cpf','telefone','btnCriarConta']) fields[id]={value:'',style:{},textContent:'',innerHTML:'',addEventListener(type,fn){this[type]=fn},appendChild(){}};
 Object.assign(fields.email,{value:'simulado@example.invalid'});fields.senha.value=fields.confirmarSenha.value='Ficticia1';fields.nome.value='Pessoa Simulada';fields.cpf.value='52998224725';fields.telefone.value='11999999999';
 const node={id:'nome_aluno_logado',classList:{remove(){}},replaceChildren(){identity=''},removeAttribute(){}};
 const s={Headers,Response,TextEncoder,crypto:require('node:crypto').webcrypto,URLSearchParams,console:{warn(){},error(){}},API_BASE:'https://api.example.invalid',
  localStorage:{getItem:k=>store.get(k)??null,setItem:(k,v)=>store.set(k,String(v)),removeItem:k=>store.delete(k)},
  document:{getElementById:k=>fields[k],querySelectorAll:q=>q.includes('[id=')?[node]:[],createElement:()=>({}),createTextNode:text=>({text})},
  location:{href:tipo+'.html',search:''},addEventListener:(k,f)=>events[k]=f,setTimeout:fn=>timers.push(fn),
  fetch:(url,opts)=>{const d=deferred();calls.push({url,opts,...d});return d.promise}};
 s.window=s;vm.createContext(s);
 const dir=process.env.AUTH_SOURCE_DIR||__dirname+'/js';
 vm.runInContext(fs.readFileSync(dir+'/sessao.js','utf8'),s);
 vm.runInContext(fs.readFileSync(dir+'/'+(tipo==='login'?'login':'register')+'.js','utf8'),s);
 return {s,store,fields,timers,calls,events,get identity(){return identity},set identity(v){identity=v},submit(){return fields[tipo==='login'?'formLogin':'formRegister'].submit({preventDefault(){}})},
  reply(index,token,status=200){calls[index].resolve(Response.json(status===200?(token?{access_token:token}:{id:901}):{detail:'Credenciais rejeitadas'},{status}))},
  stable(){return JSON.stringify({store:[...store].sort(),identity,href:s.location.href,msg:fields.msg.textContent,html:fields.msg.innerHTML,timers:timers.length})}};
}
async function timer(e,index=0){await e.timers[index]();await new Promise(r=>setImmediate(r));}
for(const tipo of ['login','register']) {
 test(tipo+': sucesso normal preserva destino e payload',async()=>{
  const e=ambiente(tipo);e.store.set('pos_login_redirect','curso.html?curso_id=7&contratacao_id=8&demonstracao_id=9');
  const p=e.submit();assert.match(e.calls[0].url,new RegExp('/'+tipo+'$'));assert.equal(e.calls[0].opts.method,'POST');
  e.reply(0,'NORMAL');await p;assert.equal(e.store.get('access_token'),'NORMAL');assert.equal(e.timers.length,1);
  await timer(e);assert.equal(e.s.location.href,'curso.html?curso_id=7&contratacao_id=8&demonstracao_id=9');
  if(tipo==='login')assert.equal(e.calls[0].opts.body.get('username'),'simulado@example.invalid');else assert.equal(JSON.parse(e.calls[0].opts.body).nome,'Pessoa Simulada');
 });
 for(const action of ['logout','novo login','401','logout e nova tentativa','outra aba logout','outra aba login'])test(`${tipo}: 200 atrasado após ${action} não altera sessão/cache/identificação`,async()=>{
  const e=ambiente(tipo),p=e.submit();
  if(action==='logout')e.s.Sessao.encerrar();
  if(action==='novo login')e.s.Sessao.definirToken('NOVA');
  if(action==='401'){
   e.s.Sessao.definirToken('INVALIDADA');const req=e.s.Sessao.fetch('/me',{headers:{Authorization:'Bearer INVALIDADA'}});e.reply(1,null,401);await req;
  }
  if(action==='logout e nova tentativa'){e.s.Sessao.encerrar();e.s.Sessao.iniciarAutenticacao()}
  if(action.startsWith('outra aba')){const other=ambiente('login',e.store);if(action.endsWith('logout'))other.s.Sessao.encerrar();else other.s.Sessao.definirToken('OUTRA_ABA');e.events.storage({key:'auth_generation'})}
  e.store.set('me_cache','CACHE POSTERIOR');e.identity='IDENTIDADE POSTERIOR';const before=e.stable();e.reply(0,'ANTIGA');await p;assert.equal(e.stable(),before);
 });
 for(const order of ['antiga primeiro','nova primeiro'])test(`${tipo}: duas tentativas concorrentes (${order}), somente a mais recente vence`,async()=>{
  const e=ambiente(tipo),first=e.submit(),second=e.submit();
  if(order==='antiga primeiro'){e.reply(0,'ANTIGA');await first;assert.equal(e.store.has('access_token'),false);e.reply(1,'NOVA');await second}
  else {e.reply(1,'NOVA');await second;const before=e.stable();e.reply(0,'ANTIGA');await first;assert.equal(e.stable(),before)}
  assert.equal(e.store.get('access_token'),'NOVA');assert.equal(e.timers.length,1);
 });
 test(tipo+': rejeição antiga não invalida outra sessão nem altera mensagem',async()=>{
  const e=ambiente(tipo),p=e.submit();e.s.Sessao.definirToken('VALIDA');e.store.set('me_cache','cache');e.identity='ATUAL';const before=e.stable();e.reply(0,null,401);await p;assert.equal(e.stable(),before);
 });
 test(tipo+': nova tentativa rejeitada não permite sucesso da anterior',async()=>{
  const e=ambiente(tipo),a=e.submit(),b=e.submit();e.reply(1,null,401);await b;const before=e.stable();e.reply(0,'VELHA');await a;assert.equal(e.stable(),before);assert.equal(e.store.has('access_token'),false);
 });
 test(tipo+': corpo atrasado também é ignorado',async()=>{
  const e=ambiente(tipo),d=deferred(),p=e.submit();e.calls[0].resolve({ok:true,json:()=>d.promise,text:()=>d.promise});await Promise.resolve();await Promise.resolve();
  e.s.Sessao.encerrar();const before=e.stable();d.resolve(tipo==='login'?{access_token:'ANTIGO'}:JSON.stringify({access_token:'ANTIGO'}));await p;assert.equal(e.stable(),before);
 });
 for(const action of ['troca','401','mesmo token','nova tentativa'])test(`${tipo}: temporizador após ${action} não redireciona nem consome contexto`,async()=>{
  const e=ambiente(tipo),p=e.submit();e.store.set('pos_login_redirect','checkout.html?curso_id=4&demonstracao_id=2');e.reply(0,'A');await p;
  if(action==='troca')e.s.Sessao.definirToken('B');
  if(action==='mesmo token'){e.s.Sessao.encerrar();e.s.Sessao.definirToken('A')}
  if(action==='nova tentativa')e.s.Sessao.iniciarAutenticacao();
  if(action==='401'){const r=e.s.Sessao.fetch('/me',{headers:{Authorization:'Bearer A'}});e.reply(1,null,401);await r}
  const before=e.stable();await timer(e);assert.equal(e.stable(),before);
 });
 test(tipo+': redirecionamento de sessão preexistente respeita geração',async()=>{
  const store=new Map([['access_token','A']]),e=ambiente(tipo,store);e.s.Sessao.encerrar();e.s.Sessao.definirToken('A');const before=e.stable();await timer(e);assert.equal(e.stable(),before);
 });
 test(tipo+': erro de rede antigo não altera sessão mais recente',async()=>{
  const e=ambiente(tipo),p=e.submit();e.s.Sessao.definirToken('NOVA');const before=e.stable();e.calls[0].reject(new TypeError('offline'));await p;assert.equal(e.stable(),before);
 });
}
test('cadastro sem token mantém confirmação e link de login',async()=>{
 const e=ambiente('register');e.store.set('pos_login_redirect','curso.html?curso_id=7&demonstracao_id=4');const p=e.submit();e.reply(0,null);await p;
 assert.equal(e.store.has('access_token'),false);assert.equal(e.timers.length,0);assert.match(e.fields.msg.innerHTML,/Conta criada com sucesso/);assert.match(e.fields.msg.innerHTML,/login.html\?next=curso.html%3Fcurso_id%3D7%26demonstracao_id%3D4/);
});
test('cadastro sem token atrasado não altera a identificação/mensagem posterior',async()=>{
 const e=ambiente('register'),p=e.submit();e.s.Sessao.definirToken('NOVA');const before=e.stable();e.reply(0,null);await p;assert.equal(e.stable(),before);
});
for(const firstType of ['login','register'])test('tentativa em outra aba supera '+firstType+' pendente mesmo antes de obter token',async()=>{
 const a=ambiente(firstType),old=a.submit(),b=ambiente(firstType==='login'?'register':'login',a.store),newer=b.submit();const before=a.stable();a.reply(0,'ANTIGA');await old;assert.equal(a.stable(),before);b.reply(0,'ATUAL');await newer;assert.equal(a.store.get('access_token'),'ATUAL');
});
for(const [profile,dest] of [[{is_admin:false,tipo_admin:'admin_prod'},'admin/index.html'],[{is_admin:false,tipo_admin:'admin_adm'},'admin/index.html'],[{is_admin:false,tipo_admin:'admin_prod',is_aluno:true},'minha-area.html'],[{is_admin:false,tipo_admin:'admin_adm',is_vendedor:true},'minha-area.html'],[{is_admin:true},'admin/index.html'],[{is_vendedor:true},'minhas-vendas.html'],[{is_aluno:true},'cursos.html'],[{is_admin:true,is_aluno:true},'minha-area.html'],[{},'index.html']])test('login normal: perfil preserva destino '+dest,async()=>{
 const e=ambiente(),p=e.submit();e.reply(0,'NORMAL');await p;await timer(e);assert.equal(e.calls[1].url,'https://api.example.invalid/me');
 e.calls[1].resolve(Response.json(profile));await new Promise(r=>setImmediate(r));assert.equal(e.s.location.href,dest);
});
test('login normal: compra pendente reconstrói destino sem alterar parâmetros salvos',async()=>{
 const e=ambiente();e.store.set('continuar_compra_apos_login','1');e.store.set('estado_compra_curso',JSON.stringify({curso_id:71}));const p=e.submit();e.reply(0,'NORMAL');await p;await timer(e);assert.equal(e.s.location.href,'curso-info.html?curso_id=71');assert.equal(e.store.get('continuar_compra_apos_login'),'1');
});
test('login normal: next explícito preservado',async()=>{
 const e=ambiente();e.s.location.search='?next='+encodeURIComponent('checkout.html?curso_id=7&contratacao_id=4');const p=e.submit();e.reply(0,'NORMAL');await p;await timer(e);assert.equal(e.s.location.href,'checkout.html?curso_id=7&contratacao_id=4');
});
test('login: /me atrasado do redirecionamento não navega após troca de sessão',async()=>{
 const e=ambiente(),p=e.submit();e.reply(0,'ANTIGA');await p;await timer(e);e.s.Sessao.definirToken('NOVA');const before=e.stable();e.calls[1].resolve(Response.json({is_admin:true}));await new Promise(r=>setImmediate(r));assert.equal(e.stable(),before);
});
test('login: /me 401 legítimo invalida e mantém destino de login',async()=>{
 const e=ambiente(),p=e.submit();e.reply(0,'INVALIDA');await p;await timer(e);e.reply(1,null,401);await new Promise(r=>setImmediate(r));assert.equal(e.store.has('access_token'),false);assert.equal(e.s.location.href,'login.html');
});
