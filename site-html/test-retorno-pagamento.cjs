const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const app=fs.readFileSync(__dirname+'/js/app.js','utf8');
function ambiente(pagina='pagamento_sucesso.html',search='?payment_id=123&status=approved'){
 const elementos={},eventos={},timers=[],pedidos=[];
 const store=new Map([['access_token','token'],['ultimo_checkout_curso_id','1'],['estado_compra_curso','contexto'],['ultimo_curso_id_compra','1']]);
 const s={URLSearchParams,Date,console:{error(){},warn(){}},setTimeout:fn=>timers.push(fn),alert(){},confirm:()=>true,
 localStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v),removeItem:k=>store.delete(k)},
 window:{addEventListener:(t,f)=>eventos[t]=f,location:{search,pathname:'/checkout.html',href:pagina,replace(url){this.href=url}},history:{replaceState(...args){s.historico=args}}},
 document:{title:'Pagamento',body:{dataset:{},style:{}},addEventListener(){},querySelector:()=>s.radio,getElementById:id=>elementos[id]??={style:{},value:'',textContent:'',disabled:false,addEventListener(t,fn){this[t]=fn}}}};
 vm.createContext(s);vm.runInContext(app,s);
 s.apiPostAuth=async(url,payload)=>{pedidos.push({url,payload});return s.resultado};
 const html=fs.readFileSync(__dirname+'/'+pagina,'utf8');
 const script=html.match(/<script>\s*([\s\S]*?)<\/script>/)[1].replace('    carregarCheckout();','').replace('    verificarPagamento();','');
 vm.runInContext(script,s);
 if(pagina==='checkout.html'){
  vm.runInContext('dadosCheckout={id:1};cupomAplicadoCursoInfo={codigo_cupom:"AW265"}',s);
  s.radio={value:'tempo_1',dataset:{tempoId:'1',valorCents:'4990'}};
 }
 return {s,elementos,eventos,timers,pedidos,store,html};
}
const resultado=(status,mais={})=>({ok:true,curso_id:1,status,liberou_acesso:false,...mais});
test('estado inicial neutro, sem afirmação de aprovação',()=>{
 const x=ambiente();assert.match(x.html,/<h2 id="tituloPagamento">\s*Verificando pagamento/);assert.match(x.html,/<p id="msg">\s*Consultando/);
});
for(const [status,titulo] of [['PENDING','Pagamento pendente'],['IN_PROCESS','Pagamento em processamento'],['REJECTED','Pagamento não aprovado'],['CANCELLED','Pagamento cancelado']])test('HTTP 200 '+status+' preserva contexto e não redireciona',async()=>{
 const x=ambiente();x.s.resultado=resultado(status,{payment_method_id:'pix'});await x.s.verificarPagamento();
 assert.equal(x.elementos.tituloPagamento.textContent,titulo);assert.equal(x.timers.length,0);assert.equal(x.store.get('estado_compra_curso'),'contexto');
 if(status==='PENDING'){assert.equal(x.elementos.msg.textContent,'Seu pagamento ainda não foi confirmado.');assert.equal(x.elementos.msgComplemento.textContent,'O acesso ao curso será liberado após a confirmação!');assert.equal(x.elementos.msgComplemento.hidden,false);}
});
for(const liberou of [true,false])test('aprovado '+(liberou?'novo':'já processado')+' confirmado limpa e redireciona',async()=>{
 const x=ambiente();x.s.resultado=resultado('APPROVED',{liberou_acesso:liberou});await x.s.verificarPagamento();
 assert.equal(x.elementos.tituloPagamento.textContent,'Pagamento aprovado!');assert.equal(x.store.has('estado_compra_curso'),false);assert.equal(x.timers.length,1);x.timers[0]();assert.equal(x.s.window.location.href,'cursos.html');
});
for(const r of [resultado('APPROVED',{ocorrencia_financeira:'COBRANCA_DUPLICADA'}),resultado('APPROVED',{liberou_acesso:null}),resultado('REFUNDED'),{},resultado('APPROVED',{curso_id:2})])test('ocorrência ou resposta incompatível não afirma acesso liberado',async()=>{
 const x=ambiente();x.s.resultado=r;await x.s.verificarPagamento();assert.equal(x.elementos.tituloPagamento.textContent,'Pagamento não confirmado');assert.equal(x.timers.length,0);assert.equal(x.store.get('estado_compra_curso'),'contexto');
});
for(const query of ['','?status=approved','?payment_id=abc','?payment_id=-1','?payment_id=123&status=approved&collection_status=approved'])test('parâmetros não determinam aprovação: '+query,async()=>{
 const x=ambiente(undefined,query);x.s.resultado=resultado('PENDING');await x.s.verificarPagamento();assert.notEqual(x.elementos.tituloPagamento.textContent,'Pagamento aprovado!');assert.equal(x.timers.length,0);
 if(!query.includes('payment_id=123'))assert.equal(x.pedidos.length,0);
});
test('falha de consulta mostra mensagem neutra sem botão de consulta',async()=>{
 const x=ambiente();x.s.apiPostAuth=async()=>{throw Error('Indisponível')};await x.s.verificarPagamento();assert.equal(x.elementos.msg.textContent,'Não foi possível confirmar a situação do pagamento. Consulte novamente em instantes.');assert.doesNotMatch(x.html,/btnConsultarPagamento|Consultar novamente/);
 x.s.apiPostAuth=async()=>resultado('APPROVED');await x.s.verificarPagamento();assert.equal(x.elementos.tituloPagamento.textContent,'Pagamento aprovado!');
});
test('consulta pendente pode posteriormente confirmar aprovação',async()=>{
 const x=ambiente();x.s.resultado=resultado('PENDING');await x.s.verificarPagamento();x.s.resultado=resultado('APPROVED');await x.s.verificarPagamento();assert.equal(x.pedidos.length,2);assert.equal(x.timers.length,1);
});
for(const status of ['PENDING','APPROVED'])test('confirmação em Meus Cursos interpreta '+status+' e deduplica',async()=>{
 const x=ambiente();let resolver;x.s.apiPostAuth=()=>{x.pedidos.push(1);return new Promise(r=>resolver=r)};
 const a=x.s.tentarConfirmarPagamentoAoVoltar(),b=x.s.tentarConfirmarPagamentoAoVoltar();resolver(resultado(status));await Promise.all([a,b]);
 assert.equal(x.pedidos.length,1);assert.equal(x.store.has('ultimo_checkout_curso_id'),status!=='APPROVED');assert.equal(!!x.s.historico,status==='APPROVED');
});
for(const search of ['?curso_id=1&demonstracao_id=2&origem=cursos','?curso_id=1&renovacao=1&contratacao_id=7&origem=cursos'])test('checkout: duplo clique, pageshow e contexto '+search,async()=>{
 const x=ambiente('checkout.html',search);let resolver;x.s.apiPostAuth=(url,payload)=>{x.pedidos.push({url,payload});return new Promise(r=>resolver=r)};
 const abertura=x.s.adquirirAgora();await x.s.adquirirAgora();assert.equal(x.pedidos.length,1);assert.equal(x.elementos.btnAdquirirAgora.disabled,true);assert.equal(x.elementos.msgCheckout.textContent,'Abrindo checkout do Mercado Pago...');
 resolver({init_point:'https://example.com/mp'});await abertura;assert.equal(x.elementos.msgCheckout.textContent,'');assert.equal(x.elementos.btnAdquirirAgora.disabled,false);
 x.elementos.msgCheckout.textContent='Abrindo checkout do Mercado Pago...';x.elementos.btnAdquirirAgora.disabled=true;x.eventos.pageshow({persisted:true});
 assert.equal(x.elementos.msgCheckout.textContent,'');assert.equal(x.elementos.btnAdquirirAgora.disabled,false);assert.equal(x.pedidos.length,1);assert.equal(x.s.window.location.search,search);
 assert.equal(x.pedidos[0].payload.codigo_cupom,'AW265');assert.equal(x.s.radio.dataset.tempoId,'1');
 assert.equal(x.pedidos[0].payload.tipo_compra,search.includes('renovacao')?'RENOVACAO':'NOVA');
 assert.equal(x.pedidos[0].payload[search.includes('renovacao')?'contratacao_id':'demonstracao_id'],search.includes('renovacao')?7:2);
});
test('restauração ignora resposta antiga sem redirecionar ou alterar nova operação',async()=>{
 const x=ambiente('checkout.html','?curso_id=1');let resolver;x.s.apiPostAuth=()=>new Promise(r=>resolver=r);
 const abertura=x.s.adquirirAgora();x.eventos.pageshow({persisted:true});resolver({init_point:'https://example.com/antigo'});await abertura;assert.equal(x.s.window.location.href,'checkout.html');assert.equal(x.elementos.btnAdquirirAgora.disabled,false);
});
test('falha de abertura restaura botão e permite nova tentativa',async()=>{
 const x=ambiente('checkout.html','?curso_id=1');x.s.apiPostAuth=async()=>{throw Error('Falha de rede')};await x.s.adquirirAgora();assert.equal(x.elementos.btnAdquirirAgora.disabled,false);assert.match(x.elementos.msgCheckout.textContent,/Falha de rede/);
 x.s.apiPostAuth=async()=>({init_point:'https://example.com/mp'});await x.s.adquirirAgora();assert.equal(x.elementos.msgCheckout.textContent,'');
});

test('navegação reutiliza cabeçalho, Início e logout com confirmação',()=>{
 const x=ambiente();
 assert.match(x.html,/<meta name="viewport"/);
 assert.match(x.html,/<body class="curso-page">/);
 assert.match(x.html,/class="curso-header-acoes"/);
 assert.match(x.html,/href="cursos.html" title="Voltar"/);
 assert.match(x.html,/onclick="irParaInicio\('index.html'\); return false;"/);
 assert.match(x.html,/onclick="sairComConfirmacao\(\)"/);
 x.s.irParaInicio('index.html');assert.equal(x.s.window.location.href,'index.html');
 x.s.confirm=()=>false;x.s.sairComConfirmacao();assert.equal(x.store.get('access_token'),'token');
 x.s.confirm=()=>true;x.s.sairComConfirmacao();assert.equal(x.store.has('access_token'),false);assert.equal(x.s.window.location.href,'index.html');
});
test('consulta inicial preservada e nenhuma promessa fictícia de e-mail',async()=>{
 const x=ambiente();x.s.resultado=resultado('PENDING',{payment_method_id:'pix',email_enviado:true});
 const script=x.html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
 assert.equal((script.match(/    verificarPagamento\(\);/g)||[]).length,1);
 assert.doesNotMatch(script,/setInterval|btnConsultarPagamento|addEventListener/);
 await vm.runInContext('verificarPagamento()',x.s);
 assert.equal(x.pedidos.length,1);assert.equal(x.timers.length,0);
 assert.doesNotMatch(x.elementos.msg.textContent,/e-mail/);
 assert.doesNotMatch(x.elementos.msgComplemento.textContent,/e-mail/);
});
