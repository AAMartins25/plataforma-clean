const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright-core');
const origin='http://127.0.0.1:8772',headers={Authorization:'Bearer isolado-aluno'};
(async()=>{
 const b=await chromium.launch({executablePath:'/home/codespace/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell',args:['--no-sandbox']});
 try {
  const p=await b.newPage({viewport:{width:320,height:900}});p.on('dialog',d=>d.accept());
  await p.route('**/*',r=>r.request().url().startsWith(origin)?r.continue():r.abort());
  await p.route('**/__ckeditor/**',r=>r.abort());
  const tentativa=(await (await p.request.get(origin+'/baterias/1/minha-tentativa-ativa?contratacao_id=1',{headers})).json()).tentativa;
  const texto='<b>Legado literal</b>\nSegunda linha';
  const created=await p.request.post(origin+'/me/anotacoes-questoes',{headers,data:{questao_id:10,bateria_id:1,tentativa_id:tentativa.id,contratacao_id:1,texto}});
  assert.equal(created.status(),200);const aid=(await created.json()).id;
  await p.goto(origin+'/__preview/entrar?perfil=aluno');
  // A completed attempt must reopen its review without submitting a new attempt.
  await p.locator('.sprint-revisao-questao-card').first().waitFor();
  const conjunto=await p.evaluate(()=>{
    const orig=questoes, url=location.href, ids=[...respostasConfirmadas];
    questoes=questoes.slice(0,9);const normal=bateriaRespondida();
    history.replaceState(null,'',url+'&revisao_id=1');const programada=bateriaRespondida();
    respostasConfirmadas.delete(Number(questoes[0].id));const incompleta=bateriaRespondida();
    questoes=orig;respostasConfirmadas.clear();ids.forEach(id=>respostasConfirmadas.add(id));history.replaceState(null,'',url);
    return {normal,programada,incompleta};
  });
  assert.deepEqual(conjunto,{normal:false,programada:true,incompleta:false});
  await p.goto(origin+'/minhas-anotacoes.html?curso_id=1&contratacao_id=1');
  const legacy=p.locator(`#box_anotacao_${aid} .registro-legado`);await legacy.waitFor();
  assert.equal(await legacy.textContent(),texto);assert.equal(await legacy.locator('b').count(),0);
  await p.evaluate(id=>editarAnotacao(id),aid);
  const plain=p.locator(`#texto_edicao_${aid}`);assert.equal(await plain.evaluate(e=>e.readOnly),false);
  await plain.fill('Anotação antiga editada sem CDN');
  const saved=p.waitForResponse(r=>r.request().method()==='PUT');await p.locator(`#btn_salvar_${aid}`).click();
  assert.equal((await saved).status(),200);
  const rows=await (await p.request.get(origin+'/me/minhas-anotacoes?contratacao_id=1',{headers})).json();
  assert.equal(rows.find(r=>r.anotacao_id===aid).texto_formato,'texto_puro');
  const rich=rows.find(r=>r.texto_formato==='html_v1');let updates=0;
  p.on('request',r=>{if(r.method()==='PUT')updates++;});
  await p.evaluate(id=>editarAnotacao(id),rich.anotacao_id);
  assert.equal(await p.locator(`#texto_edicao_${rich.anotacao_id}`).evaluate(e=>e.readOnly),true);
  await p.evaluate(id=>salvarEdicaoAnotacao(id),rich.anotacao_id);assert.equal(updates,0);
  const after=await (await p.request.get(origin+'/me/minhas-anotacoes?contratacao_id=1',{headers})).json();
  assert.equal(after.find(r=>r.anotacao_id===rich.anotacao_id).anotacao,rich.anotacao);
  const xss=await p.evaluate(()=>RegistroConteudo.renderizar('<p onclick="alert(1)">Teste</p><img src=x onerror=alert(1)><script>alert(1)</script>','html_v1'));
  assert.ok(!/<script|<img|onclick|onerror/.test(xss));
  await p.unroute('**/__ckeditor/**');
  await p.goto(origin+'/__preview/entrar?perfil=admin');
  await p.selectOption('#cursoExistenteSelect','1');await p.click('#btnUsarCursoExistente');
  await p.getByRole('button',{name:'Trabalhar nesta disciplina',exact:true}).click();
  await p.getByRole('button',{name:'Aulas',exact:true}).first().click();
  await p.getByRole('button',{name:'🏁 Questões',exact:true}).click();
  await p.getByRole('button',{name:'Abrir / editar questões',exact:true}).first().click();
  await p.locator('#cardQuestao_1').getByRole('button',{name:'Editar',exact:true}).click();
  await p.waitForFunction(()=>document.querySelectorAll('#camposQuestaoCompleta .ck-content[contenteditable=true]').length===7);
  assert.equal(await p.locator('#camposQuestaoCompleta .teoria-markdown-controles button').count(),7);
  assert.equal(await p.locator('#camposQuestaoCompleta .ck-content').first().evaluate(e=>e.ckeditorInstance.ui.componentFactory.has('imagemPropria')),true);
  const result={conjuntoVigenteRevisao:'OK',editorAdmin7BotoesMarkdown:'OK',imagensAdminPreservadas:'OK',retomadaConcluida:'OK' ,legadoLiteral:'OK',fallbackTextoSemCDN:'OK',htmlBloqueadoSemCDN:'OK',htmlPreservado:'OK',xssExibicao:'OK'};
  fs.writeFileSync(path.resolve(__dirname,'../evidencias/aluno-formatacao/legado.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await b.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
