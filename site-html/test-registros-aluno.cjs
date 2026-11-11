const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const origin = process.env.ALUNO_PREVIEW_URL || 'http://127.0.0.1:8772';
const out = path.resolve(__dirname, '../evidencias/aluno-formatacao');
const rich = '<p><strong>Negrito</strong> <i>itálico</i> <u>sublinhado</u></p><ul><li>Lista</li></ul><figure class="table"><table><tbody><tr><td>Coluna A</td><td>Coluna B</td></tr><tr><td>Valor 1</td><td>Valor 2</td></tr></tbody></table></figure><p><span class="ro-math-inline">p \\land q \\Rightarrow r</span></p>';
const contexto = 'curso_id=1&contratacao_id=1';
async function setData(p, id) {
  await p.waitForFunction(id => document.getElementById(id)?.parentElement.querySelector('.ck-content')?.ckeditorInstance, id);
  await p.locator('#'+id).evaluate((field, html) => field.parentElement.querySelector('.ck-content').ckeditorInstance.setData(html), rich);
}
async function overflow(p) {const n=await p.evaluate(()=>document.documentElement.scrollWidth-innerWidth);if(n){console.log(await p.evaluate(()=>[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).slice(0,18).map(e=>({tag:e.tagName,classe:e.className,width:e.getBoundingClientRect().width,right:e.getBoundingClientRect().right,whiteSpace:getComputedStyle(e).whiteSpace}))));await p.screenshot({path:path.join(out,'overflow-debug.png')});}assert.equal(n,0);}
(async () => {
  fs.mkdirSync(out,{recursive:true});
  const b = await chromium.launch({executablePath:'/home/codespace/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell',args:['--no-sandbox']});
  const results=[];
  try {
    let index=0;
    for (const width of (process.env.TEST_WIDTH ? [Number(process.env.TEST_WIDTH)] : [320,390,768,1366])) {
      const p=await b.newPage({viewport:{width,height:900}}); const errors=[];let posts=0;
      p.on('pageerror',e=>errors.push(e.message));p.on('dialog',d=>d.accept());
      await p.route('**/*',r=>r.request().url().startsWith(origin)?r.continue():r.abort());
      // Every width exercises a fresh resolution; records still go to the synthetic API.
      await p.route('**/baterias/1/minha-tentativa-ativa*',r=>r.fulfill({json:{tentativa:null,respostas:[]}}));
      p.on('request',r=>{if(r.url().endsWith('/baterias/concluir')&&r.method()==='POST')posts++;});
      await p.goto(origin+'/__preview/entrar?perfil=aluno');
      await p.locator('#btnResponder_10').waitFor();
      assert.equal(await p.locator('.sprint-conclusao-btn:disabled').count(),2);
      await p.evaluate(()=>concluirBateriaAluno('agora'));assert.equal(posts,0);
      for(let id=1;id<=10;id++) {
        await p.locator(`input[name=resposta_${id}]`).first().check();
        if(id<=2)await p.locator(`input[name=dificuldade_${id}]`).first().check();
      }
      assert.equal(await p.locator('.sprint-conclusao-btn:disabled').count(),2);
      for(let id=1;id<=9;id++)await p.locator('#btnResponder_'+id).click();
      assert.equal(await p.locator('.sprint-conclusao-btn:disabled').count(),2);
      await p.evaluate(()=>revisarAgora());assert.equal(await p.locator('#btnResponder_10').count(),1);
      await p.locator('input[name=resposta_10][value=NAO_SEI]').check();
      await p.locator('#btnResponder_10').click();
      assert.equal(await p.locator('.sprint-conclusao-btn:disabled').count(),0);
      await p.locator('input[name=resposta_10][value=C]').check();
      assert.equal(await p.locator('.sprint-conclusao-btn:disabled').count(),2);
      await p.locator('#btnResponder_10').click();
      await overflow(p);
      await p.locator('#boxConcluirBateria').screenshot({path:path.join(out,`botoes-${width}.png`)});
      await p.getByRole('button',{name:'Revisar agora',exact:true}).click();
      const qid=++index;
      await p.locator(`#registro_anotacao_${qid} .sprint-registro-abrir`).click();
      await setData(p,`anotacao_texto_${qid}`);
      const ed=p.locator(`#anotacao_texto_${qid}`);
      assert.equal(await ed.evaluate(f=>f.parentElement.querySelector('.ck-content').ckeditorInstance.plugins.has('ImageUpload')),false);
      await overflow(p);
      await p.locator(`#registro_anotacao_${qid}`).screenshot({path:path.join(out,`editor-${width}.png`)});
      const saved=p.waitForResponse(r=>r.url().includes('/me/anotacoes-questoes')&&r.request().method()==='POST');
      await p.locator(`#btn_salvar_anotacao_${qid}`).click();assert.equal((await saved).status(),200);
      await p.locator(`#registro_mensagem_${qid} .sprint-registro-abrir`).click();
      await setData(p,`mensagem_texto_${qid}`);
      const sent=p.waitForResponse(r=>r.url().includes('/me/mensagens-prof')&&r.request().method()==='POST');
      await p.locator(`#btn_salvar_mensagem_${qid}`).click();assert.equal((await sent).status(),200);
      await p.goto(origin+'/minhas-anotacoes.html?'+contexto);
      await p.locator('.registro-conteudo strong').first().waitFor();
      assert.ok(await p.locator('.registro-conteudo .katex').count());assert.ok(await p.locator('.registro-conteudo table').count());await overflow(p);
      await p.locator('.minhas-anotacoes-btn-editar').first().click();
      const edit=p.locator('textarea[id^=texto_edicao_]').first();const id=await edit.getAttribute('id');await setData(p,id);
      const update=p.waitForResponse(r=>r.url().includes('/me/anotacoes-questoes/')&&r.request().method()==='PUT');
      await p.locator('button[id^=btn_salvar_]').first().click();assert.equal((await update).status(),200);
      await p.goto(origin+'/mensagens-prof.html?'+contexto);
      await p.locator('.registro-conteudo strong').first().waitFor();await overflow(p);
      await p.getByRole('button',{name:'Reformular mensagem ao prof'}).first().click();
      const reform=p.locator('textarea[id^=reformulacao_texto_]').first();await setData(p,await reform.getAttribute('id'));
      const replaced=p.waitForResponse(r=>r.url().includes('/reformular')&&r.request().method()==='POST');
      await p.getByRole('button',{name:'Confirmar e enviar',exact:true}).click();assert.equal((await replaced).status(),200);
      await p.locator('.registro-conteudo strong').first().waitFor();await overflow(p);
      assert.deepEqual(errors,[]);
      results.push({width,botoes:'OK',acionamentoAntecipado:'bloqueado',decimaResposta:'OK',alteracaoExigeResponder:'OK',anotacaoSalvarReabrirEditar:'OK',mensagemEnviarReformular:'OK',formulasTabelas:'OK',imagens:'sem plugin',overflow:0});
      console.log(JSON.stringify(results.at(-1)));await p.close();
    }
    fs.writeFileSync(path.join(out,'navegador.json'),JSON.stringify(results,null,2));
  } finally {await b.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
