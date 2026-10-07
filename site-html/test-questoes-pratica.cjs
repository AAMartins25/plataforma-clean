const fs = require('fs');
const vm = require('vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(__dirname + '/js/app.js', 'utf8');
const code = source.slice(source.indexOf('function contextoQuestoesPratica()'), source.indexOf('let questoesPraticaAdmin'));
const params = new URLSearchParams('curso_id=1&curso_nome=Curso&disciplina_id=1&disciplina_nome=Disciplina&assunto_id=1&assunto_nome=Assunto&demonstracao_id=1');
const elements = new Map();
function el(id) {
 if (!elements.has(id)) elements.set(id, {innerHTML:'',innerText:'',style:{},disabled:false,appendChild(){},focus(){}});
 return elements.get(id);
}
let response = 'E';
let questionType = 'CERTO_ERRADO';
let alternativeLetters = '';
let busyResolve;
let failResponse = false;
const calls = [];
const filters = {TODAS:{habilitado:true,quantidade:2},REVER:{habilitado:true,quantidade:1}};
const ctx = vm.createContext({URLSearchParams,Number,String,Math,console,
 qs:name=>params.get(name),escapeHtml:s=>String(s??'').replaceAll('<','&lt;'),
 confirm:()=>true,window:{location:{href:''}},setTimeout:fn=>fn(),
 document:{getElementById:el,createElement:()=>el('created'),querySelector:selector=>{
  if(selector.includes("resposta_aluno")) return {value:response};
  if(selector.includes("dificuldade_questao")) return {value:'DIFICIL'};
  if(selector.includes('button')) return el('responder');
  return null;
 },querySelectorAll:()=>[]},
 apiGetAuth:async path=>{calls.push({path}); return path.includes('filtros')?filters:[];},
 apiPostAuth:async(path,payload)=>{
  calls.push({path,payload});
  if(path.includes('proxima'))return {questao:{id:10,tipo:questionType,enunciado:'<Teste>',alternativas:[...alternativeLetters].map(letra=>({id:letra,letra,texto:letra}))},ids_questoes_sessao:[10,11],token_sessao:'proof',numero_questao:1};
  if(failResponse)throw new Error('Erro de conexão');
  if(busyResolve) await new Promise(resolve=>busyResolve=resolve);
  return {acertou:false,nao_soube:false,gabarito:'C',comentario:'Comentário do backend'};
 }});
vm.runInContext(code,ctx);
async function run(expression){return vm.runInContext(expression,ctx);}
(async()=>{
 assert.equal(await run('contextoQuestoesPraticaQuery()'),'?demonstracao_id=1');
 await run('pageQuestoesDisciplinas()');
 assert.ok(calls.at(-1).path.includes('/cursos/1/disciplinas-proprias?demonstracao_id=1'));
 await run('pageQuestoesAssuntos()');
 assert.ok(calls.at(-1).path.includes('/disciplinas-proprias/1/assuntos-proprios?demonstracao_id=1'));
 await run('pageQuestoesPratica()');
 const next=calls.find(c=>c.path.includes('/proxima'));
 assert.equal(next.payload.demonstracao_id,1);
 assert.ok(el('area_questao').innerHTML.includes('Rever esta questão'));
 assert.ok(el('area_questao').innerHTML.includes('&lt;Teste>'));
 assert.ok(!el('area_questao').innerHTML.includes('Gabarito:'));
 el('rever_questao').checked=true;
 await run('responderQuestaoPratica()');
 const answered=calls.find(c=>c.path.includes('/responder'));
 assert.equal(answered.payload.resposta_marcada,'E');
 assert.equal(answered.payload.token_sessao,'proof');
 assert.equal(answered.payload.rever,true);
 assert.ok(!('acertou' in answered.payload));
 assert.ok(!('nao_soube' in answered.payload));
 assert.ok(el('mensagem_questao').innerHTML.includes('Não foi desta vez'));
 assert.ok(el('mensagem_questao').innerHTML.includes('Comentário do backend'));
 assert.ok(calls.filter(c=>c.path.includes('filtros')).length>=2);
 const before=calls.length;
 await run('responderQuestaoPratica()');
 assert.equal(calls.length,before,'prevent resubmission after success');
 await run('continuarDepoisQuestoesPratica()');
 assert.ok(ctx.window.location.href.includes('questoes-assuntos.html'));
 assert.ok(ctx.window.location.href.includes('demonstracao_id=1'));
 for(const letras of ['ABCD','ABCDE']) {
  questionType='MULTIPLA'; alternativeLetters=letras;
  await run('pageQuestoesPratica()');
  for(const letra of letras) assert.ok(el('area_questao').innerHTML.includes(`value="${letra}"`));
  assert.ok(el('area_questao').innerHTML.includes('Rever esta questão'));
 }
 questionType='CERTO_ERRADO'; alternativeLetters='';
 await run('pageQuestoesPratica()');
 busyResolve=()=>{};
 const pending=run('responderQuestaoPratica()');
 const requestCount=calls.filter(c=>c.path.includes('/responder')).length;
 await run('responderQuestaoPratica()');
 assert.equal(calls.filter(c=>c.path.includes('/responder')).length,requestCount);
 busyResolve(); await pending; busyResolve=null;
 await run('pageQuestoesPratica()');
 failResponse=true;
 await run('responderQuestaoPratica()');
 assert.ok(el('mensagem_questao').innerHTML.includes('Erro de conexão'));
 assert.equal(await run('questaoPraticaAtual.id'),10);
 assert.equal(await run('tokenSessaoQuestaoPratica'),'proof');
 assert.equal(el('responder').disabled,false);
 assert.ok(!calls.some(c=>c.path.includes('baterias')));
 assert.ok(!code.includes('sprint.html'));
 console.log('Frontend: contexto, renderização, payload, feedback do servidor, filtros, retorno, reenvio e erro preservando seleção: OK');
})().catch(err=>{console.error(err);process.exitCode=1});
