const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const page = fs.readFileSync(__dirname + '/mensagens-prof.html', 'utf8');
const script = page.match(/<script>\s*([\s\S]*?)<\/script>/)[1]
  .replace(/document\.getElementById\("anoAtual"\)[\s\S]*?carregarMensagens\(\);\s*$/, '');
const admin = fs.readFileSync(__dirname + '/admin/admin-mensagens-questoes.html', 'utf8');
assert.match(page, /Reformular mensagem ao prof/);
assert.match(page, /Ao enviar esta nova mensagem, a conversa anterior será apagada\. Copie trechos que considerar importantes da conversa atual e cole na nova mensagem a ser enviada ao professor\./);
assert.match(page, /Confirmar e enviar/);
assert.match(page, />Cancelar<\/button>/);
assert.match(page, /\/reformular`/);
assert.match(page, /estado_conversa: p\.estado/);
assert.match(page, /operacao_id: p\.operacaoId/);
assert.match(admin, /Esta conversa foi substituída ou atualizada\. A lista foi atualizada; confira a conversa atual antes de responder\./);
assert.match(admin, /erro\.status = res\.status/);

const ids = new Map();
ids.set('titulo_curso_mensagens_prof', { innerText: '' });
const ctx = {
  URLSearchParams, Map, console,
  window: { location: { search: '?curso_id=1&demonstracao_id=8' }, crypto: { randomUUID: () => '123e4567-e89b-42d3-a456-426614174000' } },
  location: { search: '?curso_id=1&demonstracao_id=8' },
  document: { getElementById: id => ids.get(id) || null },
  alert: () => {}, confirm: () => true,
};
vm.createContext(ctx);
vm.runInContext(script, ctx);
vm.runInContext("conversas=[{conversa_id:4,estado_conversa:'" + 'a'.repeat(64) + "',mensagens:[]}];", ctx);
let writes = 0, loads = 0, failOnce = true;
ctx.renderizarConversas = () => {};
vm.runInContext('carregarMensagens = async function() {}', ctx);
ctx.apiPost = async (path, body) => {
  writes++;
  assert.equal(vm.runInContext(`contextoMensagens(${JSON.stringify(path)})`, ctx), '/me/mensagens-prof/4/reformular?curso_id=1&demonstracao_id=8');
  assert.equal(body.confirmado, true);
  if (failOnce) { failOnce = false; throw Object.assign(new Error('timeout'), { status: 503 }); }
  return { conversa_id: 5 };
};

(async () => {
  ctx.abrirReformulacao(4);
  assert.match(ctx.montarAreaReformulacao(vm.runInContext('conversas[0]', ctx)), /a conversa anterior será apagada/);
  const editor = { value: 'Nova dúvida', focus() {} };
  ids.set('reformulacao_texto_4', editor);
  ctx.cancelarReformulacao(4);
  assert.equal(writes, 0, 'cancelar não faz escrita');

  ctx.abrirReformulacao(4);
  ids.set('reformulacao_texto_4', editor);
  await ctx.confirmarReformulacao(4);
  assert.equal(writes, 1);
  const pending = vm.runInContext('reformulacoesPendentes.get(4)', ctx);
  assert.equal(pending.fase, 'incerta', 'falha/timeout mantém operação e rascunho para retry');
  const op = pending.operacaoId;
  ids.set('reformulacao_texto_4', { value: 'Nova dúvida' });
  await ctx.confirmarReformulacao(4);
  assert.equal(writes, 2);
  assert.equal(vm.runInContext('reformulacoesPendentes.has(4)', ctx), false);
  assert.equal(op, '123e4567-e89b-42d3-a456-426614174000');
  assert.equal(ctx.contextoMensagens('/me/mensagens-prof/4/reformular'), '/me/mensagens-prof/4/reformular?curso_id=1&demonstracao_id=8');
  console.log('Mensagens ao professor: aviso, confirmação/cancelamento, idempotência de retry e atualização administrativa: OK');
})().catch(err => { console.error(err); process.exitCode = 1; });
