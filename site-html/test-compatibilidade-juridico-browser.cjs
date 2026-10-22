// Chromium com toda a rede interceptada, inclusive a API e a preferência simulada.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const documentos=JSON.parse(fs.readFileSync('backend/documentos_juridicos/1.0/manifesto.json')).documentos;
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE});
 let casos=0;
 try{
  for(const file of ['curso-info.html','checkout.html'])for(const antigo of [true,false])for(const modo of ['404','desativado','ativo','503','rede']){
   const ctx=await browser.newContext(),page=await ctx.newPage();const erros=[],posts=[];
   let politica=modo,modulos=0;
   page.on('pageerror',e=>erros.push(e.message));
   await ctx.route('**/*',async route=>{
    const url=new URL(route.request().url());
    if(url.hostname==='127.0.0.1'){
     const nome=url.pathname.slice(1);
     const texto=antigo&&nome===file?execFileSync('git',['show','origin/main:site-html/'+file]):null;
     if(nome==='js/juridico.js')modulos++;
     const arquivo=path.resolve('site-html',nome);
     if(!texto&&!fs.existsSync(arquivo))return route.fulfill({status:404,body:''});
     return route.fulfill({body:texto||fs.readFileSync(arquivo),contentType:nome.endsWith('.js')?'application/javascript':nome.endsWith('.css')?'text/css':nome.endsWith('.pdf')?'application/pdf':'text/html'});
    }
    const headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*','Access-Control-Allow-Methods':'*'};
    if(route.request().method()==='OPTIONS')return route.fulfill({status:204,headers});
    if(url.pathname==='/public/juridico/vigente'){
     if(politica==='rede')return route.abort('failed');
     if(politica==='404'||politica==='503')return route.fulfill({status:Number(politica),json:{detail:'Simulado'},headers});
     return route.fulfill({json:{obrigatorio:politica==='ativo',documentos:politica==='ativo'?documentos.map(d=>({id:d.tipo==='TERMOS'?1:2,tipo:d.tipo,titulo:d.titulo,versao:d.versao,pdf_site_url:d.site_url})):[]},headers});
    }
    if(url.pathname==='/checkout/mercadopago'){
     const pedido=route.request().postDataJSON();posts.push(pedido);
     if(politica==='ativo'&&!pedido.aceite_juridico?.aceito)return route.fulfill({status:400,json:{detail:'ACEITE_OBRIGATORIO'},headers});
     return route.fulfill({json:{init_point:page.url()+'#simulado'},headers});
    }
    let json={};
    if(url.pathname==='/me')json={id:1,nome:'Aluno Teste',is_admin:false};
    if(url.pathname==='/public/cursos/1/checkout')json={id:1,nome:'Curso Teste',disciplinas:[],tempos_acesso:[{id:1,meses:4,valor_cents:4990},{id:2,meses:8,valor_cents:9980}]};
    return route.fulfill({json,headers});
   });
   await page.addInitScript(()=>localStorage.setItem('access_token','simulado'));
   const renovacao=file==='checkout.html';
   await page.goto(`http://127.0.0.1:8769/${file}?curso_id=1${renovacao?'&renovacao=1&contratacao_id=7':''}`);
   await page.locator('input[data-tempo-id="1"]').check();
   await page.locator('#btnAdquirirAgora').click();
   const msg=page.locator(file==='checkout.html'?'#msgCheckout':'#msgCursoInfo');
   if(modo==='ativo'){
    await page.locator('#aceiteJuridico').waitFor();assert.equal(await page.locator('#aceiteJuridico').isChecked(),false);
    await msg.filter({hasText:'Confirme'}).waitFor();assert.equal(posts.length,0);
    assert.equal(await page.locator('#linkTermos').getAttribute('href'),'http://127.0.0.1:8769/'+documentos.find(d=>d.tipo==='TERMOS').site_url);
    for(const width of [320,375,768,1440]){
     await page.setViewportSize({width,height:900});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    }
    await page.locator('#aceiteJuridico').check();await page.locator('input[data-tempo-id="2"]').check();
    assert.equal(await page.locator('#aceiteJuridico').isChecked(),false);
    await page.locator('#aceiteJuridico').check();await page.locator('#btnAdquirirAgora').click();
    await page.waitForURL('**/*#simulado');assert.equal(posts.length,1);assert.equal(posts[0].aceite_juridico.termos_id,1);
   }else if(['rede','503'].includes(modo)){
    await msg.filter({hasText:'Não foi possível confirmar a política jurídica'}).waitFor();assert.equal(posts.length,0);
    assert.equal(await page.locator('#btnAdquirirAgora').isEnabled(),true);
    politica='desativado';await page.locator('#btnAdquirirAgora').click();await page.waitForURL('**/*#simulado');assert.equal(posts.length,1);
   }else{
    await page.waitForURL('**/*#simulado');assert.equal(posts.length,1);assert.equal(posts[0].aceite_juridico,undefined);
   }
   if(renovacao){assert.equal(posts[0].tipo_compra,'RENOVACAO');assert.equal(posts[0].contratacao_id,7);}
   if(antigo)assert.equal(modulos,1,'módulo antigo ausente deve ser carregado uma única vez');
   assert.deepEqual(erros,[]);casos++;console.log(`${file}: HTML ${antigo?'antigo':'novo'}, ${modo}: OK`);
   await ctx.close();
  }
 }finally{await browser.close();}
 console.log(`${casos} cenários Chromium aprovados; compras/renovações simuladas.`);
})().catch(e=>{console.error(e);process.exitCode=1;});
