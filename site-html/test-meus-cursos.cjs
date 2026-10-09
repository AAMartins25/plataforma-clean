const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/js/app.js','utf8');
const pago=(id=7)=>({id,origem:'PAGAMENTO',data_fim:'2027-02-09T00:00:00',renovacao_disponivel:true});
const demo={id:2,data_fim:'2026-10-20T00:00:00',aquisicao_disponivel:true};
const curso=(contratacoes=[],demonstracoes=[demo],id=1)=>({curso_id:id,nome_curso:'Curso '+id,contratacoes,demonstracoes});
async function renderizar(acessos){
 const elementos={};const erros=[];
 const criar=()=>({style:{},innerHTML:'',children:[],appendChild(c){this.children.push(c)}});
 const s={console:{log(){},error(){}},Date,URLSearchParams,localStorage:{getItem:()=> 'token'},window:{location:{}},document:{body:{dataset:{}},addEventListener(){},getElementById:id=>elementos[id]??=criar(),createElement:criar}};
 vm.createContext(s);vm.runInContext(source,s);
 s.apiGetAuth=async url=>url==='/me/cursos'?acessos:[];s.tentarConfirmarPagamentoAoVoltar=async()=>{};s.showError=(_,err)=>erros.push(err);
 const original=JSON.stringify(acessos);await s.pageCursos();assert.deepEqual(erros,[]);assert.equal(JSON.stringify(acessos),original);
 return elementos.lista.children.map(c=>c.innerHTML);
}
test('somente demonstração mantém aquisição e contexto gratuito',async()=>{const cards=await renderizar([curso()]);assert.equal(cards.length,1);assert.match(cards[0],/demonstracao_id=2/);assert.match(cards[0],/ADQUIRIR/)});
test('somente contratação mantém vencimento e contexto pago',async()=>{const cards=await renderizar([curso([pago()],[])]);assert.equal(cards.length,1);assert.match(cards[0],/contratacao_id=7/);assert.match(cards[0],/09\/02\/2027/)});
test('pago vigente oculta demonstração e Abrir usa contratação',async()=>{const cards=await renderizar([curso([pago()])]);assert.equal(cards.length,1);assert.match(cards[0],/href="curso.html[^"\n]*contratacao_id=7/);assert.doesNotMatch(cards[0],/demonstracao_id|ADQUIRIR/)});
for(const status of ['pending','rejected','approved'])test('pagamento '+status+' sem liberação mantém demonstração',async()=>{const c=curso();c.pagamento_status=status;assert.match((await renderizar([c]))[0],/demonstracao_id=2/)});
test('após liberação a próxima listagem prioriza contratação',async()=>{const c=curso();assert.match((await renderizar([c]))[0],/demonstracao_id/);c.contratacoes=[pago()];assert.doesNotMatch((await renderizar([c]))[0],/demonstracao_id/)});
test('expiração da demonstração não interfere na contratação',async()=>{assert.deepEqual(await renderizar([curso([pago()])]),await renderizar([curso([pago()],[])]))});
test('cursos diferentes permanecem independentes',async()=>{const cards=await renderizar([curso([pago()]),curso([], [demo],2)]);assert.equal(cards.length,2);assert.match(cards[1],/curso_id=2/);assert.match(cards[1],/demonstracao_id/)});
test('múltiplos contratos e renovação permanecem',async()=>{const cards=await renderizar([curso([pago(7),pago(8)])]);assert.equal(cards.length,2);assert.match(cards[0],/RENOVAR/);assert.match(cards[1],/renovacao=1&contratacao_id=8/)});
test('concessão ADMIN mantém comportamento e demonstração',async()=>{const cards=await renderizar([curso([{...pago(),origem:'ADMIN'}])]);assert.equal(cards.length,2);assert.match(cards[1],/demonstracao_id/)});
