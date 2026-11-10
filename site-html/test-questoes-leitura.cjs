// Renderizadores reais das telas complementares; somente leituras da API de prévia.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright-core');
const origin='http://127.0.0.1:8769',destino=path.resolve(__dirname,'../evidencias/questoes-editor');
(async()=>{const browser=await chromium.launch({executablePath:'/home/codespace/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell',args:['--no-sandbox']});const resultados=[];
 try{for(const width of [1366,768,320])for(const tela of ['questoes-criticas','minhas-anotacoes','mensagens-prof']){
  const p=await browser.newPage({viewport:{width,height:900}}),erros=[];p.on('pageerror',e=>erros.push(e.message));
  await p.route('**/*',r=>r.request().url().startsWith(origin)?r.continue():r.abort());
  await p.goto(origin+'/__preview/entrar?perfil=aluno');await p.goto(origin+'/'+tela+'.html?curso_id=1&contratacao_id=1');await p.waitForLoadState('networkidle');
  await p.evaluate(async tela=>{
   const qs=await (await fetch('/baterias/1/questoes?contratacao_id=1',{headers:{Authorization:'Bearer isolado-aluno'}})).json();
   const q={...qs[0],questao_id:qs[0].id,questao_ordem:1,anotacao_id:1,conversa_id:1,status:'ABERTA',mensagens:[],anotacao:'Nota sintética',texto:'Nota sintética',texto_resposta:qs[0].alternativas[0].texto,texto_resposta_formato:'html_v1'};
   q.enunciado=q.enunciado.replace('Texto de teste','TokenSemEspacos'.repeat(40));
   const html=tela==='questoes-criticas'?montarCardQuestaoCritica(q,1,'erros'):tela==='minhas-anotacoes'?montarCardAnotacao(q):montarCardConversa(q);
   document.querySelector('main').innerHTML=html;
  },tela);
  await p.waitForFunction(()=>[...document.querySelectorAll('main .questao-conteudo-rico img')].some(i=>i.complete&&i.naturalWidth>0));
  assert.ok(await p.locator('main .questao-conteudo-rico strong').count());assert.ok(await p.locator('main .katex').count());assert.ok(await p.locator('main .questao-conteudo-rico table').count());
  assert.ok(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${tela}/${width}: transbordamento`);
  assert.deepEqual(erros,[],`${tela}/${width}: erros JS`);
  if(width===320)await p.screenshot({path:path.join(destino,tela+'-320.png'),fullPage:true});
  resultados.push({tela,width,formatacao:true,formula:true,tabela:true,imagem:true,overflow:false});await p.close();
 }
 const legado=await browser.newPage();await legado.route('**/*',r=>r.request().url().startsWith(origin)?r.continue():r.abort());
 await legado.goto(origin+'/__preview/entrar?perfil=aluno');await legado.goto(origin+'/teoria.html?curso_id=1&contratacao_id=1');await legado.waitForLoadState('networkidle');
 const compatibilidade=await legado.evaluate(async()=>{
  pastaAtualId=null;aulaAtualId=null;
  document.querySelector('main').innerHTML='<div id="questoes_999"></div>';
  tryMany=async()=>[{enunciado:'Legado <b>literal</b>',alternativas:{A:'Alternativa antiga'},comentario:{A:'Comentário <b>literal</b>',geral:'Comentário geral antigo'}}];
  await carregarQuestoes(999);
  const antigo=document.querySelector('main').textContent;
  document.querySelector('main').innerHTML='<div id="questoes_999"></div>';
  tryMany=async()=>[{enunciado:'<p><strong>Enunciado novo</strong></p>',enunciado_formato:'html_v1',alternativas:[{letra:'A',texto:'<p><i>Alternativa nova</i></p>',texto_formato:'html_v1'}],comentario:'<p><u>Comentário novo</u></p>',comentario_formato:'html_v1'}];
  await carregarQuestoes(999);
  return {antigo,novo:document.querySelector('main strong')?.textContent,alternativa:document.querySelector('main i')?.textContent,comentario:document.querySelector('main u')?.textContent};
 });
 assert.ok(compatibilidade.antigo.includes('Comentário <b>literal</b>'));assert.ok(compatibilidade.antigo.includes('Comentário geral antigo'));
 assert.equal(compatibilidade.novo,'Enunciado novo');assert.equal(compatibilidade.alternativa,'Alternativa nova');assert.equal(compatibilidade.comentario,'Comentário novo');
 await legado.close();
 fs.writeFileSync(path.join(destino,'leitura-complementar.json'),JSON.stringify(resultados,null,2));console.log('9 cenários: críticas, anotações e mensagens em desktop, tablet e celular; teoria com formatos legado e novo: OK');}
 finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
