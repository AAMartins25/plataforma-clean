const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(__dirname + '/js/app.js', 'utf8');

function cenario(pagina) {
  const indicadores = new Map();
  const lista = {
    children: [], isConnected: true, innerHTML: '',
    appendChild(elemento) {
      this.children.push(elemento);
      const id = Number(elemento.innerHTML.match(/data-progresso-id="(\d+)"/)[1]);
      const barra = {style: {width: '0%'}};
      const texto = {textContent: '…', classList: {toggle() {}}};
      indicadores.set(id, {barra, texto, removeAttribute() {},
        querySelector(seletor) { return seletor === '[data-progresso-barra]' ? barra : texto; }});
    },
    querySelector(seletor) {
      return indicadores.get(Number(seletor.match(/\d+/)[0]));
    },
    querySelectorAll() { return []; }
  };
  const elementos = {lista};
  const chamadas = [];
  let concluir;
  const progresso = new Promise(resolve => { concluir = resolve; });
  const url = pagina === 'disciplinas'
    ? '?curso_id=1&curso_nome=Curso&contratacao_id=7'
    : '?curso_id=1&disciplina_id=2&disciplina_nome=Disciplina&curso_nome=Curso&contratacao_id=7';
  const sandbox = {
    console: {log() {}, warn() {}, error() {}}, URLSearchParams, encodeURIComponent,
    window: {location: {search: url}}, location: {pathname: '/site-html/' + pagina + '.html'},
    Sessao: {snapshot: () => 'sessao', mesma: valor => valor === 'sessao'},
    document: {
      currentScript: {src: 'https://example.test/js/app.js'},
      body: {getAttribute: () => pagina}, addEventListener() {},
      getElementById(id) { return elementos[id] ||= {innerText: ''}; },
      createElement() { return {innerHTML: '', classList: {add() {}}}; }
    }
  };
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  const itens = pagina === 'disciplinas'
    ? [{id: 2, nome: 'Disciplina', bloqueada: false}]
    : [{id: 3, nome: 'Assunto'}];
  sandbox.apiGetAuth = async caminho => {
    chamadas.push(caminho);
    if (caminho.includes('/pasta-teoria')) return {id: 5};
    return caminho.includes('progresso-') ? progresso : itens;
  };
  return {sandbox, lista, indicadores, chamadas, concluir};
}

for (const pagina of ['disciplinas', 'assuntos']) {
  test(`${pagina}: lista e navegação aparecem antes do progresso`, async () => {
    const {sandbox, lista, indicadores, chamadas, concluir} = cenario(pagina);
    await (pagina === 'disciplinas' ? sandbox.pageDisciplinas() : sandbox.pageAssuntos());
    assert.equal(lista.children.length, 1);
    assert.match(lista.children[0].innerHTML, /Abrir/);
    if (pagina === 'disciplinas') {
      assert.match(lista.children[0].innerHTML, /assuntos\.html\?curso_id=/);
    } else {
      await sandbox.abrirAssuntoDireto(3, 'Assunto', 'Disciplina');
      assert.match(sandbox.window.location.href, /teoria\.html\?pasta_id=5/);
    }
    assert.equal(chamadas.length, pagina === 'disciplinas' ? 2 : 3);
    const id = pagina === 'disciplinas' ? 2 : 3;
    assert.equal(indicadores.get(id).texto.textContent, '…');
    concluir({percentuais: [{[pagina === 'disciplinas' ? 'disciplina_id' : 'assunto_id']: id,
                            percentual: 50}]});
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(indicadores.get(id).texto.textContent, '50%');
    assert.equal(indicadores.get(id).barra.style.width, '50%');
  });
}
