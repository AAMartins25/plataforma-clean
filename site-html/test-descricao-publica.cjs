const assert = require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright-core');
const root=__dirname, marker='<!--resumao:descricao-publica:html:v1-->';
const server=http.createServer((req,res)=>{
 const file=path.resolve(root,'.'+new URL(req.url,'http://local').pathname);
 if(!file.startsWith(root+path.sep)||!fs.existsSync(file)){res.writeHead(404);res.end();return;}
 res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(file));
});
(async()=>{
 let browser;
 try {
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const origin=`http://127.0.0.1:${server.address().port}`;
 browser=await chromium.launch({executablePath:'/home/codespace/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell',args:['--no-sandbox']});
 for (const width of [1366,768,390,320]) {
  const page=await browser.newPage({viewport:{width,height:1000}});
  let raw='  Legado <b>literal</b> & prova\n\nSegunda linha  ', saves=[], cdnFailure=false;
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>localStorage.setItem('access_token','token-ficticio'));
  await page.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url());
   if(url.origin===origin)return route.continue();
   if(url.hostname==='cdn.ckeditor.com'){
    if(cdnFailure)return route.abort();
    if(url.pathname.endsWith('.umd.js'))return route.fulfill({contentType:'text/javascript',body:fs.readFileSync(process.env.CKEDITOR_TEST_BUNDLE||'/workspaces/resumao-editor-teoria-dev/.local/ckeditor-seguranca-tools/node_modules/ckeditor5/dist/browser/ckeditor5.umd.js')});
    if(url.pathname.endsWith('.css'))return route.fulfill({contentType:'text/css',body:fs.readFileSync('/workspaces/resumao-editor-teoria-dev/.local/ckeditor-seguranca-tools/node_modules/ckeditor5/dist/ckeditor5.css')});
    return route.abort();
   }
   if(url.hostname!=='plataforma-quality-backend.onrender.com')return route.abort();
   let json={};const p=url.pathname;
   if(p==='/me')json={id:2,nome:'ADM teste',is_admin:true,tipo_admin:'admin_geral',ativo:true};
   else if(p==='/cursos')json=req.method()==='POST'?{id:1,nome:'Curso novo',ativo:true,publicado:false}:[{id:1,nome:'Curso teste',ativo:true,publicado:true}];
   else if(p==='/admin/ckeditor-chave')json={licenseKey:'GPL'};
   else if(p==='/admin/cursos/1/config-publica'){
    if(req.method()==='PUT'){const body=req.postDataJSON();saves.push(body);raw=body.descricao_publica_formato==='html_v1'?marker+body.descricao_publica:body.descricao_publica;json={ok:true};}
    else json={curso_id:1,publicado:true,descricao_publica:raw,tempos_acesso:[4,8,12].map((meses,i)=>({id:i+1,meses,valor_cents:4990*(i+1)}))};
   }
   else if(p==='/cursos/1/disciplinas-proprias')json=[];
   else if(p==='/public/cursos/1/checkout')json={id:1,nome:'Curso teste',descricao_publica:raw.startsWith(marker)?'Versão textual':raw,descricao_publica_html:raw.startsWith(marker)?raw.slice(marker.length):null,disciplinas:[],tempos_acesso:[]};
   else if(p==='/public/juridico/vigente')json={obrigatorio:false,documentos:[]};
   else throw Error('Rota não prevista '+p);
   return route.fulfill({json,headers:{'Access-Control-Allow-Origin':'*'}});
  });
  async function abrir(){
   await page.goto(origin+'/admin/criar-curso-completo.html');
   await page.locator('#cursoExistenteSelect option[value="1"]').waitFor({state:'attached'});
   await page.selectOption('#cursoExistenteSelect','1');await page.click('#btnUsarCursoExistente');
   await page.waitForFunction(()=>document.querySelector('#avisoDescricaoPublica')?.textContent==='');
  }
  await abrir();
  assert.equal(await page.locator('#boxConfigPublicaCurso .ck-content').getAttribute('contenteditable'),'false');
  await page.click('#btnEditarConfigPublicaCurso');
  await page.waitForFunction(()=>document.querySelector('#boxConfigPublicaCurso .ck-content').getAttribute('contenteditable')==='true');
  assert.ok((await page.locator('#boxConfigPublicaCurso .ck-content').textContent()).includes('<b>literal</b>'));
  await page.click('#btnSalvarConfigPublicaCurso');await page.waitForFunction(()=>document.querySelector('#msgConfigPublicaCurso').textContent.includes('sucesso'));
  assert.equal(saves.at(-1).descricao_publica,raw);assert.equal(saves.at(-1).descricao_publica_formato,undefined);
  await page.click('#btnEditarConfigPublicaCurso');
  await page.evaluate(()=>{
   const editable=document.querySelector('#boxConfigPublicaCurso .ck-editor__editable');
   editable.ckeditorInstance.setData('<h2>Curso completo</h2><p><strong>Negrito</strong> e <i>itálico</i></p><ul><li>Um</li><li>Dois</li></ul><ol><li>Primeiro</li></ol><p>'+('L'.repeat(250))+'</p>');
  });
  await page.click('#btnSalvarConfigPublicaCurso');await page.waitForFunction(()=>document.querySelector('#msgConfigPublicaCurso').textContent.includes('sucesso'));
  assert.equal(saves.at(-1).descricao_publica_formato,'html_v1');
  assert.deepEqual(saves.at(-1).tempos_acesso,[4,8,12].map((meses,i)=>({meses,valor_cents:4990*(i+1)})));
  const saved=raw;await abrir();assert.ok((await page.locator('#boxConfigPublicaCurso .ck-content').innerHTML()).includes('<strong>Negrito</strong>'));
  await page.click('#btnEditarConfigPublicaCurso');await page.click('#btnSalvarConfigPublicaCurso');await page.waitForFunction(()=>document.querySelector('#msgConfigPublicaCurso').textContent.includes('sucesso'));assert.equal(raw,saved);
  assert.ok(await page.evaluate(()=>{const el=document.querySelector('#boxConfigPublicaCurso .ck-editor');return el.getBoundingClientRect().right<=innerWidth}),`overflow editor ${width}`);
  await page.screenshot({path:path.join(root,'../evidencias',`adm-${width}.png`),fullPage:true});
  raw+='<img src=x onerror="window.xss=1"><script>window.xss=1</script><svg onload="window.xss=1"></svg>';
  await page.goto(origin+'/curso-info.html?curso_id=1');await page.locator('#informacoes_curso h2').waitFor({state:'attached'});
  await page.evaluate(()=>document.querySelector('#informacoes_curso').style.display='block');
  assert.equal(await page.locator('#informacoes_curso strong').textContent(),'Negrito');
  assert.equal(await page.locator('#informacoes_curso ul li').count(),2);
  assert.equal(await page.locator('#informacoes_curso img, #informacoes_curso script, #informacoes_curso svg').count(),0);
  assert.equal(await page.evaluate(()=>window.xss),undefined);
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`overflow público ${width}`);
  await page.screenshot({path:path.join(root,'../evidencias',`publico-${width}.png`),fullPage:true});
  raw='  Legado <b>literal</b>\n\n2 < 3  ';
  await page.goto(origin+'/curso-info.html?curso_id=1');
  await page.waitForFunction(()=>document.querySelector('#informacoes_curso').textContent.includes('2 < 3'));
  assert.equal(await page.locator('#informacoes_curso').textContent(),raw);
  assert.equal(await page.locator('#informacoes_curso b').count(),0);
  await page.goto(origin+'/admin/criar-curso-completo.html');
  await page.fill('#cursoNome','Curso novo');
  await page.locator('#formCurso button[type="submit"]').click();
  await page.waitForFunction(()=>document.querySelector('#avisoDescricaoPublica')?.textContent==='');
  await page.waitForFunction(()=>document.querySelector('#boxConfigPublicaCurso .ck-content')?.getAttribute('contenteditable')==='true');
  assert.equal(await page.locator('#boxConfigPublicaCurso .ck-content').textContent(),'');
  cdnFailure=true;
  for(const valor of [raw,saved]) {
   raw=valor;
   await page.goto(origin+'/admin/criar-curso-completo.html');
   await page.locator('#cursoExistenteSelect option[value="1"]').waitFor({state:'attached'});
   await page.selectOption('#cursoExistenteSelect','1');await page.click('#btnUsarCursoExistente');
   await page.waitForFunction(()=>document.querySelector('#avisoDescricaoPublica')?.textContent.includes('indisponível'));
   await page.click('#btnEditarConfigPublicaCurso');
   assert.equal(await page.locator('#cursoDescricaoPublica').isDisabled(),valor.startsWith(marker));
   await page.click('#btnSalvarConfigPublicaCurso');
   await page.waitForFunction(()=>document.querySelector('#msgConfigPublicaCurso').textContent.includes('sucesso'));
   assert.equal(saves.at(-1).descricao_publica,valor);
  }
  assert.deepEqual(errors,[]);await page.close();
  console.log(`OK ADM/HTML/legado/XSS/responsividade ${width}px`);
 }
 } finally {if(browser)await browser.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
