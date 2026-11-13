// Integração HTTP com a aplicação FastAPI real e SQLite descartável iniciados pelo pytest.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
  const origin=process.env.HOME_REAL_ORIGIN;
  assert.ok(origin?.startsWith('http://127.0.0.1:'),'Requer servidor de teste local');
  const artifacts=process.env.HOME_REAL_ARTIFACTS;
  if(artifacts)fs.mkdirSync(artifacts,{recursive:true});
  const browser=await chromium.launch({executablePath:process.env.CHROMIUM_BIN,args:['--no-sandbox']});
  const measurements=[];
  try {
    for(const width of [320,390,768,1366])for(const signedIn of [false,true]){
      const ctx=await browser.newContext({viewport:{width,height:900}});
      if(signedIn)await ctx.addInitScript(()=>localStorage.setItem('access_token','sessao-local-simulada'));
      let contract;
      await ctx.route('**/*',async route=>{
        const url=new URL(route.request().url());
        if(url.origin===origin)return route.continue();
        if(url.origin!=='https://plataforma-quality-backend.onrender.com')return route.abort();
        if(url.pathname==='/cursos-publicos'){
          // Resposta HTTP real do endpoint; não usa JSON simulado ou função substituída.
          const response=await ctx.request.get(origin+'/cursos-publicos');
          assert.equal(response.status(),200);contract=await response.json();
          return route.fulfill({response});
        }
        if(url.pathname==='/me')return route.fulfill({json:{id:1,nome:'Alexandre de Oliveira Administrador',ativo:true,is_aluno:true}});
        return route.abort();
      });
      const page=await ctx.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
      await page.goto(origin+'/index.html');
      const card=page.locator('.curso-publico-card').filter({hasText:'Professor de Educação Infantil'}).filter({hasText:'Alvorada/RS'});
      await card.waitFor();if(signedIn)await page.locator('.ro-header-identity').waitFor();
      assert.equal(await page.locator('.curso-publico-card').count(),4);
      assert.equal(await page.locator('.home-course-arrow').count(),0);
      assert.equal(await card.locator('.home-course-meta').innerText(),'Alvorada/RS • 2026');
      assert.equal(await card.locator('.curso-publico-nome').innerText(),'Professor de Educação Infantil');
      assert.deepEqual(await card.locator('.home-course-content > span').evaluateAll(es=>es.map(e=>e.className)),['home-course-meta','curso-publico-nome']);
      const partial=page.locator('.curso-publico-card').filter({hasText:'Curso parcial'});
      assert.equal(await partial.locator('.home-course-meta').innerText(),'Órgão confirmado • 2027');
      const legacy=page.locator('.curso-publico-card').filter({hasText:'Curso antigo sem metadados'});
      assert.equal(await legacy.locator('.home-course-meta').count(),0);
      assert.equal(await page.getByLabel('Localizar curso',{exact:true}).getAttribute('placeholder'),'Digite o nome completo ou palavra(s)-chave');
      const geometry=await page.evaluate(()=>{
        const r=s=>{const b=document.querySelector(s).getBoundingClientRect();return {x:b.x,y:b.y,w:b.width,h:b.height}};
        const input=document.querySelector('#buscaCurso'),style=getComputedStyle(input),ph=getComputedStyle(input,'::placeholder');
        const canvas=document.createElement('canvas'),c=canvas.getContext('2d');c.font=`${ph.fontWeight} ${ph.fontSize} ${ph.fontFamily}`;
        const textWidth=c.measureText(input.placeholder).width+(parseFloat(ph.letterSpacing)||0)*(input.placeholder.length-1);
        const overlay=document.querySelector('.home-search-placeholder');
        const wrapped=getComputedStyle(overlay).display!=='none';
        return {placeholderWrapped:wrapped,placeholderFits:wrapped?overlay.scrollWidth<=overlay.clientWidth&&overlay.scrollHeight<=input.clientHeight:textWidth<=input.clientWidth-parseFloat(style.paddingLeft)-parseFloat(style.paddingRight),name:r('.home-brand-name'),button:r('.ro-header-access a'),brand:r('.home-brand-title'),header:r('.home-header'),input:r('#buscaCurso'),placeholderWidth:textWidth,inputTextWidth:input.clientWidth-parseFloat(style.paddingLeft)-parseFloat(style.paddingRight),overflow:document.documentElement.scrollWidth>innerWidth};
      });
      assert.equal(geometry.overflow,false);
      assert.ok(Math.abs(geometry.name.x+geometry.name.w/2-geometry.button.x-geometry.button.w/2)<.5);
      assert.ok(geometry.placeholderFits,`Placeholder ${geometry.placeholderWidth} > ${geometry.inputTextWidth} em ${width}`);
      if(artifacts){await page.screenshot({path:path.join(artifacts,`real-${width}-${signedIn?'logado':'publico'}.png`),fullPage:true});fs.writeFileSync(path.join(artifacts,'contrato-http-local.json'),JSON.stringify(contract,null,2));}
      measurements.push({width,signedIn,...geometry});
      const search=page.locator('#buscaCurso');
      await search.fill('RESUMÃO PROF EDUC INFANTIL ALVORADA-RS 26');assert.equal(await page.locator('.curso-publico-card').count(),1);
      assert.equal(await page.locator('.home-search-placeholder').isVisible(),false);
      await search.fill('ALVORADA');assert.equal(await page.locator('.curso-publico-card').count(),1);
      await search.fill('antigo');assert.equal(await page.locator('.curso-publico-card').count(),1);
      await search.fill('');assert.equal(await page.locator('.curso-publico-card').count(),4);
      assert.deepEqual(errors,[]);
      await card.click();await page.waitForURL('**/curso-info.html?**');
      assert.equal(new URL(page.url()).searchParams.get('curso_id'),'39');
      assert.equal(new URL(page.url()).searchParams.get('curso_nome'),'RESUMÃO PROF EDUC INFANTIL ALVORADA-RS 26');
      await ctx.close();
    }
    if(artifacts)fs.writeFileSync(path.join(artifacts,'medidas-integracao.json'),JSON.stringify(measurements,null,2));
    console.log('Integração HTTP real: 4 larguras × visitante/logado, metadados completos/parciais/legados, pesquisa e clique aprovados.');
  }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
