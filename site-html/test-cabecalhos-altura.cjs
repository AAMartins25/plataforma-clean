// Geometria dos HTMLs/CSSs e scripts visuais reais, sem executar APIs/regras de negócio.
// PLAYWRIGHT_MODULE=/path/to/playwright-core CHROMIUM_PATH=/path/to/chrome node site-html/test-cabecalhos-altura.cjs
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const origin = 'http://cabecalhos.test';
const root = __dirname;
const visualScripts = new Set(['cabecalho.js','cabecalhos-altura.js','funcionalidades-cabecalho.js',
  'teoria-cabecalho.js','disciplinas-layout.js','assuntos-layout.js','admin-painel-cabecalho.js']);
const mime = {'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.woff2':'font/woff2'};
function pages(dir) {
  return fs.readdirSync(dir,{withFileTypes:true}).flatMap(e => {
    const file = path.join(dir,e.name);
    if (e.isDirectory()) return pages(file);
    return e.name.endsWith('.html') && fs.readFileSync(file,'utf8').includes('<header') ? [path.relative(root,file)] : [];
  });
}
function fixture(file) {
  return fs.readFileSync(file,'utf8').replace(/<script\b([^>]*)>[\s\S]*?<\/script>/gi,(all,attrs) => {
    const src = attrs.match(/src=["']([^"']+)/i)?.[1];
    return src && visualScripts.has(src.split('/').at(-1).split('?')[0]) ? all : '';
  }).replace('</body>',`<script>
    const header = document.querySelector('body>header');
    for (const h of header.querySelectorAll('h1,h2')) if (!h.textContent.trim()) h.textContent = h.tagName==='H1'?'Curso de Matemática':'Minhas atividades';
    for (const [id,text] of [['titulo_disciplina','Matemática'],['titulo_assunto_header','Geometria']]) {const e=document.getElementById(id);if(e)e.textContent=text;}
  </script></body>`);
}
async function geometry(page) {
  return page.evaluate(() => {
    const header = document.querySelector('body>header');
    const capture = () => {
      const box = e => {const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height};};
      const style = e => {const c=getComputedStyle(e);return {font:c.font,color:c.color,background:c.background,border:c.border,padding:c.padding};};
      const elements = [...header.querySelectorAll('h1,h2,p,img,svg,.ro-identity,.ro-nav-control,.ro-header-access a')]
        .filter(e=>e.getClientRects().length&&!e.closest('[aria-hidden=true]'))
        .map(e=>({box:box(e),style:style(e),href:e.getAttribute('href'),onclick:e.getAttribute('onclick')}));
      const cards = [...document.querySelectorAll('main>.card')].map(e=>({box:box(e),style:style(e)}));
      return {header:box(header),elements,cards,overflow:document.documentElement.scrollWidth>innerWidth};
    };
    const original = Cabecalho.comAlturaOriginal(header,capture);
    const expanded = capture();
    return {original,expanded};
  });
}
function check({original,expanded},label) {
  const fator = label.startsWith('curso-info.html/') ? 1.06 * .92 * .92 : label.startsWith('admin/index.html/') ? 1.06 * .85 : 1.06;
  assert.ok(Math.abs(expanded.header.h-original.header.h*fator)<.04,label+' fator de altura');
  assert.equal(expanded.header.w,original.header.w,label+' largura do cabeçalho');
  assert.equal(expanded.overflow,false,label+' sem overflow');
  assert.equal(expanded.elements.length,original.elements.length);
  for (let i=0;i<original.elements.length;i++) {
    const a=original.elements[i],b=expanded.elements[i];
    assert.deepEqual(b.style,a.style,label+' fontes/cores/bordas/espaçamentos');
    assert.equal(b.href,a.href); assert.equal(b.onclick,a.onclick);
    for (const k of ['x','w','h']) assert.ok(Math.abs(b.box[k]-a.box[k])<.08,label+' elemento '+k);
    assert.ok(b.box.y>=expanded.header.y-.1 && b.box.y+b.box.h<=expanded.header.y+expanded.header.h+.1,label+' elemento dentro da faixa');
  }
  assert.equal(expanded.cards.length,original.cards.length);
  for (let i=0;i<original.cards.length;i++) {
    const a=original.cards[i],b=expanded.cards[i];assert.deepEqual(b.style,a.style);
    for (const k of ['x','w','h']) assert.ok(Math.abs(b.box[k]-a.box[k])<.08,label+' card preservado '+k);
  }
}
async function noOverlap(page,label) {
  const collisions = await page.evaluate(() => {
    const header=document.querySelector('body>header'),range=document.createRange();
    const controls=[...header.querySelectorAll('.ro-nav-control,.ro-header-access a')].filter(e=>e.getClientRects().length);
    const titles=[...header.querySelectorAll('h1,h2,p,.ro-identity')].filter(e=>e.getClientRects().length&&!e.closest('[aria-hidden=true]'));
    return titles.flatMap(e=>{
      range.selectNodeContents(e);const textRects=[...range.getClientRects()].filter(r=>r.width&&r.height);
      return controls.filter(control=>!e.contains(control)&&textRects.some(r=>{
        const box=control.getBoundingClientRect(),size=parseFloat(getComputedStyle(control,'::before').fontSize);
        // Os ícones transparentes conservam a área de toque; mede a área visual do símbolo.
        const c=control.matches('.ro-nav-control')?{left:box.left+(box.width-size)/2,right:box.left+(box.width+size)/2,
          top:box.top+(box.height-size)/2,bottom:box.top+(box.height+size)/2}:box;
        return r.left<c.right-.5&&r.right>c.left+.5&&r.top<c.bottom-.5&&r.bottom>c.top+.5;
      })).map(control=>e.textContent.trim()+' / '+control.title);
    });
  });
  assert.deepEqual(collisions,[],label+' sem sobreposição visual');
  for (const control of await page.locator('header .ro-nav-control:visible,header .ro-header-access a:visible').all()) {
    await control.click({trial:true,timeout:2000});
  }
}
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{}),args:['--no-sandbox']});
  const selected=process.env.HEADER_PAGES?process.env.HEADER_PAGES.split(','):pages(root).sort();
  const dynamic=new Set(['index.html','cursos.html','minha-area.html','curso.html','minhas-anotacoes.html',
    'mensagens-prof.html','revisoes-programadas.html','dashboard.html','teoria.html','disciplinas.html','admin/index.html','login.html']);
  try {
    for (const file of selected) {
      const context=await browser.newContext({viewport:{width:1366,height:900}});
      await context.route('**/*',route=>{
        const u=new URL(route.request().url());if(u.origin!==origin)return route.abort();
        const file=path.resolve(root,'.'+u.pathname);
        if(!file.startsWith(root+path.sep)||!fs.existsSync(file))return route.fulfill({status:404,body:''});
        return route.fulfill({contentType:mime[path.extname(file)]||'application/octet-stream',body:file.endsWith('.html')?fixture(file):fs.readFileSync(file)});
      });
      const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
      await page.goto(origin+'/'+file+'?curso_nome=Curso%20de%20Matem%C3%A1tica&disciplina_nome=Matem%C3%A1tica&assunto_nome=Geometria');
      await page.locator('header.ro-header').waitFor();
      for (const width of [1366,768,390,320]) {
        await page.setViewportSize({width,height:900});await page.waitForTimeout(180);
        check(await geometry(page),file+'/'+width);await noOverlap(page,file+'/'+width);
      }
      if (dynamic.has(file)) {
        // Nome carregado depois do layout, com repetição de resize: não pode acumular 6%.
        await page.evaluate(()=>{
          let user=document.getElementById('nomeUsuarioLogadoGlobal')||document.getElementById('nome_aluno_logado');
          if(!user){user=document.createElement('div');user.id='nomeUsuarioLogadoGlobal';document.body.append(user);}
          user.textContent='Ana';user.title='Ana Silva';user.style.fontSize='.68rem';
        });
        await page.waitForTimeout(200);
        for (const width of [768,320,1366,390]) {
          await page.setViewportSize({width,height:900});await page.waitForTimeout(180);
          const sample=await geometry(page);check(sample,file+'/nome tardio/'+width);await noOverlap(page,file+'/'+width);
          await page.evaluate(()=>{for(let i=0;i<3;i++)window.dispatchEvent(new Event('resize'));});
          await page.waitForTimeout(180);
          assert.ok(Math.abs((await geometry(page)).expanded.header.h-sample.expanded.header.h)<.04,file+' sem crescimento acumulado');
          // A medição não pode limitar a rolagem quando o aluno está no final.
          await page.evaluate(()=>window.scrollTo({top:document.documentElement.scrollHeight,behavior:'instant'}));
          const bottom=await page.evaluate(()=>scrollY);
          await page.evaluate(()=>window.dispatchEvent(new Event('resize')));
          await page.waitForTimeout(180);
          assert.ok(Math.abs(await page.evaluate(()=>scrollY)-bottom)<=1,file+' rolagem preservada no fim da página');
        }
      }
      assert.deepEqual(errors,[],file+' sem erros JavaScript');
      console.log(file+': 1366/768/390/320, altura proporcional, fontes/alinhamentos/cards/controles preservados: OK');
      await context.close();
    }
  } finally {await browser.close();}
})().catch(err=>{console.error(err);process.exitCode=1;});
