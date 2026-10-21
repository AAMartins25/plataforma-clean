const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const page = fs.readFileSync(__dirname + '/sprint.html', 'utf8');
const script = page.match(/<script>\s*([\s\S]*?)<\/script>/)[1]
  .replace(/\s*carregarBateria\(\);\s*$/, '');
assert.match(page, /const titulo = nota \? "Fazer anotação" : "Enviar mensagem ao professor"/);
assert.match(page, /<h3>\$\{titulo\}<\/h3>/);
assert.match(page, /const labelBotao = nota \? "Salvar" : "Enviar"/);
assert.doesNotMatch(page, /Fazer anotação \/ enviar mensagem ao professor/);
assert.match(page, /Escreva sua anotação\.\.\./);
assert.match(page, /Escreva sua dúvida ou pergunta\.\.\./);
assert.match(page, /Promise\.allSettled\(tipos\.map\(carregarRegistroQuestao\)\)/);
assert.match(page, /rows\.map\(row => \[Number\(row\.questao_id\), row\]\)/);
assert.match(page, /Você já fez anotação nesta questão\. Caso deseje editá-la, entre em/);
assert.match(page, /Você já enviou mensagem ao prof a respeito desta questão\./);

const elements = new Map();
const ctx = {
  window: { location: { search: '?curso_id=1&demonstracao_id=8' } },
  URLSearchParams, Map, Promise, console,
  document: { getElementById: id => elements.get(id) || null },
  apiGetAuth: async path => path.startsWith('/me/minhas-anotacoes')
    ? [{ questao_id: 7, tentativa_id: 2 }]
    : [{ questao_id: 7, tentativa_id: 2 }],
  apiPostAuth: async (path, body) => { calls.push({ path, body }); return {}; },
  alert: () => {}, confirm: () => true,
};
const calls = [];
vm.createContext(ctx);
vm.runInContext(script, ctx);
vm.runInContext('bateriaId=4; tentativaAnotacaoId=9; questoes=[{id:7}];', ctx);

(async () => {
  const gets = [];
  ctx.apiGetAuth = async path => {
    gets.push(path);
    if (path.startsWith('/me/minhas-anotacoes')) return [{ questao_id: 7, tentativa_id: 2 }];
    return [{ questao_id: 7, tentativa_id: 3 }];
  };
  await ctx.recuperarAnotacoesTentativa();
  assert.equal(gets.length, 2, 'anotação e conversa são consultadas separadamente');
  assert.ok(gets[0].includes('demonstracao_id=8'));
  assert.ok(gets[1].includes('demonstracao_id=8'));
  assert.equal(vm.runInContext('cacheRegistrosQuestao.anotacao.has(7)', ctx), true, 'tentativa antiga não impede identificação da mesma questão');
  assert.equal(vm.runInContext('cacheRegistrosQuestao.mensagem.has(7)', ctx), true);

  const note = { value: 'Minha anotação' }, noteButton = { disabled: false };
  const message = { value: 'Minha dúvida' }, messageButton = { disabled: false };
  elements.set('anotacao_texto_8', note); elements.set('btn_salvar_anotacao_8', noteButton);
  elements.set('mensagem_texto_8', message); elements.set('btn_salvar_mensagem_8', messageButton);
  await ctx.salvarAnotacaoParaMim(8);
  assert.equal(calls[0].path, '/me/anotacoes-questoes');
  assert.equal(calls[0].body.tentativa_id, 9);
  await ctx.salvarEnviarProf(8);
  assert.equal(calls[1].path, '/me/mensagens-prof');
  assert.equal(calls[1].body.tentativa_id, 9);
  console.log('Sprint: seções independentes, lookup por questão/contexto, tentativas repetidas e gravações separadas: OK');
})().catch(err => { console.error(err); process.exitCode = 1; });
