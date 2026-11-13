// Home real no Chromium, com APIs simuladas. Nunca acessa Render ou pagamentos reais.
// PLAYWRIGHT_MODULE e CHROMIUM_BIN permitem reutilizar o navegador local.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = __dirname;
const artifacts = process.env.HOME_TEST_ARTIFACTS;
const courses = [
  {id: 1, nome: 'RESUMÃO PROFESSOR EDUCAÇÃO INFANTIL ALVORADA-RS 2026', ativo: true},
  {id: 2, nome: 'RESUMÃO AGENTE COMUNITÁRIO DE SAÚDE PORTO ALEGRE-RS 2026', ativo: true},
  {id: 3, nome: 'RESUMÃO TÉCNICO JUDICIÁRIO 2026', ativo: true},
  {id: 4, nome: 'RESUMÃO ASSISTENTE ADMINISTRATIVO 2026', ativo: true},
  {id: 5, nome: 'RESUMÃO PROFESSOR MATEMÁTICA 2026', ativo: true},
  {id: 6, nome: 'RESUMÃO FISCAL 2026', ativo: true},
  {id: 7, nome: 'Curso inativo', ativo: false}
];
const server = http.createServer((req, res) => {
  const file = path.resolve(root, '.' + new URL(req.url, 'http://localhost').pathname);
  if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
    res.writeHead(404).end(); return;
  }
  res.setHeader('Content-Type', ({'.html':'text/html; charset=utf-8', '.css':'text/css', '.js':'application/javascript', '.woff2':'font/woff2'})[path.extname(file)] || 'application/octet-stream');
  res.end(fs.readFileSync(file));
});

(async () => {
  let browser;
  try {
    if (artifacts) fs.mkdirSync(artifacts, {recursive: true});
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const origin = `http://127.0.0.1:${server.address().port}`;
    browser = await chromium.launch({executablePath: process.env.CHROMIUM_BIN, args: ['--no-sandbox']});
    const measurements = [];
    async function context(width, user = null, data = courses, fail = false) {
      const ctx = await browser.newContext({viewport: {width, height: 900}, reducedMotion: 'reduce'});
      if (user) await ctx.addInitScript(() => localStorage.setItem('access_token', 'token-ficticio'));
      await ctx.route('**/*', async route => {
        const u = new URL(route.request().url());
        if (u.origin === origin) return route.continue();
        if (u.origin !== 'https://plataforma-quality-backend.onrender.com') return route.abort();
        const payload = u.pathname === '/cursos-publicos' ? data : u.pathname === '/me' ? user : [];
        await route.fulfill({status: fail && u.pathname === '/cursos-publicos' ? 503 : 200, json: payload});
      });
      return ctx;
    }
    function noOverflow(page) {
      return page.evaluate(() => document.documentElement.scrollWidth <= innerWidth);
    }
    for (const width of [320, 390, 768, 1366]) {
      for (const signedIn of [false, true]) {
        const user = signedIn ? {id: 1, nome: 'Alexandre de Oliveira Administrador', ativo: true, is_aluno: true, is_admin: true, tipo_admin: 'admin_geral'} : null;
        const ctx = await context(width, user);
        const page = await ctx.newPage();
        const errors = []; page.on('pageerror', e => errors.push(e.message));
        await page.goto(origin + '/index.html');
        await page.locator('.curso-publico-card').first().waitFor();
        if (signedIn) await page.locator('.ro-header-identity').waitFor();
        assert.equal(await page.locator('.curso-publico-card').count(), 4);
        assert.equal(await page.locator('.home-course-meta').count(), 0, 'Não deve inventar metadados');
        const sorted = courses.filter(c => c.ativo).sort((a,b) => a.nome.localeCompare(b.nome));
        assert.deepEqual(await page.locator('.curso-publico-nome').allTextContents(), sorted.slice(0,4).map(c => c.nome));
        assert.equal(await page.locator('.curso-publico-card').first().getAttribute('href'), `curso-info.html?curso_id=${sorted[0].id}&curso_nome=${encodeURIComponent(sorted[0].nome)}`);
        const geometry = await page.evaluate(() => {
          const r = e => {const b=e.getBoundingClientRect();return {x:b.x,y:b.y,w:b.width,h:b.height};};
          return {brand: r(document.querySelector('.home-brand-title')), access: r(document.querySelector('.ro-header-access a')), width: innerWidth};
        });
        assert.ok(Math.abs(geometry.brand.x + geometry.brand.w/2 - width/2) < 1);
        assert.ok(Math.abs(geometry.access.x + geometry.access.w/2 - width/2) < 1);
        assert.ok(geometry.access.y >= geometry.brand.y + geometry.brand.h, 'Acesso abaixo da marca');
        assert.ok(geometry.access.w >= 44 && geometry.access.h >= 44);
        assert.equal(await noOverflow(page), true);
        assert.equal(await page.locator('h1').innerText(), 'Resumão Online\nDIRETO AO PONTO');
        if (artifacts) {
          await page.screenshot({path: path.join(artifacts, `home-${width}-${signedIn?'logado':'publico'}.png`), fullPage: true});
          await page.screenshot({path: path.join(artifacts, `top-${width}-${signedIn?'logado':'publico'}.png`), clip:{x:0,y:0,width,height:Math.min(900,await page.evaluate(()=>document.documentElement.scrollHeight))}});
        }
        await page.getByRole('button', {name: 'Mais cursos', exact: true}).click();
        assert.equal(await page.locator('.curso-publico-card').count(), 6);
        await page.getByRole('button', {name: 'Menos cursos', exact: true}).click();
        assert.equal(await page.locator('.curso-publico-card').count(), 4);
        await page.locator('#buscaCurso').fill('PROFESSOR');
        assert.equal(await page.locator('.curso-publico-card').count(), 2);
        await page.locator('#buscaCurso').fill('sem-resultado');
        assert.equal(await page.locator('#lista-cursos-publicos').innerText(), 'Nenhum curso encontrado.');
        await page.locator('#buscaCurso').fill('');
        const toggle = page.locator('.home-cursos-toggle');
        await toggle.focus(); await page.keyboard.press('Enter');
        assert.equal(await page.locator('#area_cursos_disponiveis').isVisible(), false);
        assert.equal(await toggle.getAttribute('aria-expanded'), 'false');
        await page.keyboard.press('Space');
        assert.equal(await page.locator('#area_cursos_disponiveis').isVisible(), true);
        await page.locator('.home-atendimento-header').click();
        assert.equal(await page.locator('#area_atendimento_clean').isVisible(), true);
        assert.equal(await noOverflow(page), true);
        assert.deepEqual(errors, []);
        measurements.push({width,signedIn,...geometry,overflow:false,errors});
        await ctx.close();
      }
    }
    // Dados opcionais e conteúdo não confiável: nomes preservados e escapados.
    const special = {id: 8, nome:'Nome oficial <img src=x onerror=alert(1)>', cargo:'Professor <b>teste</b>', orgao:'Órgão & Município', uf:'RS', ano:2026, ativo:true};
    const ctx = await context(320, null, [special]); const page = await ctx.newPage();
    await page.goto(origin + '/index.html'); await page.locator('.curso-publico-card').waitFor();
    assert.equal(await page.locator('.curso-publico-nome').innerText(), special.cargo);
    assert.equal(await page.locator('.home-course-official-name').innerText(), special.nome);
    assert.deepEqual(await page.locator('.home-course-meta > span').allTextContents(), ['Órgão & Município','RS','2026']);
    assert.equal(await page.locator('.curso-publico-card img,.curso-publico-card b').count(), 0);
    assert.equal(await noOverflow(page), true);
    await page.locator('.curso-publico-card').click();
    await page.waitForURL('**/curso-info.html?**');
    assert.equal(new URL(page.url()).searchParams.get('curso_nome'),special.nome);
    assert.equal(new URL(page.url()).searchParams.get('curso_id'),'8');
    await ctx.close();
    // Mesmos destinos e estados de autenticação do acesso central.
    for (const [user, target] of [
      [null, 'login.html'],
      [{is_aluno:true}, 'cursos.html'],
      [{is_admin:true,tipo_admin:'admin_geral'}, 'admin/index.html'],
      [{is_aluno:true,is_admin:true,tipo_admin:'admin_geral'}, 'minha-area.html']
    ]) {
      const ctx = await context(390, user && {id:1,nome:'Teste',ativo:true,...user}); const page = await ctx.newPage();
      await page.goto(origin + '/index.html');
      await page.evaluate(()=>{localStorage.setItem('ultimo_curso_id_compra','1');localStorage.setItem('ultimo_checkout_curso_id','1');});
      await page.getByRole('link',{name:'Entre ou faça cadastro',exact:true}).click();
      await page.waitForURL(origin+'/'+target);
      assert.equal(await page.evaluate(()=>localStorage.getItem('ultimo_curso_id_compra')),null);
      assert.equal(await page.evaluate(()=>localStorage.getItem('ultimo_checkout_curso_id')),null);
      if(!user)assert.equal(await page.evaluate(()=>localStorage.getItem('pos_login_redirect')),'cursos.html');
      await ctx.close();
    }
    for(const data of [[],[{id:1,nome:'CURSO'+ 'X'.repeat(400),ativo:true}]]) {
      const ctx=await context(320,null,data);const page=await ctx.newPage();await page.goto(origin+'/index.html');
      await page.waitForFunction(()=>document.querySelector('#lista-cursos-publicos').textContent.trim());
      assert.equal(await noOverflow(page),true);await ctx.close();
    }
    const errorCtx=await context(320,null,[],true);const errorPage=await errorCtx.newPage();
    await errorPage.goto(origin+'/index.html');await errorPage.locator('#lista-cursos-publicos h2').filter({hasText:'Erro'}).waitFor();await errorCtx.close();
    if(artifacts)fs.writeFileSync(path.join(artifacts,'measurements.json'),JSON.stringify(measurements,null,2));
    console.log('Home: 4 larguras × visitante/logado; alinhamento, overflow, catálogo, pesquisa, teclado, atendimento, nomes/metadados, escaping, navegação, autenticação e estados vazio/erro aprovados.');
  } finally {await browser?.close();await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{console.error(e);process.exitCode=1;});
