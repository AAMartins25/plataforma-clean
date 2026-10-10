const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const app=fs.readFileSync(__dirname+'/js/app.js','utf8');
const html=fs.readFileSync(__dirname+'/checkout.html','utf8');
function ambiente(search='?curso_id=1&demonstracao_id=2&origem=cursos',checkout=true){
 const elementos={},store=new Map([['access_token','token']]),pedidos=[];
 const s={URLSearchParams,console:{error(){}},Date,Number,String,Math,JSON,encodeURIComponent,
  confirm:()=>true,localStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v),removeItem:k=>store.delete(k)},
  window:{addEventListener(){},location:{search,pathname:'/checkout.html',href:'https://example.com/checkout.html'+search,replace(url){this.href=url}}},
  document:{getElementById(id){return elementos[id]??={style:{},value:'',textContent:''}},querySelector(){return s.radio},addEventListener(){},body:{dataset:{},style:{}}},
  fetch:async(url,opts)=>{pedidos.push({url,opts});return{ok:true,json:async()=>url.includes('validar')?{codigo_cupom:'AW265',percentual_desconto:12,vendedor_id:1}:{init_point:'https://example.com/pagamento'}}},
 };
 vm.createContext(s);vm.runInContext(app,s);
 if(checkout){const script=html.match(/<script>\s*([\s\S]*?)<\/script>/)[1].replace('    carregarCheckout();','');vm.runInContext(script,s);vm.runInContext('dadosCheckout={id:1,tempos_acesso:[{id:1,meses:4,valor_cents:4990},{id:2,meses:8,valor_cents:9980},{id:3,meses:12,valor_cents:14970}]}',s);}
 else vm.runInContext('dadosCursoInfo={id:1}',s);
 return{s,elementos,store,pedidos};
}
for(const [tempo,valor] of [[1,4990],[2,9980],[3,14970]])test('cupom período '+tempo,async()=>{
 const {s,elementos}=ambiente();s.radio={value:'tempo_'+tempo,dataset:{tempoId:String(tempo),valorCents:String(valor)}};
 s.controleAvisoDemo();assert.equal(elementos.box_cupom_desconto.style.display,'block');
 elementos.codigo_cupom_desconto.value=' aw265 ';await s.aplicarCupomCursoInfo();
 assert.equal(vm.runInContext('cupomAplicadoCursoInfo.valor_final_cents',s),valor-Math.round(valor*12/100));
 assert.equal(elementos.resumoCupomDesconto.style.display,'block');
 s.radio={value:'tempo_3',dataset:{tempoId:'3',valorCents:'14970'}};s.controleAvisoDemo();
 assert.equal(vm.runInContext('cupomAplicadoCursoInfo',s),null);
});
test('payload preserva demonstração e cupom',async()=>{
 const {s,elementos,pedidos}=ambiente();s.radio={value:'tempo_1',dataset:{tempoId:'1',valorCents:'4990'}};
 elementos.codigo_cupom_desconto.value='AW265';await s.aplicarCupomCursoInfo();await s.adquirirAgora();
 const payload=JSON.parse(pedidos.at(-1).opts.body);assert.deepEqual(payload,{tempo_acesso_id:1,codigo_cupom:'AW265',tipo_compra:'NOVA',demonstracao_id:2});
});
test('renovação mantém contrato e não oferece demo',async()=>{
 const {s,pedidos,elementos}=ambiente('?curso_id=1&renovacao=1&contratacao_id=7&origem=cursos');
 s.renderizarOpcoesAcesso();assert.doesNotMatch(elementos.opcoesAcesso.innerHTML,/value="demo"/);
 s.radio={value:'tempo_2',dataset:{tempoId:'2',valorCents:'9980'}};await s.adquirirAgora();
 assert.deepEqual(JSON.parse(pedidos.at(-1).opts.body),{tempo_acesso_id:2,codigo_cupom:null,tipo_compra:'RENOVACAO',contratacao_id:7});
});
test('validação atrasada não reaplica cupom após troca',async()=>{
 const {s,elementos}=ambiente();let concluir;
 s.fetch=()=>new Promise(resolve=>concluir=()=>resolve({ok:true,json:async()=>({codigo_cupom:'AW265',percentual_desconto:12})}));
 s.radio={value:'tempo_1',dataset:{tempoId:'1',valorCents:'4990'}};elementos.codigo_cupom_desconto.value='AW265';
 const aplicacao=s.aplicarCupomCursoInfo();s.controleAvisoDemo();concluir();await aplicacao;
 assert.equal(vm.runInContext('cupomAplicadoCursoInfo',s),null);
});
test('cupom inválido não é aplicado',async()=>{
 const {s,elementos}=ambiente();s.fetch=async()=>({ok:false,status:400,text:async()=>'Cupom inválido'});
 s.radio={value:'tempo_1',dataset:{tempoId:'1',valorCents:'4990'}};elementos.codigo_cupom_desconto.value='XXXXX';
 await s.aplicarCupomCursoInfo();assert.equal(vm.runInContext('cupomAplicadoCursoInfo',s),null);assert.match(elementos.msgCupomDesconto.textContent,/inválido/);
});
test('compra normal usa mesmo cupom',async()=>{
 const {s,elementos,pedidos}=ambiente('?curso_id=1',false);s.radio={value:'tempo_1',dataset:{tempoId:'1',valorCents:'4990'}};
 s.document.getElementById('codigo_cupom_desconto').value='AW265';await s.aplicarCupomCursoInfo();await s.adquirirAgoraCursoInfo();
 assert.equal(JSON.parse(pedidos.at(-1).opts.body).codigo_cupom,'AW265');
});
test('mensagem do limite gratuito preservada',async()=>{
 const {s,elementos}=ambiente('?curso_id=1',false);s.radio={value:'demo',dataset:{}};
 s.fetch=async()=>({ok:false,status:409,text:async()=>JSON.stringify({detail:'Você já possui acesso gratuito a 3 cursos.'})});
 await s.adquirirAgoraCursoInfo();assert.match(elementos.msgCursoInfo.textContent,/3 cursos/);
});
test('navegação e confirmação de logout',()=>{
 const {s,store}=ambiente();s.voltarCheckout();assert.equal(s.window.location.href,'cursos.html');
 s.confirm=()=>false;s.sairComConfirmacao();assert.equal(store.get('access_token'),'token');
 s.confirm=()=>true;s.sairComConfirmacao();assert.equal(store.get('access_token'),undefined);assert.equal(s.window.location.href,'index.html');
 assert.match(html,/pagina_antes_inicio/);assert.match(html,/class="curso-header-acoes"/);assert.doesNotMatch(html,/🎓/);
 const normal=ambiente('?curso_id=1&origem=inicio');normal.s.voltarCheckout();assert.equal(normal.s.window.location.href,'index.html');
 const externo=ambiente('?curso_id=1&origem=https://externo.test');externo.s.voltarCheckout();assert.equal(externo.s.window.location.href,'curso-info.html?curso_id=1');
});
test('backend orienta para fluxo próprio de renovação',()=>{
 const {s}=ambiente();const erro=s.erroApiCompra(JSON.stringify({detail:{codigo:'USE_RENOVACAO',curso_id:1,contratacao_id:7,mensagem:'Renove'}}),409);
 assert.equal(s.tratarErroCompra(erro),true);assert.match(s.window.location.href,/renovacao=1&contratacao_id=7/);
});
