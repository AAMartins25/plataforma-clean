// CKEditor 49.1.0 real e API real do preview_questoes_editor.py, com dados sintéticos.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright-core');
const origem=process.env.QUESTOES_PREVIEW_URL||'http://127.0.0.1:8769';
assert.match(origem,/^http:\/\/127\.0\.0\.1:\d+$/,'Somente prévia local permitida');
const evidencias=path.resolve(__dirname,'../evidencias/questoes-editor');fs.mkdirSync(evidencias,{recursive:true});
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_BIN||'/home/codespace/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell',args:['--no-sandbox']});
 const resultados=[];
 try{
 for(const width of [1366,768,390,320]){
  const page=await browser.newPage({viewport:{width,height:900}}),erros=[];page.on('pageerror',e=>erros.push(e.message));
  page.on('dialog',d=>d.accept());
  await page.route('**/*',r=>r.request().url().startsWith(origem)?r.continue():r.abort());
  await page.goto(origem+'/__preview/entrar?perfil=admin');
  await page.selectOption('#cursoExistenteSelect','1');await page.click('#btnUsarCursoExistente');
  await page.getByRole('button',{name:'Trabalhar nesta disciplina',exact:true}).click();
  await page.getByRole('button',{name:'Aulas',exact:true}).first().click();
  await page.getByRole('button',{name:'🏁 Questões',exact:true}).click();
  await page.getByRole('button',{name:'Abrir / editar questões',exact:true}).first().click();
  await page.locator('#cardQuestao_1').getByRole('button',{name:'Editar',exact:true}).click();
  await page.waitForFunction(()=>document.querySelectorAll('#camposQuestaoCompleta .ck-content[contenteditable="true"]').length===7);
  assert.equal(await page.locator('#camposQuestaoCompleta .ck-editor').count(),7);
  const formato='<h2>Questão formatada</h2><p style="text-align:center"><strong>Negrito</strong> <i>itálico</i> <u>sublinhado</u></p><ul><li>Primeiro</li><li>Segundo</li></ul><p><span class="ro-math-inline">x^2 + y^2</span></p><figure class="table"><table><tbody><tr><th>Conceito</th><th>Descrição</th><th>Conclusão</th></tr><tr><td>A</td><td>'+('Descrição extensa. '.repeat(15))+'</td><td>'+('SemEspacos'.repeat(30))+'</td></tr></tbody></table><figcaption>Legenda</figcaption></figure>';
  const plugins=await page.locator('#camposQuestaoCompleta .ck-content').first().evaluate(e=>{
   const ed=e.ckeditorInstance;return ['Bold','Italic','Underline','Table','TeoriaFormula'].map(n=>[n,ed.plugins.has(n)]);
  });assert.ok(plugins.slice(0,4).every(([,v])=>v));
  await page.locator('#camposQuestaoCompleta .ck-content').evaluateAll((els,html)=>els.forEach((el,i)=>el.ckeditorInstance.setData(i===0?html:'<p><strong>Campo '+i+'</strong> com <i>formatação</i>.</p>')),formato);
  await page.selectOption('#questaoGabarito','B');
  await page.waitForFunction(()=>document.documentElement.scrollWidth<=innerWidth+1);
  const medida=await page.evaluate(()=>({pagina:document.documentElement.scrollWidth-innerWidth,editores:[...document.querySelectorAll('#camposQuestaoCompleta .ck-editor')].map(e=>e.getBoundingClientRect().width)}));
  assert.ok(medida.pagina<=1,`${width}: ADM transbordou ${medida.pagina}`);
  await page.locator('#camposQuestaoCompleta').screenshot({path:path.join(evidencias,`admin-${width}.png`)});
  await page.getByRole('button',{name:'Salvar edição',exact:true}).click();
  await page.waitForFunction(()=>!document.querySelector('#textoBotaoSalvarQuestao') || document.querySelector('#textoBotaoSalvarQuestao').textContent!=='Salvar edição');
  await page.locator('#cardQuestao_1').getByRole('button',{name:'Editar',exact:true}).click();
  await page.waitForFunction(()=>document.querySelectorAll('#camposQuestaoCompleta .ck-content[contenteditable="true"]').length===7);
  assert.equal(await page.locator('#questaoGabarito').inputValue(),'B');
  const dados=await page.evaluate(()=>QuestaoEditores.dados());
  assert.equal(dados.enunciado_formato,'html_v1');assert.match(dados.enunciado,/<strong>Negrito/);assert.match(dados.enunciado,/ro-math-inline/);assert.equal(dados.alternativas.length,5);
  await page.getByRole('button',{name:'Descartar e fechar edição',exact:true}).click();
  // Certo/errado mantém opções fixas e somente dois editores.
  await page.locator('#cardQuestao_3').getByRole('button',{name:'Editar',exact:true}).click();
  await page.waitForFunction(()=>document.querySelectorAll('#camposQuestaoCompleta .ck-content[contenteditable="true"]').length===2);
  assert.equal(await page.locator('#camposQuestaoCompleta textarea[id^="alternativa_"]').count(),0);
  assert.ok((await page.locator('#camposQuestaoCompleta .ck-content').first().textContent()).includes('<b>literal</b>'));
  assert.equal(await page.locator('input[name="gabarito_certo_errado"]:checked').inputValue(),'E');
  // Fechar edição destrói todas as instâncias das questões, mantendo só o editor de descrição pública.
  await page.getByRole('button',{name:'Descartar e fechar edição',exact:true}).click();
  await page.waitForFunction(()=>!document.querySelector('#camposQuestaoCompleta .ck-editor'));
  // Leitura, resultado e revisão programada usam a mesma formatação.
  await page.goto(origem+'/__preview/entrar?perfil=aluno');
  await page.locator('.sprint-questao-enunciado strong').first().waitFor();
  assert.equal(await page.locator('#questao_1 .sprint-questao-enunciado .katex').count(),1);
  assert.equal(await page.locator('#questao_1 .sprint-questao-enunciado table').count(),1);
  assert.ok(await page.locator('.alternativa-opcao strong').count()>=5);
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${width}: leitura transborda`);
  await page.locator('#area_questoes').screenshot({path:path.join(evidencias,`aluno-${width}.png`)});
  await page.evaluate(()=>revisarAgora());
  await page.locator('.sprint-revisao-comentario-texto strong').first().waitFor();
  assert.ok(await page.locator('.sprint-revisao-alternativa strong').count()>=9);
  assert.ok((await page.locator('#area_questoes').textContent()).includes('Legado <b>literal</b>'));
  await page.screenshot({path:path.join(evidencias,`revisao-${width}.png`),fullPage:true});
  await page.goto(origem+'/__preview/entrar?perfil=revisao');
  await page.locator('.sprint-questao-enunciado strong').first().waitFor();
  assert.equal(await page.locator('#questao_1 .sprint-questao-enunciado .katex').count(),1);
  assert.deepEqual(erros,[],`${width}: erros JS`);
  resultados.push({width,editores:7,certoErrado:2,edicao:'OK',legado:'OK',leitura:'OK',revisao:'OK',overflow:medida.pagina});
  await page.close();
 }
 fs.writeFileSync(path.join(evidencias,'navegador.json'),JSON.stringify(resultados,null,2));console.log(JSON.stringify(resultados));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
