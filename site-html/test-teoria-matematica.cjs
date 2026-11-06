// Integração local: CKEditor core 49.1.0 (GPL apenas no teste), KaTeX local,
// funções reais de leitura e rotas reais com SQLite descartável via stdin.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const readline = require('node:readline');
const {spawn} = require('node:child_process');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const dist = process.env.CKEDITOR_TEST_DIST;
assert.ok(dist, 'Defina CKEDITOR_TEST_DIST (distribuição oficial 49.1.0).');
const root = __dirname;
const teoria = fs.readFileSync(path.join(root, 'teoria.html'), 'utf8');
const funcoes = teoria.slice(teoria.indexOf('    function limparTextoTeoria('), teoria.indexOf('    async function abrirSecaoTeoria('));
assert.ok(funcoes.includes('TeoriaMatematica.renderizar'));
const scripts = ['js/vendor/katex/katex.min.js', 'js/teoria-matematica.js',
  'js/editor-teoria-matematica.js', 'js/vendor/markdown-it-15.0.3.min.js',
  'js/vendor/dompurify-3.4.17.min.js', 'js/editor-teoria-markdown.js', 'js/editor-teoria.js'];
const harness = `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  ${['css/style.css', 'css/editor-teoria-markdown.css', 'css/teoria-matematica.css', 'js/vendor/katex/katex.min.css', 'ckeditor/ckeditor5.css'].map(p => `<link rel="stylesheet" href="/${p}">`).join('')}
  <style>body{padding:12px}main{max-width:100%;min-width:0}.assunto{min-width:0}#leitura{margin-top:30px}</style>
  </head><body><main><div class="assunto"><textarea id="editor"></textarea></div>
  <section id="leitura" class="teoria-page"><div id="detalhes_aula"></div><span id="paginacao_teoria"></span></section></main>
  <script src="/ckeditor/ckeditor5.umd.js"></script>${scripts.map(p => `<script src="/${p}"></script>`).join('')}
  <script>window.RESUMAO_CKEDITOR_LICENSE_KEY='GPL';
  window.dados=()=>editor.getData().replace(/ data-list-item-id="[^"]*"/g,'');
  let paginasTeoria=[],paginaTeoriaAtual=0;
  function esc(s){return String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');}
  ${funcoes}
  window.preparar=async html=>{window.editor=await TeoriaEditor.iniciar(document.querySelector('#editor'),html||'');};
  window.mostrar=lista=>{paginasTeoria=construirPaginasTeoria(lista);paginaTeoriaAtual=0;renderizarPaginaTeoria();return paginasTeoria.length;};
  </script></body></html>`;

(async () => {
  let browser;
  const bridge = spawn(process.env.PYTHON_TEST_BIN || 'python', ['-u', 'test_teoria_matematica.py', '--bridge'], {
    cwd: path.join(root, '../backend'), stdio: ['pipe', 'pipe', 'inherit'],
    env: {...process.env, PYTHONDONTWRITEBYTECODE: '1', SECRET_KEY: 'matematica-local-chave-sintetica-para-testes-123456'}
  });
  const pendentes = [];
  let prontoResolve, prontoReject;
  const pronto = new Promise((resolve, reject) => {prontoResolve = resolve; prontoReject = reject;});
  const tempo = setTimeout(() => prontoReject(new Error('SQLite de teste não iniciou')), 30000);
  readline.createInterface({input: bridge.stdout}).on('line', linha => {
    let r; try { r = JSON.parse(linha); } catch { return; }
    if (r.ready) { clearTimeout(tempo); prontoResolve(); }
    else { const next = pendentes.shift(); if(next) r.error ? next.reject(new Error(r.error)) : next.resolve(r); }
  });
  bridge.on('exit', code => {prontoReject(new Error('Ponte SQLite encerrou: ' + code)); for (const p of pendentes.splice(0)) p.reject(new Error('Ponte encerrada'));});
  const api = req => new Promise((resolve, reject) => {pendentes.push({resolve, reject});bridge.stdin.write(JSON.stringify(req) + '\n');});
  const servidor = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://localhost');
    if (url.pathname === '/') {res.setHeader('Content-Type', 'text/html; charset=utf-8');res.end(harness);return;}
    const base = url.pathname.startsWith('/ckeditor/') ? dist : root;
    const nome = path.resolve(base, '.' + url.pathname.replace(/^\/ckeditor/, ''));
    if (!nome.startsWith(base + path.sep) || !fs.existsSync(nome) || fs.statSync(nome).isDirectory()) {res.writeHead(404);res.end();return;}
    const tipo = {'.js':'text/javascript','.css':'text/css','.woff2':'font/woff2'}[path.extname(nome)] || 'application/octet-stream';
    res.setHeader('Content-Type', tipo);res.end(fs.readFileSync(nome));
  });
  try {
    await pronto;
    await new Promise(resolve => servidor.listen(0, '127.0.0.1', resolve));
    const origem = `http://127.0.0.1:${servidor.address().port}`;
    browser = await chromium.launch({executablePath: process.env.CHROMIUM_BIN || '/home/codespace/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell', args: ['--no-sandbox']});
    for (const largura of [1280, 768, 390, 320]) {
      const page = await browser.newPage({viewport:{width:largura,height:900}});
      const erros = [], externos = [];
      page.on('pageerror', e => erros.push(e.message));
      await page.route('**/*', route => {
        if (!route.request().url().startsWith(origem)) {externos.push(route.request().url());return route.abort();}
        return route.continue();
      });
      await page.exposeFunction('testApi', api);
      await page.goto(origem);
      const botaoFormula = async () => {
        // O CKEditor recalcula o agrupamento da toolbar após readonly/foco.
        await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
        const botao = page.getByRole('button',{name:'Fórmula',exact:true});
        if (!await botao.isVisible()) await page.locator('.ck-toolbar__grouped-dropdown > button').click();
        return botao;
      };
      await page.evaluate(() => preparar('<p><strong>Original</strong> intacto.</p>'));
      const analise = await page.evaluate(() => {
        const c = t => TeoriaMarkdown.converter(t);
        const texto = h => {const t=document.createElement('template');t.innerHTML=h;return t.content.textContent;};
        const simples = c(String.raw`Texto **forte** \(x^2 + y^2\) e \(P \land Q\).`);
        const fonte = '\n  \\begin{aligned}\na &= b \\\\\nc &= d\n\\end{aligned}\n';
        const bloco = c('\\['+fonte+'\\]');
        const misto = c(String.raw`Antes \[x+1\] depois.`);
        const tabela = c('| A | B |\n|---|---|\n| \\(p \\lor q\\) | ok |');
        const lista = c('- Primeiro \\(x\\)\n- Segundo\n\n  \\[\n  y^2\n  \\]');
        const aposLista = c('- Item\n\n  \\[\n  x\n  \\]\n\n\\[\n\\begin{aligned}\ny &= z\n\n a &= b\n\\end{aligned}\n\\]');
        const codigo = c('`\\(literal\\)`\n\n```latex\n\\[codigo\\]\n```');
        const escape = c(String.raw`Escapado \\(literal\\)`);
        const incompleto = c(String.raw`Sem fechar \(x + y`);
        const html = c(String.raw`\(x < y \land y > 0\)`);
        const enfase = c(String.raw`**Antes \[x+1\] depois**`);
        const fechamento = c(String.raw`Literal \) e \]`);
        const inicio=performance.now();
        for(const entrada of ['\\( '.repeat(15000),'\\[\n'.repeat(10000)]) {
          try {c(entrada);} catch(erro) {if(!erro.message.includes('muitos blocos'))throw erro;}
        }
        const tempoIncompletos=performance.now()-inicio;
        let limite=false, quantidade=false;
        try{c('\\('+'x'.repeat(4097)+'\\)');}catch{limite=true;}
        try{c('\\(x\\) '.repeat(201));}catch{quantidade=true;}
        return {simples,bloco,misto,tabela,lista,aposLista,codigo,escape,incompleto,html,fonte,limite,quantidade,enfase,fechamento,tempoIncompletos,
          fonteBloco:texto(bloco.html), fonteHtml:(()=>{const t=document.createElement('template');t.innerHTML=html.html;return t.content.querySelector('.ro-math-inline').textContent;})()};
      });
      assert.equal((analise.simples.html.match(/ro-math-inline/g)||[]).length,2);
      assert.equal(analise.fonteBloco,analise.fonte);
      assert.ok(analise.misto.html.includes('</p><figure') || /<\/p>\s*<figure/.test(analise.misto.html),analise.misto.html);
      assert.ok(analise.tabela.html.includes('ro-math-inline'));
      assert.ok(analise.lista.html.includes('ro-math-display'),analise.lista.html);
      assert.equal((analise.aposLista.html.match(/ro-math-display/g)||[]).length,2,analise.aposLista.html);
      assert.ok(!analise.codigo.html.includes('ro-math-'));
      assert.ok(!analise.escape.html.includes('ro-math-'));
      assert.ok(analise.incompleto.html.includes('\\(') && analise.incompleto.avisos.length);
      assert.equal(analise.fonteHtml, String.raw`x < y \land y > 0`);
      assert.ok(analise.limite && analise.quantidade);
      assert.ok(analise.enfase.html.includes('<strong>Antes </strong>'),analise.enfase.html);
      assert.ok(analise.enfase.html.includes('<strong> depois</strong>'),analise.enfase.html);
      assert.ok(analise.fechamento.html.includes('\\)') && analise.fechamento.html.includes('\\]'));
      assert.ok(analise.tempoIncompletos<5000,'delimitadores incompletos causaram processamento excessivo');

      const markdown = '# Matemática e lógica\n\nTexto **formatado** \\(x^2 + y^2 = z^2\\).\n\n\\[\n\\forall x,\\; P(x) \\Rightarrow Q(x)\n\\]\n\n| Regra | Expressão |\n|---|---|\n| Negação | \\(\\neg P \\lor Q\\) |\n\n- Item \\(\\text{a  b}\\)';
      await page.getByRole('button',{name:'Importar Markdown',exact:true}).click();
      await page.locator('[data-md="fonte"]').fill(markdown);
      await page.getByRole('button',{name:'Importar texto',exact:true}).click();
      assert.equal(await page.locator('.ck-content .katex').count(),4);
      const importado = await page.evaluate(() => dados());
      assert.ok(!importado.includes('class="katex'));
      assert.ok(importado.includes('\\text{a  b}'));
      await page.evaluate(() => editor.execute('undo'));
      assert.equal(await page.evaluate(() => dados()),'<p><strong>Original</strong> intacto.</p>');
      await page.evaluate(() => editor.execute('redo'));
      assert.equal(await page.evaluate(() => dados()),importado);

      const salvo = await page.evaluate(async () => {
        const r=await testApi({method:'post',path:'/materiais',json:{aula_id:1,tipo:'TEXTO',titulo:'Fórmulas',...TeoriaEditor.conteudo(document.querySelector('#editor'))}});
        if(r.status!==200)throw new Error(JSON.stringify(r)); return r.body;
      });
      assert.equal(salvo.conteudo_formato,'html_v1');
      assert.equal(salvo.conteudo,importado);
      await page.evaluate(async id => {
        await TeoriaEditor.destruir(document.querySelector('#editor'));
        const r=await testApi({method:'get',path:'/aulas/1/materiais'});
        const material=r.body.find(x=>x.id===id);await preparar(material.conteudo);
      },salvo.id);
      assert.equal(await page.evaluate(() => dados()),importado);
      await page.evaluate(() => {
        const formula=[...editor.model.document.getRoot().getChild(1).getChildren()].find(x=>x.name==='roMathInline');
        editor.model.change(w=>w.setSelection(formula,'on'));
      });
      await (await botaoFormula()).click();
      assert.equal(await page.locator('.ro-math-dialogo textarea').inputValue(),'x^2 + y^2 = z^2');
      const novaFonte=String.raw`\frac{1}{2} + \text{a  b}`;
      await page.locator('.ro-math-dialogo textarea').fill(novaFonte);
      await page.getByRole('button',{name:'Aplicar fórmula',exact:true}).click();
      const editado=await page.evaluate(()=>dados());
      assert.ok(editado.includes(novaFonte));
      await page.evaluate(()=>editor.execute('undo'));
      assert.equal(await page.evaluate(()=>dados()),importado);
      await page.evaluate(()=>editor.execute('redo'));
      assert.equal(await page.evaluate(()=>dados()),editado);
      const atualizado=await page.evaluate(async id=>{
        const r=await testApi({method:'put',path:'/materiais/'+id,json:{aula_id:1,tipo:'TEXTO',titulo:'Editado',...TeoriaEditor.conteudo(document.querySelector('#editor'))}});
        if(r.status!==200)throw new Error(JSON.stringify(r));
        const lista=await testApi({method:'get',path:'/aulas/1/materiais'});return lista.body.find(x=>x.id===id);
      },salvo.id);
      assert.equal(atualizado.conteudo,editado);
      await page.evaluate(html=>editor.setData(html),atualizado.conteudo);
      assert.equal(await page.evaluate(()=>dados()),editado);
      // A fonte multiline e seus espaços sobrevivem aos conversores do CKEditor.
      const multiline=await page.evaluate(html=>{editor.setData(html);return editor.model.document.getRoot().getChild(0).getAttribute('latex');},analise.bloco.html);
      assert.equal(multiline,analise.fonte);
      // Conversão de apresentação em ambos os sentidos, sem perder a fonte.
      const modos=await page.evaluate(()=>{
        editor.model.change(w=>w.setSelection(editor.model.document.getRoot().getChild(0),'on'));
        editor.execute('formula',{fonte:'x_1',bloco:false});
        const inline=dados();editor.execute('formula',{fonte:'x_1',bloco:true});
        return {inline,bloco:dados()};
      });
      assert.ok(modos.inline.includes('<span class="ro-math-inline">x_1</span>'));
      assert.ok(modos.bloco.includes('<figure class="ro-math-display">x_1</figure>'));
      const colagem=await page.evaluate(()=>{
        editor.setData('');editor.editing.view.focus();
        const transfer=new DataTransfer();
        transfer.setData('text/html','<p><strong>Negrito</strong> <i>Itálico</i> <u>Sublinhado</u></p><p style="mso-list:l0 level1 lfo1"><span style="mso-list:Ignore">•</span>Um</p><p style="mso-list:l0 level1 lfo1"><span style="mso-list:Ignore">•</span>Dois</p>');
        editor.ui.getEditableElement().dispatchEvent(new ClipboardEvent('paste',{clipboardData:transfer,bubbles:true,cancelable:true}));
        return dados();
      });
      for(const esperado of ['<strong>Negrito</strong>','<i>Itálico</i>','<u>Sublinhado</u>','<ul>','Um','Dois']) assert.ok(colagem.includes(esperado),colagem);

      // Segurança de renderização, erros e ausência de requisições externas.
      const seguranca=await page.evaluate(()=>{
        const alvo=document.createElement('div');document.body.appendChild(alvo);
        const casos=[String.raw`\includegraphics{https://invalid.example/x}`,String.raw`\href{javascript:alert(1)}{x}`,String.raw`\htmlClass{evil}{x}`,String.raw`\def\a{\a}\a`,'<img src=x onerror="window.__executou=1">',String.raw`\comandoInexistente`];
        const resultados=casos.map(fonte=>{TeoriaMatematica.desenhar(alvo,fonte,false);return !alvo.querySelector('img,a[href],.evil,script,[onerror]');});
        alvo.remove();return {resultados,executou:!!window.__executou};
      });
      assert.ok(seguranca.resultados.every(Boolean));assert.ok(!seguranca.executou);
      const paginas=await page.evaluate(material=>mostrar([
        {conteudo:'Legado literal \\(x\\) <b>texto</b>',conteudo_formato:'texto_puro'},
        {conteudo:'<p>HTML antigo \\(y\\)</p>',conteudo_formato:'html_v1'},
        {...material,conteudo:'<p>'+'Introdução '.repeat(270)+'</p>'+material.conteudo+'<p>'+'Fim '.repeat(700)+'</p>'}
      ]),atualizado);
      assert.ok(paginas>=4);
      assert.equal(await page.locator('#leitura .katex').count(),0);
      let total=0;
      for(let i=0;i<paginas;i++) {
        const dados=await page.evaluate(()=>({katex:document.querySelectorAll('#leitura .katex').length,
          largura:document.documentElement.scrollWidth,viewport:innerWidth,html:paginasTeoria[paginaTeoriaAtual].conteudo}));
        total+=dados.katex;assert.ok(dados.largura<=dados.viewport+2,JSON.stringify(dados));
        assert.ok(!dados.html.includes('class="katex'));
        if(i<paginas-1)await page.evaluate(()=>proximaPaginaTeoria());
      }
      assert.equal(total,4);
      await page.evaluate(()=>{
        mostrar([{conteudo:'<figure class="ro-math-display">'+Array(100).fill('x').join('+')+'</figure>',conteudo_formato:'html_v1'}]);
      });
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),'fórmula longa causou overflow');
      await page.evaluate(()=>editor.enableReadOnlyMode('teste'));
      assert.ok(await (await botaoFormula()).isDisabled());
      await page.evaluate(()=>editor.disableReadOnlyMode('teste'));
      await (await botaoFormula()).click();
      await page.locator('.ro-math-dialogo textarea').fill('x+1');
      await page.locator('.ro-math-dialogo select').selectOption('display');
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2));
      await page.getByRole('button',{name:'Aplicar fórmula',exact:true}).click();
      assert.ok((await page.evaluate(()=>dados())).includes('ro-math-display'));
      if(process.env.MATH_TEST_ARTIFACTS){fs.mkdirSync(process.env.MATH_TEST_ARTIFACTS,{recursive:true});await page.screenshot({path:path.join(process.env.MATH_TEST_ARTIFACTS,`matematica-${largura}.png`),fullPage:true});}
      await page.evaluate(()=>TeoriaEditor.destruir(document.querySelector('#editor')));
      assert.equal(await page.locator('.ro-math-dialogo').count(),0);
      assert.deepEqual(erros,[]);assert.deepEqual(externos,[]);
      console.log(`${largura}px: importação, fonte, SQLite, reabertura, edição, undo/redo, segurança, paginação e responsividade OK`);
      await page.close();
    }
  } finally {
    clearTimeout(tempo);
    if(browser)await browser.close();
    bridge.stdin.end();
    await new Promise(resolve=>servidor.close(resolve));
  }
})().catch(e=>{console.error(e);process.exitCode=1;});
