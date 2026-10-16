const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const app = fs.readFileSync(__dirname + '/js/app.js', 'utf8');
const sessao = fs.readFileSync(__dirname + '/js/sessao.js', 'utf8');

function ambiente(admin = false) {
  const scripts = [], calls = [], store = new Map([['access_token', 'SIMULADO']]);
  const s = {
    URL, URLSearchParams, Headers, Response, TextEncoder, crypto: require('node:crypto').webcrypto,
    console: {warn() {}, log() {}},
    localStorage: {getItem: k => store.get(k) ?? null, setItem: (k,v) => store.set(k,String(v)), removeItem: k => store.delete(k)},
    document: {
      currentScript: {src: 'https://frontend.example.invalid/js/app.js'}, scripts,
      body: {dataset: {}}, getElementById() {return null;}, addEventListener() {}, querySelectorAll() {return [];},
      createElement() {return {};}, head: {appendChild: el => scripts.push(el)}
    },
    location: {pathname: admin ? '/admin/index.html' : '/cursos.html'}, addEventListener() {},
    fetch: async (url, options) => {calls.push({url, options}); return Response.json({nome: 'Ana Silva'});}
  };
  s.window = s; vm.createContext(s); vm.runInContext(app, s);
  return {s, scripts, calls, store, inicializar() {vm.runInContext(sessao, s); scripts[0].onload();}};
}

for (const admin of [false, true]) test(`HTML antigo ${admin ? 'admin' : 'aluno'}: requisição aguarda dependência real`, async () => {
  const e = ambiente(admin), pending = e.s.apiGetAuth('/me');
  assert.equal(e.calls.length, 0);
  assert.equal(e.scripts[0].src, 'https://frontend.example.invalid/js/sessao.js');
  e.inicializar(); await pending;
  assert.equal(e.calls.length, 1);
  assert.equal(new Headers(e.calls[0].options.headers).get('Authorization'), 'Bearer SIMULADO');
  assert.equal(e.scripts[1].src, 'https://frontend.example.invalid/js/cabecalho.js');
});

test('consumidores simultâneos compartilham uma única carga', async () => {
  const e = ambiente();
  const a = e.s.carregarSessao(), b = e.s.carregarSessao();
  assert.equal(a, b); assert.equal(e.scripts.length, 1);
  e.inicializar(); assert.equal(await a, e.s.Sessao); await b;
  const current = e.s.Sessao; await e.s.carregarSessao();
  assert.equal(e.s.Sessao, current); assert.equal(e.scripts.length, 2);
});

test('cabeçalho já declarado não é carregado duas vezes', async () => {
  const e = ambiente(); e.scripts.push({src: 'https://frontend.example.invalid/js/cabecalho.js'});
  const pending = e.s.carregarSessao();
  vm.runInContext(sessao, e.s); e.scripts[1].onload(); await pending;
  assert.equal(e.scripts.length, 2);
});

test('sessão já carregada mantém a instância, cache e geração', async () => {
  const e = ambiente(); vm.runInContext(sessao, e.s);
  e.store.set('auth_generation', 'GERACAO'); e.store.set('me_cache', 'CACHE');
  const current = e.s.Sessao;
  assert.equal(await e.s.carregarSessao(), current);
  assert.equal(e.scripts.length, 0); assert.equal(e.store.get('me_cache'), 'CACHE');
  assert.equal(e.store.get('auth_generation'), 'GERACAO');
});

for (const mode of ['rede', 'script sem exportação']) test(mode + ': falha explícita, sem requisição protegida ou perda de token', async () => {
  const e = ambiente(), pending = e.s.apiGetAuth('/me');
  if (mode === 'rede') e.scripts[0].onerror(); else e.scripts[0].onload();
  await assert.rejects(pending, /Não foi possível/);
  assert.equal(e.calls.length, 0); assert.equal(e.store.get('access_token'), 'SIMULADO');
});

test('logout durante carga não permite usar o token removido', async () => {
  const e = ambiente(), loading = e.s.carregarSessao();
  const logout = e.s.logout(); e.inicializar(); await loading; await logout;
  assert.equal(e.store.has('access_token'), false);
  await assert.rejects(e.s.apiGetAuth('/me'), /não está logado/);
  assert.equal(e.calls.length, 0); assert.equal(e.s.location.href, 'index.html');
});

for (const action of ['logout', 'clearToken', 'setToken']) test(action + ': espera pelo script não altera sessão posterior de outra aba', async () => {
  const e = ambiente();
  const pending = e.s[action]('TOKEN_ANTIGO');
  e.store.set('access_token', 'NOVA'); e.store.set('auth_generation', 'GERACAO_NOVA');
  e.inicializar(); await pending;
  assert.equal(e.store.get('access_token'), 'NOVA');
  assert.equal(e.store.get('auth_generation'), 'GERACAO_NOVA');
  assert.equal(e.s.location.href, undefined);
});
