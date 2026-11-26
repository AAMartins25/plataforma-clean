// API simulada; Playwright e Chromium são fornecidos pelo ambiente de teste.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const root = __dirname;
const fonte = fs.readFileSync(path.join(root, 'test-gestao-cursos-browser.py'), 'utf8');
const mock = fonte.match(/MOCK=r'''\n([\s\S]*?)\n'''/)[1];
const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost').pathname;
  let conteudo;
  if (url.endsWith('/js/app.js')) conteudo = mock;
  else if (url.endsWith('/js/admin.js')) conteudo = fs.readFileSync(path.join(root, 'js/admin.js'), 'utf8') + '\n' + mock;
  else if (url.endsWith('/js/sessao.js') || url.endsWith('/js/admin-acesso.js')) conteudo = '';
  else if (url.endsWith('/js/editor-descricao-publica.js')) conteudo = 'window.DescricaoPublicaEditor={carregar:async()=>{},bloquear:()=>{},limpar:()=>{},obter:()=>""};';
  else {
    try { conteudo = fs.readFileSync(path.join(root, url)); }
    catch (_) { res.writeHead(404); return res.end(); }
  }
  res.setHeader('Content-Type', url.endsWith('.js') ? 'text/javascript; charset=utf-8' : url.endsWith('.css') ? 'text/css; charset=utf-8' : 'text/html; charset=utf-8');
  res.end(conteudo);
});
(async () => {
  let browser;
  try {
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    browser = await chromium.launch({executablePath: process.env.CHROMIUM_BIN, args: ['--no-sandbox']});
    for (const width of [320, 390, 768, 1366]) for (const uf of ['NACIONAL', 'REGIONAL']) {
      const page = await browser.newPage({viewport: {width, height: 900}});
      await page.goto(`http://127.0.0.1:${server.address().port}/admin/criar-curso-completo.html`);
      await page.waitForFunction(() => window.GestaoCursos && window.chamadas?.some(c => c[1] === '/admin/cursos'));
      for (const seletor of ['#novo-uf', '#editar-uf']) {
        const valores = await page.locator(seletor + ' option').evaluateAll(options => options.map(o => o.value));
        assert.equal(valores.length, 30);
        assert.deepEqual(valores.slice(0, 4), ['', 'NACIONAL', 'REGIONAL', 'AC']);
      }
      await page.evaluate(uf => {
        cursoNome.value='Curso Nacional';
        for(const [k,v] of Object.entries({banca:'Banca',cargo:'Cargo',orgao:'Órgão',ano:2026,uf}))
          document.getElementById('novo-'+k).value=v;
        formCurso.requestSubmit();
      }, uf);
      await page.waitForFunction(uf => window.chamadas.some(c => c[0] === 'POST' && c[1] === '/cursos' && c[2].uf === uf), uf);
      await page.waitForFunction(() => cursoExistenteSelect.value === '20');
      await page.evaluate(async uf => {
        dadosCursos.push({id:30,nome:'Outro âmbito',ativo:true,uf:uf === 'NACIONAL' ? 'REGIONAL' : 'NACIONAL'});
        await GestaoCursos.carregar(20);
      }, uf);
      assert.deepEqual(await page.locator('#filtro-uf option').evaluateAll(o => o.slice(0, 3).map(x=>x.value)), ['', 'NACIONAL', 'REGIONAL']);
      await page.selectOption('#filtro-uf', uf);
      assert.deepEqual(await page.locator('#cursoExistenteSelect option').evaluateAll(o=>o.slice(1).map(x=>x.value)), ['20']);
      await page.evaluate(() => { btnUsarCursoExistente.click(); btnEditarCurso.click(); });
      assert.equal(await page.locator('#editar-uf').inputValue(), uf);
      await page.evaluate(() => { document.querySelector('#editar-nome').value='Editado Nacional'; formEditarCurso.requestSubmit(); });
      await page.waitForFunction(uf => window.chamadas.some(c => c[0] === 'PUT' && c[1] === '/cursos/20' && c[2].uf === uf), uf);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth || document.body.scrollWidth > innerWidth), false);
      await page.goto(`http://127.0.0.1:${server.address().port}/admin/cursos.html`);
      const opcoes = await page.locator('#novo-uf option').evaluateAll(o => o.map(x=>x.value));
      assert.equal(opcoes.length, 30); assert.deepEqual(opcoes.slice(0, 4), ['', 'NACIONAL', 'REGIONAL', 'AC']);
      await page.selectOption('#novo-uf', uf);
      assert.equal(await page.locator('#novo-uf').inputValue(), uf);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth || document.body.scrollWidth > innerWidth), false);
      await page.close();
      console.log(`UF ${uf}: cadastro, edição, filtro e largura ${width}px aprovados`);
    }
  } finally { await browser?.close(); server.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
