// PLAYWRIGHT_MODULE=/path/to/playwright-core CHROMIUM_PATH=/path/to/chrome node site-html/test-minhas-anotacoes-questao.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const origin = 'http://anotacoes.test';
const api = 'https://plataforma-quality-backend.onrender.com';
const imageId = '12345678-1234-4234-8234-123456789abc';
const imageSrc = '/midias/imagens/' + imageId;
const richQuestion = `<p><strong>Referência: Prova 2026</strong></p><p>Enunciado formatado <em>com destaque</em>.</p><p>A) Alternativa um</p><p>B) Alternativa dois</p><figure class="table"><table><tbody><tr><th>Item</th><th>Valor</th></tr><tr><td>Área</td><td>25</td></tr></tbody></table></figure><p><span class="ro-math-inline">x^2 + y^2</span></p><figure class="image"><img src="${imageSrc}" alt="Figura da questão"></figure>`;
const richNote = '<p><strong>Anotação do aluno</strong> <em>com formatação</em></p><ul><li>Revisar o cálculo</li></ul><p><span class="ro-math-inline">x^2</span></p>';
const fixtures = [
  {anotacao_id: 11, questao_id: 101, disciplina_id: 1, disciplina_nome: 'Matemática', disciplina_ordem: 1,
    assunto_id: 1, assunto_nome: 'Geometria', assunto_ordem: 1, bateria_id: 7, tipo: 'MULTIPLA',
    enunciado: richQuestion, enunciado_formato: 'html_v1', texto_resposta: '<p>B) Alternativa dois</p>', texto_resposta_formato: 'html_v1',
    gabarito: 'B', comentario: '<p>Comentário <u>formatado</u>.</p>', comentario_formato: 'html_v1', anotacao: richNote, texto_formato: 'html_v1'},
  {anotacao_id: 12, questao_id: 102, disciplina_id: 1, disciplina_nome: 'Matemática', disciplina_ordem: 1,
    assunto_id: 2, assunto_nome: 'Álgebra', assunto_ordem: 2, bateria_id: 7, tipo: 'CERTO_ERRADO',
    enunciado: 'Enunciado legado\nSegunda linha', gabarito: 'E', comentario: 'Comentário legado', anotacao: 'Anotação simples', texto_formato: 'texto_puro'},
  {anotacao_id: 13, disciplina_id: 2, disciplina_nome: 'Outra origem', disciplina_ordem: 2,
    assunto_id: 3, assunto_nome: 'Geral', assunto_ordem: 1, enunciado: 'Conteúdo sem vínculo', anotacao: 'Registro sem questão', texto_formato: 'texto_puro'}
];
const mime = {'.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.woff2':'font/woff2'};
(async () => {
  const browser = await chromium.launch({headless:true,
    ...(process.env.CHROMIUM_PATH ? {executablePath:process.env.CHROMIUM_PATH} : {}), args:['--no-sandbox']});
  try {
    for (const width of [1366,768,390,320]) {
      const context = await browser.newContext({viewport:{width,height:900}});
      const errors = [], mutations = [], requests = [];
      let records = structuredClone(fixtures);
      await context.addInitScript(() => localStorage.setItem('access_token','synthetic-test-token'));
      await context.route('**/*', async route => {
        const request = route.request(), url = new URL(request.url());
        if (url.origin === origin) {
          if (url.pathname === '/test-image.svg') return route.fulfill({contentType:'image/svg+xml', body:'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="160"><rect width="600" height="160" fill="#fdee8a"/></svg>'});
          const file = path.resolve(__dirname, '.' + decodeURIComponent(url.pathname));
          if (!file.startsWith(__dirname + path.sep) || !fs.existsSync(file)) return route.fulfill({status:404,body:'Not found'});
          return route.fulfill({contentType:mime[path.extname(file)] || 'application/octet-stream',body:fs.readFileSync(file)});
        }
        if (url.origin !== api) return route.abort();
        requests.push({path:url.pathname,query:url.search,method:request.method()});
        if (url.pathname === '/me') return route.fulfill({json:{id:1,nome:'Ana Silva'}});
        if (url.pathname === '/me/minhas-anotacoes') return route.fulfill({json:records});
        if (url.pathname === '/baterias/7/imagens/assinaturas') return route.fulfill({json:{imagens:[{src:imageSrc,url:'/test-image.svg'}]}});
        if (url.pathname === '/me/ckeditor-chave') return route.fulfill({json:{licenseKey:''}});
        if (request.method() === 'PUT') {
          const body = request.postDataJSON(); mutations.push({method:'PUT',body});
          records.find(a=>a.anotacao_id===12).anotacao=body.texto;
          return route.fulfill({json:body});
        }
        if (request.method() === 'DELETE') {
          mutations.push({method:'DELETE'}); records=records.filter(a=>a.anotacao_id!==12);
          return route.fulfill({status:204});
        }
        return route.fulfill({status:404,json:{detail:'Unexpected test request'}});
      });
      const page = await context.newPage();
      page.on('pageerror',err=>errors.push(err.message));
      await page.goto(origin+'/minhas-anotacoes.html?curso_id=1&contratacao_id=9&curso_nome=Curso');
      const card = id => page.locator(`.minhas-anotacoes-anotacao-card:has(#box_anotacao_${id})`);
      const toggle = id => card(id).locator('.minhas-anotacoes-alternar-questao');
      const question = id => page.locator('#questao_relacionada_'+id);
      const checkOverflow = async () => assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth > innerWidth), false, 'sem overflow horizontal');
      await card(11).waitFor();
      for (const id of [11,12]) {
        assert.equal(await question(id).isVisible(),false);
        assert.equal(await toggle(id).getAttribute('aria-expanded'),'false');
        assert.equal(await toggle(id).textContent(),'Ver questão relacionada');
      }
      assert.equal(await card(13).locator('.minhas-anotacoes-alternar-questao').count(),0,'outra origem mantém apresentação');
      assert.equal(await card(13).locator('.minhas-anotacoes-enunciado').isVisible(),true);
      const order = await card(11).evaluate(c => {
        const note=c.querySelector('.minhas-anotacoes-bloco-aluno').getBoundingClientRect();
        const actions=c.querySelector('.minhas-anotacoes-acoes').getBoundingClientRect();
        const last=c.querySelector('.minhas-anotacoes-btn-excluir').getBoundingClientRect();
        const toggle=c.querySelector('.minhas-anotacoes-alternar-questao').getBoundingClientRect();
        return {ordered:note.bottom<=actions.top && actions.bottom<=toggle.top,right:Math.abs(last.right-actions.right)};
      });
      assert.equal(order.ordered,true); assert.ok(order.right<.02,'Editar e Excluir à direita');
      const noteBefore = await card(11).locator('.minhas-anotacoes-bloco-aluno').innerHTML();
      await checkOverflow();
      await toggle(11).click();
      assert.equal(await question(11).isVisible(),true);
      assert.equal(await toggle(11).getAttribute('aria-expanded'),'true');
      assert.equal(await toggle(11).textContent(),'Ocultar questão relacionada');
      await question(11).locator('.katex').waitFor();
      await page.waitForFunction(()=>document.querySelector('#questao_relacionada_11 img')?.naturalWidth > 0);
      assert.match(await question(11).innerText(),/Referência: Prova 2026/);
      assert.match(await question(11).innerText(),/A\) Alternativa um/);
      assert.match(await question(11).innerText(),/B\) Alternativa dois/);
      assert.equal(await question(11).locator('table').count(),1);
      assert.equal(await question(11).locator('.minhas-anotacoes-comentario u').textContent(),'formatado');
      assert.equal(await question(11).locator('img').evaluate(img=>img.naturalWidth),600);
      const contentBefore = await question(11).innerHTML();
      if (process.env.SCREENSHOT_DIR) {
        fs.mkdirSync(process.env.SCREENSHOT_DIR,{recursive:true});
        await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR,`anotacoes-expandida-${width}.png`),fullPage:true});
      }
      await checkOverflow();
      await toggle(11).focus(); await page.keyboard.press('Enter');
      assert.equal(await question(11).isVisible(),false);
      await page.keyboard.press('Space');
      assert.equal(await question(11).isVisible(),true);
      assert.equal(await question(11).innerHTML(),contentBefore,'reabrir preserva o DOM completo');
      assert.equal(await card(11).locator('.minhas-anotacoes-bloco-aluno').innerHTML(),noteBefore);
      assert.equal(await question(12).isVisible(),false,'cards independentes');
      await toggle(12).click(); assert.match(await question(12).innerText(),/Gab\. ERRADO/);
      await checkOverflow();
      assert.equal(mutations.length,0,'expandir e recolher não gravam dados');
      await page.locator('#filtro_assunto').selectOption('2'); assert.equal(await page.locator('.minhas-anotacoes-anotacao-card').count(),1);
      await page.locator('#filtro_assunto').selectOption('');
      await page.locator('#filtro_disciplina').selectOption('2'); assert.equal(await page.locator('.minhas-anotacoes-anotacao-card').count(),1);
      await page.locator('#filtro_disciplina').selectOption('1'); assert.equal(await page.locator('.minhas-anotacoes-anotacao-card').count(),2);
      // Conteúdo rico: abrir o editor e cancelar conserva a anotação original.
      await card(11).getByRole('button',{name:'Editar',exact:true}).click();
      await card(11).getByRole('button',{name:'Cancelar',exact:true}).click();
      assert.equal(await card(11).locator('.minhas-anotacoes-bloco-aluno').innerHTML(),noteBefore);
      // O editor existente permite texto simples quando não há chave comercial na fixture.
      await card(12).getByRole('button',{name:'Editar',exact:true}).click();
      const field = page.locator('#texto_edicao_12');
      await page.waitForFunction(()=>document.getElementById('texto_edicao_12')?.readOnly===false);
      await field.fill('Anotação simples revisada');
      await card(12).getByRole('button',{name:'Salvar',exact:true}).click();
      await card(12).locator('.minhas-anotacoes-bloco-aluno-texto').filter({hasText:'Anotação simples revisada'}).waitFor();
      assert.deepEqual(mutations[0],{method:'PUT',body:{texto:'Anotação simples revisada',texto_formato:'texto_puro'}});
      page.once('dialog',d=>d.dismiss()); await card(12).getByRole('button',{name:'Excluir',exact:true}).click();
      assert.equal(mutations.length,1,'cancelar exclusão não remove');
      page.once('dialog',d=>d.accept()); await card(12).getByRole('button',{name:'Excluir',exact:true}).click();
      await card(12).waitFor({state:'detached'}); assert.equal(mutations[1].method,'DELETE');
      for (const r of requests.filter(r=>r.path.startsWith('/me') || r.path.includes('/assinaturas'))) assert.ok(r.query.includes('contratacao_id=9'),'contexto preservado');
      await checkOverflow(); assert.deepEqual(errors,[]);
      if (process.env.SCREENSHOT_DIR) {
        fs.mkdirSync(process.env.SCREENSHOT_DIR,{recursive:true});
        await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR,`anotacoes-${width}.png`),fullPage:true});
      }
      console.log(`${width}px: recolher/expandir, teclado, formatação, imagem, tabela, fórmula, filtros, editar/cancelar/salvar/excluir e ausência de overflow: OK`);
      await context.close();
    }
  } finally {await browser.close();}
})().catch(err=>{console.error(err);process.exitCode=1;});
