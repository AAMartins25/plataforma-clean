// Chromium local: nenhuma conexão externa é permitida. Requer Playwright instalado.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs=require('node:fs');
const crypto=require('node:crypto');
const documentos=JSON.parse(fs.readFileSync('backend/documentos_juridicos/1.0/manifesto.json','utf8')).documentos;
const {execFileSync} = require('node:child_process');
(async () => {
 const browser = await chromium.launch({headless:true, executablePath:process.env.CHROMIUM_EXECUTABLE});
 const results=[];
 try {
 for(const file of ['checkout.html','curso-info.html']) {
  const ctx=await browser.newContext();
  const page=await ctx.newPage();let versao=1, baseline=true, modo='ativo', posts=0;
  await ctx.route('**/*',async route=>{
   const url=new URL(route.request().url());
   if(url.hostname==='127.0.0.1') {
    if(baseline && [file,'js/app.js'].includes(url.pathname.slice(1))) {
     return route.fulfill({body:execFileSync('git',['show',`HEAD:site-html${url.pathname}`]),contentType:url.pathname.endsWith('.js')?'application/javascript':'text/html'});
    }
    const arquivo=path.join(process.cwd(),'site-html',url.pathname);
    if(!fs.existsSync(arquivo)) return route.fulfill({status:404,body:''});
    const tipo=arquivo.endsWith('.js')?'application/javascript':arquivo.endsWith('.css')?'text/css':arquivo.endsWith('.pdf')?'application/pdf':'text/html';
    return route.fulfill({body:fs.readFileSync(arquivo),contentType:tipo});
   }
   let json={};
   if(url.pathname==='/checkout/mercadopago') posts++;
   if(url.pathname==='/public/juridico/vigente' && modo==='antigo') return route.fulfill({status:404,body:'Não encontrado',headers:{'Access-Control-Allow-Origin':'*'}});
   if(url.pathname==='/public/juridico/vigente' && modo==='desativado') return route.fulfill({json:{obrigatorio:false,documentos:[]},headers:{'Access-Control-Allow-Origin':'*'}});
   if(url.pathname==='/public/juridico/vigente') json={obrigatorio:true,documentos:[
    {id:versao,tipo:'TERMOS',versao:String(versao),titulo:'FIXTURE TERMOS',pdf_site_url:documentos.find(d=>d.tipo==='TERMOS').site_url,url:'/public/juridico/documentos/'+versao},
    {id:2,tipo:'PRIVACIDADE',versao:'1',titulo:'FIXTURE PRIVACIDADE',pdf_site_url:documentos.find(d=>d.tipo==='PRIVACIDADE').site_url,url:'/public/juridico/documentos/2'}]};
   else if(url.pathname==='/public/cursos/1/checkout') json={id:1,nome:'Curso de teste',descricao_publica:'Descrição de teste',disciplinas:[],tempos_acesso:[{id:1,meses:4,valor_cents:4990},{id:2,meses:8,valor_cents:9980}]};
   else if(url.pathname==='/me') json={id:1,nome:'Aluno de teste',is_admin:false};
   await route.fulfill({json,headers:{'Access-Control-Allow-Origin':'*'}});
  });
  await page.addInitScript(()=>localStorage.setItem('access_token','fixture-token'));
  await page.goto(`http://127.0.0.1:8769/${file}?curso_id=1`);
  await page.locator('input[data-tempo-id="1"]').waitFor();
  const visual = () => page.evaluate(() => ({
   cards:[...document.querySelectorAll('.card')].slice(0,2).map(e=>{const r=e.getBoundingClientRect();return [r.x,r.y,r.width,r.height];}),
   button:['backgroundColor','color','borderRadius','fontFamily','fontSize'].map(k=>getComputedStyle(document.getElementById('btnAdquirirAgora'))[k])
  }));
  const original={};
  for(const width of [320,1440]) {
   await page.setViewportSize({width,height:900});original[width]=await visual();
   await page.screenshot({path:path.resolve(`evidencias/aceite/original-${file}-${width}.png`),fullPage:true});
  }
  baseline=false;
  await page.reload();
  await page.locator('input[data-tempo-id="1"]').waitFor();
  await page.locator('#boxAceiteJuridico').waitFor({state:'visible'});
  for(const width of [320,1440]) {
   await page.setViewportSize({width,height:900});assert.deepEqual(await visual(),original[width],`${file}: layout original`);
  }
  await page.evaluate(()=>{
   window.chamadas=[];
   apiPostAuth=async (url,payload)=>{window.chamadas.push({url,payload});await new Promise(r=>setTimeout(r,100));return {init_point:location.href+'#simulado'};};
  });
  assert.equal(await page.locator('#aceiteJuridico').isChecked(),false);
  assert.equal((await page.locator('#textoAceiteJuridico').innerText()).trim(),'Ciente dos Termos de Contratação e da Política de Privacidade e Proteção de Dados.');
  assert.notEqual(await page.locator('#linkTermos').getAttribute('href'),await page.locator('#linkPrivacidade').getAttribute('href'));
  for(const [tipo,linkId] of [['TERMOS','linkTermos'],['PRIVACIDADE','linkPrivacidade']]) {
   const doc=documentos.find(d=>d.tipo===tipo);
   const href=await page.locator('#'+linkId).getAttribute('href');
   assert.equal(href,`http://127.0.0.1:8769/${doc.site_url}`);
   const popupPromise=page.waitForEvent('popup');
   const responsePromise=ctx.waitForEvent('response',r=>r.url()===href);
   await page.locator('#'+linkId).click();
   const popup=await popupPromise;const response=await responsePromise;
   assert.equal(response.status(),200);
   assert.equal(crypto.createHash('sha256').update(fs.readFileSync('site-html/'+doc.site_url)).digest('hex'),doc.pdf_sha256);
   await popup.close();
  }

  await page.locator('input[data-tempo-id="1"]').check();
  await page.locator('#btnAdquirirAgora').click();
  await page.waitForTimeout(200);
  assert.equal(await page.evaluate(()=>chamadas.length),0);
  await page.locator('#aceiteJuridico').check();
  await page.locator('input[data-tempo-id="2"]').check();
  assert.equal(await page.locator('#aceiteJuridico').isChecked(),false);
  await page.locator('#aceiteJuridico').check();versao=3;
  await page.locator('#btnAdquirirAgora').click();await page.waitForTimeout(200);
  assert.equal(await page.evaluate(()=>chamadas.length),0);
  assert.equal(await page.locator('#aceiteJuridico').isChecked(),false);
  await page.locator('#aceiteJuridico').check();
  await page.evaluate(()=>{document.getElementById('btnAdquirirAgora').click();document.getElementById('btnAdquirirAgora').click();});
  await page.waitForTimeout(300);
  assert.equal(await page.evaluate(()=>chamadas.length),1);
  assert.equal(await page.evaluate(()=>chamadas[0].payload.aceite_juridico.termos_id),3);
  for(const width of [320,375,768,1024,1440]) {
   await page.setViewportSize({width,height:900});
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${file} overflow ${width}`);
   const box=await page.locator('#boxAceiteJuridico').boundingBox();
   assert.ok(box.x>=0 && box.x+box.width<=width+1);
   await page.screenshot({path:path.resolve(`evidencias/aceite/${file}-${width}.png`),fullPage:true});
  }
  // Retorno após login: restaura o plano, mas não o checkbox.
  if(file==='curso-info.html') {
   await page.evaluate(()=>{
    localStorage.setItem('continuar_compra_apos_login','1');
    localStorage.setItem('estado_compra_curso',JSON.stringify({curso_id:1,tempo_acesso_id:1,codigo_cupom:null}));
   });
   const antes=posts;
   await page.reload();await page.locator('#msgCursoInfo').filter({hasText:'Confirme'}).waitFor();
   assert.equal(await page.locator('#aceiteJuridico').isChecked(),false);
   assert.equal(await page.evaluate(()=>getComputedStyle(document.body).visibility),'visible');
   assert.equal(posts,antes,'retorno após login não inicia pagamento');
  }
  // Demonstração continua sem checkbox obrigatório.
  await page.reload();await page.locator('input[value="demo"]').waitFor();
  await page.evaluate(()=>{window.chamadas=[];apiPostAuth=async(url,payload)=>{chamadas.push({url,payload});throw new Error('Fim da simulação');};});
  await page.locator('input[value="demo"]').check();
  await page.locator('#btnAdquirirAgora').click();await page.waitForTimeout(100);
  assert.equal(await page.evaluate(()=>chamadas[0].url),'/cursos/1/demonstracao');
  for(modo of ['desativado','antigo']) {
   await page.reload();await page.locator('input[data-tempo-id="1"]').waitFor();
   await page.evaluate(()=>{window.chamadas=[];apiPostAuth=async(url,payload)=>{chamadas.push({url,payload});return {init_point:location.href+'#simulado'};};});
   await page.locator('input[data-tempo-id="1"]').check();
   await page.locator('#btnAdquirirAgora').click();await page.waitForTimeout(200);
   assert.equal(await page.evaluate(()=>chamadas.length),1,`${file}: compatibilidade ${modo}`);
  }
  modo='desativado';
  await page.reload();await page.locator('input[data-tempo-id="1"]').waitFor();
  await page.evaluate(()=>{window.chamadas=[];apiPostAuth=async(url,payload)=>{chamadas.push({url,payload});return {init_point:location.href+'#simulado'};};});
  await page.locator('input[data-tempo-id="1"]').check();
  await page.waitForTimeout(100);modo='ativo';
  await page.locator('#btnAdquirirAgora').click();await page.waitForTimeout(200);
  assert.equal(await page.evaluate(()=>chamadas.length),0,'ativação sem reload exige confirmação');
  await page.locator('#boxAceiteJuridico').waitFor({state:'visible'});
  await page.locator('#aceiteJuridico').check();
  await page.locator('#btnAdquirirAgora').click();await page.waitForTimeout(200);
  assert.equal(await page.evaluate(()=>chamadas.length),1);
  results.push(`${file}: bloqueio, aceite, troca de prazo/versão, duplo clique, links e 5 larguras OK`);
  await ctx.close();
 }
 console.log(results.join('\n'));
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
