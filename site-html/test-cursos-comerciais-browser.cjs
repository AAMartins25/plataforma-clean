// Navegador real com páginas e scripts reais; API simulada, sem rede externa.
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright-core');
const root=__dirname;
const server=http.createServer((req,res)=>{
 const nome=path.resolve(root,'.'+new URL(req.url,'http://localhost').pathname);
 if(!nome.startsWith(root+path.sep)||!fs.existsSync(nome)||fs.statSync(nome).isDirectory()){res.writeHead(404);res.end();return;}
 res.setHeader('Content-Type',({'.html':'text/html; charset=utf-8','.js':'text/javascript','.css':'text/css','.woff2':'font/woff2'})[path.extname(nome)]||'application/octet-stream');res.end(fs.readFileSync(nome));
});
(async()=>{
 let browser;
 try{
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  browser=await chromium.launch({executablePath:process.env.CHROMIUM_BIN||'/home/codespace/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell',args:['--no-sandbox']});
  const origem=`http://127.0.0.1:${server.address().port}`;
  for(const width of [1280,390]){
   const page=await browser.newPage({viewport:{width,height:900}});
   let publicado=true,ativo=true,permitirExcluir=false;const calls=[],alerts=[],erros=[];
   page.on('pageerror',e=>erros.push(e.message));
   page.on('dialog',async d=>{alerts.push(d.message());await d.accept(d.type()==='prompt'?'Nome atualizado':undefined)});
   await page.addInitScript(()=>localStorage.setItem('access_token','token-local-ficticio'));
   await page.route('**/*',async route=>{
    const req=route.request(),url=new URL(req.url());
    if(req.url().startsWith(origem+'/'))return route.continue();
    if(url.origin!=='https://plataforma-quality-backend.onrender.com')return route.abort();
    const p=url.pathname,method=req.method();let json={},status=200;
    calls.push({p,method,body:req.postDataJSON()});
    if(p==='/me')json={id:2,nome:'ADM fictício',is_admin:true,tipo_admin:'admin_geral',ativo:true};
    else if(p==='/cursos')json=ativo?[{id:1,nome:'Curso teste',ativo,publicado}]:[];
    else if(p==='/admin/cursos/1/config-publica')json={curso_id:1,publicado,tempos_acesso:[],descricao_publica:'Descrição'};
    else if(p==='/cursos/1/disciplinas-proprias')json=[];
    else if(p==='/admin/cursos/1/retirar-venda'){assert.equal(method,'PUT');publicado=false;json={ok:true,publicado};}
    else if(p==='/admin/cursos/1/publicar'){assert.equal(method,'PUT');publicado=true;json={ok:true,publicado};}
    else if(p==='/cursos/1'&&method==='PUT'){assert.deepEqual(req.postDataJSON(),{nome:'Nome atualizado'});json={id:1,nome:'Nome atualizado',ativo};}
    else if(p==='/cursos/1'&&method==='DELETE'){
     if(permitirExcluir){ativo=false;publicado=false;json={id:1,ativo};}
     else{status=409;json={detail:'Este curso possui vínculos acadêmicos ou financeiros. Utilize Desativar venda.'};}
    }
    else if(p==='/public/cursos/1/checkout')json={id:1,nome:'Curso teste',publicado:false,disciplinas:[],tempos_acesso:[{id:1,meses:4,valor_cents:4990}]};
    else if(p==='/public/juridico/vigente')json={obrigatorio:false,documentos:[]};
    else if(p==='/checkout/mercadopago'){status=409;json={detail:'A venda deste curso está desativada.'};}
    else throw Error('Rota não prevista no teste: '+p);
    await route.fulfill({status,json,headers:{'Access-Control-Allow-Origin':'*'}});
   });
   await page.goto(origem+'/admin/criar-curso-completo.html');
   await page.locator('#cursoExistenteSelect option[value="1"]').waitFor({state:'attached'});
   await page.locator('#cursoExistenteSelect').selectOption('1');await page.locator('#btnUsarCursoExistente').click();
   await page.locator('#btnRetirarCursoVenda').waitFor({state:'visible'});
   await page.locator('#btnRetirarCursoVenda').click();await page.getByRole('button',{name:'Ativar venda',exact:true}).waitFor({state:'visible'});
   assert.equal(publicado,false);assert.equal(ativo,true);
   await page.getByRole('button',{name:'Ativar venda',exact:true}).click();await page.locator('#btnRetirarCursoVenda').waitFor({state:'visible'});
   assert.equal(publicado,true);
   await page.locator('#btnExcluirCurso').click();await page.waitForFunction(()=>document.querySelector('#cursoExistenteSelect').value==='1');
   await page.waitForFunction(()=>document.querySelector('#btnRetirarCursoVenda').offsetWidth>0);
   assert.ok(alerts.some(x=>x.startsWith('Erro ao excluir curso:')&&x.includes('Desativar venda')));
   await page.locator('#btnEditarCurso').click();await page.waitForFunction(()=>document.querySelector('#msgCurso').textContent.includes('Nome atualizado'));
   assert.deepEqual(calls.find(x=>x.p==='/cursos/1'&&x.method==='PUT').body,{nome:'Nome atualizado'});
   if(process.env.VENDAS_TEST_ARTIFACTS){fs.mkdirSync(process.env.VENDAS_TEST_ARTIFACTS,{recursive:true});await page.screenshot({path:path.join(process.env.VENDAS_TEST_ARTIFACTS,`adm-${width}.png`),fullPage:true});}
   permitirExcluir=true;await page.locator('#btnExcluirCurso').click();await page.waitForFunction(()=>document.querySelector('#msgCurso').textContent.includes('conteúdo foi preservado'));
   assert.equal(ativo,false);
   for(const renovacao of [false,true]){
    await page.goto(origem+'/checkout.html?curso_id=1'+(renovacao?'&renovacao=1&contratacao_id=7':''));
    await page.locator('input[data-tempo-id="1"]').waitFor();
    assert.equal(await page.locator('input[value="demo"]').count(),0);
    assert.equal(await page.locator('#btnAdquirirAgora').innerText(),renovacao?'Renovar acesso':'Retomar pagamento');
    if(!renovacao){
     await page.locator('input[data-tempo-id="1"]').check();await page.locator('#btnAdquirirAgora').click();
     await page.waitForFunction(()=>document.querySelector('#msgCheckout').textContent.includes('venda deste curso está desativada'));
     assert.equal(await page.locator('#btnAdquirirAgora').isDisabled(),false);
    }
   }
   assert.deepEqual(erros,[]);await page.close();
   console.log(`${width}px: desativar/ativar, exclusão 409, edição sem ativo, exclusão permitida, URL direta e renovação OK`);
  }
 }finally{await browser?.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
