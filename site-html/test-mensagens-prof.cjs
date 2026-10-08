const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const page=fs.readFileSync(__dirname+'/mensagens-prof.html','utf8');
const source=page.match(/function contextoMensagens\(path\) \{[\s\S]*?\n\}/)[0];
for(const query of ['curso_id=1&demonstracao_id=1','curso_id=1&contratacao_id=2']){
 const ctx={URLSearchParams,location:{search:'?'+query}};vm.createContext(ctx);vm.runInContext(source,ctx);
 assert.equal(ctx.contextoMensagens('/me/mensagens-prof/3/responder'),'/me/mensagens-prof/3/responder?'+query);
}
assert.match(page,/apiPost\(`\/me\/mensagens-prof\/\$\{conversaId\}\/responder`/);
const sprint=fs.readFileSync(__dirname+'/sprint.html','utf8');
const send=sprint.slice(sprint.indexOf('async function salvarEnviarProf'));
assert.match(send,/tentativa_id: tentativaAnotacaoId/);
assert.match(sprint,/conversas\.filter\(c => Number\(c\.tentativa_id\)/);
const admin=fs.readFileSync(__dirname+'/admin/admin-mensagens-questoes.html','utf8');
assert.match(admin,/conversa\.tipo === "CERTO_ERRADO"/);
console.log('Mensagens frontend: contexto, continuação por ID, tentativa e tipo da questão: OK');
