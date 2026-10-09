// DOM e API simulados: testa o script real sem rede nem escrita de conteúdo.
const assert = require('node:assert/strict');
const { test } = require('node:test');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const script = readFileSync(path.join(__dirname, '../admin-criar-curso-completo.js'), 'utf8');

function ambiente() {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, {
      value: '', innerHTML: '', textContent: '', style: {},
      addEventListener() {}, scrollIntoView() {}, insertAdjacentHTML() {}
    });
    return elements.get(id);
  };
  const calls = [], alerts = [], questions = [];
  const ctx = {
    document: { getElementById: element, querySelector: element },
    console: { log() {}, error() {} }, setTimeout() {},
    confirm: () => true, prompt: () => 'Novo título', alert: message => alerts.push(message),
    apiGetAuth: async url => {
      calls.push(['GET', url]);
      if (url.endsWith('/questoes')) return questions;
      if (url.endsWith('/baterias')) return [{ id: 1, titulo: 'Bateria', ordem: 4, status: 'CONCLUIDA' }];
      if (url.endsWith('/materiais')) return [{ id: 3, titulo: 'Texto', tipo: 'TEXTO' }];
      if (url.endsWith('/videos')) return [{ id: 2, titulo: 'Vídeo', provedor: 'CLOUDFLARE', cloudflare_uid: 'uid' }];
      return [];
    },
    apiPostAuth: async (url, body) => {
      calls.push(['POST', url, body]);
      const result = { ...body, id: 9, ordem: 12 };
      if (url === '/questoes') questions.push(result);
      return result;
    },
    apiPutAuth: async (url, body) => {
      calls.push(['PUT', url, body]);
      const result = { ...body, id: 9 };
      if (url.startsWith('/questoes/')) questions[0] = result;
      return result;
    },
    apiDeleteAuth: async url => calls.push(['DELETE', url])
  };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(script, ctx);
  ctx.abrirConteudoAula(1, 'Aula');
  return { ctx, calls, alerts, element, questions };
}

function preencherVideo(env) {
  env.element('tituloVideoAula').value = 'Título';
  env.element('provedorVideoAula').value = 'CLOUDFLARE';
  env.element('uidCloudflareVideoAula').value = 'uid';
}

function preencherQuestao(env, tipo = 'MULTIPLA_4') {
  env.element('questaoTipoQuestao').value = tipo;
  env.element('questaoEnunciado').value = 'Enunciado';
  env.element('questaoGabarito').value = tipo === 'CERTO_ERRADO' ? 'C' : 'A';
  env.element('questaoComentario').value = 'Comentário';
  for (const letra of 'ABCDE') env.element(`alternativa_${letra}`).value = `Texto ${letra}`;
}

test('criação delega ordenação ao backend para textos, vídeos e baterias', async () => {
  const env = ambiente();
  env.element('tituloTextoTeoria').value = 'Título';
  env.element('textoTeoriaAula').value = 'Conteúdo';
  await env.ctx.salvarNovoTextoTeoria();
  preencherVideo(env);
  await env.ctx.salvarNovoResumoVideo();
  await env.ctx.criarBateriaQuestoes();
  const posts = env.calls.filter(c => c[0] === 'POST');
  assert.deepEqual(posts.map(c => c[1]), ['/materiais', '/videos', '/baterias']);
  for (const [, , body] of posts) assert.equal(Object.hasOwn(body, 'ordem'), false);
  assert.equal(posts[1][2].cloudflare_uid, 'uid');
});

test('edição de vídeo omite duração, transcrição e ativo, preservando os valores', async () => {
  const env = ambiente();
  preencherVideo(env);
  await env.ctx.salvarEdicaoVideo(2, 4);
  const body = env.calls.find(c => c[0] === 'PUT')[2];
  for (const key of ['duracao_segundos', 'transcricao', 'ativo']) assert.equal(Object.hasOwn(body, key), false);
  assert.equal(body.ordem, 4);
});

test('editar título da bateria omite status e ativo', async () => {
  const env = ambiente();
  await env.ctx.abrirQuestoesAula(1, 'Aula');
  await env.ctx.editarTituloBateria(1, 'Título', 4);
  const body = env.calls.find(c => c[0] === 'PUT')[2];
  assert.equal(Object.hasOwn(body, 'status'), false);
  assert.equal(Object.hasOwn(body, 'ativo'), false);
});

test('questão e alternativas são criadas juntas e atualizadas juntas', async () => {
  const env = ambiente();
  await env.ctx.abrirQuestoesAula(1, 'Aula');
  await env.ctx.abrirQuestoesDaBateria(1);
  preencherQuestao(env);
  await env.ctx.criarQuestaoManual();
  const post = env.calls.find(c => c[0] === 'POST');
  assert.equal(post[1], '/questoes');
  assert.equal(post[2].alternativas.length, 4);
  assert.equal(Object.hasOwn(post[2], 'ordem'), false);
  assert.equal(env.calls.filter(c => c[0] === 'POST').length, 1);
  env.ctx.editarQuestao(9);
  preencherQuestao(env);
  env.element('alternativa_A').value = 'Alternativa editada';
  await env.ctx.criarQuestaoManual();
  const put = env.calls.find(c => c[0] === 'PUT' && c[1] === '/questoes/9');
  assert.equal(put[2].alternativas[0].texto, 'Alternativa editada');
  assert.equal(Object.hasOwn(put[2], 'ativo'), false);
});

test('CERTO/ERRADO envia lista vazia de alternativas', async () => {
  const env = ambiente();
  await env.ctx.abrirQuestoesDaBateria(1);
  preencherQuestao(env, 'CERTO_ERRADO');
  await env.ctx.criarQuestaoManual();
  assert.equal(env.calls.find(c => c[0] === 'POST')[2].alternativas.length, 0);
});

test('cards oferecem exclusão de texto e vídeo e recarregam a lista', async () => {
  const env = ambiente();
  await env.ctx.abrirTeoriaAula(1, 'Aula');
  assert.match(env.element('boxConteudoAula').innerHTML, /excluirTextoTeoria\(3\)/);
  await env.ctx.excluirTextoTeoria(3);
  await env.ctx.abrirVideoAula(1, 'Aula');
  assert.match(env.element('boxConteudoAula').innerHTML, /excluirResumoVideo\(2\)/);
  await env.ctx.excluirResumoVideo(2);
  assert.deepEqual(env.calls.filter(c => c[0] === 'DELETE'), [['DELETE', '/materiais/3'], ['DELETE', '/videos/2']]);
});

test('exclusão cancelada não chama a API', async () => {
  const env = ambiente();
  env.ctx.confirm = () => false;
  await env.ctx.excluirTextoTeoria(3);
  await env.ctx.excluirResumoVideo(2);
  assert.equal(env.calls.filter(c => c[0] === 'DELETE').length, 0);
});

test('bloqueio por histórico apresenta a mensagem do backend', async () => {
  const env = ambiente();
  env.ctx.apiDeleteAuth = async () => { throw new Error('{"detail":"Histórico de alunos deve ser preservado"}'); };
  await env.ctx.excluirBateria(1);
  await env.ctx.excluirQuestao(9);
  assert.equal(env.alerts.length, 2);
  assert.ok(env.alerts.every(message => message.includes('Histórico de alunos deve ser preservado')));
});
