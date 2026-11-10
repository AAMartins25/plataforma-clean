// Teste local: renderizadores reais, dados sintéticos apenas em memória no navegador.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const origin = process.env.QUESTOES_PREVIEW_URL || 'http://127.0.0.1:8769';
assert.match(origin, /^http:\/\/127\.0\.0\.1:\d+$/);
const out = path.resolve(__dirname, '../evidencias/alinhamento-alternativas');
fs.mkdirSync(out, {recursive:true});

async function medir(page, tela, width, minimo = 9) {
  await page.waitForFunction(() => [...document.querySelectorAll('.questao-alternativa img')].every(i => i.complete && i.naturalWidth));
  const medidas = await page.locator('.questao-alternativa').evaluateAll(rows => rows.map(row => {
    const letra = row.querySelector(':scope > b, :scope > .questoes-criticas-alternativa-letra');
    const texto = row.lastElementChild;
    const walker = document.createTreeWalker(texto, NodeFilter.SHOW_TEXT);
    const rects = [];
    while(walker.nextNode()) {
      const node = walker.currentNode;
      if(!node.textContent.trim() || node.parentElement.closest('.katex-mathml')) continue;
      const range = document.createRange(); range.selectNodeContents(node);
      rects.push(...[...range.getClientRects()].filter(r => r.width && r.height));
    }
    const lr = letra.getBoundingClientRect(), tr = texto.getBoundingClientRect();
    const first = rects[0];
    return {display:getComputedStyle(row).display, delta:Math.abs(lr.top - tr.top),
      linha:first ? Math.abs(first.top - lr.top) : 0,
      recuo:tr.left - lr.right,
      invadeLetra:rects.some(r => r.left < tr.left - 1),
      transborda:row.scrollWidth > row.clientWidth + 1};
  }));
  assert.ok(medidas.length >= minimo, `${tela}: alternativas ausentes`);
  for(const [i,m] of medidas.entries()) {
    assert.equal(m.display,'grid',`${tela}/${width}/${i}: layout`);
    assert.ok(m.delta <= 1, `${tela}/${width}/${i}: blocos desalinhados ${JSON.stringify(m)}`);
    assert.ok(m.linha <= 8, `${tela}/${width}/${i}: primeira linha desalinhada ${JSON.stringify(m)}`);
    assert.ok(m.recuo >= 6 && !m.invadeLetra, `${tela}/${width}/${i}: recuo ${JSON.stringify(m)}`);
    assert.ok(!m.transborda, `${tela}/${width}/${i}: overflow`);
  }
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${tela}/${width}: overflow página`);
  await page.screenshot({path:path.join(out,`${tela}-${width}.png`),fullPage:true});
  return {tela,width,alternativas:medidas.length,alinhamento:'OK',recuo:'OK',overflow:false};
}

(async()=>{
  const browser = await chromium.launch({executablePath:process.env.CHROMIUM_BIN || '/home/codespace/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell',args:['--no-sandbox']});
  const results=[];
  try {
    for(const width of [1366,768,390,320]) {
      const page=await browser.newPage({viewport:{width,height:900}}), errors=[];
      page.on('pageerror',e=>errors.push(e.message));
      await page.route('**/*',r=>r.request().url().startsWith(origin)?r.continue():r.abort());
      await page.goto(origin+'/__preview/entrar?perfil=aluno');
      await page.locator('#questao_1').waitFor();
      // Inclui imagens autorizadas e fórmulas da fixture original.
      await page.evaluate(()=>{
        const base=questoes[0];
        const imagem=base.enunciado.match(/<figure class="image[\s\S]*?<\/figure>/)?.[0] || '';
        const longo='Alternativa extensa com várias linhas e conteúdo preservado. '.repeat(10);
        const textos=[
          '<p><strong>Negrito</strong> e <i>itálico</i>. '+longo+'</p><p>Segundo parágrafo.</p>',
          '<ul><li>Primeiro item '+longo+'</li><li>Segundo item<ul><li>Subitem</li></ul></li></ul>',
          '<ol><li>Lista numerada '+longo+'</li><li>Outro item</li></ol>',
          '<p>Fórmula <span class="ro-math-inline">x^2 + y^2</span> '+longo+'</p><figure class="ro-math-display">\\frac{a+b}{c}</figure>',
          '<p>Imagem e texto '+longo+' '+('PalavraSemEspacos'.repeat(30))+'</p>'+imagem
        ];
        window.fixtureQuestoes=[
          {...base,id:1,gabarito:'B',alternativas:textos.map((texto,i)=>({letra:'ABCDE'[i],texto,texto_formato:'html_v1'}))},
          {...base,id:2,gabarito:'A',enunciado:'Questão antiga',enunciado_formato:'texto_puro',alternativas:[... 'ABCDE'].map(letra=>({letra,texto:'Texto antigo <b>literal</b> '+longo+'\nContinuação com quebra explícita.',texto_formato:'texto_puro'}))}
        ];
        questoes=structuredClone(window.fixtureQuestoes);renderizarTodasQuestoes();
      });
      await page.waitForFunction(()=>document.querySelectorAll('.questao-alternativa .katex').length>=2);
      assert.ok(await page.locator('.questao-alternativa img').count(),'Fixture deve conter imagem real');
      results.push(await medir(page,'resolucao',width));
      // Clique no texto formatado, troca de opção e resposta persistida em memória.
      await page.locator('#alt_1_B li').first().click();
      assert.equal(await page.locator('input[name="resposta_1"]:checked').inputValue(),'B');
      await page.locator('#alt_1_A strong').click();
      assert.equal(await page.locator('input[name="resposta_1"]:checked').inputValue(),'A');
      await page.locator('input[name="dificuldade_1"]').first().check();
      await page.evaluate(()=>responderQuestaoLista(1,0));
      assert.equal(await page.evaluate(()=>respostasAluno[1]),'A');
      await page.evaluate(()=>{respostasAluno[2]='A';revisarAgora()});
      results.push(await medir(page,'revisao',width));
      assert.equal(await page.locator('.sprint-revisao-alternativa-correta').count(),2);
      assert.equal(await page.locator('.sprint-revisao-alternativa-errada').count(),1);
      assert.ok((await page.locator('.sprint-revisao-alternativa').allTextContents()).some(s=>s.includes('<b>literal</b>')));
      const sinteticas = await page.evaluate(()=>window.fixtureQuestoes);
      // Renderizador antigo não usado pelo fluxo principal: fornece a variável
      // ehCertoErrado que ele já pressupõe, sem corrigir essa pendência fora do escopo.
      await page.evaluate(()=>{window.ehCertoErrado=false;indiceAtual=0;renderizarQuestao()});
      results.push(await medir(page,'resolucao-individual',width,5));
      assert.equal(await page.locator('input[name="resposta"]:checked').inputValue(),'A');
      await page.locator('.questao-alternativa').nth(1).locator('li').first().click();
      assert.equal(await page.locator('input[name="resposta"]:checked').inputValue(),'B');
      await page.goto(origin+'/__preview/entrar?perfil=revisao');
      await page.locator('#questao_1').waitFor();
      assert.equal(await page.locator('.questao-alternativa').count(),9);
      await page.goto(origin+'/questoes-criticas.html?curso_id=1&contratacao_id=1');
      await page.waitForLoadState('networkidle');
      await page.evaluate(qs=>{
        document.querySelector('main').innerHTML=qs.map((q,i)=>montarCardQuestaoCritica({...q,questao_id:q.id,questao_ordem:i+1},i+1,'erros')).join('');
      },sinteticas);
      results.push(await medir(page,'criticas',width));
      await page.goto(origin+'/teoria.html?curso_id=1&contratacao_id=1');
      await page.waitForLoadState('networkidle');
      await page.evaluate(async qs=>{
        pastaAtualId=null;aulaAtualId=null;
        document.querySelector('#detalhes_aula').innerHTML='<div class="card"><div id="questoes_1"></div></div>';
        document.querySelector('#detalhes_aula').style.display='block';
        tryMany=async()=>qs;
        await carregarQuestoes(1);
      },sinteticas);
      results.push(await medir(page,'teoria',width));
      assert.deepEqual(errors,[],`${width}: erros de JavaScript`);
      await page.close();
    }
    fs.writeFileSync(path.join(out,'resultado.json'),JSON.stringify(results,null,2));
    console.log(JSON.stringify(results,null,2));
  } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
