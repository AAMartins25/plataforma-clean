const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(__dirname + '/js/app.js', 'utf8');
const pendente = () => {
  let resolve, reject;
  const promise = new Promise((ok, erro) => { resolve = ok; reject = erro; });
  return {promise, resolve, reject};
};
const proximoTurno = () => new Promise(resolve => setImmediate(resolve));
const acesso = [{curso_id: 1, nome_curso: 'Curso do aluno A', contratacoes: [], demonstracoes: []}];
const expirado = [{curso_id: 2, nome_curso: 'Curso expirado', ativo: false, contratacao_id: 7}];
function ambiente() {
  const elementos = {}, eventos = {}, documento = {}, chamadas = [];
  let token = 'aluno-A', generation = 'A';
  class Elemento {
    style = {}; attributes = {}; children = []; html = '';
    set innerHTML(value) { this.html = value; this.children = []; }
    get innerHTML() { return this.html; }
    appendChild(child) { this.children.push(child); }
    setAttribute(key, value) { this.attributes[key] = value; }
    scrollIntoView() {}
  }
  const Sessao = {snapshot: () => ({token, generation}), mesma: origem => origem.token === token && origem.generation === generation};
  const s = {console, Date, URLSearchParams, setTimeout, Sessao,
    localStorage: {getItem: key => key === 'access_token' ? token : null, setItem() {}},
    window: {Sessao, location: {}, addEventListener: (event, fn) => { eventos[event] = fn; }},
    document: {body: {dataset: {}, getAttribute: () => 'cursos'}, addEventListener: (event, fn) => { documento[event] = fn; },
      getElementById: id => elementos[id] ??= new Elemento(), createElement: () => new Elemento()}};
  vm.createContext(s); vm.runInContext(source, s);
  const ativos = pendente(), historico = pendente(), pagamento = pendente();
  s.apiGetAuth = url => { chamadas.push(url); return url === '/me/cursos' ? ativos.promise : historico.promise; };
  s.tentarConfirmarPagamentoAoVoltar = () => pagamento.promise;
  return {s, elementos, eventos, documento, chamadas, ativos, historico, pagamento,
    trocar: (novoToken = 'aluno-B') => { token = novoToken; generation = 'B'; }};
}
test('HTML mostra Carregando antes mesmo de executar app.js', () => {
  assert.match(fs.readFileSync(__dirname + '/cursos.html', 'utf8'), /id="lista"[^>]*aria-busy="true"[^>]*><p role="status">Carregando\.\.\.<\/p>/);
});
test('confirma pagamento antes das duas consultas, sem requisições extras', async () => {
  const a = ambiente(); const fim = a.s.pageCursos();
  assert.match(a.elementos.lista.innerHTML, /Carregando/);
  assert.deepEqual(a.chamadas, []);
  a.pagamento.resolve(); await proximoTurno();
  assert.deepEqual(a.chamadas, ['/me/cursos', '/me/desempenho/contextos-expirados']);
  a.ativos.resolve(acesso); await proximoTurno();
  assert.equal(a.elementos.lista.children.length, 1);
  assert.equal(a.elementos.lista.attributes['aria-busy'], 'false');
  assert.match(a.elementos.lista_expirados.innerHTML, /Carregando/);
  a.historico.resolve(expirado); await fim;
  assert.match(a.elementos.lista_expirados.innerHTML, /contratacao_id=7/);
  assert.equal(a.elementos.lista_expirados.style.display, 'none');
});
test('histórico pode aparecer antes da consulta ativa, sem simular ausência', async () => {
  const a = ambiente(); a.pagamento.resolve(); const fim = a.s.pageCursos();
  a.historico.resolve(expirado); await proximoTurno();
  assert.match(a.elementos.lista.innerHTML, /Carregando/);
  assert.match(a.elementos.lista_expirados.innerHTML, /Curso expirado/);
  a.ativos.resolve([]); await fim;
  assert.match(a.elementos.lista.innerHTML, /Você não possui curso ativo/);
});
for (const falha of ['ativos', 'historico']) test(`falha em ${falha} não apaga a outra lista nem simula ausência`, async () => {
  const a = ambiente(); a.pagamento.resolve(); const fim = a.s.pageCursos();
  a[falha].reject(new Error('HTTP 503'));
  if (falha === 'ativos') a.historico.resolve(expirado); else a.ativos.resolve(acesso);
  await fim;
  const lista = a.elementos[falha === 'ativos' ? 'lista' : 'lista_expirados'];
  assert.match(lista.innerHTML, /role="alert"/);
  assert.doesNotMatch(lista.innerHTML, /Você não possui/);
  assert.equal(lista.attributes['aria-busy'], 'false');
  if (falha === 'ativos') assert.match(a.elementos.lista_expirados.innerHTML, /Curso expirado/);
  else assert.equal(a.elementos.lista.children.length, 1);
});
test('ausência real só é exibida depois da resposta vazia', async () => {
  const a = ambiente(); a.pagamento.resolve(); const fim = a.s.pageCursos();
  assert.doesNotMatch(a.elementos.lista.innerHTML, /Você não possui/);
  a.ativos.resolve([]); a.historico.resolve([]); await fim;
  assert.match(a.elementos.lista.innerHTML, /Você não possui curso ativo/);
  assert.equal(a.elementos.card_cursos_expirados.style.display, 'none');
});
test('troca de sessão durante confirmação impede consultas com a nova identidade', async () => {
  const a = ambiente(); const fim = a.s.pageCursos(); a.trocar(); a.pagamento.resolve(); await fim;
  assert.deepEqual(a.chamadas, []);
  assert.match(a.elementos.lista.innerHTML, /Sua sessão mudou/);
});
test('respostas tardias da sessão anterior são descartadas, incluindo erro', async () => {
  const a = ambiente(); a.pagamento.resolve(); const fim = a.s.pageCursos(); await proximoTurno();
  a.trocar(); a.ativos.resolve(acesso); a.historico.reject(new Error('SessaoAlteradaError')); await fim;
  assert.equal(a.elementos.lista.children.length, 0);
  assert.match(a.elementos.lista.innerHTML, /Sua sessão mudou/);
  assert.equal(a.elementos.card_cursos_expirados.style.display, 'none');
});
for (const evento of ['storage', 'pageshow']) test(`${evento} remove cursos já exibidos ao mudar a sessão`, async () => {
  const a = ambiente(); a.pagamento.resolve(); const fim = a.s.pageCursos(); a.ativos.resolve(acesso); a.historico.resolve(expirado); await fim;
  a.trocar(); a.eventos[evento]({key: 'auth_generation'});
  assert.equal(a.elementos.lista.children.length, 0);
  assert.equal(a.elementos.lista_expirados.innerHTML, '');
  assert.match(a.elementos.lista.innerHTML, /Sua sessão mudou/);
});
test('inicialização ocorre no DOMContentLoaded uma única vez, sem aguardar load', async () => {
  const a = ambiente(); let inicios = 0;
  a.s.pageCursos = () => { inicios++; }; a.s.exibirNomeUsuarioLogado = () => {}; a.s.bindBotaoEntrarEEstudarSeExistir = () => {};
  a.documento.DOMContentLoaded(); assert.equal(inicios, 1);
  await a.s.window.onload(); assert.equal(inicios, 1);
});

test('identificação e botão de áreas compartilham /me, sem reutilizar perfil entre sessões', async () => {
  const a = ambiente(); const primeira = pendente(), segunda = pendente(); let consultas = 0;
  a.s.apiGetAuth = path => { assert.equal(path, '/me'); consultas++; return consultas === 1 ? primeira.promise : segunda.promise; };
  a.s.document.body.dataset.page = 'cursos';
  const identificacao = a.s.getMeSafe(), areas = a.s.obterPerfilMeusCursos();
  assert.equal(consultas, 1);
  primeira.resolve({nome: 'Aluno A', is_aluno: true, is_admin: true});
  assert.equal((await identificacao).nome, 'Aluno A'); assert.equal((await areas).is_admin, true);
  a.trocar(); const novo = a.s.obterPerfilMeusCursos(); assert.equal(consultas, 2);
  segunda.resolve({nome: 'Aluno B', is_aluno: true}); assert.equal((await novo).nome, 'Aluno B');
});
test('perfil tardio de outra sessão não é entregue ao cabeçalho', async () => {
  const a = ambiente(), perfil = pendente(); a.s.apiGetAuth = () => perfil.promise;
  const consulta = a.s.obterPerfilMeusCursos(); a.trocar(); perfil.resolve({nome: 'Aluno A'});
  await assert.rejects(consulta, {name: 'SessaoAlteradaError'});
});

test('sem autenticação redireciona ao login sem consultar cursos', async () => {
  const a = ambiente(); a.trocar(null); await a.s.pageCursos();
  assert.equal(a.s.window.location.href, 'login.html'); assert.deepEqual(a.chamadas, []);
});
