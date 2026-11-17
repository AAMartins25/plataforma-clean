// PLAYWRIGHT_MODULE=/caminho/playwright-core CHROMIUM_PATH=/caminho/chromium node site-html/test-admin-painel-cabecalho.cjs
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const root = __dirname, origin = 'http://admin-cabecalho.test';
const mime = {'.html':'text/html','.css':'text/css','.js':'text/javascript'};
async function abrir(browser, width, baseline) {
  const page = await browser.newPage({viewport:{width,height:900}});
  await page.route('**/*', route => {
    const u = new URL(route.request().url()), file = path.resolve(root, '.' + u.pathname);
    if (u.origin !== origin || !file.startsWith(root + path.sep) || !fs.existsSync(file)) return route.abort();
    let body = fs.readFileSync(file);
    if (file.endsWith('.html')) {
      let html = body.toString().replace(/<script\b([^>]*)>[\s\S]*?<\/script>/gi, (all, attrs) => {
        const src = attrs.match(/src=["']([^"']+)/i)?.[1]?.split('/').at(-1).split('?')[0];
        return src === 'cabecalho.js' || (!baseline && src === 'admin-painel-cabecalho.js') ? all : '';
      });
      if (baseline) html = html.replace(/<link\b[^>]*admin-painel-cabecalho\.css[^>]*>/, '');
      body = Buffer.from(html);
    }
    return route.fulfill({body, contentType:mime[path.extname(file)] || 'application/octet-stream'});
  });
  await page.goto(`${origin}/admin/index.html`);
  await page.locator('header.ro-header').waitFor();
  await page.waitForTimeout(200);
  return page;
}
async function medir(page) {
  return page.evaluate(() => {
    const header = document.querySelector('header'), titulo = header.querySelector('h1'), card = document.querySelector('main > .card');
    const box = e => { const r = e.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height,right:r.right,bottom:r.bottom}; };
    const range = document.createRange(); range.selectNodeContents(titulo);
    const estilo = e => {const s=getComputedStyle(e); return {font:s.font,color:s.color,background:s.backgroundColor,border:s.border,padding:s.padding,shadow:s.boxShadow};};
    return {header:box(header), titulo:box(titulo), texto:[...range.getClientRects()].filter(r=>r.width&&r.height).map(r=>({x:r.x,y:r.y,right:r.right,bottom:r.bottom})),
      estilo:estilo(titulo), controles:[...header.querySelectorAll('.ro-nav-control')].map(e=>({box:box(e),style:estilo(e),href:e.getAttribute('href'),handler:e.getAttribute('onclick')})),
      identidade:(() => { const nome=header.querySelector('.ro-identity'); if(!nome)return null; const r=document.createRange();r.selectNodeContents(nome);const b=r.getBoundingClientRect();return {x:b.x,y:b.y,right:b.right,bottom:b.bottom}; })(), card:box(card), cardStyle:estilo(card), overflow:document.documentElement.scrollWidth>innerWidth};
  });
}
const proximo = (a,b,label,erro=.08) => assert.ok(Math.abs(a-b)<erro,`${label}: ${a} / ${b}`);
const colisao = (a,b) => a.x < b.right-.1 && a.right > b.x+.1 && a.y < b.bottom-.1 && a.bottom > b.y+.1;
function verificar(antes,depois,label) {
  proximo(depois.header.h,antes.header.h*.85,label+' altura');
  proximo(depois.titulo.x+depois.titulo.w/2,depois.header.x+depois.header.w/2,label+' centro horizontal');
  proximo(depois.titulo.y+depois.titulo.h/2,depois.header.y+depois.header.h/2-5,label+' centro vertical');
  for (const k of ['w','h']) proximo(depois.titulo[k],antes.titulo[k],label+' título '+k);
  assert.deepEqual(depois.estilo,antes.estilo,label+' fonte e estilo');
  assert.deepEqual(depois.cardStyle,antes.cardStyle,label+' estilo do card');
  for (const k of ['x','w','h']) proximo(depois.card[k],antes.card[k],label+' card '+k);
  proximo(depois.card.y-depois.header.bottom,antes.card.y-antes.header.bottom,label+' intervalo');
  assert.equal(depois.overflow,antes.overflow,label+' responsividade');
  for (let i=0;i<depois.controles.length;i++) {
    const a=antes.controles[i],b=depois.controles[i];
    assert.deepEqual(b.style,a.style,label+' estilo do controle'); assert.equal(b.href,a.href); assert.equal(b.handler,a.handler);
    for (const k of ['x','w','h']) proximo(b.box[k],a.box[k],label+' controle '+k);
    assert.ok(depois.texto.every(l=>!colisao(l,b.box)),label+' título sem sobreposição');
    assert.ok(b.box.bottom<=depois.header.bottom+.1,label+' controle na faixa');
  }
  if (depois.identidade) assert.ok(depois.texto.every(l=>!colisao(l,depois.identidade)),label+' título e identificação');
}
(async()=>{
  const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH,args:['--no-sandbox']});
  try {
    for(const width of [1366,768,390,320]) {
      const [antes,depois]=await Promise.all([abrir(browser,width,true),abrir(browser,width,false)]);
      verificar(await medir(antes),await medir(depois),`${width}px`);
      for(const page of [antes,depois]) await page.evaluate(()=>{const e=document.createElement('div');e.id='nomeUsuarioLogadoGlobal';e.textContent='Ana';e.title='Ana Silva';document.body.append(e);});
      await Promise.all([antes.waitForTimeout(300),depois.waitForTimeout(300)]);
      verificar(await medir(antes),await medir(depois),`${width}px / identificação tardia`);
      for(const page of [antes,depois]) await page.evaluate(()=>{document.querySelector('.ro-identity').textContent='Alexandrinaconstantinopolitana';});
      await Promise.all([antes.waitForTimeout(200),depois.waitForTimeout(200)]);
      verificar(await medir(antes),await medir(depois),`${width}px / identificação extensa`);
      await Promise.all([antes.close(),depois.close()]);
      console.log(`${width}px: altura, centralização, controles e cards OK`);
    }
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
