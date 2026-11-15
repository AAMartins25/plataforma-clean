// API e navegações de destino simuladas; HTML, CSS e handlers reais, sem banco.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const root = __dirname;
const out = process.env.MEUS_CURSOS_ARTIFACTS || '/tmp/resumao-meus-cursos-browser';
fs.mkdirSync(out, { recursive: true });
const server = http.createServer((req, res) => {
  const file = path.resolve(root, '.' + new URL(req.url, 'http://local').pathname);
  if (!file.startsWith(root + path.sep) || !fs.existsSync(file)) { res.writeHead(404).end(); return; }
  res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : file.endsWith('.svg') ? 'image/svg+xml' : 'text/html');
  res.end(fs.readFileSync(file));
});
const contrato = (id, origem = 'PAGAMENTO') => ({ id, origem, data_fim: '2027-02-09T00:00:00', renovacao_disponivel: true });
const demo = id => ({ id, data_fim: '2026-12-08T00:00:00', aquisicao_disponivel: true });
const curso = (id, nome, contratacoes = [], demonstracoes = []) => ({ curso_id: id, nome_curso: nome, contratacoes, demonstracoes });
const ativos = [
  curso(1, 'RESUMÃO PROFESSOR EDUCAÇÃO INFANTIL E ANOS INICIAIS — ALVORADA/RS 2026', [contrato(101)], [demo(201)]),
  curso(2, 'Teste gratuito', [], [demo(202)]),
  curso(3, 'Concessão administrativa', [contrato(103, 'ADMIN')], [demo(203)]),
  { curso_id: 4, nome_curso: 'Acesso legado', data_fim: '2027-01-01T00:00:00' },
  curso(5, 'Dois contratos independentes', [contrato(105), contrato(106)]),
  curso(6, '<img src=x onerror="window.xss=1"> Nome literal ' + 'NomeExtenso'.repeat(12), [contrato(107)])
];
const expirados = [
  { curso_id: 1, nome_curso: ativos[0].nome_curso, ativo: false, contratacao_id: 90, data_inicio: '2026-01-01', data_fim: '2026-02-01', bloqueio_manual: false },
  { curso_id: 2, nome_curso: 'Demonstração expirada', ativo: false, demonstracao_id: 91, data_inicio: '2026-01-02', data_fim: '2026-01-03', bloqueio_manual: false },
  { curso_id: 3, nome_curso: 'Contexto com bloqueio manual', ativo: false, contratacao_id: 92, data_inicio: '2026-01-01', data_fim: '2026-06-01', bloqueio_manual: true },
  { curso_id: 9, nome_curso: 'Histórico ainda ativo: não exibir', ativo: true }
];
(async () => {
  let browser;
  try {
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const origin = `http://127.0.0.1:${server.address().port}`;
    browser = await chromium.launch({ executablePath: process.env.CHROMIUM_EXECUTABLE, args: ['--no-sandbox'] });
    const results = [];
    for (const width of [320, 390, 768, 1366]) {
      const page = await browser.newPage({ viewport: { width, height: 950 }, reducedMotion: 'reduce' });
      const errors = [], calls = [];
      let fixture = { ativos: [], expirados: [], longo: false, multi: false };
      page.on('pageerror', error => errors.push(error.message));
      await page.addInitScript(() => {
        localStorage.setItem('access_token', 'token-ficticio');
        localStorage.removeItem('me_cache');
        if (new URLSearchParams(location.search).has('abrir')) localStorage.setItem('abrir_cursos_expirados', '1');
      });
      await page.route('**/*', async route => {
        const req = route.request(), url = new URL(req.url());
        if (url.origin === origin) {
          if (/\/(curso|curso-expirado|checkout|minha-area|login)\.html$/.test(url.pathname)) return route.fulfill({ contentType: 'text/html', body: '<main>Destino simulado</main>' });
          return route.continue();
        }
        if (url.hostname !== 'plataforma-quality-backend.onrender.com') return route.abort();
        calls.push({ method: req.method(), path: url.pathname });
        assert.equal(req.method(), 'GET', 'A apresentação não pode criar transações');
        let json;
        if (url.pathname === '/me') json = { id: 7, nome: fixture.longo ? 'MARIAAPARECIDAALEXANDRACRISTINA DOS SANTOS MARTINS' : 'ARLEN MARTINS', is_aluno: true, is_admin: fixture.multi, ativo: true };
        else if (url.pathname === '/me/cursos') json = fixture.ativos;
        else if (url.pathname === '/me/desempenho/contextos-expirados') json = fixture.expirados;
        else if (url.pathname === '/cursos-publicos') json = [];
        else throw Error('API não prevista: ' + url.pathname);
        return route.fulfill({ json, headers: { 'Access-Control-Allow-Origin': '*' } });
      });
      const goto = async (auto = false) => {
        await page.goto(origin + '/cursos.html' + (auto ? '?abrir=1' : ''));
        await page.waitForFunction(() => document.querySelector('#card_cursos_expirados').style.display === 'block' && !!document.querySelector('.ro-identity'));
        assert.equal(await page.locator('.ro-identity').textContent(), fixture.longo ? 'MARIAAPARECIDAALEXANDRACRISTINA' : 'ARLEN');
      };
      const layout = async () => {
        assert.equal(await page.evaluate(() => getComputedStyle(document.documentElement).fontSize), width < 768 ? '16px' : width < 1024 ? '15.2px' : '14.4px');
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth && document.body.scrollWidth <= innerWidth));
        assert.ok(await page.evaluate(() => {
          const header = document.querySelector('header').getBoundingClientRect();
          const elements = [...document.querySelectorAll('header h1,.ro-identity,.ro-header-navigation a')].filter(e => e.getClientRects().length).map(e => e.getBoundingClientRect());
          return elements.every(r => r.top >= header.top && r.bottom <= header.bottom && r.left >= 0 && r.right <= innerWidth) && elements.every((a, i) => elements.slice(i + 1).every(b => !(a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom)));
        }), 'Sobreposição no cabeçalho');
      };
      await page.goto(origin + '/index.html');
      await page.waitForFunction(() => !!document.querySelector('.ro-identity'));
      const homeHeight = await page.locator('header').evaluate(e => e.getBoundingClientRect().height);
      await goto(); await layout();
      const headerHeight = await page.locator('header').evaluate(e => e.getBoundingClientRect().height);
      if (Math.abs(homeHeight - headerHeight) >= 0.2) {
        await page.screenshot({ path: path.join(out, `header-debug-${width}.png`), fullPage: true });
        console.log(await page.evaluate(() => [...document.querySelectorAll('header,header *')].map(e => { const c = getComputedStyle(e), r = e.getBoundingClientRect(); return { tag: e.tagName, cls: e.className, h: r.height, y: r.y, row: c.gridRow, padding: c.padding, text: e.childElementCount ? '' : e.textContent }; })));
      }
      assert.ok(Math.abs(homeHeight - headerHeight) < 0.2, `${homeHeight} / ${headerHeight}`);
      await page.locator('.ro-identity').hover();
      assert.equal(await page.locator('header').evaluate(e => e.getBoundingClientRect().height), headerHeight);
      await page.mouse.move(0, 0);
      assert.equal(await page.locator('#lista').innerText(), 'Você não possui curso ativo no momento.');
      assert.equal(await page.locator('#lista_expirados').innerText(), 'Nenhum curso com acesso expirado no momento');
      assert.ok(await page.locator('#btnCursosExpirados').isDisabled());
      assert.equal(await page.getByText('Cursos disponíveis', { exact: true }).count(), 0);
      await page.screenshot({ path: path.join(out, `vazio-${width}.png`), fullPage: true });
      fixture = { ativos: [ativos[0]], expirados: [], longo: true, multi: false };
      await goto(); await layout();
      assert.equal(await page.locator('#lista > .meus-curso-card').count(), 1);
      assert.match(await page.locator('.meus-curso-vencimento').innerText(), /09\/02\/2027/);
      assert.equal(await page.locator('#lista a[href*="demonstracao_id"]').count(), 0);
      await page.screenshot({ path: path.join(out, `um-curso-${width}.png`), fullPage: true });
      fixture = { ativos, expirados, longo: true, multi: true };
      await goto(); await layout();
      assert.equal(await page.locator('#lista > .meus-curso-card').count(), 8);
      assert.equal(await page.locator('#lista_expirados > .meus-curso-card').count(), 3);
      assert.ok(await page.locator('#btnVoltarMinhaArea').isVisible());
      assert.equal(await page.locator('#lista img').count(), 0);
      assert.equal(await page.evaluate(() => window.xss), undefined);
      assert.ok(await page.locator('#lista a[href*="contratacao_id=106"][href*="renovacao=1"]').isVisible());
      assert.ok(await page.locator('#lista a[href*="demonstracao_id=203"]').count() === 2);
      // The section is reachable and operable using native Tab, Space and Enter.
      for (let n = 0; n < 40; n++) {
        await page.keyboard.press('Tab');
        if (await page.locator('#btnCursosExpirados').evaluate(e => e === document.activeElement)) break;
      }
      assert.ok(await page.locator('#btnCursosExpirados').evaluate(e => e === document.activeElement));
      await page.keyboard.press('Space');
      assert.equal(await page.locator('#btnCursosExpirados').getAttribute('aria-expanded'), 'true');
      assert.ok(await page.locator('#lista_expirados').isVisible());
      await page.keyboard.press('Enter');
      assert.equal(await page.locator('#btnCursosExpirados').getAttribute('aria-expanded'), 'false');
      await page.keyboard.press('Enter');
      assert.ok(await page.locator('#btnCursosExpirados').evaluate(e => e === document.activeElement));
      await layout();
      assert.ok(await page.locator('#lista_expirados').evaluate(e => [...e.children].every((card, index, cards) => !index || card.getBoundingClientRect().top - cards[index - 1].getBoundingClientRect().bottom >= 10)), 'Intervalo entre cards expirados');
      await page.screenshot({ path: path.join(out, `varios-${width}.png`), fullPage: true });
      // Follow existing links and verify the access/renewal contexts have not changed.
      const follow = async (selector, expected) => {
        await page.locator(selector).first().click();
        await page.waitForURL(url => url.pathname.endsWith(expected.page));
        const url = new URL(page.url());
        for (const [key, value] of Object.entries(expected.query)) assert.equal(url.searchParams.get(key), value);
      };
      await follow('#lista .meus-curso-abrir', { page: 'curso.html', query: { curso_id: '1', contratacao_id: '101', curso_nome: ativos[0].nome_curso } });
      await goto();
      await follow('#lista a[href*="renovacao=1"]', { page: 'checkout.html', query: { curso_id: '1', contratacao_id: '101', renovacao: '1', origem: 'cursos' } });
      await goto();
      await follow('#lista a.meus-curso-acao-secundaria[href*="demonstracao_id=202"]', { page: 'checkout.html', query: { curso_id: '2', demonstracao_id: '202', origem: 'cursos' } });
      for (const [index, key, id] of [[0, 'contratacao_id', '90'], [1, 'demonstracao_id', '91'], [2, 'contratacao_id', '92']]) {
        await goto(true);
        assert.ok(await page.locator('#lista_expirados').isVisible());
        assert.equal(await page.locator('#btnCursosExpirados').getAttribute('aria-expanded'), 'true');
        assert.equal(await page.evaluate(() => localStorage.getItem('abrir_cursos_expirados')), null);
        await page.locator('#lista_expirados .meus-curso-abrir').nth(index).click();
        await page.waitForURL(url => url.pathname.endsWith('curso-expirado.html'));
        const url = new URL(page.url()), expired = expirados[index];
        assert.equal(url.searchParams.get(key), id);
        assert.equal(url.searchParams.get('bloqueio_manual'), expired.bloqueio_manual ? '1' : '0');
        for (const key of ['data_inicio', 'data_fim']) {
          assert.equal(url.searchParams.get(key), expired[key]);
          assert.equal(await page.evaluate(({ id, key }) => localStorage.getItem(`curso_expirado_${id}_${key}`), { id: expired.curso_id, key }), expired[key]);
        }
      }
      assert.deepEqual(errors, []);
      results.push({ width, headerHeight, homeHeight, activeCases: [0, 1, 8], expiredCases: [0, 3], keyboard: true, contextsPreserved: true, overflow: false });
      console.log(`OK ${width}px: estados vazios/um/vários, teclado, acesso/renovação/aquisição/expirados e escala`);
      await page.close();
    }
    fs.writeFileSync(path.join(out, 'resultados.json'), JSON.stringify(results, null, 2));
  } finally {
    if (browser) await browser.close();
    server.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
