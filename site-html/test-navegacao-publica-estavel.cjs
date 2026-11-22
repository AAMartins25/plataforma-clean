const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const root = __dirname;
(async () => {
  const browser = await chromium.launch({executablePath: process.env.CHROMIUM_PATH, args: ['--no-sandbox']});
  try {
    for (const width of [1366, 768, 375, 320]) for (const authenticated of [false, true]) {
      const context = await browser.newContext({viewport: {width, height: 850}});
      await context.addInitScript((signed) => {
        if (signed) {localStorage.setItem('access_token', 'teste'); localStorage.setItem('auth_generation', 'teste');}
        window.quadrosCabecalho = [];
        let ultimo = '';
        function medir() {
          const h = document.querySelector('body > header'), m = document.querySelector('main');
          if (h && m) {
            const valores = [h.getBoundingClientRect().height, m.getBoundingClientRect().top].map(x => Math.round(x * 10) / 10);
            if (JSON.stringify(valores) !== ultimo) {window.quadrosCabecalho.push(valores); ultimo = JSON.stringify(valores);}
          }
          requestAnimationFrame(medir);
        }
        requestAnimationFrame(medir);
      }, authenticated);
      await context.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.hostname !== 'localhost') {
          if (!url.hostname.includes('onrender.com')) return route.abort();
          await new Promise(resolve => setTimeout(resolve, 400));
          const dados = url.pathname === '/cursos-publicos' ? ['Alfa', 'Beta', 'Gama', 'Delta', 'Épsilon', 'Zeta'].map((nome, i) => ({id: i + 1, nome: `Curso ${nome}`, ativo: true}))
            : url.pathname === '/me' ? {id: 1, nome: 'Ana Silva', ativo: true, is_aluno: true}
            : url.pathname.includes('/public/cursos/') ? {id: 1, nome: 'Curso Alfa', disciplinas: [], tempos: []} : [];
          return route.fulfill({status: 200, contentType: 'application/json', headers: {'access-control-allow-origin': '*'}, body: JSON.stringify(dados)});
        }
        const file = path.join(root, decodeURIComponent(url.pathname));
        if (!fs.existsSync(file) || !fs.statSync(file).isFile()) return route.fulfill({status: 404});
        const ext = path.extname(file), mime = {'.css': 'text/css', '.js': 'text/javascript', '.svg': 'image/svg+xml', '.png': 'image/png'};
        return route.fulfill({body: fs.readFileSync(file), contentType: mime[ext] || 'text/html'});
      });
      const page = await context.newPage();
      await page.goto('http://localhost/index.html');
      await page.locator('.curso-publico-card').first().waitFor();
      assert.equal(await page.locator('.curso-publico-card').count(), 4);
      await page.getByRole('button', {name: 'Mais cursos'}).click();
      assert.equal(await page.locator('.curso-publico-card').count(), 6);
      await page.getByRole('button', {name: 'Menos cursos'}).click();
      assert.equal(await page.locator('.curso-publico-card').count(), 4);
      await page.locator('#buscaCurso').fill('Alfa');
      assert.equal(await page.locator('.curso-publico-card').count(), 1);
      await page.locator('#buscaCurso').fill('');
      await page.locator('.home-atendimento-header').click();
      assert.equal(await page.locator('#area_atendimento_clean').isVisible(), true);
      await page.locator('.curso-publico-card').first().click();
      await page.waitForURL('**/curso-info.html?**');
      await page.waitForTimeout(1000);
      const durante = await page.evaluate(() => window.quadrosCabecalho);
      assert.ok(durante.length === 1, `Curso público ${width}: ${JSON.stringify(durante)}`);
      await page.locator('header a[title="Voltar"]').click();
      await page.waitForURL('**/index.html');
      await page.waitForTimeout(1000);
      const retorno = await page.evaluate(() => window.quadrosCabecalho);
      assert.ok(retorno.length === 1, `Retorno à Home ${width}: ${JSON.stringify(retorno)}`);
      await page.locator('.home-brand-access a').click();
      await page.waitForURL(authenticated ? '**/cursos.html' : '**/login.html');
      console.log(`Home → curso público → Voltar, ${width}, ${authenticated ? 'aluno' : 'visitante'}: OK`);
      await context.close();
    }
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
