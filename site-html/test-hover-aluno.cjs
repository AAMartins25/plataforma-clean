// PLAYWRIGHT_MODULE=/caminho/playwright-core CHROMIUM_PATH=/caminho/chrome node site-html/test-hover-aluno.cjs
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const root = __dirname, origin = 'http://aluno-hover.test';
const pages = 'assuntos aula cartoes curso-expirado curso cursos dashboard desempenho-expirado disciplinas-expirado disciplinas fale-com-a-clean interatividade-assuntos interatividade-disciplinas interatividade mensagens-prof-expirado mensagens-prof meus-dados minha-area minhas-anotacoes-expirado minhas-anotacoes pastas questoes-assuntos questoes-criticas questoes-disciplinas questoes-ia questoes-pratica quiz reembolso revisoes-programadas sprint teoria'.split(' ');
const mime = {'.html':'text/html','.css':'text/css','.js':'text/javascript'};
const luminancia = rgb => rgb.map(v => {v /= 255; return v <= .04045 ? v/12.92 : ((v+.055)/1.055)**2.4;}).reduce((a,v,i) => a + v * [.2126,.7152,.0722][i], 0);
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:process.env.CHROMIUM_PATH, args:['--no-sandbox']});
  let verificacoes = 0;
  try {
    for (const name of pages) {
      const page = await browser.newPage({viewport:{width:1366,height:900}});
      await page.route('**/*', route => {
        const u = new URL(route.request().url()), file = path.resolve(root, '.' + u.pathname);
        if (u.origin !== origin || !file.startsWith(root + path.sep) || !fs.existsSync(file)) return route.abort();
        let body = fs.readFileSync(file);
        if (file.endsWith('.html')) body = Buffer.from(body.toString().replace(/<script\b([^>]*)>[\s\S]*?<\/script>/gi, (all, attrs) => /src=["']js\/cabecalho\.js/.test(attrs) ? all : ''));
        return route.fulfill({body, contentType:mime[path.extname(file)] || 'application/octet-stream'});
      });
      await page.goto(`${origin}/${name}.html`);
      await page.addStyleTag({content:'*,*::before,*::after { transition-duration: 0s !important; animation-duration: 0s !important; }'});
      if (name === 'fale-com-a-clean') await page.evaluate(() => document.querySelector('#hover-aluno-css').media = 'all');
      // Exemplos reais de controles inseridos dinamicamente pelas páginas de estudo.
      if (['curso','disciplinas','assuntos','questoes-disciplinas','questoes-assuntos','questoes-pratica','sprint','teoria','mensagens-prof','minhas-anotacoes'].includes(name)) {
        await page.evaluate(() => {
          const host = document.createElement('div');
          host.innerHTML = `<a href="#" class="btn curso-acao-btn">Abrir</a><button class="btn questoes-pratica-btn">Responder</button><button class="botao-estudo-lateral">Texto</button><button class="btn mensagens-prof-btn-enviar">Enviar</button><button class="btn" disabled>Desabilitado</button><button class="botao-estudo-lateral ativo">Selecionado</button><a href="#" id="link-comum">Link</a>`;
          document.querySelector('main')?.append(host);
        });
      }
      const cdp = await page.context().newCDPSession(page); await cdp.send('DOM.enable'); await cdp.send('CSS.enable');
      const {root:doc} = await cdp.send('DOM.getDocument');
      const {nodeIds} = await cdp.send('DOM.querySelectorAll',{nodeId:doc.nodeId,selector:'button,input[type=button],input[type=submit],a.btn,a[role=button],#link-comum'});
      for (const width of [1366,768,390,320]) {
        await page.setViewportSize({width,height:900});
        for (const nodeId of nodeIds) {
          const {object} = await cdp.send('DOM.resolveNode',{nodeId});
          const read = async () => (await cdp.send('Runtime.callFunctionOn',{objectId:object.objectId,returnByValue:true,functionDeclaration:`function(){let s=getComputedStyle(this),r=this.getBoundingClientRect();return {visible:!!(r.width&&r.height)&&s.visibility!=='hidden'&&s.display!=='none', target:this.matches('button,input[type=button],input[type=submit],a.btn,a[role=button]'), excluded:this.matches(':disabled,[disabled],[aria-disabled="true"],.disabled,.desabilitado,.btn-ativo,.fale-clean-btn-tipo-ativo,.ativo,.active,.selecionado,.selecionada,[aria-pressed="true"],[aria-selected="true"]'),background:s.backgroundColor,color:s.color,border:s.border,shadow:s.boxShadow,transform:s.transform,opacity:s.opacity,outline:s.outlineStyle,transition:s.transitionProperty,width:r.width,height:r.height,tag:this.outerHTML.slice(0,110)}}`})).result.value;
          await cdp.send('CSS.forcePseudoState',{nodeId,forcedPseudoClasses:['hover']});
          await page.evaluate(() => { for (const s of document.querySelectorAll('link[href*="hover-aluno.css"]')) s.disabled = true; });
          const before = await read();
          await page.evaluate(() => { for (const s of document.querySelectorAll('link[href*="hover-aluno.css"]')) s.disabled = false; });
          await page.waitForTimeout(25);
          const after = await read();
          if (after.visible) {
            const label = `${name}/${width}: ${after.tag}`;
            for (const prop of ['color','border','shadow','transform','opacity','outline','transition']) assert.equal(after[prop],before[prop],`${label} ${prop}`);
            for (const prop of ['width','height']) assert.ok(Math.abs(after[prop] - before[prop]) < .05, `${label} ${prop}`);
            if (after.target && !after.excluded) {
              assert.equal(after.background,'rgb(150, 190, 250)',`${label} fundo`);
              const rgb = after.color.match(/\d+/g)?.slice(0,3).map(Number);
              assert.ok(rgb && (luminancia([150,190,250])+.05)/(luminancia(rgb)+.05)>=4.5,`${label} contraste ${after.color}`);
            } else assert.equal(after.background,before.background,`${label} estado ou link`);
            if (after.target && !after.excluded) {
              for (const state of [['hover','active'], ['focus-visible']]) {
                await cdp.send('CSS.forcePseudoState',{nodeId,forcedPseudoClasses:state});
                await page.evaluate(() => { for (const s of document.querySelectorAll('link[href*="hover-aluno.css"]')) s.disabled = true; });
                const original = await read();
                await page.evaluate(() => { for (const s of document.querySelectorAll('link[href*="hover-aluno.css"]')) s.disabled = false; });
                await page.waitForTimeout(10);
                const atual = await read();
                assert.equal(atual.background, original.background, `${label} ${state.join('+')} fundo`);
                assert.equal(atual.outline, original.outline, `${label} ${state.join('+')} foco`);
              }
            }
            verificacoes++;
          }
          await cdp.send('CSS.forcePseudoState',{nodeId,forcedPseudoClasses:[]});
        }
      }
      await page.close();
    }
    console.log(`${pages.length} páginas, ${verificacoes} controles/estados em 1366, 768, 390 e 320 px: OK`);
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode=1; });
