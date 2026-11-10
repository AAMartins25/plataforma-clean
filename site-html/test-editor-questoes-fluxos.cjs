const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright-core');
const origin=process.env.QUESTOES_PREVIEW_URL||'http://127.0.0.1:8769';assert.match(origin,/^http:\/\/127\.0\.0\.1:\d+$/);
const evidencias=path.resolve(__dirname,'../evidencias/questoes-editor');
const canon=html=>html.replace(/ data-list-item-id="[^"]*"/g,'');
const executavel='/home/codespace/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell';
async function entrar(page){
 await page.goto(origin+'/__preview/entrar?perfil=admin');await page.selectOption('#cursoExistenteSelect','1');await page.click('#btnUsarCursoExistente');
 await page.getByRole('button',{name:'Trabalhar nesta disciplina',exact:true}).click();await page.getByRole('button',{name:'Aulas',exact:true}).first().click();await page.getByRole('button',{name:'🏁 Questões',exact:true}).click();
}
(async()=>{
 const browser=await chromium.launch({executablePath:executavel,args:['--no-sandbox']});const resultados={};
 try{
  const p=await browser.newPage({viewport:{width:390,height:900}}),erros=[];
  p.on('pageerror',e=>erros.push(e.message));p.on('dialog',d=>d.accept(d.type()==='prompt'?'Criação visual '+Date.now():undefined).catch(()=>{}));
  await p.route('**/*',r=>r.request().url().startsWith(origin)?r.continue():r.abort());
  await entrar(p);
  await p.evaluate(async()=>{
   const headers={Authorization:'Bearer isolado-admin','Content-Type':'application/json'};
   let r=await fetch('/disciplinas-proprias/1/assuntos-proprios',{method:'POST',headers,body:JSON.stringify({curso_disciplina_propria_id:1,nome:'Assunto de criação visual '+Date.now(),ativo:true})});
   if(!r.ok)throw new Error(await r.text());const assunto=await r.json();
   r=await fetch('/assuntos-proprios/'+assunto.id+'/pasta-teoria',{headers});if(!r.ok)throw new Error(await r.text());const pasta=await r.json();
   await abrirQuestoesAula(pasta.aula_id,'Aula de criação visual');
  });
  await p.getByRole('button',{name:'Criar bateria de questões',exact:true}).click();
  const novo= p.locator('#listaBateriasAula').getByRole('button',{name:'Abrir / editar questões',exact:true}).last();await novo.click();
  await p.waitForFunction(()=>document.querySelectorAll('#camposQuestaoCompleta .ck-content[contenteditable="true"]').length===7);
  await p.getByRole('button',{name:'Importar Markdown',exact:true}).first().click();
  const dlg=p.locator('dialog[open]');await dlg.locator('[data-md="fonte"]').fill('## Enunciado importado\n\n**Negrito** e *itálico*.\n\n- Primeiro\n- Segundo\n\nFórmula: \\(x^2\\).\n\n| A | B | C |\n|---|---|---|\n| Um | Dois | Três |');
  await dlg.getByRole('button',{name:'Importar material',exact:true}).click();await dlg.waitFor({state:'hidden'});
  await p.locator('#camposQuestaoCompleta .ck-content').evaluateAll(els=>els.forEach((el,i)=>{if(i)el.ckeditorInstance.setData(i===6?'<p><strong>Comentário formatado</strong> '+('Explicação. '.repeat(40))+'</p>':'<p><strong>Alternativa '+i+'</strong></p>')}));
  const antes=await p.evaluate(()=>QuestaoEditores.dados());assert.match(antes.enunciado,/<strong>/);assert.match(antes.enunciado,/ro-math-inline/);assert.match(antes.enunciado,/<table>/);
  await p.locator('#camposQuestaoCompleta .ck-content').first().evaluate(el=>{const ed=el.ckeditorInstance;ed.model.change(w=>w.setSelection(ed.model.document.getRoot(),'end'));});
  const png=fs.readFileSync(process.env.QUESTOES_PNG_FIXTURE||path.join(evidencias,'figura-fixture.png'));
  await p.locator('#camposQuestaoCompleta .teoria-imagens-controles input[type=file]').first().setInputFiles({name:'figura.png',mimeType:'image/png',buffer:png});
  await p.waitForFunction(()=>TeoriaEditor.pronto(document.querySelector('#questaoEnunciado'))&&QuestaoEditores.dados().enunciado.includes('<img '));
  const conteudo=await p.evaluate(()=>QuestaoEditores.dados().enunciado);assert.ok(!conteudo.includes('__imagens')&&!conteudo.includes('assinatura'));
  const resposta=p.waitForResponse(r=>new URL(r.url()).pathname==='/questoes'&&r.request().method()==='POST');
  await p.getByRole('button',{name:'Salvar questão',exact:true}).click();const r=await resposta;assert.equal(r.status(),200);const questao=await r.json();
  const card=p.locator('#cardQuestao_'+questao.id);await card.getByRole('button',{name:'Visualizar comentário',exact:true}).click();assert.ok(await card.locator('strong').count()>=6);
  await card.getByRole('button',{name:'Editar',exact:true}).click();await p.waitForFunction(()=>document.querySelectorAll('#camposQuestaoCompleta .ck-content[contenteditable="true"]').length===7);
  await p.waitForFunction(()=>[...document.querySelectorAll('#camposQuestaoCompleta .ck-content img')].every(i=>i.complete&&i.naturalWidth>0));
  assert.equal(canon((await p.evaluate(()=>QuestaoEditores.dados())).enunciado),canon(conteudo));
  await p.selectOption('#questaoTipoQuestao','MULTIPLA_4');await p.waitForFunction(()=>document.querySelectorAll('#camposQuestaoCompleta .ck-content[contenteditable="true"]').length===6);
  assert.equal(canon((await p.evaluate(()=>QuestaoEditores.dados())).enunciado),canon(conteudo));
  await p.selectOption('#questaoTipoQuestao','CERTO_ERRADO');await p.waitForFunction(()=>document.querySelectorAll('#camposQuestaoCompleta .ck-content[contenteditable="true"]').length===2);
  await p.check('input[name="gabarito_certo_errado"][value="E"]');
  const edicao=p.waitForResponse(r=>new URL(r.url()).pathname==='/questoes/'+questao.id&&r.request().method()==='PUT');
  await p.getByRole('button',{name:'Salvar edição',exact:true}).click();assert.equal((await edicao).status(),200);await p.waitForFunction(()=>document.querySelector('#textoBotaoSalvarQuestao')?.textContent!=='Salvar edição');await card.getByRole('button',{name:'Editar',exact:true}).waitFor();
  const q=await p.evaluate(async id=>(await fetch('/baterias/'+id+'/questoes',{headers:{Authorization:'Bearer isolado-admin'}})).json(),questao.bateria_id);
  assert.equal(q[0].tipo_questao,'CERTO_ERRADO');assert.deepEqual(q[0].alternativas,[]);assert.equal(q[0].gabarito,'E');
  await p.evaluate(async bateria=>{
   for(let i=0;i<8;i++){
    const r=await fetch('/questoes',{method:'POST',headers:{Authorization:'Bearer isolado-admin','Content-Type':'application/json'},body:JSON.stringify({bateria_id:bateria,enunciado:'Questão de teste '+i,comentario:'Comentário',tipo:'CERTO_ERRADO',tipo_questao:'CERTO_ERRADO',gabarito:'C',alternativas:[]})});if(!r.ok)throw new Error(await r.text());
   }
   await abrirQuestoesDaBateria(bateria);
  },questao.bateria_id);
  await p.waitForFunction(()=>document.querySelectorAll('#camposQuestaoCompleta .ck-content[contenteditable="true"]').length===7);
  await p.selectOption('#questaoTipoQuestao','CERTO_ERRADO');await p.waitForFunction(()=>document.querySelectorAll('#camposQuestaoCompleta .ck-content[contenteditable="true"]').length===2);
  await p.locator('#camposQuestaoCompleta .ck-content').evaluateAll(els=>els.forEach((el,i)=>el.ckeditorInstance.setData(i?'<p>Comentário final</p>':'<p>Décima questão</p>')));
  const conclusao=p.waitForResponse(r=>new URL(r.url()).pathname==='/baterias/'+questao.bateria_id+'/concluir'&&r.request().method()==='PUT');
  await p.getByRole('button',{name:'Salvar questão',exact:true}).click();assert.equal((await conclusao).status(),200);
  await p.goto(origin+'/__preview/entrar?perfil=aluno');
  await p.goto(origin+`/sprint.html?bateria_id=${questao.bateria_id}&contratacao_id=1&modo=resolver`);
  await p.waitForFunction(()=>[...document.querySelectorAll('.sprint-questao-enunciado img')].some(i=>i.complete&&i.naturalWidth>0));
  assert.ok(await p.locator('.sprint-questao-enunciado .katex').count());assert.ok(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await p.screenshot({path:path.join(evidencias,'imagem-importacao-aluno-390.png'),fullPage:true});
  assert.deepEqual(erros,[]);
  resultados.criacao='OK';resultados.markdown='OK';resultados.imagemUploadReaberturaLeitura='OK';resultados.trocaTipos='OK';resultados.conclusaoBateria='OK';
  await p.close();
  // CDN indisponível: HTML fica protegido; legado mantém a edição textual.
  const offline=await browser.newPage({viewport:{width:320,height:900}}),alertas=[];let puts=0;
  offline.on('dialog',d=>{alertas.push(d.message());d.accept()});offline.on('request',r=>{if(r.method()==='PUT'&&new URL(r.url()).pathname==='/questoes/1')puts++});
  await offline.route('**/*',r=>r.request().url().includes('/__ckeditor/')?r.abort():r.request().url().startsWith(origin)?r.continue():r.abort());
  await entrar(offline);await offline.locator('#listaBateriasAula').getByRole('button',{name:'Abrir / editar questões',exact:true}).first().click();
  await offline.locator('#cardQuestao_1').getByRole('button',{name:'Editar',exact:true}).click();await offline.waitForFunction(()=>document.querySelectorAll('#camposQuestaoCompleta .questao-editor-aviso').length===7&&[...document.querySelectorAll('#camposQuestaoCompleta .questao-editor-aviso')].every(e=>e.textContent.includes('indisponível')));
  assert.equal(await offline.locator('#questaoEnunciado').evaluate(e=>e.readOnly),true);
  await offline.getByRole('button',{name:'Salvar edição',exact:true}).click();assert.equal(puts,0);assert.ok(alertas.some(a=>a.includes('Reabra a questão')));
  await offline.getByRole('button',{name:'Descartar e fechar edição',exact:true}).click();await offline.locator('#cardQuestao_3').getByRole('button',{name:'Editar',exact:true}).click();
  await offline.waitForFunction(()=>[...document.querySelectorAll('#camposQuestaoCompleta .questao-editor-aviso')].every(e=>e.textContent.includes('indisponível')));
  assert.equal(await offline.locator('#questaoEnunciado').evaluate(e=>e.readOnly),false);assert.match(await offline.locator('#questaoEnunciado').inputValue(),/<b>literal<\/b>/);
  resultados.falhaCdnPreservaHtmlELegado='OK';await offline.close();
  fs.writeFileSync(path.join(evidencias,'fluxos.json'),JSON.stringify(resultados,null,2));console.log(JSON.stringify(resultados));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
