const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const app=fs.readFileSync(__dirname+'/js/app.js','utf8');
const modulo=fs.readFileSync(__dirname+'/js/juridico.js','utf8');
const turno=()=>new Promise(resolve=>setImmediate(resolve));
const ativo=()=>({obrigatorio:true,documentos:[
 {tipo:'TERMOS',id:1,titulo:'Termos',versao:'1.0',pdf_site_url:'juridico/termos.pdf'},
 {tipo:'PRIVACIDADE',id:2,titulo:'Privacidade',versao:'1.0',pdf_site_url:'juridico/privacidade.pdf'}]});
function ambiente(politica='404'){
 const elementos={},scripts=[],posts=[],eventos={};let ctx;
 function elemento(id){
  const el={id,style:{},checked:false,hidden:true,disabled:false,textContent:'',focus(){this.focado=true;},remove(){},insertAdjacentElement(_,filho){elementos[filho.id]=filho;}};
  Object.defineProperty(el,'innerHTML',{set(html){for(const [,id] of html.matchAll(/id="([^"]+)"/g))elementos[id]=elemento(id);}});
  return el;
 }
 for(const id of ['opcoes_acesso','msgCursoInfo','btnAdquirirAgora'])elementos[id]=elemento(id);
 const e={politica,loader:'ok',consultas:0,token:'teste',scripts,elementos,posts,eventos,radio:{value:'tempo_1',dataset:{tempoId:'1'}}};
 const s={URL,URLSearchParams,AbortController,setTimeout,clearTimeout,queueMicrotask,
  console:{warn(){},error(){},log(){}},location:{href:'https://frontend.example.invalid/curso-info.html?curso_id=1',pathname:'/curso-info.html',search:'?curso_id=1'},
  localStorage:{getItem:k=>k==='access_token'?e.token:null,setItem(){},removeItem(){}},alert(){},
  document:{currentScript:{src:'https://frontend.example.invalid/js/app.js'},readyState:'complete',body:{dataset:{},style:{}},
   getElementById:id=>elementos[id]||null,querySelector:()=>e.radio,querySelectorAll:()=>[],scripts,createElement:()=>elemento(''),
   addEventListener:(t,f)=>{(eventos[t]??=[]).push(f);},head:{appendChild(script){scripts.push(script);if(e.loader==='pendente')return;
    queueMicrotask(()=>{if(e.loader==='erro')return script.onerror();if(e.loader!=='semExport')vm.runInContext(modulo,ctx);script.onload();});}}},
  addEventListener:(t,f)=>{(eventos[t]??=[]).push(f);},fetch:async(_url,options)=>{
   e.consultas++;if(e.politica==='rede')throw Error('Rede simulada');
   if(e.politica==='timeout')return new Promise((_,reject)=>options.signal.addEventListener('abort',()=>reject(Error('Abortado'))));
   const valor=e.politica;return{status:valor==='404'?404:valor==='503'?503:200,
    json:async()=>valor==='ativo'?ativo():valor==='desativado'?{obrigatorio:false,documentos:[]}:valor};
  }};
 s.window=s;ctx=vm.createContext(s);vm.runInContext(app,ctx);vm.runInContext('dadosCursoInfo={id:1};cupomAplicadoCursoInfo=null;',ctx);
 e.apiOriginal=s.apiPostAuth;
 s.apiPostAuth=async(url,payload)=>{posts.push({url,payload});return{init_point:s.location.href+'#simulado'};};
 return Object.assign(e,{s,ctx,comprar:()=>vm.runInContext('adquirirAgoraCursoInfo()',ctx),carregar:()=>vm.runInContext('carregarJuridico()',ctx),instalar:async()=>{vm.runInContext(modulo,ctx);await turno();}});
}
for(const politica of ['404','desativado'])test('HTML antigo sem módulo/campo e política '+politica+' preserva compra',async()=>{
 const e=ambiente(politica);assert.equal(e.s.Juridico,undefined);await e.comprar();
 assert.equal(e.scripts.length,1);assert.equal(e.posts.length,1);assert.equal(e.elementos.aceiteJuridico,undefined);
 assert.equal(e.posts[0].payload.tempo_acesso_id,1);assert.equal(e.posts[0].payload.codigo_cupom,null);assert.equal(e.posts[0].payload.aceite_juridico,undefined);
});
test('consumidores compartilham carga e instância; URL relativa ao app.js',async()=>{
 const e=ambiente();const a=e.carregar(),b=e.carregar();assert.equal(a,b);assert.equal(e.scripts.length,1);
 assert.equal(e.scripts[0].src,'https://frontend.example.invalid/js/juridico.js?v=aceite-3');
 assert.equal(await a,await b);assert.equal(await e.carregar(),e.s.Juridico);assert.equal(e.scripts.length,1);
});
for(const loader of ['erro','semExport'])test('falha do módulo '+loader+' permite retry sem chamar pagamento',async()=>{
 const e=ambiente();e.loader=loader;await e.comprar();assert.equal(e.posts.length,0);
 assert.match(e.elementos.msgCursoInfo.textContent,/Não foi possível carregar os documentos jurídicos/);
 assert.equal(e.elementos.btnAdquirirAgora.disabled,false);e.loader='ok';await e.comprar();assert.equal(e.posts.length,1);
});
test('HTML antigo com política ativa cria checkbox e exige confirmação explícita',async()=>{
 const e=ambiente('ativo');await e.comprar();assert.equal(e.posts.length,0);assert.equal(e.elementos.aceiteJuridico.checked,false);
 assert.equal(e.elementos.boxAceiteJuridico.hidden,false);assert.equal(e.elementos.linkTermos.href,'https://frontend.example.invalid/juridico/termos.pdf');
 e.elementos.aceiteJuridico.checked=true;await e.comprar();assert.equal(e.posts.length,1);
 assert.deepEqual(JSON.parse(JSON.stringify(e.posts[0].payload.aceite_juridico)),{aceito:true,termos_id:1,privacidade_id:2});
});
for(const politica of ['rede','503',{}, {obrigatorio:'false',documentos:[]},{obrigatorio:true,documentos:[]}])
 test('estado indeterminado bloqueia: '+JSON.stringify(politica),async()=>{
  const e=ambiente(politica);await e.comprar();assert.equal(e.posts.length,0);
  assert.match(e.elementos.msgCursoInfo.textContent,/Não foi possível confirmar a política jurídica/);assert.equal(e.elementos.btnAdquirirAgora.disabled,false);
 });
test('erro não reutiliza política desativada em cache',async()=>{
 const e=ambiente('desativado');await e.instalar();e.politica='503';await e.comprar();assert.equal(e.posts.length,0);
});
test('política ativa observada não é rebaixada por 404 posterior',async()=>{
 const e=ambiente('ativo');await e.instalar();e.elementos.aceiteJuridico.checked=true;e.politica='404';await e.comprar();
 assert.equal(e.posts.length,0);assert.equal(e.elementos.aceiteJuridico.checked,false);
});
test('desativação explícita pelo backend é permitida',async()=>{
 const e=ambiente('ativo');await e.instalar();e.politica='desativado';await e.comprar();assert.equal(e.posts.length,1);assert.equal(e.posts[0].payload.aceite_juridico,undefined);
});
test('troca de prazo durante carga não abre pagamento da seleção anterior',async()=>{
 const e=ambiente();e.loader='pendente';const p=e.comprar();e.radio={value:'tempo_2',dataset:{tempoId:'2'}};
 vm.runInContext(modulo,e.ctx);e.scripts[0].onload();await p;assert.equal(e.posts.length,0);
});
test('erro durante refresh após rejeição backend mantém mensagem e botão utilizáveis',async()=>{
 const e=ambiente();e.s.apiPostAuth=async()=>{e.politica='503';throw Error('ACEITE_OBRIGATORIO');};await e.comprar();
 assert.match(e.elementos.msgCursoInfo.textContent,/Não foi possível confirmar a política jurídica/);assert.equal(e.elementos.btnAdquirirAgora.disabled,false);
});
test('timeout da consulta é indeterminado e bloqueia',async()=>{
 const e=ambiente('timeout');let prazo;e.s.setTimeout=fn=>{prazo=fn;return 1;};e.s.clearTimeout=()=>{};
 const p=e.comprar();await turno();prazo();await p;assert.equal(e.posts.length,0);assert.match(e.elementos.msgCursoInfo.textContent,/Não foi possível confirmar a política jurídica/);
});
test('sem token, mantém redirecionamento sem carregar módulo',async()=>{
 const e=ambiente();e.token=null;await e.comprar();assert.equal(e.scripts.length,0);assert.equal(e.posts.length,0);assert.equal(e.s.location.href,'login.html');
});

for(const politica of ['404','desativado','ativo','503','rede'])test('checkout inline legado usa a proteção compartilhada: '+politica,async()=>{
 const e=ambiente(politica);
 e.s.Sessao={fetch:async(url,options)=>{e.posts.push({url,payload:JSON.parse(options.body)});return{ok:true,json:async()=>({init_point:'simulado'})};}};
 if(['ativo','503','rede'].includes(politica)) {
  await assert.rejects(e.apiOriginal('/checkout/mercadopago',{tempo_acesso_id:1,tipo_compra:'RENOVACAO',contratacao_id:7}));
  assert.equal(e.posts.length,0);
  if(politica==='ativo') {
   e.elementos.aceiteJuridico.checked=true;
   await e.apiOriginal('/checkout/mercadopago',{tempo_acesso_id:1,tipo_compra:'RENOVACAO',contratacao_id:7});
   assert.equal(e.posts[0].payload.aceite_juridico.aceito,true);
  }
 } else {
  await e.apiOriginal('/checkout/mercadopago',{tempo_acesso_id:1,tipo_compra:'RENOVACAO',contratacao_id:7});
 }
 if(e.posts.length) {
  assert.equal(e.posts[0].payload.tipo_compra,'RENOVACAO');assert.equal(e.posts[0].payload.contratacao_id,7);
  assert.equal(e.posts[0].payload.politicaConferida,undefined);
 }
});
