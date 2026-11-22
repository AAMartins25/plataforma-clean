const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const root = __dirname;
(async () => {
  const browser = await chromium.launch({executablePath: process.env.CHROMIUM_PATH, args: ['--no-sandbox']});
  try {
    for (const width of [1366, 768, 375, 320]) for (const destino of ['dashboard','minhas-anotacoes','mensagens-prof','revisoes-programadas','questoes-criticas']) {
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
      }, true);
      await context.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.hostname !== 'localhost') {
          if (!url.hostname.includes('onrender.com')) return route.abort();
          await new Promise(resolve => setTimeout(resolve, 400));
          const dados = url.pathname === '/cursos-publicos' ? [{id: 1, nome: 'Curso Alfa', ativo: true}]
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
      await page.goto('http://localhost/curso.html?curso_id=1&curso_nome=Curso%20Alfa&contratacao_id=2');
      await page.locator(`a[href^="${destino}.html"]`).click();
      await page.waitForURL(`**/${destino}.html?**`);
      assert.equal(new URL(page.url()).searchParams.get('contratacao_id'), '2');
      await page.waitForTimeout(1100);
      let frames = await page.evaluate(() => window.quadrosCabecalho);
      assert.equal(frames.length,1, `${destino} ${width}: ${JSON.stringify(frames)}`);
      await page.locator('header a[title="Voltar"]').click();
      await page.waitForURL('**/curso.html?**');
      assert.equal(new URL(page.url()).searchParams.get('contratacao_id'), '2');
      await page.waitForTimeout(500);
      frames = await page.evaluate(() => window.quadrosCabecalho);
      assert.equal(frames.length,1, `retorno ${width}: ${JSON.stringify(frames)}`);
      console.log(`Curso → ${destino} → Voltar, ${width}: OK`);
      await context.close();
    }
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
