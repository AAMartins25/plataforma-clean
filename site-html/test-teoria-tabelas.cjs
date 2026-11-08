// Leitura real, importador Markdown e paginação; nenhuma conexão externa.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const root = __dirname;
const fonte = fs.readFileSync(path.join(root, 'teoria.html'), 'utf8');
const funcoes = fonte.slice(fonte.indexOf('    function limparTextoTeoria('), fonte.indexOf('    async function abrirSecaoTeoria('));
const scripts = ['js/vendor/katex/katex.min.js', 'js/teoria-matematica.js', 'js/teoria-imagens.js', 'js/teoria-tabelas.js', 'js/vendor/markdown-it-15.0.3.min.js', 'js/vendor/dompurify-3.4.17.min.js', 'js/editor-teoria-markdown.js'];
let pagina = fonte.slice(0, fonte.indexOf('  <script src="js/vendor/katex'))
  .replace(/<script[^>]*src=[^>]+><\/script>/g, '')
  .replace(/<script>[\s\S]*?<\/script>/g, '');
pagina += scripts.map(s => `<script src="/${s}"></script>`).join('') + `<script>
const API_BASE = location.origin;
let paginasTeoria=[], paginaTeoriaAtual=0, aulaAtualId=1;
function esc(s){return String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');}
function contextoAcessoQuery(){return '';}
${funcoes}
window.mostrar=html=>{paginasTeoria=construirPaginasTeoria([{conteudo_formato:'html_v1',conteudo:html}]);paginaTeoriaAtual=0;renderizarPaginaTeoria();return paginasTeoria.length;};
window.estado=()=>({atual:paginaTeoriaAtual,total:paginasTeoria.length});
document.querySelector('#menu_estudo_lateral').style.display='flex';
</script></body></html>`;
const servidor = http.createServer((req,res) => {
  const url = new URL(req.url,'http://localhost');
  if(url.pathname === '/') {res.setHeader('Content-Type','text/html; charset=utf-8');res.end(pagina);return;}
  const nome = path.resolve(root, '.'+url.pathname);
  if(!nome.startsWith(root+path.sep)||!fs.existsSync(nome)){res.writeHead(404);res.end();return;}
  res.setHeader('Content-Type',({'.css':'text/css','.js':'text/javascript','.woff2':'font/woff2'})[path.extname(nome)]||'application/octet-stream');
  res.end(fs.readFileSync(nome));
});
(async()=>{
 let browser;
 try {
  await new Promise(r=>servidor.listen(0,'127.0.0.1',r));
  browser=await chromium.launch({executablePath:process.env.CHROMIUM_BIN||'/home/codespace/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell',args:['--no-sandbox']});
  const longo='Informação extensa com explicação e associação entre dados. '.repeat(4);
  const token='ReferenciaSemEspacos'.repeat(18);
  const cenarios={
   duas:`<table><thead><tr><th>Conceito</th><th>Descrição</th></tr></thead><tbody><tr><th>Princípio</th><td>${longo}${token}</td></tr></tbody></table>`,
   seis:`<figure class="table"><table><thead><tr>${Array.from({length:6},(_,i)=>`<th>Cabeçalho ${i+1}</th>`).join('')}</tr></thead><tbody>${Array.from({length:3},(_,r)=>`<tr>${Array.from({length:6},(_,c)=>`<td>Linha ${r+1} Coluna ${c+1} ${longo}${token}</td>`).join('')}</tr>`).join('')}</tbody></table><figcaption>Legenda preservada</figcaption></figure>`,
   doze:`<table><thead><tr>${Array.from({length:12},(_,i)=>`<th>Coluna ${i+1}</th>`).join('')}</tr></thead><tbody><tr>${Array.from({length:12},(_,i)=>`<td>Valor ${i+1} ${longo}</td>`).join('')}</tr></tbody></table>`,
   semCabecalho:`<table><tbody><tr><td>${longo}</td><td>${token}</td><td>Dado associado</td></tr></tbody></table>`,
   mescladas:`<table><thead><tr><th rowspan="2">Grupo</th><th colspan="2">Resultados</th></tr><tr><th>Anterior</th><th>Atual</th></tr></thead><tbody><tr><th rowspan="2">Grupo A</th><td>${longo}</td><td>${token}</td></tr><tr><td>Dado B</td><td>Dado C</td></tr></tbody></table>`,
   fixa:`<figure class="table" style="width:1800px"><table style="width:1800px;min-width:1600px"><colgroup><col style="width:900px"><col style="width:900px"></colgroup><tbody><tr><td width="900" style="width:900px;white-space:nowrap"><p style="white-space:nowrap">${token}</p></td><td>${longo}</td></tr></tbody></table></figure>`,
   formula:`<table><tr><th>Nome</th><th>Fórmula</th></tr><tr><td>${longo}</td><td><span class="ro-math-inline">x^2 + y^2</span></td></tr></table>`
  };
  const resultados=[];
  for(const largura of [1280,768,390,320]) {
   const page=await browser.newPage({viewport:{width:largura,height:900}});
   const erros=[];page.on('pageerror',e=>erros.push(e.message));
   await page.route('**/*',r=>r.request().url().startsWith(`http://127.0.0.1:${servidor.address().port}`)?r.continue():r.abort());
   await page.goto(`http://127.0.0.1:${servidor.address().port}`);
   cenarios.markdown=await page.evaluate(({longo,token})=>TeoriaMarkdown.converter(`| Conceito | Explicação | Referência |\n| --- | --- | --- |\n| Associação | ${longo} | ${token} |`).html,{longo,token});
   for(const [nome,html] of Object.entries(cenarios)) {
    const antes=await page.locator('#menu_estudo_lateral').evaluate(e=>({html:e.outerHTML,width:e.offsetWidth}));
    const total=await page.evaluate(html=>mostrar('<p>'+ 'Introdução. '.repeat(260)+'</p>'+html+'<p>'+'Conclusão. '.repeat(260)+'</p>'),html);
    assert.ok(total>=3,`${nome}: tabela entre páginas`);
    let tabelas=0;
    for(let i=0;i<total;i++) {
     assert.equal(await page.locator('#paginacao_teoria').innerText(),`${i+1}/${total}`);
     const medida=await page.evaluate(()=>{
      const raiz=document.querySelector('.teoria-conteudo-rico');
      const excessos=[raiz,...raiz.querySelectorAll('table,figure.table,th,td')].filter(e=>e.scrollWidth>e.clientWidth+1).map(e=>[e.tagName,e.scrollWidth,e.clientWidth]);
      return {excessos,documento:document.documentElement.scrollWidth>innerWidth+1,tabelas:raiz.querySelectorAll('table').length};
     });
     assert.deepEqual(medida.excessos,[],`${largura}/${nome}: transbordamento`);
     assert.equal(medida.documento,false,`${largura}/${nome}: página transborda`);
     tabelas+=medida.tabelas;
     if(medida.tabelas){
      const preservado=await page.evaluate(html=>{
       const t=document.createElement('template');t.innerHTML=html;
       return [...t.content.querySelectorAll('th,td')].every((e,i)=>{
        const atual=document.querySelectorAll('.teoria-conteudo-rico th,.teoria-conteudo-rico td')[i];
        return atual && (e.querySelector('.ro-math-inline') || atual.textContent===e.textContent) && atual.colSpan===e.colSpan && atual.rowSpan===e.rowSpan;
       });
      },html);
      assert.ok(preservado,'células e mesclagens preservadas');
      if(await page.locator('.teoria-conteudo-rico').evaluate(e=>e.clientWidth-parseFloat(getComputedStyle(e).paddingLeft)-parseFloat(getComputedStyle(e).paddingRight)<=600) && ['seis','markdown','mescladas'].includes(nome)) {
       assert.equal(await page.locator('.teoria-conteudo-rico td').first().evaluate(e=>getComputedStyle(e).display),'block');
       assert.ok(await page.locator('[data-teoria-rotulo]').count());
      }
      if(nome==='doze')assert.equal(await page.locator('.teoria-conteudo-rico td').first().evaluate(e=>getComputedStyle(e).display),'block');
      if(nome==='semCabecalho')assert.equal(await page.locator('.teoria-conteudo-rico td').last().getAttribute('data-teoria-rotulo'),'Coluna 3');
      if(nome==='formula')assert.equal(await page.locator('.katex').count(),1);
      if(nome==='mescladas')assert.match(await page.locator('td').last().getAttribute('data-teoria-rotulo'),/Grupo A.*Resultados.*Atual/);
      if(largura===1280 && nome==='seis') {
       const estadoAntes=await page.evaluate(()=>({pagina:estado(),texto:document.querySelector('.teoria-conteudo-rico').textContent}));
       for(const width of [320,1280]) {
        await page.setViewportSize({width,height:900});
        assert.equal(await page.locator('.teoria-conteudo-rico td').first().evaluate(e=>getComputedStyle(e).display),width===320?'block':'table-cell');
        assert.ok(await page.evaluate(()=>[document.documentElement,...document.querySelectorAll('.teoria-conteudo-rico table,.teoria-conteudo-rico td')].every(e=>e.scrollWidth<=e.clientWidth+1)));
        assert.deepEqual(await page.evaluate(()=>({pagina:estado(),texto:document.querySelector('.teoria-conteudo-rico').textContent})),estadoAntes,'redimensionar preserva conteúdo e página');
       }
      }
      if(process.env.TABLE_TEST_ARTIFACTS){fs.mkdirSync(process.env.TABLE_TEST_ARTIFACTS,{recursive:true});await page.screenshot({path:path.join(process.env.TABLE_TEST_ARTIFACTS,`${largura}-${nome}.png`),fullPage:true});}
     }
     if(i<total-1)await page.getByTitle('Próxima página').click();
    }
    assert.equal(tabelas,1,'tabela inteira, exibida uma vez');
    assert.equal(await page.getByTitle('Próxima página').count(),0);
    const depois=await page.locator('#menu_estudo_lateral').evaluate(e=>({html:e.outerHTML,width:e.offsetWidth}));
    assert.deepEqual(depois,antes,'menu lateral preservado');
    resultados.push(`${largura}px ${nome}: ${total} páginas, sem rolagem horizontal`);
    console.log(resultados.at(-1));
   }
   assert.deepEqual(erros,[]);await page.close();
  }
  console.log(`${resultados.length} cenários aprovados.`);
 }finally{await browser?.close();await new Promise(r=>servidor.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
