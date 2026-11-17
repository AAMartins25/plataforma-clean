// PLAYWRIGHT_MODULE=/caminho/playwright-core CHROMIUM_PATH=/caminho/chrome node site-html/test-curso-titulo.cjs
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const root = __dirname, origin = 'http://curso-teste.local';
const visuais = new Set(['cabecalho.js', 'cabecalhos-altura.js', 'disciplinas-layout.js', 'curso-titulo-referencia.js']);
const mime = {'.html':'text/html', '.css':'text/css', '.js':'text/javascript'};
async function abrir(browser, file, width, nome, baseline = false) {
  const page = await browser.newPage({viewport:{width, height:900}});
  await page.route('**/*', route => {
    const u = new URL(route.request().url()), arquivo = path.resolve(root, '.' + u.pathname);
    if (u.origin !== origin || !arquivo.startsWith(root + path.sep) || !fs.existsSync(arquivo)) return route.abort();
    let corpo = fs.readFileSync(arquivo);
    if (arquivo.endsWith('.html')) corpo = Buffer.from(corpo.toString().replace(/<script\b([^>]*)>[\s\S]*?<\/script>/gi, (all, attrs) => {
      const src = attrs.match(/src=["']([^"']+)/i)?.[1]?.split('/').at(-1).split('?')[0];
      return visuais.has(src) && !(baseline && src === 'curso-titulo-referencia.js') ? all : '';
    }).replace('</body>', `<div id="nomeUsuarioLogadoGlobal" title="Ana Silva">Ana</div><script>document.querySelector('header h1').textContent=${JSON.stringify(nome)}</script></body>`));
    return route.fulfill({body:corpo, contentType:mime[path.extname(arquivo)] || 'application/octet-stream'});
  });
  await page.goto(`${origin}/${file}`);
  if (file === 'curso.html' && !baseline) await page.locator('.curso-titulo-alinhado').waitFor();
  await page.waitForTimeout(450);
  return page;
}
async function medir(page, curso) {
  return page.evaluate(curso => {
    const header = document.querySelector('header'), titulo = header.querySelector(curso ? '.curso-titulo-referencia' : 'h1');
    const box = e => { const r = e.getBoundingClientRect(); return {left:r.left, top:r.top, right:r.right, bottom:r.bottom, width:r.width, height:r.height}; };
    const range = document.createRange(); range.selectNodeContents(titulo);
    return {header:box(header), titulo:box(titulo), linhas:[...range.getClientRects()].filter(r => r.width && r.height).map(r=>({left:r.left,top:r.top,right:r.right,bottom:r.bottom})),
      controles:[...header.querySelectorAll('.ro-nav-control')].map(box), card:box(document.querySelector('main > .card')), fonte:getComputedStyle(titulo).fontSize,
      overflow:document.documentElement.scrollWidth > innerWidth};
  }, curso);
}
function overlap(a,b) { return a.left < b.right - .03 && a.right > b.left + .03 && a.top < b.bottom - .03 && a.bottom > b.top + .03; }
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:process.env.CHROMIUM_PATH, args:['--no-sandbox']});
  try {
    for (const width of [1366,768,390,320]) for (const nome of ['Curso de Matemática', 'Matemática'.repeat(20)]) {
      const [curso, referencia, baseline] = await Promise.all([abrir(browser,'curso.html',width,nome), abrir(browser,'disciplinas.html',width,nome), abrir(browser,'curso.html',width,nome,true)]);
      const [a,b,c] = await Promise.all([medir(curso,true),medir(referencia,false),medir(baseline,false)]);
      const label = `${width}px / ${nome.length} caracteres`;
      assert.equal(a.fonte,b.fonte,label+' fonte');
      assert.equal(a.linhas.length,b.linhas.length,label+' quebra');
      for (let i=0;i<a.linhas.length;i++) for (const k of ['left','top','right','bottom']) assert.ok(Math.abs(a.linhas[i][k]-b.linhas[i][k]) < .08, label+' posição '+k);
      assert.ok(Math.abs((a.card.top-a.header.bottom)-(b.card.top-b.header.bottom)) < .08,label+' espaço');
      assert.ok(a.header.height >= c.header.height-.08,label+' altura mínima');
      if (nome.length < 30) assert.ok(Math.abs(a.header.height-c.header.height)<.08,label+' altura preservada');
      assert.ok(a.linhas.every(l=>l.top>=a.header.top-.08 && l.bottom<=a.header.bottom+.08),label+' título dentro do cabeçalho');
      for (const [i,controle] of a.controles.entries()) {
        if (width <= 480) assert.ok(controle.width>=44-.08 && controle.height>=44-.08,label+' área de toque');
        assert.ok(Math.abs(controle.width-c.controles[i].width)<.08 && Math.abs(controle.height-c.controles[i].height)<.08,label+' dimensões do controle');
        assert.ok(controle.bottom<=a.header.bottom+.08,label+' controle dentro do cabeçalho');
        assert.ok(a.linhas.every(l=>!overlap(l,controle)),label+' título e controle');
        assert.ok(a.controles.slice(i+1).every(outro=>!overlap(outro,controle)),label+' controles');
      }
      assert.equal(a.overflow,false,label+' overflow');
      await Promise.all([curso.close(),referencia.close(),baseline.close()]);
      console.log(label+': OK');
    }
    const curso = await abrir(browser, 'curso.html', 320, 'Curso de Matemática');
    const alturaInicial = (await medir(curso, true)).header.height;
    await curso.evaluate(() => { document.querySelector('#titulo_curso').textContent = 'Matemática'.repeat(20); });
    await curso.waitForTimeout(600);
    let dados = await medir(curso, true);
    assert.ok(dados.header.height > alturaInicial && dados.linhas.every(l => l.bottom <= dados.header.bottom + .08), 'nome carregado depois aumenta o cabeçalho');
    await curso.setViewportSize({width:768, height:900});
    await curso.waitForTimeout(600);
    const ref = await abrir(browser, 'disciplinas.html', 768, 'Matemática'.repeat(20));
    dados = await medir(curso, true);
    const comparacao = await medir(ref, false);
    assert.equal(dados.linhas.length, comparacao.linhas.length, 'quebra após resize');
    assert.ok(Math.abs(dados.linhas[0].top - comparacao.linhas[0].top) < .08, 'posição após resize');
    await curso.setViewportSize({width:320, height:900});
    await curso.evaluate(() => { document.querySelector('#titulo_curso').textContent = 'Curso de Matemática'; });
    await curso.waitForTimeout(600);
    dados = await medir(curso, true);
    assert.ok(Math.abs(dados.header.height - alturaInicial) < .08, 'altura restaurada após nome curto');
    await Promise.all([curso.close(), ref.close()]);
    console.log('Nome tardio e redimensionamento: OK');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode=1; });
