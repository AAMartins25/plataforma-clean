const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const codigo=fs.readFileSync(__dirname+'/js/admin-contestacoes.js','utf8');
const flush=()=>new Promise(r=>setImmediate(r));
const base={id:1,pagamento_id:5,curso:'Curso',aluno:'Aluno',valor_cents:4990,status:'ABERTA',situacao_acesso:'AGUARDANDO_DEVOLUCAO'};
async function tela(casos=[base],admin=true,pendencias=[]){
 const handlers={}, chamadas=[], alertas=[];
 const lista={innerHTML:'',querySelectorAll:()=>[],addEventListener:(tipo,fn)=>{handlers[tipo]=fn;}};
 const ctx={document:{getElementById:()=>lista},confirm:()=>true,alert:m=>alertas.push(m),
 apiGetAuth:async url=>{chamadas.push(['GET',url]);return url==='/me'?{is_admin:admin}:{contestacoes:casos,pendencias,tem_proxima:false};},
 apiPostAuth:async(url,payload)=>{chamadas.push(['POST',url,payload]);return {};}};
 vm.runInNewContext(codigo,ctx);await flush();return {ctx,lista,handlers,chamadas,alertas};
}
function submit(t){return t.handlers.submit({preventDefault(){},target:{dataset:{confirmar:'1'},elements:{referencia:{value:' extrato '},conferido:{checked:true}}}});}
function click(t,disabled=false){return t.handlers.click({target:{closest:()=>({dataset:{bloquear:'1'},disabled})}});}
test('botão único imediatamente após reembolsos',()=>{
 const html=fs.readFileSync(__dirname+'/admin/index.html','utf8');
 assert.equal((html.match(/href="contestacoes.html"/g)||[]).length,1);
 assert.match(html,/Reembolsos Solicitados\s*<\/a>\s*<a[^>]*href="contestacoes.html"/);
});
test('não administrador não consulta casos',async()=>{
 const t=await tela([],false);assert.equal(t.chamadas.length,1);assert.match(t.lista.innerHTML,/restrito/);
 submit(t);await flush();assert.equal(t.chamadas.length,1);
});
test('escapa dados e não oferece bloqueio antes de devolução',async()=>{
 const t=await tela([{...base,aluno:'<img onerror="1">'}]);
 assert.doesNotMatch(t.lista.innerHTML,/<img/);assert.match(t.lista.innerHTML,/&lt;img/);
 assert.doesNotMatch(t.lista.innerHTML,/data-bloquear/);assert.match(t.lista.innerHTML,/não bloqueia/);
});
test('confirmação financeira gera apenas um POST sem bloqueio automático',async()=>{
 const t=await tela();submit(t);await flush();
 const posts=t.chamadas.filter(c=>c[0]==='POST');assert.equal(posts.length,1);
 assert.match(posts[0][1],/confirmar-devolucao$/);assert.equal(posts[0][2].referencia_devolucao,'extrato');
});
test('caso ambíguo mantém bloqueio desabilitado',async()=>{
 const t=await tela([{...base,devolucao_confirmada_em:'2026-10-19T12:00:00',situacao_acesso:'CONFERENCIA_NECESSARIA'}]);
 assert.match(t.lista.innerHTML,/CONFERENCIA_NECESSARIA/);assert.match(t.lista.innerHTML,/data-bloquear="1"\s+disabled/);
 await click(t,true);assert.equal(t.chamadas.filter(c=>c[0]==='POST').length,0);
});
test('bloqueio requer confirmação explícita',async()=>{
 const t=await tela([{...base,devolucao_confirmada_em:'2026-10-19',situacao_acesso:'BLOQUEIO_DISPONIVEL'}]);
 t.ctx.confirm=()=>false;await click(t);assert.equal(t.chamadas.filter(c=>c[0]==='POST').length,0);
 t.ctx.confirm=()=>true;await click(t);await flush();assert.match(t.chamadas.find(c=>c[0]==='POST')[1],/confirmacao_bloqueio=true/);
});
test('cliques duplicados não repetem operação e falha só relê',async()=>{
 const t=await tela();let rejeitar;
 t.ctx.apiPostAuth=(url,payload)=>{t.chamadas.push(['POST',url,payload]);return new Promise((_,reject)=>{rejeitar=reject;});};
 submit(t);submit(t);assert.equal(t.chamadas.filter(c=>c[0]==='POST').length,1);
 rejeitar(new Error('comunicação perdida'));await flush();await flush();
 assert.equal(t.chamadas.filter(c=>c[0]==='POST').length,1);
 assert.equal(t.chamadas.filter(c=>c[1].startsWith('/admin/contestacoes?')).length,2);
 assert.match(t.alertas[0],/Resultado não confirmado/);
});
test('falha de releitura remove ações até recarregar',async()=>{
 const t=await tela();t.ctx.apiGetAuth=async()=>{throw Error('offline');};
 submit(t);await flush();assert.match(t.lista.innerHTML,/Consulta indisponível/);assert.doesNotMatch(t.lista.innerHTML,/<button/);
});

test('pendência sem compra identificada é visível, escapada e sem ações financeiras',async()=>{
 const t=await tela([],true,[{notificacao_id:10,caso_mp:'999',pagamentos_mp:['101','102'],motivo:'<script>erro</script>',tentativas:2}]);
 assert.match(t.lista.innerHTML,/Pendências de recebimento/);
 assert.match(t.lista.innerHTML,/CONFERENCIA_NECESSARIA/);
 assert.match(t.lista.innerHTML,/101, 102/);
 assert.match(t.lista.innerHTML,/&lt;script&gt;/);
 assert.doesNotMatch(t.lista.innerHTML,/<script>|data-bloquear|data-confirmar/);
 assert.equal(t.chamadas.filter(c=>c[0]==='POST').length,0);
});
