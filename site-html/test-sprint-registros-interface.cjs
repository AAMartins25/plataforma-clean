// Usa API sintética em memória e CKEditor real; não acessa banco nem serviços externos.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const root = __dirname;
const ck = process.env.CKEDITOR_DIST;
assert.ok(ck, 'Informe CKEDITOR_DIST com o diretório browser do CKEditor 49.1.0 existente.');
const source = fs.readFileSync(path.join(root, 'sprint.html'), 'utf8')
  .replace(/<script src="js\/(sessao|app|cabecalho)\.js"[^>]*><\/script>/g, '')
  .replace(/\s*carregarBateria\(\);\s*(<\/script>)/, '$1');
const rich = '<p><strong>Anotação</strong> <i>formatada</i> <u>teste</u></p><figure class="table"><table><tbody><tr><td>A</td><td>B</td></tr></tbody></table></figure><p><span class="ro-math-inline">x^2</span></p>';
(async () => {
  const browser = await chromium.launch({executablePath: process.env.CHROMIUM_PATH || '/home/codespace/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell', args: ['--no-sandbox']});
  try {
    for (const width of [320, 390, 768, 1366]) {
      const p = await browser.newPage({viewport: {width, height: 900}});
      const errors = [], posts = [];
      p.on('pageerror', e => errors.push(e.message));
      p.on('dialog', d => d.accept());
      await p.route('**/*', async r => {
        const u = new URL(r.request().url());
        let file;
        if (u.hostname === 'cdn.ckeditor.com') file = path.join(ck, path.basename(u.pathname));
        else if (u.origin === 'http://resumao.test') {
          if (u.pathname === '/sprint.html') return r.fulfill({contentType:'text/html', body:source});
          file = path.join(root, u.pathname);
        } else return r.abort();
        if (!fs.existsSync(file)) return r.fulfill({status:404, body:''});
        const contentType = file.endsWith('.css') ? 'text/css' : file.endsWith('.js') ? 'text/javascript' : 'application/octet-stream';
        await r.fulfill({contentType, body:fs.readFileSync(file)});
      });
      await p.goto('http://resumao.test/sprint.html?curso_id=1&contratacao_id=2&revisao_id=3');
      await p.exposeFunction('registrarPost', (url, body) => posts.push({url, body}));
      await p.evaluate(() => {
        window.apiGetAuth = async url => url === '/me/ckeditor-chave' ? {licenseKey:'GPL'} : [];
        window.apiPostAuth = async (url, body) => window.registrarPost(url, body);
        bateriaId = 4; tentativaAnotacaoId = 9; modo = 'revisao';
        questoes = [{id:7, enunciado:'Questão de teste', alternativas:[{letra:'C', texto:'Correto'}], gabarito:'C'}];
        respostasAluno[7] = 'C'; respostasConfirmadas.add(7);
        revisarAgora();
      });
      const note = p.locator('#registro_anotacao_7'), message = p.locator('#registro_mensagem_7');
      const screenshot = async state => {
        if (!process.env.SCREENSHOT_DIR) return;
        fs.mkdirSync(process.env.SCREENSHOT_DIR, {recursive:true});
        await p.screenshot({path:path.join(process.env.SCREENSHOT_DIR, `${state}-${width}.png`), fullPage:true});
      };
      const overflow = async () => assert.equal(await p.evaluate(() => document.documentElement.scrollWidth - innerWidth), 0, `overflow a ${width}px`);
      const ready = async host => host.locator('.ck-content[contenteditable="true"]').waitFor();
      const open = async host => {await host.locator('.sprint-registro-abrir').click(); await ready(host);};
      const data = async (host, text) => host.locator('.ck-content').evaluate((el, text) => el.ckeditorInstance.setData(text), text);
      await note.locator('.sprint-registro-abrir').waitFor();
      assert.equal(await p.locator('.ck-editor, textarea, section h3').count(), 0);
      for (const host of [note, message]) {
        const style = await host.locator('button').evaluate(el => {
          const s = getComputedStyle(el), b = el.getBoundingClientRect();
          return {radius:s.borderRadius, height:b.height, width:b.width, parent:el.parentElement.clientWidth, background:s.backgroundColor, color:s.color};
        });
        assert.equal(style.radius, '999px'); assert.ok(style.height <= (width === 320 ? 54 : 40), JSON.stringify(style)); assert.ok(style.width < style.parent);
        assert.equal(style.background, 'rgb(248, 242, 230)'); assert.equal(style.color, 'rgb(31, 78, 121)');
      }
      await overflow(); await screenshot("fechados");
      await open(note); assert.equal(await message.locator('textarea, .ck-editor').count(), 0);
      await data(note, rich); await overflow();
      await open(message); await data(message, '<p>Rascunho da mensagem</p>'); await overflow();
      assert.equal(await p.locator('.ck-content[contenteditable="true"]').count(), 2);
      await screenshot("abertos");
      await note.getByRole('button', {name:'Cancelar', exact:true}).click();
      assert.equal(posts.length, 0); assert.match(await message.locator('.ck-content').innerText(), /Rascunho/);
      await open(note); assert.equal(await note.locator('.ck-content').innerText(), '\n');
      await message.getByRole('button', {name:'Cancelar', exact:true}).click();
      assert.equal(await message.locator('.ck-editor').count(), 0);
      await open(message); assert.equal(await message.locator('.ck-content').innerText(), '\n');
      await data(note, rich); await data(message, rich); await overflow();
      // Cancelar durante envio pendente não deve apagar o formulário em processamento.
      await p.evaluate(() => {
        const original = window.apiPostAuth;
        window.apiPostAuth = (url, body) => new Promise(resolve => {window.terminarEnvio = async () => {await original(url, body); resolve({});};});
      });
      await note.getByRole('button', {name:'Salvar', exact:true}).click();
      await note.getByRole('button', {name:'Cancelar', exact:true}).click();
      assert.equal(await note.locator('.ck-editor').count(), 1);
      await p.evaluate(() => window.terminarEnvio());
      await note.getByRole('heading', {name:'Anotação', exact:true}).waitFor();
      assert.equal(await note.locator('button, textarea, .ck-editor').count(), 0);
      assert.equal(await note.getByRole('link', {name:'📝 Anotações'}).getAttribute('href'), 'minhas-anotacoes.html?curso_id=1&contratacao_id=2');
      assert.equal(await message.locator('.ck-editor').count(), 1);
      await message.getByRole('button', {name:'Enviar', exact:true}).click();
      await p.evaluate(() => window.terminarEnvio());
      await message.getByRole('heading', {name:'Mensagem ao professor', exact:true}).waitFor();
      assert.equal(await message.locator('button, textarea, .ck-editor').count(), 0);
      assert.match(await message.innerText(), /reformulá-la/);
      assert.equal(posts.length, 2);
      assert.deepEqual(posts.map(x => x.url), ['/me/anotacoes-questoes', '/me/mensagens-prof']);
      for (const {body} of posts) {
        assert.equal(body.texto_formato, 'html_v1'); assert.match(body.texto, /<strong>|<b>/); assert.match(body.texto, /<table>/); assert.match(body.texto, /ro-math-inline/);
        assert.equal(body.tentativa_id, 9); assert.equal(body.bateria_id, 4); assert.equal(body.contratacao_id, 2);
      }
      await overflow();
      // Registros carregados de outra tentativa (legados e formatados) usam os mesmos avisos.
      await p.evaluate(async width => {
        window.apiGetAuth = async () => [{questao_id:7, tentativa_id:1, texto:'Registro existente', texto_formato:width === 320 ? 'texto_puro' : 'html_v1'}];
        revisarAgora(); await recuperarAnotacoesTentativa();
      }, width);
      await note.getByRole('heading', {name:'Anotação', exact:true}).waitFor();
      await message.getByRole('heading', {name:'Mensagem ao professor', exact:true}).waitFor();
      assert.equal(await p.locator('section button, section textarea, section .ck-editor').count(), 0);
      await overflow(); assert.deepEqual(errors, []);
      await screenshot("registrados");
      console.log(`${width}px: abertura independente, cancelamento, reabertura, salvar/enviar, títulos e registros existentes: OK; overflow: 0`);
      await p.close();
    }
  } finally {await browser.close();}
})().catch(e => {console.error(e); process.exitCode = 1;});
