const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(__dirname + '/revisoes-programadas.html', 'utf8')
  .match(/<script>([\s\S]*?)<\/script>/)[1];

for (const [query, expected] of [
  ['curso_id=1&curso_nome=Direito&contratacao_id=10', 'Direito'],
  ['curso_id=2&curso_nome=Outro+curso&demonstracao_id=20', 'Outro curso'],
  ['curso_id=2&contratacao_id=30', 'Curso'],
  ['curso_nome=Curso+sem+identificador', ''],
  ['curso_id=0&curso_nome=Curso+inválido', ''],
  ['curso_id=3&curso_nome=%3Cb%3ECurso%3C%2Fb%3E&contratacao_id=40', '<b>Curso</b>']
]) {
  test('nome imediato com consultas pendentes: ' + query, () => {
    const title = {textContent: ''}, calls = [], storageReads = [];
    const sandbox = {
      URLSearchParams, console, location: {search: '?' + query},
      document: {getElementById: () => title},
      localStorage: {getItem(key) { storageReads.push(key); return 'token'; }},
      Sessao: {fetch(url) { calls.push(url); return new Promise(() => {}); }}
    };
    vm.runInNewContext(source, sandbox);
    assert.equal(title.textContent, expected);
    assert.deepEqual(storageReads, ['access_token']);
    const context = new URLSearchParams();
    const params = new URLSearchParams(query);
    for (const key of ['contratacao_id', 'demonstracao_id']) {
      if (params.get(key)) context.set(key, params.get(key));
    }
    assert.deepEqual(calls, ['https://plataforma-quality-backend.onrender.com/me/revisoes?' + context]);
  });
}
