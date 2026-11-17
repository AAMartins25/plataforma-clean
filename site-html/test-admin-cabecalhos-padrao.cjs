// PLAYWRIGHT_MODULE=/caminho/playwright-core CHROMIUM_PATH=/caminho/chromium node site-html/test-admin-cabecalhos-padrao.cjs
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{execFileSync}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright-core');
const root=__dirname, origin='http://admin-padrao.test', ref=process.env.ADMIN_BASE_REF||'9727e41';
const excecoes=new Set(['index.html','aula-conteudo.html']);
const paginas=fs.readdirSync(path.join(root,'admin')).filter(f=>f.endsWith('.html')&&!excecoes.has(f)).sort();
const mime={'.html':'text/html','.css':'text/css','.js':'text/javascript'}, cache=new Map();
function original(rel){if(!cache.has(rel))cache.set(rel,execFileSync('git',['show',`${ref}:site-html/${rel}`],{cwd:root}));return cache.get(rel);}
async function abrir(browser,width,file,baseline){
 const page=await browser.newPage({viewport:{width,height:900}});
 await page.route('**/*',route=>{
  const u=new URL(route.request().url()),rel=u.pathname.replace(/^\/(?:base\/)?/,''),filePath=path.resolve(root,rel);
  if(u.origin!==origin||!filePath.startsWith(root+path.sep)||(!baseline&&!fs.existsSync(filePath)))return route.abort();
  let body;try{body=baseline?original(rel):fs.readFileSync(filePath);}catch{return route.abort();}
  if(filePath.endsWith('.html'))body=Buffer.from(body.toString().replace(/<script\b([^>]*)>[\s\S]*?<\/script>/gi,(all,attrs)=>{
   const src=attrs.match(/src=["']([^"']+)/i)?.[1]?.split('/').at(-1).split('?')[0];
   return ['cabecalho.js','admin-painel-cabecalho.js','admin-cabecalho-padrao.js'].includes(src)?all:'';
  }));
  return route.fulfill({body,contentType:mime[path.extname(filePath)]||'application/octet-stream'});
 });
 await page.goto(`${origin}${baseline?'/base':''}/admin/${file}`);
 if(!baseline&&!excecoes.has(file))await page.waitForFunction(()=>document.querySelector('header')?.style.getPropertyValue('--admin-titulo-y'),null,{timeout:7000});
 await page.waitForTimeout(120);return page;
}
async function medir(page){return page.evaluate(()=>{
 const header=document.querySelector('header'),titulo=header.querySelector('h1'),nav=header.querySelector('.ro-header-navigation'),main=document.querySelector('main');
 const caixa=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height,right:r.right,bottom:r.bottom};};
 const estilo=e=>{const s=getComputedStyle(e);return {font:s.font,color:s.color,background:s.backgroundColor,padding:s.padding,border:s.border,shadow:s.boxShadow};};
 const range=document.createRange();range.selectNodeContents(titulo);
 const identidade=(()=>{const e=header.querySelector('.ro-identity');if(!e)return null;const r=document.createRange();r.selectNodeContents(e);const a=r.getBoundingClientRect(),b=e.getBoundingClientRect();return {x:Math.max(a.left,b.left),right:Math.min(a.right,b.right),y:a.top,bottom:a.bottom};})();
 return {header:caixa(header),titulo:caixa(titulo),tituloStyle:estilo(titulo),linhas:[...range.getClientRects()].filter(r=>r.width&&r.height).map(r=>({x:r.x,y:r.y,right:r.right,bottom:r.bottom})),
  nav:[...nav.querySelectorAll('a,button')].filter(e=>e.getClientRects().length).map(e=>({box:caixa(e),style:estilo(e),text:e.textContent.trim(),href:e.getAttribute('href'),onclick:e.getAttribute('onclick')})),
  textos:[...header.querySelectorAll('.ro-header-titles > p')].filter(e=>e.getClientRects().length).map(e=>({box:caixa(e),style:estilo(e),text:e.textContent.trim()})),
  cards:[...main.querySelectorAll(':scope > .card')].map(e=>({box:caixa(e),style:estilo(e)})),main:caixa(main),identidade,overflow:document.documentElement.scrollWidth>innerWidth};
});}
const perto=(a,b,label,t=.16)=>assert.ok(Math.abs(a-b)<t,`${label}: ${a} / ${b}`);
const colide=(a,b)=>a.x<b.right-.05&&a.right>b.x+.05&&a.y<b.bottom-.05&&a.bottom>b.y+.05;
function verificar(a,b,reference,label,extenso){
 if(extenso)assert.ok(b.header.h>=reference.header.h-.16,label+' altura mínima');else perto(b.header.h,reference.header.h,label+' altura');
 perto(b.titulo.x+b.titulo.w/2,b.header.x+b.header.w/2,label+' centro horizontal');
 perto(b.titulo.y+b.titulo.h/2-b.header.y,b.header.h/2-5,label+' centro vertical');
 assert.ok(b.titulo.y>=b.header.y-.16&&b.titulo.bottom<=b.header.bottom+.16,label+' título na faixa');
 assert.deepEqual(b.tituloStyle,a.tituloStyle,label+' fonte e cor do título');
 assert.equal(b.nav.length,a.nav.length,label+' navegação');
 for(let i=0;i<b.nav.length;i++){
  const x=a.nav[i],y=b.nav[i];assert.equal(y.text,x.text);assert.equal(y.href,x.href);assert.equal(y.onclick,x.onclick);assert.deepEqual(y.style,x.style,label+' estilo do controle');
  perto(y.box.w,x.box.w,label+' largura do controle');perto(y.box.h,x.box.h,label+' altura do controle');
  assert.ok(!b.linhas.some(l=>colide(l,y.box)),label+' colisão título/controle');
  assert.ok(y.box.bottom<=b.main.y+.2||y.box.y>=b.main.bottom-.2,label+' colisão controle/conteúdo');
  assert.ok(y.box.x>=-.2&&y.box.right<=b.header.w+.2,label+' controle fora da tela');
  for(const texto of b.textos)assert.ok(!colide(y.box,texto.box),label+' colisão controle/texto');
 }
 assert.equal(b.textos.length,a.textos.length,label+' textos auxiliares');
 for(let i=0;i<b.textos.length;i++){const x=a.textos[i],y=b.textos[i];assert.equal(y.text,x.text);assert.deepEqual(y.style,x.style);perto(y.box.w,x.box.w,label+' largura texto');perto(y.box.h,x.box.h,label+' altura texto');assert.ok(!b.linhas.some(l=>colide(l,y.box)),label+' colisão texto/título');assert.ok(y.box.bottom<=b.main.y+.2,label+' colisão texto/conteúdo');}
 assert.equal(b.cards.length,a.cards.length,label+' cards');
 for(let i=0;i<b.cards.length;i++){const x=a.cards[i],y=b.cards[i];assert.deepEqual(y.style,x.style,label+' estilo card');perto(y.box.x,x.box.x,label+' card x');perto(y.box.w,x.box.w,label+' card largura');perto(y.box.h,x.box.h,label+' card altura');}
 if(b.identidade)assert.ok(!b.linhas.some(l=>colide(l,b.identidade)),label+' identificação/título');
 assert.ok(!b.overflow||a.overflow,label+' overflow');
}
(async()=>{
 assert.equal(paginas.length,17,'Inventário das páginas administrativas');
 for(const file of excecoes)assert.equal(fs.readFileSync(path.join(root,'admin',file),'utf8'),original(`admin/${file}`).toString(),file+' deve permanecer inalterado');
 for(const file of paginas){const html=fs.readFileSync(path.join(root,'admin',file),'utf8');assert.ok(html.includes('admin-cabecalho-padrao.css')&&html.includes('admin-cabecalho-padrao.js'),file+' deve aderir ao padrão');}
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH,args:['--no-sandbox']});
 try{
  const referencias={};
  for(const width of [1366,768,390,320]){
   const referencia=await abrir(browser,width,'index.html',true), medidaRef=await medir(referencia);await referencia.close();referencias[width]=medidaRef;
   for(const file of paginas){
    const [antes,depois]=await Promise.all([abrir(browser,width,file,true),abrir(browser,width,file,false)]);
    verificar(await medir(antes),await medir(depois),medidaRef,`${file}/${width}`,false);
    for(const control of await depois.locator('header .ro-header-navigation a:visible,header .ro-header-navigation button:visible').all())await control.click({trial:true,timeout:3000});
    for(const page of [antes,depois])await page.evaluate(()=>{const e=document.createElement('div');e.id='nomeUsuarioLogadoGlobal';e.textContent='Alexandrinaconstantinopolitana';e.title='Alexandrinaconstantinopolitana Silva';e.style.fontSize='.68rem';document.body.append(e);document.querySelector('header h1').textContent='⚙️ Administração de Cursos, Disciplinas e Avaliações da Plataforma';});
    await Promise.all([antes.waitForTimeout(300),depois.waitForTimeout(300)]);
    verificar(await medir(antes),await medir(depois),medidaRef,`${file}/${width}/nome e título extensos`,true);
    await Promise.all([antes.close(),depois.close()]);
   }
   console.log(`${width}px: ${paginas.length} páginas, controles e títulos extensos OK`);
  }
  for(const file of paginas){
   const page=await abrir(browser,1366,file,false);
   await page.evaluate(()=>{const e=document.createElement('div');e.id='nomeUsuarioLogadoGlobal';e.textContent='Alexandrinaconstantinopolitana';e.title='Alexandrinaconstantinopolitana Silva';document.body.append(e);});
   for(const width of [320,768,390,1366]){
    await page.setViewportSize({width,height:900});await page.waitForTimeout(350);
    const b=await medir(page),r=referencias[width],label=`${file}/${width}/resize`;
    assert.ok(b.header.h>=r.header.h-.16,label+' altura');
    perto(b.titulo.x+b.titulo.w/2,b.header.x+b.header.w/2,label+' centro horizontal');
    perto(b.titulo.y+b.titulo.h/2-b.header.y,b.header.h/2-5,label+' centro vertical');
    for(const n of b.nav){assert.ok(!b.linhas.some(l=>colide(l,n.box)),label+' navegação');assert.ok(n.box.bottom<=b.main.y+.2,label+' navegação/conteúdo');}
    if(b.identidade)assert.ok(!b.linhas.some(l=>colide(l,b.identidade)),label+' identificação');
   }
   await page.evaluate(()=>window.scrollTo(0,document.documentElement.scrollHeight));
   const posicao=await page.evaluate(()=>window.scrollY);
   await page.evaluate(()=>window.dispatchEvent(new Event('resize')));await page.waitForTimeout(250);
   perto(await page.evaluate(()=>window.scrollY),posicao,`${file}/rolagem`);
   await page.close();
  }
  console.log('Redimensionamentos sucessivos e rolagem: OK');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
