// Cabeçalhos reais e folhas de estilo locais; nenhuma consulta à produção.
// NAV_BASE_REF permite comparar alturas e controles com um commit anterior.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = __dirname;
const widths = [1366, 768, 390, 320];
const files = fs.readdirSync(root).filter(f => f.endsWith('.html')).concat(
  fs.readdirSync(root + '/admin').filter(f => f.endsWith('.html')).map(f => 'admin/' + f))
  .filter(f => !process.env.NAV_PAGES || process.env.NAV_PAGES.split(',').includes(f));
const originals = new Map();
function read(file, baseline = false) {
  if (!baseline || !process.env.NAV_BASE_REF) return fs.readFileSync(path.join(root, file), 'utf8');
  if (!originals.has(file)) originals.set(file, execFileSync('git',
    ['show', `${process.env.NAV_BASE_REF}:site-html/${file}`], {cwd: root, encoding: 'utf8'}));
  return originals.get(file);
}
const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://local');
  if (url.pathname === '/fixture') {res.setHeader('Content-Type', 'text/html; charset=utf-8');res.end('<!doctype html><html></html>');return;}
  const baseline = url.pathname.startsWith('/baseline/');
  const file = url.pathname.replace(/^\/(?:baseline\/)?/, '');
  if (file.includes('..') || !fs.existsSync(path.join(root, file))) {res.writeHead(404).end(); return;}
  res.setHeader('Content-Type', (file.endsWith('.css') ? 'text/css' : file.endsWith('.js') ? 'text/javascript' : 'text/html') + '; charset=utf-8');
  res.end(read(file, baseline));
});
const near = (a, b, message) => assert.ok(Math.abs(a - b) <= 0.035, `${message}: ${a} / ${b}`);
const labels = ['Voltar', 'Voltar para cursos', 'Início', 'Página inicial', 'Sair'];
async function measure(page) {
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  return page.evaluate(() => {
    const box = e => {const r = e.getBoundingClientRect(); return {x:r.x, y:r.y, w:r.width, h:r.height};};
    const style = e => {const s = getComputedStyle(e); return Object.fromEntries(
      ['fontFamily','fontSize','fontWeight','lineHeight','padding','borderRadius','color','backgroundColor','letterSpacing','textTransform'].map(k => [k,s[k]]));};
    const header = document.querySelector('body > header');
    return {
      height: box(header).h,
      controls: [...header.querySelectorAll('.ro-header-navigation a, .ro-header-navigation button')].map(e => ({
        label:e.getAttribute('aria-label') || e.title || e.textContent.trim(),
        href:e.getAttribute('href'), handler:e.getAttribute('onclick'),
        hidden:!e.getClientRects().length, box:box(e), style:style(e),
        symbol:e.dataset.roSimbolo || null
      })),
      identity:header.querySelector('.ro-identity') ? style(header.querySelector('.ro-identity')) : null,
      overflow:header.scrollWidth > innerWidth,
      contained:[...header.querySelectorAll('.ro-nav-control')].filter(e => e.getClientRects().length).every(e => {
        const r=e.getBoundingClientRect();return r.left>=0 && r.right<=innerWidth+.035 && r.top>=-.035 && r.bottom<=header.getBoundingClientRect().bottom+.035;
      })
    };
  });
}
async function load(page, origin, file, name, baseline = false) {
  const src = read(file, baseline);
  const header = src.match(/<header\b[\s\S]*?<\/header>/)?.[0];
  const head = src.match(/<head>[\s\S]*?<\/head>/)[0].replace(/<script\b[\s\S]*?<\/script>/g, '');
  const prefix = baseline ? '/baseline/' : '/';
  const body = src.match(/<body[^>]*>/)[0];
  const html = src.match(/<html[^>]*>/)[0];
  await page.goto(origin + '/fixture');
  await page.setContent(html + head.replace('<head>', `<head><base href="${origin}${prefix}${file}">`) + body + header +
    `<script src="${origin}${prefix}js/cabecalho.js"></script></body></html>`, {waitUntil:'load'});
  await page.waitForFunction(() => document.querySelector('body > header.ro-header'));
  if (name) await page.evaluate(name => {
    const e=document.createElement('div');e.id='nomeUsuarioLogadoGlobal';e.textContent=name;
    e.title=name+' Silva';e.style.cssText='opacity:.78;letter-spacing:.025rem;color:#4b5563';document.body.append(e);
  }, name);
  return measure(page);
}
(async () => {
  let browser;
  const report = {widths, pages:[], combinations:0, assertions:0};
  try {
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const origin = `http://127.0.0.1:${server.address().port}`;
    browser = await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE, args:['--no-sandbox']});
    const page = await browser.newPage();
    page.on('pageerror', error => console.error('Erro no cabeçalho:', error.message));
    await page.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
    for (const width of widths) {
      await page.setViewportSize({width,height:900});
      const reference = await load(page, origin, 'cursos.html', 'Ana');
      const referenceButton = reference.controls.find(c => c.label === 'Página inicial');
      for (const file of files) {
        if (!read(file).includes('<header')) continue;
        if (!report.pages.includes(file)) report.pages.push(file);
        for (const name of ['', 'Ana', 'Alexandrinaconstantinopolitana']) {
          const original = process.env.NAV_BASE_REF ? await load(page, origin, file, name, true) : null;
          const current = await load(page, origin, file, name);
          const context = `${file} ${width} ${name || 'anônimo'}`;
          if (original) {
            near(current.height, original.height, context + ' altura');
            assert.equal(current.controls.length, original.controls.length, context + ' quantidade');
            current.controls.forEach((c, i) => {
              const old=original.controls[i];
              assert.equal(c.href,old.href,context+' destino');
              assert.equal(c.handler,old.handler,context+' evento');
              assert.equal(c.hidden,old.hidden,context+' visibilidade');
              if (!labels.includes(c.label)) assert.deepEqual(c.style,old.style,context+' controle de seção');
            });
          }
          assert.equal(current.overflow,false,context+' rolagem horizontal');
          assert.equal(current.contained,true,context+' limites dos controles');
          for (const control of current.controls.filter(c => labels.includes(c.label))) {
            assert.ok(control.symbol,context+' símbolo');
            assert.deepEqual(control.style,referenceButton.style,context+' estilo do botão');
            if (!control.hidden) {
              near(control.box.w,referenceButton.box.w,context+' largura');
              near(control.box.h,referenceButton.box.h,context+' altura do botão');
            }
            report.assertions++;
          }
          if (current.identity) {
            assert.deepEqual(current.identity,reference.identity,context+' estilo do nome');
            report.assertions++;
          }
          if (process.env.NAV_SCREENSHOTS && name === 'Ana') {
            fs.mkdirSync(process.env.NAV_SCREENSHOTS,{recursive:true});
            await page.screenshot({path:path.join(process.env.NAV_SCREENSHOTS,`${file.replaceAll('/','-')}-${width}.png`)});
          }
          report.combinations++;
        }
      }
    }
    // O organizador preserva os nós de controle e seus listeners, inclusive
    // quando a página revela um botão e o usuário redimensiona a janela.
    await page.setContent(`<html><head><link rel="stylesheet" href="${origin}/css/style.css"></head><body><header><h1>Teste</h1><nav>
      <button id="voltar" title="Voltar">⇦</button><a id="inicio" href="cursos.html">Início</a>
      <button id="sair" title="Sair" style="display:none">⎋</button></nav></header></body></html>`);
    await page.evaluate(() => {
      window.clicks=0;document.querySelector('#voltar').addEventListener('click',()=>window.clicks++);
      document.querySelector('#sair').onclick=()=>window.clicks++;
    });
    await page.addScriptTag({url:origin+'/js/cabecalho.js'});
    await page.locator('#voltar').click();
    await page.evaluate(()=>document.querySelector('#sair').style.display='inline-block');
    await page.setViewportSize({width:768,height:900});
    await page.locator('#sair').click();
    assert.equal(await page.evaluate(()=>window.clicks),2);
    await page.keyboard.press('Tab');
    await page.locator('#voltar').focus();
    assert.equal(await page.locator('#voltar').evaluate(e=>getComputedStyle(e).outlineStyle),'solid');
    if (process.env.NAV_REPORT) fs.writeFileSync(process.env.NAV_REPORT,JSON.stringify(report,null,2)+'\n');
    console.log(`PASS: ${report.pages.length} páginas, ${report.combinations} combinações, ${report.assertions} verificações de aparência; eventos, foco, destinos e visibilidade preservados.`);
  } finally {await browser?.close();server.close();}
})().catch(error => {console.error(error);process.exitCode=1;});
