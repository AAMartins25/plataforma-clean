const assert = require('node:assert/strict');
const { test } = require('node:test');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = readFileSync(path.join(__dirname, '../admin-criar-curso-completo.js'), 'utf8');

function ambiente() {
  const elements = new Map(), calls = [], alerts = [];
  function element(id) {
    if (!elements.has(id)) {
      let html = '';
      const el = {
        value: '', textContent: '', style: {}, options: [], listeners: {},
        addEventListener(type, callback) { this.listeners[type] = callback; },
        appendChild(option) { this.options.push(option); }, scrollIntoView() {}
      };
      Object.defineProperty(el, 'innerHTML', {
        get: () => html,
        set(value) {
          html = value;
          el.options = [...value.matchAll(/<option value="([^"]*)">([^<]*)<\/option>/g)]
            .map(match => ({ value: match[1], text: match[2], textContent: match[2] }));
        }
      });
      Object.defineProperty(el, 'selectedIndex', { get: () => el.options.findIndex(o => String(o.value) === String(el.value)) });
      elements.set(id, el);
    }
    return elements.get(id);
  }
  const cursos = [{ id: 1, nome: 'Origem', ativo: true }, { id: 2, nome: 'Destino', ativo: true }];
  const ctx = {
    document: { getElementById: element, querySelector: element, createElement: () => {
      const option = { value: '', textContent: '' };
      Object.defineProperty(option, 'text', { get: () => option.textContent });
      return option;
    } },
    console: { log() {}, error() {} }, setTimeout() {},
    confirm: () => true, prompt: () => '2', alert: message => alerts.push(message),
    apiGetAuth: async url => {
      calls.push(['GET', url]);
      if (url === '/cursos') return cursos;
      if (url.endsWith('/disciplinas-proprias')) return [{ id: 26, nome: 'Direitos Humanos' }];
      if (url.endsWith('/config-publica')) return {};
      return [];
    },
    apiPostAuth: async (url, body) => {
      calls.push(['POST', url, JSON.parse(JSON.stringify(body))]);
      return { nova_disciplina_nome: 'Direitos Humanos', curso_destino_nome: 'Destino',
        novo_assunto_nome: 'Direitos Humanos', disciplina_destino_nome: 'Disciplina destino' };
    }
  };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(source, ctx);
  return { ctx, element, calls, alerts };
}

async function prepararAssunto(env) {
  await env.ctx.abrirCopiaAssunto(42, 'Direitos Humanos');
  env.element('cursoDestinoAssuntoSelect').value = '2';
  await env.element('cursoDestinoAssuntoSelect').listeners.change();
  env.element('disciplinaDestinoAssuntoSelect').value = '26';
}

test('copiar disciplina preserva método, rota, payload e mensagem de sucesso', async () => {
  const env = ambiente();
  await env.ctx.copiarDisciplinaParaOutroCurso(26, 'Direitos Humanos');
  assert.deepEqual(env.calls.find(call => call[0] === 'POST'),
    ['POST', '/admin/disciplinas/26/copiar', { curso_destino_id: 2 }]);
  assert.match(env.alerts[0], /Disciplina copiada com sucesso/);
});

test('copiar assunto preserva seletores, contrato e mensagem de sucesso', async () => {
  const env = ambiente();
  await prepararAssunto(env);
  await env.element('btnConfirmarCopiaAssunto').listeners.click();
  assert.deepEqual(env.calls.find(call => call[0] === 'POST'),
    ['POST', '/admin/assuntos/42/copiar', { disciplina_destino_id: 26 }]);
  assert.match(env.element('msgCopiarAssunto').textContent, /copiado com sucesso/);
});

test('copiar assunto mostra o motivo retornado pelo backend sem o JSON bruto', async () => {
  const env = ambiente();
  await prepararAssunto(env);
  env.ctx.apiPostAuth = async () => {
    throw new Error('POST /admin/assuntos/42/copiar -> 409\n{"detail":"A pasta possui mais de uma aula técnica."}');
  };
  await env.element('btnConfirmarCopiaAssunto').listeners.click();
  assert.equal(env.element('msgCopiarAssunto').textContent,
    'Erro ao copiar assunto: A pasta possui mais de uma aula técnica.');
});

test('cancelar confirmação não chama a rota de cópia', async () => {
  const env = ambiente();
  await prepararAssunto(env);
  env.ctx.confirm = () => false;
  await env.element('btnConfirmarCopiaAssunto').listeners.click();
  await env.ctx.copiarDisciplinaParaOutroCurso(26, 'Direitos Humanos');
  assert.equal(env.calls.filter(call => call[0] === 'POST').length, 0);
});
