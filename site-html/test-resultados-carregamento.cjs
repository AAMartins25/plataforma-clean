// Respostas sintéticas controladas: não usa banco ou serviços externos.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright-core');
const origin='http://resultados.test',api='https://plataforma-quality-backend.onrender.com';
const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.woff2':'font/woff2'};
const configs=[
 {page:'minhas-anotacoes.html',area:'area_anotacoes',loader:'carregamento_anotacoes',nav:'.minhas-anotacoes-navegacao-final',endpoint:'/me/minhas-anotacoes',load:'carregarAnotacoes',card:'.minhas-anotacoes-anotacao-card',empty:'Nenhuma anotação encontrada.',error:'Erro ao carregar anotações.',records:[
  {anotacao_id:1,questao_id:10,disciplina_id:1,disciplina_nome:'Matemática',assunto_id:1,assunto_nome:'Geometria',anotacao:'Primeira anotação',tipo:'CERTO_ERRADO',enunciado:'Questão',gabarito:'C'},
  {anotacao_id:2,questao_id:11,disciplina_id:2,disciplina_nome:'Português',assunto_id:2,assunto_nome:'Gramática',anotacao:'Segunda anotação',tipo:'CERTO_ERRADO',enunciado:'Outra questão',gabarito:'E'}]},
 {page:'mensagens-prof.html',area:'area_mensagens',loader:'carregamento_mensagens',nav:'.mensagens-prof-navegacao-final',endpoint:'/me/mensagens-prof',load:'carregarMensagens',card:'.mensagens-prof-conversa-card',empty:'Nenhuma mensagem encontrada.',error:'Erro ao carregar mensagens.',records:[
  {conversa_id:1,questao_id:10,disciplina_id:1,disciplina_nome:'Matemática',assunto_id:1,assunto_nome:'Geometria',status:'ABERTA',tipo:'CERTO_ERRADO',enunciado:'Questão',gabarito:'C',mensagens:[{autor:'ALUNO',texto:'Primeira pergunta'}]},
  {conversa_id:2,questao_id:11,disciplina_id:2,disciplina_nome:'Português',assunto_id:2,assunto_nome:'Gramática',status:'ENCERRADA',tipo:'CERTO_ERRADO',enunciado:'Outra questão',gabarito:'E',mensagens:[{autor:'ALUNO',texto:'Segunda pergunta'},{autor:'PROFESSOR',texto:'Resposta do professor'}]}]}
];
(async()=>{
 const b=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{}),args:['--no-sandbox']});
 try {
  for(const width of [1366,768,390,320]) for(const config of configs) {
   // O indicador já pertence ao HTML inicial, antes de qualquer script executar.
   assert.ok(fs.readFileSync(path.join(__dirname,config.page),'utf8').includes(`id="${config.loader}" role="status" style="text-align:left;">Carregando...</p>`));
   for(const scenario of ['rapida','lenta','vazia','erro','erro_processamento']) {
    const context=await b.newContext({viewport:{width,height:900}}),pending=[],errors=[];
    let queries=0;
    await context.addInitScript(({area,loader})=>{
     localStorage.setItem('access_token','synthetic-test-token');window.loadingHistory=[];
     new MutationObserver(()=>{
      const e=document.getElementById(area);if(!e)return;
      const indicator=document.getElementById(loader);if(!indicator)return;
      const text=(indicator && !indicator.hidden ? indicator.textContent.trim() : e.textContent.trim());
      if(window.loadingHistory.at(-1)!==text)window.loadingHistory.push(text);
     }).observe(document,{childList:true,subtree:true,attributes:true,attributeFilter:['hidden']});
    },{area:config.area,loader:config.loader});
    await context.route('**/*',async route=>{
     const u=new URL(route.request().url());
     if(u.origin===origin) {
      const file=path.resolve(__dirname,'.'+decodeURIComponent(u.pathname));
      if(!file.startsWith(__dirname+path.sep)||!fs.existsSync(file))return route.fulfill({status:404,body:''});
      return route.fulfill({contentType:mime[path.extname(file)]||'application/octet-stream',body:fs.readFileSync(file)});
     }
     if(u.origin!==api)return route.abort();
     if(u.pathname==='/me')return route.fulfill({json:{id:1,nome:'Ana Silva'}});
     if(u.pathname===config.endpoint) {
      queries++;
      const response=await new Promise(resolve=>pending.push(resolve));
      return route.fulfill(response);
     }
     return route.fulfill({status:404,json:{detail:'Unexpected request'}});
    });
    const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
    await page.goto(origin+'/'+config.page+'?curso_id=1&contratacao_id=9&curso_nome=Curso');
    const area=page.locator('#'+config.area),status=page.locator('#'+config.loader);
    const overflow=async()=>assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    const loading=async()=>{
     assert.equal(await status.innerText(),'Carregando...');assert.equal(await area.getAttribute('aria-busy'),'true');
     assert.equal(await status.evaluate(e=>getComputedStyle(e).textAlign),'left');
     const position=await status.evaluate((e,{area,nav})=>{
      const rect=e.getBoundingClientRect(),navigation=document.querySelector(nav).getBoundingClientRect();
      const main=document.querySelector('main'),mainRect=main.getBoundingClientRect();
      return {below:rect.top>=navigation.bottom,left:rect.left,contentLeft:mainRect.left+parseFloat(getComputedStyle(main).paddingLeft),empty:document.getElementById(area).getBoundingClientRect().height};
     },{area:config.area,nav:config.nav});
     assert.equal(position.below,true,'indicador somente abaixo do card de navegação');
     assert.ok(Math.abs(position.left-position.contentLeft)<.02,'alinhado à margem esquerda do conteúdo');
     assert.equal(position.empty,0,'nenhum card ou espaço de carregamento acima da navegação');
     assert.equal(await page.locator(config.card).count(),0);
     assert.equal(await area.getByText(config.empty,{exact:true}).count(),0);
     await overflow();
    };
    await status.waitFor();await loading();
    await page.locator('header .ro-header-navigation a').first().click({trial:true});
    assert.equal(queries,1);assert.ok(pending.length);
    if(scenario==='lenta') {
     await page.waitForTimeout(500);await loading();
     if(process.env.SCREENSHOT_DIR){fs.mkdirSync(process.env.SCREENSHOT_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR,`${config.area}-${width}-carregando.png`)});}
    }
    assert.deepEqual(await page.evaluate(()=>window.loadingHistory),['Carregando...'],'nenhuma mensagem vazia prematura');
    pending.shift()(scenario==='erro'?{status:500,json:{detail:'Erro simulado'}}:scenario==='erro_processamento'?{json:{invalido:true}}:{json:scenario==='vazia'?[]:config.records});
    await page.waitForFunction(id=>document.getElementById(id).getAttribute('aria-busy')==='false',config.area);
    assert.equal(await status.isVisible(),false,'indicador removido ao concluir ou falhar');
    assert.equal(await status.evaluate(e=>e.getBoundingClientRect().height),0,'indicador oculto não reserva espaço');
    if(scenario.startsWith('erro'))assert.equal(await area.getByRole('alert').innerText(),config.error);
    else if(scenario==='vazia')assert.equal(await area.innerText(),config.empty);
    else {
     assert.equal(await page.locator(config.card).count(),2);
     await page.locator('#filtro_disciplina').selectOption('1');assert.equal(await page.locator(config.card).count(),1);
     await page.locator('#filtro_assunto').selectOption('1');assert.equal(queries,1,'filtros locais não criam consultas novas');
     if(scenario==='rapida') {
      // Exercita uma recarga assíncrona real usando a mesma função da página.
      await page.evaluate(fn=>{void window[fn]();},config.load);await loading();assert.equal(queries,2);
      await page.locator('#filtro_disciplina').selectOption('2');
      await page.locator('#filtro_assunto').selectOption('2');await loading();assert.equal(queries,2);
      pending.shift()({json:config.records});
      await page.waitForFunction(id=>document.getElementById(id).getAttribute('aria-busy')==='false',config.area);
      assert.equal(await status.isVisible(),false);assert.equal(await page.locator(config.card).count(),2);
      // Recarga com erro e recuperação não deixam o indicador permanente.
      await page.evaluate(fn=>{void window[fn]();},config.load);await loading();pending.shift()({status:500,json:{detail:'Erro de recarga'}});
      await area.getByRole('alert').waitFor();assert.equal(await area.getAttribute('aria-busy'),'false');
      await page.evaluate(fn=>{void window[fn]();},config.load);await loading();pending.shift()({json:[]});
      await area.getByText(config.empty,{exact:true}).waitFor();assert.equal(await status.isVisible(),false);
     }
    }
    await overflow();assert.deepEqual(errors,[]);
    console.log(`${width}px / ${config.page} / ${scenario}: carregamento, conclusão e navegação não bloqueada: OK`);
    await context.close();
   }
  }
 } finally {await b.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
