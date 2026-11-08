// Navegador real + FastAPI/TestClient + SQLite + Storage de memória. Sem produção.
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),readline=require('node:readline');
const {spawn}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright-core');
const root=__dirname,dist=process.env.CKEDITOR_TEST_DIST;
assert.ok(dist,'Defina CKEDITOR_TEST_DIST (49.1.0 oficial).');
const teoria=fs.readFileSync(path.join(root,'teoria.html'),'utf8');
const funcoes=teoria.slice(teoria.indexOf('    function limparTextoTeoria('),teoria.indexOf('    async function abrirSecaoTeoria('));
const scripts=['ckeditor/ckeditor5.umd.js','js/vendor/katex/katex.min.js','js/teoria-matematica.js','js/editor-teoria-matematica.js','js/teoria-imagens.js', 'js/teoria-tabelas.js','js/editor-teoria-imagens.js','js/vendor/markdown-it-15.0.3.min.js','js/vendor/dompurify-3.4.17.min.js','js/editor-teoria-markdown.js','js/editor-teoria.js'];
const harness=`<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
${['css/style.css','css/editor-teoria-markdown.css','css/teoria-matematica.css','css/teoria-imagens.css','js/vendor/katex/katex.min.css','ckeditor/ckeditor5.css'].map(p=>`<link rel="stylesheet" href="/${p}">`).join('')}
<style>body{padding:12px}.assunto{min-width:0;max-width:100%}main{min-width:0;max-width:100%}#leitura{margin-top:24px}</style></head>
<body><main><div class="assunto"><textarea id="editor"></textarea></div><section id="leitura" class="teoria-page"><div id="detalhes_aula"></div><span id="paginacao_teoria"></span></section></main>
${scripts.map(p=>`<script src="/${p}"></script>`).join('')}
<script>const API_BASE=location.origin;localStorage.setItem('access_token','token-local-de-teste');window.RESUMAO_CKEDITOR_LICENSE_KEY='GPL';
let paginasTeoria=[],paginaTeoriaAtual=0,aulaAtualId=1;
function contextoAcessoQuery(){return 'contratacao_id=1';}
function esc(s){return String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');}
${funcoes}
window.preparar=async html=>{window.editor=await TeoriaEditor.iniciar(document.querySelector('#editor'),html||'');};
window.dados=()=>editor.getData().replace(/ data-list-item-id="[^"]*"/g,'');
window.mostrar=lista=>{paginasTeoria=construirPaginasTeoria(lista);paginaTeoriaAtual=0;renderizarPaginaTeoria();return paginasTeoria.length;};
</script></body></html>`;

(async()=>{
 let browser,fixture;
 const bridge=spawn(process.env.PYTHON_TEST_BIN||'python',['-u','test_imagens_teoria.py','--bridge'],{cwd:path.join(root,'../backend'),stdio:['pipe','pipe','inherit'],env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}});
 const pendentes=[];let readyResolve,readyReject;
 const ready=new Promise((r,j)=>{readyResolve=r;readyReject=j;});
 const timer=setTimeout(()=>readyReject(new Error('A ponte de testes não iniciou.')),25000);
 readline.createInterface({input:bridge.stdout}).on('line',linha=>{
  let r;try{r=JSON.parse(linha);}catch{return;}
  if(r.ready){fixture=r;clearTimeout(timer);readyResolve();}
  else {const p=pendentes.shift();if(p)r.error?p.reject(new Error(r.error)):p.resolve(r);}
 });
 bridge.on('exit',code=>{readyReject(new Error('Ponte encerrada: '+code));for(const p of pendentes.splice(0))p.reject(new Error('Ponte encerrada.'));});
 const api=req=>new Promise((resolve,reject)=>{if(process.env.IMAGE_TEST_TRACE)console.log('Início',req.method||'',req.path);pendentes.push({resolve:r=>{if(process.env.IMAGE_TEST_TRACE)console.log('Fim',req.path,r.status);resolve(r);},reject});bridge.stdin.write(JSON.stringify(req)+'\n');});
 const servidor=http.createServer(async(req,res)=>{
  try{
   const url=new URL(req.url,'http://localhost');
   if(url.pathname==='/'){res.setHeader('Content-Type','text/html; charset=utf-8');res.setHeader('Content-Security-Policy',"connect-src 'self'; img-src 'self' data:");res.end(harness);return;}
   if(process.env.IMAGE_TEST_CORRECOES&&url.pathname==='/__upload_pendente'){
    // Upload local recebido, resposta intencionalmente suspensa até abortar.
    for await(const _ of req){}
    return;
   }
   if(url.pathname.startsWith('/admin/')||url.pathname.startsWith('/aulas/')||url.pathname.startsWith('/materiais')||url.pathname.startsWith('/__imagens/')){
    if(process.env.IMAGE_TEST_TRACE)console.log('HTTP',req.method,req.url);
    const partes=[];for await(const chunk of req)partes.push(chunk);
    const r=await api({method:req.method.toLowerCase(),path:req.url,base64:Buffer.concat(partes).toString('base64'),headers:req.headers});
    res.statusCode=r.status;res.setHeader('Content-Type',r.mime||'application/json');res.end(r.base64?Buffer.from(r.base64,'base64'):JSON.stringify(r.body));return;
   }
   const base=url.pathname.startsWith('/ckeditor/')?dist:root;
   const nome=path.resolve(base,'.'+url.pathname.replace(/^\/ckeditor/,''));
   if(!nome.startsWith(base+path.sep)||!fs.existsSync(nome)||fs.statSync(nome).isDirectory()){res.writeHead(404);res.end();return;}
   res.setHeader('Content-Type',({'.js':'text/javascript','.css':'text/css','.woff2':'font/woff2'})[path.extname(nome)]||'application/octet-stream');res.end(fs.readFileSync(nome));
  }catch(e){res.statusCode=500;res.end(JSON.stringify({detail:e.message}));}
 });
 try{
  await ready;await new Promise(r=>servidor.listen(0,'127.0.0.1',r));
  const origem=`http://127.0.0.1:${servidor.address().port}`;
  browser=await chromium.launch({executablePath:process.env.CHROMIUM_BIN||'/home/codespace/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell',args:['--no-sandbox']});
  const png=Buffer.from(fixture.png,'base64'),zip=Buffer.from(fixture.zip,'base64'),ruim=Buffer.from(fixture.zipRuim,'base64');
  for(const largura of (process.env.IMAGE_TEST_WIDTHS||'1280,768,390,320').split(',').map(Number)){
   await api({path:'/__perfil',admin:true});
   const page=await browser.newPage({viewport:{width:largura,height:950}}),erros=[],externos=[],canonicas=[];
   if(process.env.IMAGE_TEST_CORRECOES)await page.clock.install();
   await page.context().grantPermissions(['clipboard-read','clipboard-write']);
   page.on('pageerror',e=>erros.push(e.message));
   if(process.env.IMAGE_TEST_TRACE)page.on('requestfailed',r=>console.log('Falha de requisição',r.url(),r.failure()));
   // A CSP do harness bloqueia rede externa sem interceptar uploads de Blob no CDP.
   page.on('request',req=>{const url=req.url();if(!url.startsWith(origem))externos.push(url);if(url.includes('/midias/imagens/'))canonicas.push(url);});
   await page.goto(origem);await page.evaluate(()=>preparar('<p>Conteúdo anterior <strong>preservado</strong>.</p>'));
   const obter=()=>page.evaluate(()=>dados());
   const esperar=()=>page.waitForFunction(()=>!TeoriaImagensEditor.estados.get(editor)?.pendente);
   const importar=async buffer=>{
    await page.getByRole('button',{name:'Importar Markdown',exact:true}).click();
    await page.locator('[data-md="zip"]').setInputFiles({name:'material.zip',mimeType:'application/zip',buffer});
    await page.getByRole('button',{name:'Importar material',exact:true}).click();await esperar();
   };
   if(process.env.IMAGE_TEST_CORRECOES){
    const anterior=await obter();
    for(const etapa of ['leitura','processamento','upload']){
     const pedido=etapa==='upload'?page.waitForRequest('**/__upload_pendente'):null;
     await page.evaluate(({etapa,png})=>{
      window.terminou=false;window.respostaTardia=()=>{};
      window.trabalhoPendente=TeoriaImagensEditor.transacao(editor,async signal=>{
       if(etapa==='leitura'){
        const file={arrayBuffer:()=>new Promise(resolve=>{window.respostaTardia=resolve;})};
        await file.arrayBuffer();
       }else if(etapa==='upload'){
        const form=new FormData();form.append('arquivos',new Blob([Uint8Array.from(atob(png),c=>c.charCodeAt(0))],{type:'image/png'}),'teste.png');
        await TeoriaImagens.api('/__upload_pendente',form,signal);
       }else await new Promise(resolve=>{window.respostaTardia=resolve;});
       signal.throwIfAborted();
       return {html:'<p>Resposta tardia '+etapa+'</p>'};
      }).catch(e=>{window.erroTimeout=e.message;}).finally(()=>{window.terminou=true;});
     },{etapa,png:fixture.png});
     if(pedido)await pedido;
     await page.clock.fastForward(60001);
     await page.waitForFunction(()=>window.terminou);
     assert.equal(await obter(),anterior);
     assert.ok(await page.evaluate(()=>!editor.isReadOnly&&TeoriaEditor.pronto(document.querySelector('#editor'))&&erroTimeout.includes('tempo excedido')));
     await page.evaluate(()=>window.respostaTardia());
     assert.equal(await obter(),anterior);
    }
    await importar(zip);await page.waitForFunction(()=>!document.querySelector('.teoria-markdown-dialogo').open);
    assert.equal(((await obter()).match(/<img /g)||[]).length,2);
    // Ctrl+V nativo continua funcionando após os três prazos expirados.
    await page.evaluate(async b64=>{
     editor.model.change(w=>{const p=w.createElement('paragraph');w.append(p,editor.model.document.getRoot());w.setSelection(p,'end');});
     editor.editing.view.focus();
     await navigator.clipboard.write([new ClipboardItem({'image/png':new Blob([Uint8Array.from(atob(b64),c=>c.charCodeAt(0))],{type:'image/png'})})]);
    },fixture.png);
    await page.keyboard.press('Control+V');await esperar();
    const final=await obter();assert.equal((final.match(/<img /g)||[]).length,3);
    assert.ok(final.includes('ro-math-display')&&final.includes('<table>'));
    const material=await page.evaluate(async()=>{
     const r=await fetch('/materiais',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({aula_id:1,tipo:'TEXTO',titulo:'Pós-timeout',...TeoriaEditor.conteudo(document.querySelector('#editor'))})});
     if(!r.ok)throw new Error(await r.text());return r.json();
    });
    await page.evaluate(async material=>{await TeoriaEditor.destruir(document.querySelector('#editor'));await preparar(material.conteudo);},material);
    // O core recompõe aspect-ratio de imagens block a partir de width/height;
    // o backend remove esse estilo e preserva as mesmas dimensões e referência.
    assert.equal(await page.evaluate(()=>TeoriaMarkdown.sanitizarHtml(dados())),material.conteudo);
    await page.evaluate(()=>TeoriaEditor.destruir(document.querySelector('#editor')));
    assert.deepEqual(erros,[]);assert.deepEqual(externos,[]);assert.deepEqual(canonicas,[]);
    console.log(`${largura}px: prazos de leitura/processamento/upload, liberação, respostas tardias, ZIP e Ctrl+V seguintes, salvar/reabrir e fórmulas OK`);
    await page.close();continue;
   }
   await importar(ruim);
   assert.equal(await obter(),'<p>Conteúdo anterior <strong>preservado</strong>.</p>');
   assert.ok((await page.locator('[data-md="erro"]').textContent()).includes('não encontrada'));
   await page.getByRole('button',{name:'Cancelar',exact:true}).click();
   await importar(zip);
   await page.waitForFunction(()=>!document.querySelector('.teoria-markdown-dialogo').open);
   const importado=await obter();
   assert.equal((importado.match(/<img /g)||[]).length,2,importado);
   assert.ok(importado.indexOf('Antes')<importado.indexOf('alt="Figura A"')&&importado.indexOf('alt="Figura A"')<importado.indexOf('meio')&&importado.indexOf('meio')<importado.indexOf('alt="Figura B"'));
   assert.ok(importado.includes('ro-math-display')&&importado.includes('<table>'));
   assert.ok(!importado.includes('assinatura')&&!importado.includes('__imagens'));
   await page.waitForFunction(()=>[...document.querySelectorAll('.ck-content img')].every(i=>i.complete&&i.naturalWidth>0));
   await page.evaluate(()=>editor.execute('undo'));assert.ok((await obter()).includes('Conteúdo anterior'));
   await page.evaluate(()=>editor.execute('redo'));assert.equal(await obter(),importado);
   const material=await page.evaluate(async()=>{
    const r=await fetch('/materiais',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({aula_id:1,tipo:'TEXTO',titulo:'Material completo',...TeoriaEditor.conteudo(document.querySelector('#editor'))})});
    if(!r.ok)throw new Error(await r.text());return r.json();
   });
   assert.equal(material.conteudo,importado);
   await page.evaluate(async material=>{await TeoriaEditor.destruir(document.querySelector('#editor'));await preparar(material.conteudo);},material);
   assert.equal(await obter(),importado);
   // A edição do texto alternativo usa o modelo de imagem core sem perder seu ID.
   await page.evaluate(()=>{
    const img=[...editor.model.createRangeIn(editor.model.document.getRoot()).getItems()].find(i=>i.name==='imageInline'||i.name==='imageBlock');
    editor.model.change(w=>w.setAttribute('alt','Figura revisada',img));
   });
   const editado=await obter();assert.ok(editado.includes('Figura revisada'));
   await page.evaluate(async id=>{
    const r=await fetch('/materiais/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({aula_id:1,tipo:'TEXTO',titulo:'Revisado',...TeoriaEditor.conteudo(document.querySelector('#editor'))})});
    if(!r.ok)throw new Error(await r.text());
   },material.id);
   // Falha de Storage no segundo arquivo: nenhum conteúdo é substituído.
   await api({path:'/__falha',falhar:true});await importar(zip);
   assert.equal(await obter(),editado);
   assert.ok((await page.locator('[data-md="erro"]').textContent()).includes('Falha simulada'));
   await page.getByRole('button',{name:'Cancelar',exact:true}).click();await api({path:'/__falha',falhar:false});
   // Imagem individual como File real da área de transferência.
   await page.evaluate(b64=>{
    editor.setData('<p>Antes.</p>');editor.editing.view.focus();
    return navigator.clipboard.write([new ClipboardItem({'image/png':new Blob([Uint8Array.from(atob(b64),c=>c.charCodeAt(0))],{type:'image/png'})})]);
   },fixture.png);await page.keyboard.press('Control+V');await esperar();
   assert.ok((await obter()).includes('<img '),await page.locator('.teoria-imagens-controles').textContent());assert.ok((await obter()).includes('Antes.'));
   // HTML misto, imagens remotas acessíveis e KaTeX com fonte LaTeX recuperável.
   await page.evaluate(()=>{
    editor.setData('<p>Prefixo.</p>');editor.editing.view.focus();
    const dt=new DataTransfer();dt.setData('text/html','<p>Texto <strong>formatado</strong><img src="https://imagens.teste/a.png" alt="A"> entre <span class="katex"><math><semantics><mi>x</mi><annotation encoding="application/x-tex">x^2</annotation></semantics></math><span class="katex-html">x²</span></span><img src="https://imagens.teste/b.png" alt="B"> fim.</p><table><tbody><tr><td>Regra</td><td>\\(P \\land Q\\)</td></tr></tbody></table>');
    editor.ui.getEditableElement().dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));
   });await esperar();
   const misto=await obter();assert.equal((misto.match(/<img /g)||[]).length,2,misto);
   assert.equal((misto.match(/ro-math-inline/g)||[]).length,2,misto);
   assert.ok(misto.includes('<strong>formatado</strong>')&&misto.includes('<table>'));
   assert.ok(misto.indexOf('alt="A"')<misto.indexOf('x^2')&&misto.indexOf('x^2')<misto.indexOf('alt="B"'));
   // Ctrl+V nativo com HTML e arquivo real: preservar a posição no parágrafo.
   await page.evaluate(b64=>{
    editor.setData('');editor.editing.view.focus();
    return navigator.clipboard.write([new ClipboardItem({
     'image/png':new Blob([Uint8Array.from(atob(b64),c=>c.charCodeAt(0))],{type:'image/png'}),
     'text/html':new Blob(['<p>Esquerda<img src="file:///temporario/figura.png" alt="Local">Direita</p>'],{type:'text/html'})
    })]);
   },fixture.png);await page.keyboard.press('Control+V');await esperar();
   assert.match(await obter(),/Esquerda.*<img .*Direita/);
   const antesFalha=await obter();
   for(const html of ['<p>Não perder<img src="blob:inacessivel"></p>','<p>Não perder<img src="https://imagens.teste/expirada.png"></p>']){
    await page.evaluate(html=>{const dt=new DataTransfer();dt.setData('text/html',html);editor.ui.getEditableElement().dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));},html);await esperar();
    assert.equal(await obter(),antesFalha);
   }
   // Inserção complementar por seleção de arquivo (mesmo handler do botão).
   await page.locator('.teoria-imagens-controles input[type="file"]').setInputFiles({name:'complementar.png',mimeType:'image/png',buffer:png});await esperar();
   assert.equal(((await obter()).match(/<img /g)||[]).length,2);
   await page.evaluate(()=>editor.execute('undo'));assert.equal(await obter(),antesFalha);
   // O limite considera também imagens que já estavam no documento.
   const vinte=await page.evaluate(()=>{
    const src=TeoriaImagens.documento(editor.getData()).content.querySelector('img').getAttribute('src');
    editor.setData('<p>'+Array(20).fill('<img src="'+src+'" alt="Ícone">').join('')+'</p>');return dados();
   });
   await page.locator('.teoria-imagens-controles input[type="file"]').setInputFiles({name:'limite.png',mimeType:'image/png',buffer:png});await esperar();
   assert.equal(await obter(),vinte);assert.ok((await page.locator('.teoria-imagens-controles').textContent()).includes('20 imagens'));
   await page.evaluate(html=>editor.setData(html),antesFalha);
   // Somente um aluno com contexto válido pode obter URLs de leitura.
   await api({path:'/__perfil',admin:false});
   const paginas=await page.evaluate(material=>mostrar([{conteudo:'Legado literal \\(x\\)',conteudo_formato:'texto_puro'},
    {conteudo:'<p>HTML anterior \\(y\\)</p>',conteudo_formato:'html_v1'},
    {...material,conteudo:'<p>'+'Introdução '.repeat(260)+'</p>'+material.conteudo+'<p>'+'Fim '.repeat(700)+'</p>'}]),material);
   let imagensLidas=0;
   for(let i=0;i<paginas;i++){
    const qtd=await page.locator('#leitura img').count();
    if(qtd){await page.waitForFunction(()=>[...document.querySelectorAll('#leitura img')].every(i=>i.complete&&i.naturalWidth>0));imagensLidas+=qtd;}
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2));
    if(i<paginas-1)await page.evaluate(()=>proximaPaginaTeoria());
   }
   assert.equal(imagensLidas,2);
   assert.ok(await page.evaluate(()=>paginasTeoria.every(p=>!p.conteudo.includes('assinatura=')&&!p.conteudo.includes('__imagens/'))));
   await api({path:'/__perfil',admin:true});
   await page.evaluate(material=>mostrar([material]),material);
   await page.waitForFunction(()=>[...document.querySelectorAll('#leitura img')].every(i=>i.complete&&i.naturalWidth>0));
   if(process.env.IMAGE_TEST_ARTIFACTS){fs.mkdirSync(process.env.IMAGE_TEST_ARTIFACTS,{recursive:true});await page.screenshot({path:path.join(process.env.IMAGE_TEST_ARTIFACTS,`imagens-${largura}.png`),fullPage:true});}
   await page.evaluate(()=>TeoriaEditor.destruir(document.querySelector('#editor')));
   assert.deepEqual(erros,[]);assert.deepEqual(externos,[]);assert.deepEqual(canonicas,[],'Referência permanente foi usada como URL pública de exibição');
   console.log(`${largura}px: ZIP, posição, clipboard File/HTML/URLs, LaTeX, falhas atômicas, salvar/reabrir/editar, aluno e paginação OK`);
   await page.close();
  }
 }finally{
  clearTimeout(timer);if(browser)await browser.close();bridge.stdin.end();await new Promise(r=>servidor.close(r));
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
