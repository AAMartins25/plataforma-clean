const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const root = __dirname, cache = new Map();
const referencia = process.env.HEADER_BASE_REF || '10ef5348ca69f274c999ff660fc33d86e9f21169';
function origem(nome, atual) {
  if (atual) return fs.readFileSync(path.join(root, nome));
  if (!cache.has(nome)) cache.set(nome, execFileSync('git', ['show', `${referencia}:site-html/${nome}`], {cwd: root}));
  return cache.get(nome);
}
(async () => {
  const browser = await chromium.launch({executablePath: process.env.CHROMIUM_PATH, args: ['--no-sandbox']});
  try {
    for (const width of [1366, 768, 375, 320]) for (const signed of [false, true]) {
      const medidas = [];
      for (const atual of [false, true]) {
        const page = await browser.newPage({viewport: {width, height: 850}});
        if (signed) await page.addInitScript(() => { localStorage.setItem('access_token', 'teste'); localStorage.setItem('auth_generation', 'teste'); });
        await page.route('**/*', async route => {
          const url = new URL(route.request().url());
          if (url.hostname !== 'localhost') {
            if (!url.hostname.includes('onrender.com')) return route.abort();
            await new Promise(resolve => setTimeout(resolve, 400));
            const data = url.pathname === '/me' ? {id: 1, nome: 'Ana Silva', ativo: true, is_aluno: true}
              : url.pathname === '/cursos-publicos' ? [{id: 1, nome: 'Curso Alfa', ativo: true}] : [];
            return route.fulfill({json: data, headers: {'access-control-allow-origin': '*'}});
          }
          const file = decodeURIComponent(url.pathname).replace(/^\//, ''), ext = path.extname(file);
          try {return route.fulfill({body: origem(file, atual), contentType: ({'.css':'text/css','.js':'text/javascript','.svg':'image/svg+xml','.png':'image/png'})[ext] || 'text/html'});}
          catch (_) {return route.fulfill({status: 404});}
        });
        await page.goto('http://localhost/index.html');
        await page.locator('.curso-publico-card').first().waitFor();
        if (signed) await page.locator('#nomeUsuarioLogadoGlobal .ro-identity').waitFor();
        await page.waitForTimeout(500);
        medidas.push(await page.evaluate(() => {
          const box = el => {if (!el) return null; const r = el.getBoundingClientRect(); return [r.x,r.y,r.width,r.height];};
          return {
            header: box(document.querySelector('header')), main: box(document.querySelector('main')),
            marca: box(document.querySelector('.home-brand-title')), livro: box(document.querySelector('.home-brand-symbol')),
            acesso: box(document.querySelector('.home-brand-access a')),
            identidade: box(document.querySelector('#nomeUsuarioLogadoGlobal .ro-identity')),
            controles: [...document.querySelectorAll('header .ro-nav-control')].filter(e => e.getClientRects().length).map(box)
          };
        }));
        await page.close();
      }
      for (const key of ['header','main','marca','livro','acesso','identidade']) {
        const [antes, depois] = medidas.map(x => x[key]);
        assert.equal(!!antes, !!depois, `${width} ${signed} ${key}`);
        if (antes) antes.forEach((valor, i) => assert.ok(Math.abs(valor-depois[i]) < 1, `${width} ${signed} ${key}: ${antes} → ${depois}`));
      }
      assert.equal(medidas[0].controles.length, medidas[1].controles.length);
      medidas[0].controles.forEach((c, i) => c.forEach((v,j) => assert.ok(Math.abs(v-medidas[1].controles[i][j]) < 1, `${width} ${signed} controle`)));
      console.log(`Home ${width}, ${signed ? 'aluno' : 'visitante'}: geometria preservada`);
    }
  } finally {await browser.close();}
})().catch(error => {console.error(error); process.exitCode = 1;});
