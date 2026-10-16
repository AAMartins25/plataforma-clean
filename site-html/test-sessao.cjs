const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/js/sessao.js','utf8');
const app=fs.readFileSync(__dirname+'/js/app.js','utf8');
function ambiente(store=new Map(),token='A') {
 if(token!==null) store.set('access_token',token);
 const elements=[{id:'nomeUsuarioLogadoGlobal'},{id:'nome_aluno_logado'}].map(x=>({...x,text:'ANA / ANA SILVA',title:'ANA SILVA',classList:{remove(){}},replaceChildren(){this.text=''},removeAttribute(k){delete this[k]},remove(){this.removed=true}}));
 const events={};let calls=0;
 const s={Headers,Response,TextEncoder,crypto:require('node:crypto').webcrypto,console,URLSearchParams,
  location:{pathname:'/index.html',search:'',href:'index.html'},
  localStorage:{getItem:k=>store.get(k)??null,setItem:(k,v)=>store.set(k,String(v)),removeItem:k=>store.delete(k)},
  addEventListener:(k,f)=>events[k]=f,
  document:{getElementById(){return null},addEventListener(){},body:{dataset:{}},querySelectorAll:q=>q.includes('[id=')?elements:[]},
  fetch:async()=>{calls++;return Response.json({nome:'Ana Silva',cpf:'NAO_CACHEAR'})}};
 s.window=s;vm.createContext(s);vm.runInContext(source,s);
 return {s,store,elements,events,get calls(){return calls},loadApp(){vm.runInContext(app,s)}};
}
const auth=e=>e.s.Sessao.fetch('/privado',{headers:{Authorization:'Bearer '+e.store.get('access_token')}});
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return{promise,resolve,reject}};
test('cache associado à sessão: reaproveita, guarda só nome e não persiste token',async()=>{
 const e=ambiente();assert.equal((await e.s.Sessao.obterMe('/me')).nome,'Ana Silva');
 const cache=JSON.parse(e.store.get('me_cache'));assert.deepEqual(cache.me,{nome:'Ana Silva'});assert.match(cache.session,/^[a-f0-9]{64}$/);assert.equal(cache.token,undefined);
 await e.s.Sessao.obterMe('/me');assert.equal(e.calls,1);
});
test('cache legado, malformado, expirado ou futuro é descartado',async()=>{
 for(const value of ['{',JSON.stringify({ts:Date.now(),me:{nome:'Outra'}}),JSON.stringify({session:'errada',ts:Date.now(),me:{nome:'Outra'}})]){
  const e=ambiente();e.store.set('me_cache',value);assert.equal((await e.s.Sessao.obterMe('/me')).nome,'Ana Silva');assert.equal(e.calls,1);
 }
 for(const age of [31000,-60000]){const e=ambiente();await e.s.Sessao.obterMe('/me');const c=JSON.parse(e.store.get('me_cache'));c.ts=Date.now()-age;e.store.set('me_cache',JSON.stringify(c));await e.s.Sessao.obterMe('/me');assert.equal(e.calls,2)}
});
for(const profile of ['expirada','inválida'])test(profile+': 401 limpa token, cache e todas as identificações',async()=>{
 const e=ambiente();await e.s.Sessao.obterMe('/me');e.s.fetch=async()=>Response.json({detail:profile},{status:401});
 assert.equal((await auth(e)).status,401);assert.equal(e.store.has('access_token'),false);assert.equal(e.store.has('me_cache'),false);
 assert.ok(e.elements.every(x=>!x.text&&!x.title));assert.equal(await e.s.Sessao.obterMe('/me'),null);
});
for(const status of [403,500,502,503])test('HTTP '+status+' preserva sessão e cache',async()=>{
 const e=ambiente();await e.s.Sessao.obterMe('/me');const c=e.store.get('me_cache');e.s.fetch=async()=>new Response('',{status});await auth(e);assert.equal(e.store.get('access_token'),'A');assert.equal(e.store.get('me_cache'),c);assert.ok(e.elements[0].text);
});
for(const name of ['TypeError','TimeoutError','AbortError'])test(name+' preserva sessão',async()=>{
 const e=ambiente();e.s.fetch=async()=>{throw Object.assign(new Error('Simulado'),{name})};await assert.rejects(auth(e),{name});assert.equal(e.store.get('access_token'),'A');assert.ok(e.elements[0].text);
});
test('401 público/login rejeitado não interfere em sessão válida',async()=>{
 const e=ambiente();e.s.fetch=async()=>new Response('',{status:401});await e.s.Sessao.fetch('/login',{method:'POST'});assert.equal(e.store.get('access_token'),'A');assert.ok(e.elements[0].text);
});
test('logout remove cache e nome sem alterar contexto de compra/estudo',async()=>{
 const e=ambiente();e.store.set('estado_compra_curso','preservar');await e.s.Sessao.obterMe('/me');e.s.Sessao.encerrar();assert.equal(e.store.has('access_token'),false);assert.equal(e.store.has('me_cache'),false);assert.ok(e.elements.every(x=>!x.text));assert.equal(e.store.get('estado_compra_curso'),'preservar');
});
test('troca de usuário descarta cache anterior',async()=>{
 const e=ambiente();await e.s.Sessao.obterMe('/me');e.s.Sessao.definirToken('B');e.s.fetch=async()=>Response.json({nome:'Bruno'});assert.equal((await e.s.Sessao.obterMe('/me')).nome,'Bruno');assert.equal(e.store.get('access_token'),'B');
});
for(const action of ['logout','novo login'])for(const status of [200,401])test(`resposta ${status} atrasada após ${action} não restaura nem encerra sessão nova`,async()=>{
 const e=ambiente(),d=deferred();e.s.fetch=()=>d.promise;const pending=auth(e);
 if(action==='logout')e.s.Sessao.encerrar();else e.s.Sessao.definirToken('B');
 d.resolve(Response.json({nome:'Antigo'},{status}));await assert.rejects(pending,{name:'SessaoAlteradaError'});assert.equal(e.store.get('access_token'),action==='logout'?undefined:'B');assert.equal(e.store.has('me_cache'),false);
});
test('corpo 200 atrasado também é descartado',async()=>{
 const e=ambiente(),d=deferred();e.s.fetch=async()=>({status:200,ok:true,json:()=>d.promise,text:async()=>''});const r=await auth(e);const body=r.json();e.s.Sessao.encerrar();d.resolve({nome:'Antigo'});await assert.rejects(body,{name:'SessaoAlteradaError'});
});
for(const action of ['logout','401'])test('múltiplas abas: '+action+' limpa nome e evento antigo preserva login novo',async()=>{
 const a=ambiente(),b=ambiente(a.store,null);
 if(action==='logout')a.s.Sessao.encerrar();else{a.s.fetch=async()=>new Response('',{status:401});await auth(a)}
 b.events.storage({key:'access_token'});assert.ok(b.elements.every(x=>!x.text));
 b.s.Sessao.definirToken('B');b.elements[0].text='BRUNO';b.events.storage({key:'access_token',oldValue:'A',newValue:null});assert.equal(b.elements[0].text,'BRUNO');assert.equal(b.store.get('access_token'),'B');
});
test('helpers reais do app propagam 401 estruturado e preservam sessão em rede/403',async()=>{
 const e=ambiente();e.loadApp();e.s.fetch=async()=>Response.json({detail:'inválido'},{status:401});await assert.rejects(e.s.apiGetAuth('/me'),{status:401});assert.equal(e.store.has('access_token'),false);
 e.s.Sessao.definirToken('B');e.s.fetch=async()=>{throw new TypeError('offline')};await e.s.entrarEEstudar();assert.equal(e.store.get('access_token'),'B');assert.equal(e.s.location.href,'index.html');
 e.s.fetch=async()=>new Response('',{status:403});await e.s.entrarEEstudar();assert.equal(e.store.get('access_token'),'B');
});
test('getMeSafe não repovoa cache nem identificação com /me atrasado',async()=>{
 const e=ambiente();e.loadApp();const d=deferred();let started;
 const ready=new Promise(r=>started=r);
 e.s.fetch=()=>{started();return d.promise};
 const pending=e.s.exibirNomeUsuarioLogado();await ready;e.s.Sessao.encerrar();
 d.resolve(Response.json({nome:'Nome Antigo'}));await pending;
 assert.equal(e.store.has('me_cache'),false);assert.equal(e.store.has('access_token'),false);assert.ok(e.elements.every(x=>!x.text));
});
test('novo login com o mesmo token tem geração própria e ignora 401 anterior',async()=>{
 const e=ambiente(),d=deferred();e.s.fetch=()=>d.promise;const pending=auth(e);
 e.s.Sessao.definirToken('A');d.resolve(new Response('',{status:401}));
 await assert.rejects(pending,{name:'SessaoAlteradaError'});assert.equal(e.store.get('access_token'),'A');
});
test('Bearer antigo iniciado após troca de sessão é descartado',async()=>{
 const e=ambiente();e.s.Sessao.definirToken('B');await assert.rejects(e.s.Sessao.fetch('/me',{headers:{Authorization:'Bearer A'}}),{name:'SessaoAlteradaError'});assert.equal(e.store.get('access_token'),'B');assert.equal(e.calls,0);
});
