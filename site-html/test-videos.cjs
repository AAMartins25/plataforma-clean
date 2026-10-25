const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const page = fs.readFileSync(path.join(__dirname, 'teoria.html'), 'utf8');
const rendering = page.slice(page.indexOf('    function renderVideo('), page.indexOf('    async function abrirAula('));
const section = page.slice(page.indexOf('    async function abrirSecaoVideo('), page.indexOf('    async function limparRefazerSprint('));
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'teste-videos-'));
const html = `<!doctype html><div id="detalhes_aula"></div><div id="paginacao_teoria"></div><pre id="resultado"></pre>
<script>
let aulaAtualId, pedidos = [], pendentes = [], videos = [
  {id: 2, ordem: 2, titulo: 'Cloudflare', provedor: 'CLOUDFLARE'},
  {id: 1, ordem: 1, titulo: 'YouTube <teste>', url: 'https://youtu.be/exemplo'},
  {id: 3, ordem: 3, titulo: 'Externo', url: 'https://example.com/video'}
];
const esc = s => String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const destacarBotaoSecao = () => {};
const contextoAcessoQuery = () => 'demonstracao_id=8';
const tryMany = async () => videos;
const renderError = (titulo, mensagem) => titulo + mensagem;
const apiGet = url => { pedidos.push(url); return new Promise(resolve => pendentes.push(resolve)); };
${rendering}
${section}
const check = (ok, mensagem) => { if (!ok) throw Error(mensagem); };
(async () => {
 await abrirSecaoVideo(10);
 const box = document.getElementById('detalhes_aula');
 const botoes = box.querySelectorAll('button');
 check(botoes.length === 3 && botoes[0].textContent === 'YouTube <teste>', 'títulos, ordem e escape');
 check(!box.querySelector('iframe') && !box.querySelector('a') && pedidos.length === 0, 'início sem players ou playback');
 botoes[0].click();
 const youtube = box.querySelector('iframe');
 check(youtube.src === 'https://www.youtube.com/embed/exemplo', 'player YouTube');
 check(botoes[0].getAttribute('aria-expanded') === 'true', 'expansão acessível');
 botoes[0].click();
 check(!youtube.isConnected && !box.querySelector('iframe'), 'remoção interrompe player');
 botoes[1].click();
 check(pedidos[0] === '/videos/2/playback?demonstracao_id=8', 'Cloudflare com contexto');
 botoes[1].click(); botoes[1].click();
 pendentes[0]({token: 'antigo'}); await Promise.resolve();
 check(!box.querySelector('iframe'), 'resposta antiga descartada após recolher e reabrir');
 pendentes[1]({token: 'novo/token'}); await Promise.resolve();
 check(box.querySelector('iframe').src.includes('novo%2Ftoken/iframe'), 'Cloudflare token novo e codificado');
 botoes[1].click();
 check(!box.querySelector('iframe'), 'Cloudflare removido');
 botoes[2].click(); check(box.querySelector('a').href === 'https://example.com/video', 'link externo preservado');
 botoes[2].click(); check(!box.querySelector('a'), 'link recolhido');
 botoes[1].click(); pendentes[2]({}); await Promise.resolve();
 check(box.textContent.includes('Não foi possível carregar este vídeo.'), 'erro de playback');
 await abrirSecaoVideo(10);
 check(!box.querySelector('iframe') && box.querySelectorAll('[aria-expanded="false"]').length === 3, 'reentrada recolhida');
 videos = []; await abrirSecaoVideo(10);
 check(box.textContent.includes('Ainda não há vídeo cadastrado.'), 'estado vazio');
 document.getElementById('resultado').textContent = 'TESTES_OK';
})().catch(e => document.getElementById('resultado').textContent = 'FALHA: ' + e.message);
</script>`;
try {
 const file = path.join(dir, 'teste.html'); fs.writeFileSync(file, html);
 const browser = process.env.CHROMIUM_BIN || '/home/codespace/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell';
 const result = spawnSync(browser, ['--no-sandbox', '--disable-gpu', '--dump-dom', '--virtual-time-budget=5000', 'file://' + file], {encoding: 'utf8', timeout: 20000});
 assert.equal(result.status, 0, result.stderr || String(result.error));
 assert.match(result.stdout, /<pre id="resultado">TESTES_OK<\/pre>/, result.stdout);
 console.log('Vídeos: abertura sob demanda, recolhimento, Cloudflare, corrida assíncrona, links, erros e estado vazio: OK');
} finally { fs.rmSync(dir, {recursive: true, force: true}); }
