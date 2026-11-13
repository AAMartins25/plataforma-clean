const {chromium}=require('/tmp/resumao-visual-tools/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),http=require('node:http');
(async()=>{
 const root=process.env.DIAG_ROOT||path.resolve(process.cwd(),'site-html');const out=process.env.DIAG_OUT;fs.mkdirSync(out,{recursive:true});
 let server,origin=process.env.DIAG_ORIGIN;
 if(!origin){server=http.createServer((req,res)=>{const p=path.resolve(root,'.'+new URL(req.url,'http://local').pathname);if(!p.startsWith(root+'/')||!fs.existsSync(p)){res.writeHead(404).end();return}res.setHeader('Content-Type',({'.html':'text/html','.css':'text/css','.js':'text/javascript','.svg':'image/svg+xml'})[path.extname(p)]||'application/octet-stream');res.end(fs.readFileSync(p))});await new Promise(r=>server.listen(0,'127.0.0.1',r));origin=`http://127.0.0.1:${server.address().port}`}
 const browser=await chromium.launch({executablePath:'/home/codespace/.cache/ms-playwright/chromium-1254/chrome-linux64/chrome',args:['--no-sandbox']});
 const samples=[],assets={};
 const actual=[{id:39,nome:'RESUMÃO PROF EDUC INFANTIL ALVORADA-RS 26',ativo:true,publicado:true,cargo:null,orgao:null,uf:null,ano:null}];
 try{
  for(const width of [320,390,768,1366])for(const signedIn of [false,true]){
   const ctx=await browser.newContext({viewport:{width,height:900}});
   if(signedIn)await ctx.addInitScript(()=>{localStorage.setItem('access_token','token-local-ficticio');localStorage.setItem('pagina_antes_inicio','cursos.html')});
   await ctx.route('**/*',async route=>{
    const req=route.request(),url=new URL(req.url());
    if(req.method()!=='GET')return route.abort();
    if(url.origin===origin)return route.continue();
    if(url.origin==='https://plataforma-quality-backend.onrender.com'){
     if(url.pathname==='/cursos-publicos')return route.fulfill({json:actual});
     if(url.pathname==='/me')return route.fulfill({json:{id:1,nome:'Alexandre de Oliveira Administrador',ativo:true,is_aluno:true}});
    }
    return route.abort();
   });
   const page=await ctx.newPage();const pending=[];
   page.on('response',r=>{const u=new URL(r.url());if(u.origin===origin&&['/css/style.css','/css/home-publica.css','/js/cabecalho.js','/js/app.js'].includes(u.pathname))pending.push((async()=>{const b=await r.body();const local=fs.readFileSync(path.join(root,u.pathname));assets[u.pathname]={status:r.status(),sha256:crypto.createHash('sha256').update(b).digest('hex'),sameAsOriginMain:b.equals(local)}})())});
   await page.goto(origin+'/index.html');await page.locator('.curso-publico-card').waitFor();if(signedIn)await page.locator('.ro-header-identity').waitFor();
   const result=await page.evaluate(()=>{
    const selectors=['.home-header','.ro-header-identity','.ro-identity','.ro-header-titles','.home-brand','.home-brand-title','.home-brand-symbol','.home-brand-wordmark','.home-brand-name','.home-brand-tagline','.ro-header-access','.ro-header-navigation'];
    const rect=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}};
    const props=['display','height','minHeight','paddingTop','paddingBottom','marginTop','marginBottom','position','gridTemplateRows','gridRowStart','rowGap','alignItems','justifyContent'];
    const nodes={};for(const selector of selectors){const e=document.querySelector(selector);if(e){const st=getComputedStyle(e);nodes[selector]={rect:rect(e),styles:Object.fromEntries(props.map(k=>[k,st[k]]))};if(selector==='.ro-identity')nodes[selector].after=Object.fromEntries(['display','position','height','visibility','marginTop'].map(k=>[k,getComputedStyle(e,'::after')[k]]))}}
    return {nodes,overflow:document.documentElement.scrollWidth>innerWidth,headerHTML:document.querySelector('.home-header').outerHTML};
   });
   samples.push({width,signedIn,...result});await page.screenshot({path:path.join(out,`${width}-${signedIn?'logado':'publico'}.png`),fullPage:true});await Promise.all(pending);await ctx.close();
  }
  fs.writeFileSync(path.join(out,'diagnostico.json'),JSON.stringify({origin,assets,samples},null,2));
  console.log(JSON.stringify({assets,measurements:samples.map(s=>({width:s.width,signedIn:s.signedIn,brandTop:s.nodes['.home-brand-title'].rect.y,nameTop:s.nodes['.home-brand-name'].rect.y,identityHeight:s.nodes['.ro-header-identity']?.rect.h,identityMin:s.nodes['.ro-identity']?.styles.minHeight,gap:s.nodes['.home-header'].styles.rowGap,header:s.nodes['.home-header'].styles,pseudo:s.nodes['.ro-identity']?.after}))},null,2));
 }finally{await browser.close();if(server)await new Promise(r=>server.close(r))}
})().catch(e=>{console.error(e);process.exitCode=1});
