const assert = require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {spawnSync}=require('node:child_process');
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
 browser=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE||'/home/codespace/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell',args:['--no-sandbox']});
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
    if(url.pathname.endsWith('.css'))return route.fulfill({contentType:'text/css',body:fs.readFileSync(process.env.CKEDITOR_TEST_CSS||'/workspaces/resumao-editor-teoria-dev/.local/ckeditor-seguranca-tools/node_modules/ckeditor5/dist/ckeditor5.css')});
    return route.abort();
   }
   if(url.hostname!=='plataforma-quality-backend.onrender.com')return route.abort();
   let json={};const p=url.pathname;
   if(p==='/me')json={id:2,nome:'ADM teste',is_admin:true,tipo_admin:'admin_geral',ativo:true};
   else if(p==='/admin/cursos')json=[{id:1,nome:'Curso teste',ativo:true,publicado:true}];
   else if(p==='/cursos')json=req.method()==='POST'?{id:1,nome:'Curso novo',ativo:true,publicado:false}:[{id:1,nome:'Curso teste',ativo:true,publicado:true}];
   else if(p==='/admin/ckeditor-chave')json={licenseKey:'GPL'};
   else if(p==='/admin/cursos/1/config-publica'){
    if(req.method()==='PUT'){const body=req.postDataJSON();saves.push(body);const clean=spawnSync(process.env.DESCRICAO_TEST_PYTHON||'python',['-c','import json,sys;sys.path.insert(0,"backend");from app.descricao_publica import preparar_descricao;print(json.dumps(preparar_descricao(json.load(sys.stdin),None)))'],{cwd:path.join(root,'..'),input:JSON.stringify(body),encoding:'utf8'});assert.equal(clean.status,0,clean.stderr);raw=JSON.parse(clean.stdout);json={ok:true};}
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
  const botaoMarkdown=page.locator('#boxConfigPublicaCurso .teoria-markdown-controles button');
  async function verificarBloqueio(bloqueado) {
   assert.equal(await botaoMarkdown.isDisabled(),bloqueado);
   assert.equal(await botaoMarkdown.evaluate(el=>getComputedStyle(el).opacity),bloqueado?'0.45':'1');
   if (bloqueado) {
    await botaoMarkdown.evaluate(el=>el.click());
    assert.equal(await page.locator('.teoria-markdown-dialogo[open]').count(),0);
   }
  }
  await verificarBloqueio(true);
  await page.click('#btnEditarConfigPublicaCurso');
  await page.waitForFunction(()=>document.querySelector('#boxConfigPublicaCurso .ck-content').getAttribute('contenteditable')==='true');
  await verificarBloqueio(false);
  const importar=async texto=>{
   await page.locator('#boxConfigPublicaCurso').getByRole('button',{name:'Importar Markdown',exact:true}).click();
   assert.ok(await page.evaluate(()=>{const r=document.querySelector('.teoria-markdown-dialogo[open]').getBoundingClientRect();return r.left>=0 && r.right<=innerWidth && r.top>=0 && r.bottom<=innerHeight;}));
   await page.locator('.teoria-markdown-dialogo[open] [data-md="fonte"]').fill(texto);
   await page.locator('.teoria-markdown-dialogo[open] [data-md="aplicar"]').click();
  };
  assert.equal(await page.locator('#boxConfigPublicaCurso .teoria-markdown-controles button').count(),1);
  await importar('![imagem](https://example.com/a.png)');
  assert.match(await page.locator('.teoria-markdown-dialogo[open] [role="alert"]').textContent(),/não suporta/);
  await page.locator('.teoria-markdown-dialogo[open] [data-md="cancelar"]').click();
  assert.ok((await page.locator('#boxConfigPublicaCurso .ck-content').textContent()).includes('<b>literal</b>'));
  await page.click('#btnSalvarConfigPublicaCurso');await page.waitForFunction(()=>document.querySelector('#msgConfigPublicaCurso').textContent.includes('sucesso'));
  await verificarBloqueio(true);
  assert.equal(saves.at(-1).descricao_publica,raw);assert.equal(saves.at(-1).descricao_publica_formato,undefined);
  await page.click('#btnEditarConfigPublicaCurso');
  await importar('# Curso completo\n\n**Negrito** e *itálico*\n\n- Um\n- Dois\n\n| Modalidade | Valor |\n| --- | --- |\n| Resumo | R$ 49,90 |');
  assert.equal(await page.locator('.teoria-markdown-dialogo[open]').count(),0);
  assert.equal(await page.locator('#boxConfigPublicaCurso .ck-content strong').textContent(),'Negrito');
  assert.equal(await page.locator('#boxConfigPublicaCurso .ck-content table').count(),1);
  await page.evaluate(()=>document.querySelector('#boxConfigPublicaCurso .ck-content').ckeditorInstance.execute('undo'));
  assert.ok((await page.locator('#boxConfigPublicaCurso .ck-content').textContent()).includes('<b>literal</b>'));
  await page.evaluate(()=>document.querySelector('#boxConfigPublicaCurso .ck-content').ckeditorInstance.execute('redo'));
  await page.click('#btnSalvarConfigPublicaCurso');await page.waitForFunction(()=>document.querySelector('#msgConfigPublicaCurso').textContent.includes('sucesso'));
  assert.deepEqual(saves.at(-1).tempos_acesso,[4,8,12].map((meses,i)=>({meses,valor_cents:4990*(i+1)})));
  assert.ok(raw.includes('<strong>Negrito</strong>') && raw.includes('<table>'));
  await page.goto(origin+'/curso-info.html?curso_id=1');
  await page.locator('#informacoes_curso strong').waitFor({state:'attached'});
  assert.equal(await page.locator('#informacoes_curso strong').textContent(),'Negrito');
  assert.equal(await page.locator('#informacoes_curso table').count(),1);
  await abrir();
  assert.equal(await page.locator('#boxConfigPublicaCurso .ck-content strong').textContent(),'Negrito');
  await page.click('#btnEditarConfigPublicaCurso');
  await page.evaluate(()=>{
   const editable=document.querySelector('#boxConfigPublicaCurso .ck-editor__editable');
   editable.ckeditorInstance.setData('<h2>Curso completo</h2><p><strong>Negrito</strong> e <i>itálico</i></p><ul><li>Um</li><li>Dois</li></ul><ol><li>Primeiro</li></ol><p>'+('L'.repeat(250))+'</p>');
  });
  await page.click('#btnSalvarConfigPublicaCurso');await page.waitForFunction(()=>document.querySelector('#msgConfigPublicaCurso').textContent.includes('sucesso'));
  assert.equal(saves.at(-1).descricao_publica_formato,'html_v1');
  assert.deepEqual(saves.at(-1).tempos_acesso,[4,8,12].map((meses,i)=>({meses,valor_cents:4990*(i+1)})));
  // Insert through the real toolbar, then exercise row/column commands and cell formatting.
  await page.click('#btnEditarConfigPublicaCurso');
  let insert=page.getByRole('button',{name:'Insert table',exact:true});
  if(!await insert.isVisible())await page.getByRole('button',{name:'Show more items',exact:true}).click();
  await insert.evaluate(el=>el.scrollIntoView({block:'center',inline:'center'}));
  await insert.click();
  await page.locator('.ck-insert-table-dropdown-grid-box').first().evaluate(el=>el.click());
  await page.waitForFunction(()=>document.querySelector('#boxConfigPublicaCurso .ck-content table'));
  const dimensions=await page.evaluate(()=>{
   const e=document.querySelector('#boxConfigPublicaCurso .ck-editor__editable').ckeditorInstance;
   const size=()=>{const t=new DOMParser().parseFromString(e.getData(),'text/html').querySelector('table');return [t.rows.length,t.rows[0].cells.length];};
   const sizes=[size()];
   for(const command of ['insertTableRowBelow','insertTableColumnRight','removeTableRow','removeTableColumn']) {
    if(!e.commands.get(command).isEnabled)throw Error(command+' disabled');
    e.execute(command);sizes.push(size());
   }
   e.setData('<h2>Curso completo</h2><p><strong>Negrito</strong> e <i>itálico</i></p><ul><li>Um</li><li>Dois</li></ul><ol><li>Primeiro</li></ol><figure class="table"><table><thead><tr><th>Modalidade</th><th>Condições</th><th>Valor</th></tr></thead><tbody><tr><td rowspan="2"><strong>Resumo</strong></td><td>4 meses</td><td>R$ 49,90</td></tr><tr><td colspan="2"><i>'+('ConteúdoLongo'.repeat(30))+'</i></td></tr></tbody></table></figure>');
   return sizes;
  });
  assert.deepEqual(dimensions,[[1,1],[2,1],[2,2],[1,2],[1,1]]);
  await page.locator('#boxConfigPublicaCurso .ck-content td').first().click();
  await page.keyboard.press('End');await page.keyboard.type(' editado');
  await page.click('#btnSalvarConfigPublicaCurso');
  await page.waitForFunction(()=>document.querySelector('#msgConfigPublicaCurso').textContent.includes('sucesso'));
  assert.ok(raw.includes('<table>') && raw.includes('rowspan="2"') && raw.includes('colspan="2"') && raw.includes('editado'));
  const saved=raw;await abrir();assert.ok((await page.locator('#boxConfigPublicaCurso .ck-content').innerHTML()).includes('<strong>Negrito</strong>'));assert.equal(await page.locator('#boxConfigPublicaCurso .ck-content td[rowspan="2"]').count(),1);assert.equal(await page.locator('#boxConfigPublicaCurso .ck-content td[colspan="2"]').count(),1);
  await page.click('#btnEditarConfigPublicaCurso');await page.click('#btnSalvarConfigPublicaCurso');await page.waitForFunction(()=>document.querySelector('#msgConfigPublicaCurso').textContent.includes('sucesso'));assert.equal(raw,saved);
  assert.ok(await page.evaluate(()=>{const el=document.querySelector('#boxConfigPublicaCurso .ck-editor');return el.getBoundingClientRect().right<=innerWidth}),`overflow editor ${width}`);
  await page.screenshot({path:path.join(root,'../evidencias',`adm-${width}.png`),fullPage:true});
  raw=raw.replace('<table>','<table onclick="window.xss=1" style="width:99999px">');
  raw+='<img src=x onerror="window.xss=1"><script>window.xss=1</script><svg onload="window.xss=1"></svg>';
  await page.goto(origin+'/curso-info.html?curso_id=1');await page.locator('#informacoes_curso h2').waitFor({state:'attached'});
  await page.evaluate(()=>document.querySelector('#informacoes_curso').style.display='block');
  assert.equal(await page.locator('#informacoes_curso strong').first().textContent(),'Negrito');assert.equal(await page.locator('#informacoes_curso table').count(),1);assert.equal(await page.locator('#informacoes_curso th').count(),3);assert.equal(await page.locator('#informacoes_curso td[rowspan="2"]').count(),1);assert.equal(await page.locator('#informacoes_curso td[colspan="2"]').count(),1);
  assert.equal(await page.locator('#informacoes_curso ul li').count(),2);
  assert.equal(await page.locator('#informacoes_curso img, #informacoes_curso script, #informacoes_curso svg').count(),0);
  assert.equal(await page.locator('#informacoes_curso table[style], #informacoes_curso [onclick], #informacoes_curso [onerror]').count(),0);
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
  await page.evaluate(()=>{for(const [k,v] of Object.entries({banca:'Banca',cargo:'Cargo',orgao:'Órgão',ano:2026,uf:'AM'}))document.getElementById('novo-'+k).value=v;});
  await page.locator('#formCurso button[type="submit"]').click();
  await page.waitForFunction(()=>document.querySelector('#avisoDescricaoPublica')?.textContent==='');
  await page.waitForFunction(()=>document.querySelector('#boxConfigPublicaCurso .ck-content')?.getAttribute('contenteditable')==='true');
  assert.equal(await page.locator('#boxConfigPublicaCurso .ck-content').textContent(),'');
  await importar('# Curso novo\n\nDescrição **criada**');
  assert.equal(await page.locator('#boxConfigPublicaCurso .ck-content strong').textContent(),'criada');
  assert.ok(await page.evaluate(()=>{const b=document.querySelector('#boxConfigPublicaCurso .teoria-markdown-controles button').getBoundingClientRect();return b.left>=0 && b.right<=innerWidth;}));
  await page.fill('#valor4Meses','49,90');await page.fill('#valor8Meses','99,80');await page.fill('#valor12Meses','149,70');
  await page.click('#btnSalvarConfigPublicaCurso');await page.waitForFunction(()=>document.querySelector('#msgConfigPublicaCurso').textContent.includes('sucesso'));
  assert.deepEqual(saves.at(-1).tempos_acesso,[4,8,12].map((meses,i)=>({meses,valor_cents:4990*(i+1)})));
  assert.ok(raw.includes('<strong>criada</strong>'));
  await abrir();assert.equal(await page.locator('#boxConfigPublicaCurso .ck-content strong').textContent(),'criada');
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
