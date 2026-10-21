// Usa HTML retornado pelo TestClient e PDFs arquivados; intercepta toda a rede.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const crypto=require('node:crypto');
(async()=>{
 const root=path.resolve('backend/documentos_juridicos/1.0');
 const evidencias=path.resolve('evidencias/aceite/documentos-v1');
 const docs=JSON.parse(fs.readFileSync(path.join(root,'manifesto.json'),'utf8')).documentos;
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE});
 try {
  for(const doc of docs){
   const id=doc.tipo==='TERMOS'?101:102;
   const html=fs.readFileSync(path.join(evidencias,`${id}.html`),'utf8');
   const texto=fs.readFileSync(path.join(root,doc.texto),'utf8');
   const ctx=await browser.newContext();const page=await ctx.newPage();
   await ctx.route('**/*',route=>{
    const url=new URL(route.request().url());
    if(url.pathname===`/documentos/${id}`)return route.fulfill({body:html,contentType:'text/html'});
    if(url.pathname===`/public/juridico/arquivos/${doc.pdf_sha256}.pdf`){
     const bytes=fs.readFileSync(path.join(root,doc.pdf));
     assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'),doc.pdf_sha256);
     return route.fulfill({body:bytes,contentType:'application/pdf'});
    }
    return route.abort();
   });
   for(const width of [320,1440]){
    await page.setViewportSize({width,height:900});
    await page.goto(`http://documentos.local/documentos/${id}`);
    assert.equal(await page.locator('pre').textContent(),texto);
    assert.equal(((await page.locator('pre').textContent()).match(/\[A PREENCHER\]/g)||[]).length,doc.campos_a_preencher);
    assert.equal(await page.locator('a').getAttribute('href'),`/public/juridico/arquivos/${doc.pdf_sha256}.pdf`);
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.screenshot({path:path.join(evidencias,`${doc.tipo}-${width}.png`),fullPage:true});
   }
   const resposta=page.waitForResponse(r=>r.url().endsWith(`${doc.pdf_sha256}.pdf`));
   await page.locator('a').click();
   assert.equal((await resposta).status(),200);
   console.log(`${doc.tipo}: texto integral, campos, link ao PDF original, 320 e 1440 px OK`);
   await ctx.close();
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
