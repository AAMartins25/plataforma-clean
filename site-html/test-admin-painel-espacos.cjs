// PLAYWRIGHT_MODULE=/caminho/playwright-core CHROMIUM_PATH=/caminho/chromium node site-html/test-admin-painel-espacos.cjs
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const root = __dirname, origin = 'http://admin-espacos.test';
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
        return ['cabecalho.js','admin-painel-cabecalho.js'].includes(src) || (!baseline && src === 'admin-painel-espacos.js') ? all : '';
      });
      if (baseline) html = html.replace(/<link\b[^>]*admin-painel-espacos\.css[^>]*>/, '');
      body = Buffer.from(html);
    }
    return route.fulfill({body, contentType:mime[path.extname(file)] || 'application/octet-stream'});
  });
  await page.goto(`${origin}/admin/index.html`);
  if (!baseline) await page.locator('.painel-compacto').waitFor();
  await page.waitForTimeout(150);
  return page;
}
async function medir(page) {
  return page.evaluate(() => {
    const card = document.querySelector('main > .card'), header=document.querySelector('header');
    const box = e => { const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height,bottom:r.bottom};};
    const estilo = e => {const s=getComputedStyle(e);return {font:s.font,color:s.color,background:s.backgroundColor,border:s.border,padding:s.padding,shadow:s.boxShadow,transform:s.transform};};
    return {header:box(header),card:box(card),cardStyle:estilo(card),items:[...card.querySelectorAll(':scope > h2, :scope > section > h3, :scope > section > .list > .btn')].filter(e=>e.getClientRects().length).map(e=>({text:e.textContent.trim(),box:box(e),style:estilo(e),href:e.getAttribute('href'),onclick:e.getAttribute('onclick')})),overflow:document.documentElement.scrollWidth>innerWidth};
  });
}
const perto=(a,b,label,t=.1)=>assert.ok(Math.abs(a-b)<t,`${label}: ${a} / ${b}`);
function comparar(a,b,label) {
  assert.equal(b.items.length,a.items.length,label+' quantidade');
  perto(b.card.y,a.card.y,label+' card y');
  perto(b.card.w,a.card.w*.96,label+' card largura');
  perto(b.card.x+b.card.w/2,a.card.x+a.card.w/2,label+' card centro');
  assert.deepEqual(b.cardStyle,a.cardStyle,label+' card estilo');
  perto(b.card.y-b.header.bottom,a.card.y-a.header.bottom,label+' distância cabeçalho/card');
  assert.equal(b.overflow,a.overflow,label+' overflow');
  const botoes=b.items.filter(e=>e.href!==null);
  if(botoes.length>1) perto(b.card.bottom-botoes.at(-1).box.bottom,botoes[1].box.y-botoes[0].box.bottom,label+' respiro inferior');
  for (let i=0;i<a.items.length;i++) {
    const x=a.items[i],y=b.items[i];assert.equal(y.text,x.text);assert.equal(y.href,x.href);assert.equal(y.onclick,x.onclick);assert.deepEqual(y.style,x.style,label+' estilo '+x.text);
    perto(y.box.h,x.box.h,label+' '+x.text+' altura');
    if(x.href !== null){perto(y.box.w,x.box.w*.96,label+' botão largura');perto(y.box.x+y.box.w/2,x.box.x+x.box.w/2,label+' botão centro');}
    else perto(y.box.x,x.box.x+(b.card.x-a.card.x),label+' título x');
    if(i===0) perto(y.box.y,x.box.y,label+' primeiro título');
    if(i>0) {
      const original=x.box.y-a.items[i-1].box.bottom, reduzido=y.box.y-b.items[i-1].box.bottom;
      perto(reduzido,original*.75,label+' intervalo '+a.items[i-1].text+' / '+x.text,.15);
    }
  }
}
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH,args:['--no-sandbox']});
 try {
  for(const width of [1366,768,390,320]){
   const [antes,depois]=await Promise.all([abrir(browser,width,true),abrir(browser,width,false)]);
   comparar(await medir(antes),await medir(depois),`${width}px`);
   await depois.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
   const posicao = await depois.evaluate(() => window.scrollY);
   await depois.evaluate(() => window.dispatchEvent(new Event('resize')));
   await depois.waitForTimeout(200);
   perto(await depois.evaluate(() => window.scrollY),posicao,`${width}px rolagem`);
   await depois.evaluate(() => window.scrollTo(0, 0));
   // Permissões podem esconder seções depois do carregamento.
   for(const page of [antes,depois]) await page.evaluate(()=>{document.querySelector('[data-admin-area="alunos"]').style.display='none';});
   await Promise.all([antes.waitForTimeout(200),depois.waitForTimeout(200)]);
   comparar(await medir(antes),await medir(depois),`${width}px / permissão`);
   for(const page of [antes,depois]) await page.evaluate(()=>{document.querySelector('[data-admin-area="alunos"]').style.display=''; document.querySelector('[data-admin-area="producao"]').hidden=true; document.querySelector('section:last-of-type').hidden=true;});
   await Promise.all([antes.waitForTimeout(200),depois.waitForTimeout(200)]);
   comparar(await medir(antes),await medir(depois),`${width}px / seções ocultas`);
   await Promise.all([antes.close(),depois.close()]);
   console.log(`${width}px: intervalos, tamanhos, estilos e permissões OK`);
  }
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
