// API em memória; CKEditor, renderizadores e scripts reais. Nenhum dado externo é alterado.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const ck = process.env.CKEDITOR_DIST;
assert.ok(ck, 'Informe CKEDITOR_DIST com a distribuição browser local do CKEditor 49.1.0.');
const origin = 'http://mensagens.test', api = 'https://plataforma-quality-backend.onrender.com';
const imageSrc = '/midias/imagens/12345678-1234-4234-8234-123456789abc';
const rich = '<p><strong>Dúvida do aluno</strong> <em>com formatação</em></p><ul><li>Revisar o cálculo</li></ul><p><span class="ro-math-inline">x^2</span></p>';
const richQuestion = `<p><strong>Referência: Prova 2026</strong></p><p>Enunciado <em>formatado</em>.</p><p>A) Alternativa um</p><p>B) Alternativa dois</p><figure class="table"><table><tbody><tr><th>Item</th><th>Valor</th></tr><tr><td>Área</td><td>25</td></tr></tbody></table></figure><p><span class="ro-math-inline">x^2 + y^2</span></p><figure class="image"><img src="${imageSrc}" alt="Figura da questão"></figure>`;
const fixtures = [
  {conversa_id:11,questao_id:101,disciplina_id:1,disciplina_nome:'Matemática',disciplina_ordem:1,assunto_id:1,assunto_nome:'Geometria',assunto_ordem:1,bateria_id:7,tipo:'MULTIPLA',gabarito:'B',
    enunciado:richQuestion+'<p>Detalhes adicionais da questão.</p>'.repeat(20),enunciado_formato:'html_v1',comentario:'<p>Comentário <u>formatado</u>.</p>',comentario_formato:'html_v1',
    status:'ABERTA',estado_conversa:'estado-11',mensagens:[{autor:'ALUNO',texto:rich,texto_formato:'html_v1'}]},
  {conversa_id:12,questao_id:102,disciplina_id:1,disciplina_nome:'Matemática',disciplina_ordem:1,assunto_id:2,assunto_nome:'Álgebra',assunto_ordem:2,bateria_id:7,tipo:'CERTO_ERRADO',gabarito:'E',
    enunciado:'Enunciado legado\nSegunda linha',comentario:'Comentário legado\n'.repeat(30),status:'ABERTA',estado_conversa:'estado-12',
    mensagens:[{autor:'ALUNO',texto:'Pergunta simples',texto_formato:'texto_puro'},{autor:'PROFESSOR',texto:'<p>Resposta <strong>do professor</strong>.</p>',texto_formato:'html_v1'}]},
  {conversa_id:14,questao_id:103,disciplina_id:1,disciplina_nome:'Matemática',disciplina_ordem:1,assunto_id:1,assunto_nome:'Geometria',assunto_ordem:1,bateria_id:7,tipo:'CERTO_ERRADO',gabarito:'C',
    enunciado:'Outra questão do mesmo assunto',comentario:'Outro comentário',status:'ENCERRADA',estado_conversa:'estado-14',
    mensagens:[{autor:'ALUNO',texto:'Pergunta encerrada',texto_formato:'texto_puro'},{autor:'PROFESSOR',texto:'Resposta final',texto_formato:'texto_puro'}]},
  {conversa_id:13,disciplina_id:2,disciplina_nome:'Outra disciplina',disciplina_ordem:2,assunto_id:3,assunto_nome:'Geral',assunto_ordem:1,status:'ABERTA',estado_conversa:'estado-13',
    mensagens:[{autor:'ALUNO',texto:'Mensagem sem questão',texto_formato:'texto_puro'}]}
];
const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.woff2':'font/woff2'};
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{}),args:['--no-sandbox']});
 try {
  for(const width of [1366,768,390,320]) {
   const context=await browser.newContext({viewport:{width,height:900}});
   let records=structuredClone(fixtures),reformAttempts=0;
   const errors=[],writes=[],requests=[];
   await context.addInitScript(()=>localStorage.setItem('access_token','synthetic-test-token'));
   await context.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    let file;
    if(url.hostname==='cdn.ckeditor.com') file=path.join(ck,path.basename(url.pathname));
    else if(url.origin===origin) {
     if(url.pathname==='/test-image.svg') return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="160"><rect width="600" height="160" fill="#fdee8a"/></svg>'});
     file=path.resolve(__dirname,'.'+decodeURIComponent(url.pathname));
     if(!file.startsWith(__dirname+path.sep)) return route.fulfill({status:404,body:''});
    }
    if(file) return route.fulfill(fs.existsSync(file)?{contentType:mime[path.extname(file)]||'application/octet-stream',body:fs.readFileSync(file)}:{status:404,body:''});
    if(url.origin!==api) return route.abort();
    requests.push({path:url.pathname,query:url.search,method:request.method(),auth:request.headers().authorization});
    if(url.pathname==='/me') return route.fulfill({json:{id:1,nome:'Ana Silva'}});
    if(url.pathname==='/me/mensagens-prof') return route.fulfill({json:records});
    if(url.pathname==='/me/ckeditor-chave') return route.fulfill({json:{licenseKey:'GPL'}});
    if(url.pathname==='/baterias/7/imagens/assinaturas') return route.fulfill({json:{imagens:[{src:imageSrc,url:'/test-image.svg'}]}});
    if(request.method()==='POST') {
     const body=request.postDataJSON();writes.push({path:url.pathname,body});
     if(url.pathname==='/me/mensagens-prof/12/responder') {
      records.find(c=>c.conversa_id===12).mensagens.push({autor:'ALUNO',...body});return route.fulfill({json:{}});
     }
     if(url.pathname==='/me/mensagens-prof/11/reformular') {
      if(++reformAttempts===1) return route.fulfill({status:503,json:{detail:'Resultado incerto simulado'}});
      const c=records.find(c=>c.conversa_id===11);c.conversa_id=21;c.estado_conversa='novo-estado';c.mensagens=[{autor:'ALUNO',texto:body.texto,texto_formato:body.texto_formato}];
      return route.fulfill({json:{conversa_id:21}});
     }
    }
    return route.fulfill({status:404,json:{detail:'Unexpected test request'}});
   });
   const page=await context.newPage();page.on('pageerror',err=>errors.push(err.message));
   await page.goto(origin+'/mensagens-prof.html?curso_id=1&contratacao_id=9&curso_nome=Curso');
   const card=id=>page.locator('#conversa_'+id),toggle=id=>card(id).locator('.mensagens-prof-alternar-questao'),question=id=>page.locator('#questao_relacionada_'+id);
   const overflow=async()=>assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`${width}px sem overflow`);
   const ready=async id=>page.waitForFunction(id=>document.getElementById(id)?.parentElement.querySelector('.ck-content')?.ckeditorInstance,id);
   const setData=async(id,text)=>{await ready(id);await page.locator('#'+id).evaluate((e,text)=>e.parentElement.querySelector('.ck-content').ckeditorInstance.setData(text),text);};
   await card(11).waitFor();await ready('nova_msg_12');
   assert.equal(await page.locator('.mensagens-prof-identificacao-card').count(),0);
   assert.equal(await page.locator('#total_mensagens').innerText(),'Total: 4');
   for(const c of records) {
    assert.equal(await card(c.conversa_id).locator(':scope > .mensagens-prof-disciplina-titulo').textContent(),c.disciplina_nome);
    assert.equal(await card(c.conversa_id).locator(':scope > .mensagens-prof-assunto-titulo').textContent(),c.assunto_nome);
    assert.equal(await card(c.conversa_id).evaluate(e=>e.firstElementChild.matches('.mensagens-prof-disciplina-titulo')&&e.firstElementChild.nextElementSibling.matches('.mensagens-prof-assunto-titulo')),true);
    assert.equal(await card(c.conversa_id).locator('.mensagens-prof-mensagem .mensagens-prof-disciplina-titulo, .mensagens-prof-mensagem .mensagens-prof-assunto-titulo').count(),0);
    const aligned=await card(c.conversa_id).locator('.mensagens-prof-reformular-acoes').evaluate(e=>Math.abs(e.getBoundingClientRect().right-e.querySelector('button').getBoundingClientRect().right));assert.ok(aligned<.02);
    if(c.questao_id) {
     assert.equal(await question(c.conversa_id).isVisible(),false);
     assert.equal(await toggle(c.conversa_id).textContent(),'Ver questão relacionada');
     assert.equal(await card(c.conversa_id).evaluate(e=>{
      const button=e.querySelector('.mensagens-prof-alternar-questao').getBoundingClientRect();
      return [...e.querySelectorAll('.mensagens-prof-mensagem, .mensagens-prof-reformular-acoes, textarea')].every(m=>m.getBoundingClientRect().bottom<=button.top);
     }),true,'mensagens, respostas e controles precedem a questão');
    }
   }
   assert.equal(await card(13).locator('.mensagens-prof-alternar-questao').count(),0);
   assert.equal(await card(11).locator('textarea[id^="nova_msg_"]').count(),0,'pendente não permite resposta');
   assert.equal(await card(14).locator('textarea[id^="nova_msg_"]').count(),0,'encerrada não permite resposta');
   assert.match(await card(11).innerText(),/Aguardando resposta do professor/);
   assert.match(await card(14).innerText(),/Chat finalizado/);
   assert.equal(await card(12).locator('.mensagens-prof-mensagem-prof strong').textContent(),'do professor');
   assert.equal(await toggle(11).evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(255, 247, 199)');
   const messagesBefore=await card(11).locator('.mensagens-prof-mensagem-aluno').innerHTML();
   const checkOpen=async id=>{
    assert.equal(await page.locator('.mensagens-prof-questao-relacionada:not([hidden])').count(),id?1:0);
    for(const current of [11,12,14]) {
     assert.equal(await question(current).isVisible(),current===id);
     assert.equal(await toggle(current).getAttribute('aria-expanded'),String(current===id));
     assert.equal(await toggle(current).textContent(),current===id?'Ocultar questão relacionada':'Ver questão relacionada');
    }
   };
   const stableToggle=async(id,top,key)=>{
    await toggle(id).evaluate((e,top)=>{e.focus({preventScroll:true});window.scrollBy({top:e.getBoundingClientRect().top-top,behavior:'instant'});},top);
    await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
    const before=await toggle(id).boundingBox();assert.ok(before.y>=0&&before.y+before.height<=900);
    if(key) await page.keyboard.press(key);else await page.mouse.click(before.x+before.width/2,before.y+before.height/2);
    await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));await page.waitForTimeout(150);
    const after=await toggle(id).boundingBox();assert.ok(Math.abs(before.y-after.y)<=1,`${width}px botão ${id}: deslocamento ${after.y-before.y}`);
    assert.equal(await toggle(id).evaluate(e=>e===document.activeElement),true,'foco preservado');
   };
   await toggle(11).click();await checkOpen(11);
   await question(11).locator('.katex').waitFor();await page.waitForFunction(()=>document.querySelector('#questao_relacionada_11 img')?.naturalWidth>0);
   assert.equal(await question(11).locator('table').count(),1);assert.equal(await question(11).locator('img').evaluate(i=>i.naturalWidth),600);
   assert.match(await question(11).innerText(),/Referência: Prova 2026/);assert.match(await question(11).innerText(),/A\) Alternativa um/);assert.match(await question(11).innerText(),/Gab\. B/);
   assert.equal(await question(11).locator('.mensagens-prof-comentario u').textContent(),'formatado');
   const questionBefore=await question(11).innerHTML();
   if(process.env.SCREENSHOT_DIR){fs.mkdirSync(process.env.SCREENSHOT_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR,`expandida-${width}.png`),fullPage:true});}
   for(const [id,top,key] of [[12,160],[14,180],[14,180],[11,440],[12,420],[11,180,'Enter'],[11,200,'Space'],[14,180,'Enter'],[14,180,'Space']]) {
    const opening=!(await question(id).isVisible());await stableToggle(id,top,key);await checkOpen(opening?id:null);await overflow();
   }
   await toggle(11).click();assert.equal(await question(11).innerHTML(),questionBefore);assert.equal(await card(11).locator('.mensagens-prof-mensagem-aluno').innerHTML(),messagesBefore);
   await card(11).getByRole('button',{name:'Reformular mensagem ao prof',exact:true}).focus();await page.keyboard.press('Tab');assert.equal(await toggle(11).evaluate(e=>e===document.activeElement),true);
   assert.equal(writes.length,0,'expansão não grava dados');
   await page.locator('#filtro_assunto').selectOption('2');assert.equal(await page.locator('.mensagens-prof-conversa-card').count(),1);assert.equal(await question(12).isVisible(),false);
   await stableToggle(12,120);await stableToggle(12,120,'Space');assert.equal(await question(12).isVisible(),false);
   await page.locator('#filtro_assunto').selectOption('');await checkOpen(null);assert.equal(await page.locator('#area_mensagens').evaluate(e=>e.style.minHeight),'');
   await page.locator('#filtro_disciplina').selectOption('2');assert.equal(await page.locator('.mensagens-prof-conversa-card').count(),1);
   await page.locator('#filtro_disciplina').selectOption('1');assert.equal(await page.locator('.mensagens-prof-conversa-card').count(),3);
   // Editor real, envio normal e permissão de aguardar a resposta seguinte.
   await setData('nova_msg_12','<p>Retorno <strong>formatado</strong> do aluno.</p>');
   page.once('dialog',d=>d.dismiss());await card(12).getByRole('button',{name:'Enviar ao prof.',exact:true}).click();assert.equal(writes.length,0);
   page.once('dialog',d=>d.accept());await card(12).getByRole('button',{name:'Enviar ao prof.',exact:true}).click();
   await card(12).getByText('Aguardando resposta do professor.',{exact:true}).waitFor();assert.equal(writes[0].path,'/me/mensagens-prof/12/responder');assert.equal(writes[0].body.texto_formato,'html_v1');
   assert.match(await card(12).innerText(),/Retorno formatado do aluno/);assert.equal(await card(12).locator('textarea[id^="nova_msg_"]').count(),0);
   // Reformular mantém o aviso, cancelamento, rascunho e retry idempotente atuais.
   await card(11).getByRole('button',{name:'Reformular mensagem ao prof',exact:true}).click();await ready('reformulacao_texto_11');
   assert.match(await card(11).getByRole('note').textContent(),/a conversa anterior será apagada/);
   await setData('reformulacao_texto_11','<p>Rascunho <strong>preservado</strong></p>');
   await toggle(11).click();await toggle(14).click();
   assert.match(await page.locator('#reformulacao_texto_11').evaluate(e=>e.parentElement.querySelector('.ck-content').ckeditorInstance.getData()),/preservado/);
   await overflow();await card(11).getByRole('button',{name:'Cancelar',exact:true}).click();assert.equal(writes.length,1);
   assert.equal(await card(11).locator('.mensagens-prof-mensagem-aluno').innerHTML(),messagesBefore);
   await card(11).getByRole('button',{name:'Reformular mensagem ao prof',exact:true}).click();await setData('reformulacao_texto_11','<p>Nova dúvida <strong>formatada</strong></p>');
   await card(11).getByRole('button',{name:'Confirmar e enviar',exact:true}).click();await card(11).getByRole('button',{name:'Tentar novamente com segurança',exact:true}).waitFor();
   assert.equal(writes[1].body.confirmado,true);assert.equal(writes[1].body.estado_conversa,'estado-11');assert.ok(writes[1].body.operacao_id);
   await card(11).getByRole('button',{name:'Tentar novamente com segurança',exact:true}).click();await card(21).waitFor();await card(11).waitFor({state:'detached'});
   assert.deepEqual(writes[1],writes[2],'retry preserva operação, estado e conteúdo');assert.equal(writes[2].body.texto_formato,'html_v1');
   assert.match(await card(21).innerText(),/Nova dúvida formatada/);assert.equal(await question(21).isVisible(),false);
   await toggle(21).click();await toggle(14).click();assert.equal(await question(21).isVisible(),false);assert.equal(await question(14).isVisible(),true);
   for(const r of requests) {assert.ok(r.query.includes('contratacao_id=9'));assert.equal(r.auth,'Bearer synthetic-test-token');}
   await overflow();assert.deepEqual(errors,[]);
   if(process.env.SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR,`final-${width}.png`),fullPage:true});
   console.log(`${width}px: identificação por mensagem, estados/permissões, conteúdo rico, expansão exclusiva, rolagem, filtros, teclado, resposta e reformulação com retry: OK`);
   await context.close();
  }
 } finally {await browser.close();}
})().catch(err=>{console.error(err);process.exitCode=1;});
