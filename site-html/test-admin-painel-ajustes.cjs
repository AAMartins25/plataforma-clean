// PLAYWRIGHT_MODULE=/caminho/playwright-core CHROMIUM_PATH=/caminho/chromium node site-html/test-admin-painel-ajustes.cjs
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{execFileSync}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright-core');
const root=__dirname,origin='http://admin-ajustes.test', mime={'.html':'text/html','.css':'text/css','.js':'text/javascript'};
const baseCache=new Map();
function base(file){if(!baseCache.has(file))baseCache.set(file,execFileSync('git',['show',`${process.env.ADMIN_BASE_REF || "8ff8ece"}:site-html/${file}`],{cwd:root}));return baseCache.get(file);}
async function abrir(browser,width,old){
 const page=await browser.newPage({viewport:{width,height:900}});
 await page.route('**/*',route=>{
  const u=new URL(route.request().url()),rel=u.pathname.replace(/^\/(?:base\/)?/,''),file=path.resolve(root,rel);
  if(u.origin!==origin||!file.startsWith(root+path.sep)||(!old && !fs.existsSync(file)))return route.abort();
  let body=old?base(rel):fs.readFileSync(file);
  if(file.endsWith('.html'))body=Buffer.from(body.toString().replace(/<script\b([^>]*)>[\s\S]*?<\/script>/gi,(all,attrs)=>{
   const src=attrs.match(/src=["']([^"']+)/i)?.[1]?.split('/').at(-1).split('?')[0];
   return ['cabecalho.js','admin-painel-cabecalho.js','admin-painel-espacos.js'].includes(src)?all:'';
  }));
  return route.fulfill({body,contentType:mime[path.extname(file)]||'application/octet-stream'});
 });
 await page.goto(`${origin}${old?'/base':''}/admin/index.html`);await page.locator('.painel-compacto').waitFor();await page.waitForTimeout(250);return page;
}
async function medir(page){return page.evaluate(()=>{
 const h=document.querySelector('header'),card=document.querySelector('main>.card');
 const box=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height,bottom:r.bottom};};
 const style=e=>{const s=getComputedStyle(e);return {font:s.font,color:s.color,background:s.backgroundColor,border:s.border,padding:s.padding,shadow:s.boxShadow};};
 return {header:box(h),title:box(h.querySelector('h1')),titleStyle:style(h.querySelector('h1')),card:box(card),cardStyle:style(card),elements:[...card.querySelectorAll(':scope>h2,:scope>section>h3,:scope>section>.list>.btn')].filter(e=>e.getClientRects().length).map(e=>({tag:e.tagName,text:e.textContent.trim(),href:e.getAttribute('href'),onclick:e.getAttribute('onclick'),box:box(e),style:style(e)})),overflow:document.documentElement.scrollWidth>innerWidth};
});}
const near=(a,b,label,t=.1)=>assert.ok(Math.abs(a-b)<t,`${label}: ${a} / ${b}`);
(async()=>{const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH,args:['--no-sandbox']});try{
 for(const width of [1366,768,390,320]){
  const [old,now]=await Promise.all([abrir(browser,width,true),abrir(browser,width,false)]);
  const a=await medir(old),b=await medir(now),label=`${width}px`;
  near(b.header.h,a.header.h,label+' altura cabeçalho');near(b.title.y,a.title.y-3,label+' título');near(b.title.x,a.title.x,label+' título horizontal');assert.deepEqual(b.titleStyle,a.titleStyle);
  near(b.card.w,a.card.w*.96,label+' largura card');near(b.card.x+b.card.w/2,a.card.x+a.card.w/2,label+' centro card');near(b.card.y,a.card.y,label+' topo card');assert.deepEqual(b.cardStyle,a.cardStyle);assert.equal(b.overflow,a.overflow);
  assert.equal(b.elements.length,a.elements.length);
  const botoes=b.elements.filter(e=>e.tag==='A');
  near(b.card.bottom-botoes.at(-1).box.bottom,botoes[1].box.y-botoes[0].box.bottom,label+' espaço inferior');
  near(a.card.h-b.card.h,(a.card.bottom-a.elements.at(-1).box.bottom)-(b.card.bottom-b.elements.at(-1).box.bottom),label+' altura ajustada ao conteúdo');
  for(let i=0;i<a.elements.length;i++){let x=a.elements[i],y=b.elements[i];assert.equal(y.text,x.text);assert.equal(y.href,x.href);assert.equal(y.onclick,x.onclick);assert.deepEqual(y.style,x.style);near(y.box.h,x.box.h,label+' altura '+x.text);near(y.box.y,x.box.y,label+' posição vertical '+x.text);if(x.tag==='A'){near(y.box.w,x.box.w*.96,label+' largura '+x.text);near(y.box.x+y.box.w/2,x.box.x+x.box.w/2,label+' centro '+x.text);}else near(y.box.x,x.box.x+(b.card.x-a.card.x),label+' alinhamento '+x.text);}
  await Promise.all([old.close(),now.close()]);console.log(label+' dimensões e título OK');
 }
 }finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
