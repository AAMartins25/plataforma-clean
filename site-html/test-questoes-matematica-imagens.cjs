// CKEditor real + API da prévia exclusiva + SQLite/Storage locais.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright-core');
const origem=process.env.QUESTOES_PREVIEW_URL||'http://127.0.0.1:8772';
assert.match(origem,/^http:\/\/127\.0\.0\.1:\d+$/);
const fixtures=process.env.GRAFICOS_FIXTURES||'/tmp/resumao-ckeditor-correcao-dados/fixtures';
const capturas=process.env.GRAFICOS_CAPTURAS;
const canon=html=>html.replace(/ data-list-item-id="[^"]*"/g,'');
async function entrar(p){
 await p.goto(origem+'/__preview/entrar?perfil=admin');await p.selectOption('#cursoExistenteSelect','1');await p.click('#btnUsarCursoExistente');
 await p.getByRole('button',{name:'Trabalhar nesta disciplina',exact:true}).click();await p.getByRole('button',{name:'Aulas',exact:true}).first().click();await p.getByRole('button',{name:'🏁 Questões',exact:true}).click();
 await p.getByRole('button',{name:'Abrir / editar questões',exact:true}).first().click();await p.locator('#cardQuestao_1').getByRole('button',{name:'Editar',exact:true}).click();
 await p.waitForFunction(()=>document.querySelectorAll('#camposQuestaoCompleta .ck-content[contenteditable="true"]').length===7);
}
(async()=>{
 const b=await chromium.launch({executablePath:process.env.CHROMIUM_BIN||'/home/codespace/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell',args:['--no-sandbox']});
 try{
 for(const width of (process.env.GRAFICOS_LARGURAS||'1366,390,320').split(',').map(Number)){
 const p=await b.newPage({viewport:{width,height:950}}),erros=[];p.on('pageerror',e=>erros.push(e.message));p.on('dialog',d=>d.accept());
 await p.route('**/*',r=>r.request().url().startsWith(origem)?r.continue():r.abort());
 await entrar(p);
 // Abrir um conteúdo antigo não deve transformar seus delimitadores literais.
 await p.locator('#camposQuestaoCompleta .ck-content').first().evaluate(el=>el.ckeditorInstance.setData('<p>Antigo $$\\frac{1}{2}$$ e \\(x\\), R$ 100,00</p>'));
 assert.equal(await p.locator('#camposQuestaoCompleta .ck-content').first().locator('.katex').count(),0);
 assert.ok((await p.evaluate(()=>QuestaoEditores.dados().enunciado)).includes('$$\\frac{1}{2}$$'));
 // A importação usa o botão real, em cada um dos sete campos independentes.
 for(let i=0;i<7;i++){
  await p.locator('#camposQuestaoCompleta').getByRole('button',{name:'Importar Markdown',exact:true}).nth(i).click();
  const dlg=p.locator('dialog[open]');
  await dlg.locator('[data-md="fonte"]').fill('**Campo '+i+'**\n\n$$\\frac{1}{2} + x^2$$\n\nNa linha: \\(a+b\\).\n\n\\[c+d\\]');
  await dlg.getByRole('button',{name:'Importar material',exact:true}).click();await dlg.waitFor({state:'hidden'});
 }
 assert.equal(await p.locator('#camposQuestaoCompleta .katex').count(),21);
 // O evento paste real também recupera HTML fragmentado + fonte text/plain.
 await p.locator('#camposQuestaoCompleta .ck-content').first().evaluate(el=>{
  const editor=el.ckeditorInstance;editor.model.change(w=>{const par=w.createElement('paragraph');w.append(par,editor.model.document.getRoot());w.setSelection(par,0)});editor.editing.view.focus();
  const d=new DataTransfer();d.setData('text/html','<p><strong>Colagem visual</strong> <span>$$</span><i>\\frac{3}{4}</i><span>$$</span></p><p><span class="katex">apresentação sem anotação</span></p><p>R$ 100,00 e $20 <code>$$literal$$</code></p>');
  // O HTML já contém uma expressão delimitada além do objeto visual. Fornecer
  // só a fonte do objeto torna a associação verificável, sem adivinhar símbolos.
  d.setData('text/plain','\\(y^2\\)');
  el.dispatchEvent(new ClipboardEvent('paste',{clipboardData:d,bubbles:true,cancelable:true}));
 });
 await p.waitForFunction(()=>!TeoriaImagensEditor.estados.get(document.querySelector('#camposQuestaoCompleta .ck-content').ckeditorInstance).pendente);
 assert.equal(await p.locator('#camposQuestaoCompleta .ck-content').first().locator('.katex').count(),5,await p.evaluate(()=>QuestaoEditores.dados().enunciado));
 const tipos=[['png','image/png'],['jpg','image/jpeg'],['webp','image/webp']];
 for(let i=0;i<7;i++){
  const [ext,mime]=tipos[i%3];
  await p.locator('#camposQuestaoCompleta .ck-content').nth(i).evaluate(el=>el.ckeditorInstance.model.change(w=>{const par=w.createElement('paragraph');w.append(par,el.ckeditorInstance.model.document.getRoot());w.setSelection(par,0)}));
  await p.locator('#camposQuestaoCompleta .teoria-imagens-controles input[type=file]').nth(i).setInputFiles({name:'grafico.'+ext,mimeType:mime,buffer:fs.readFileSync(path.join(fixtures,'grafico.'+ext))});
  await p.locator('#camposQuestaoCompleta .ck-content').nth(i).locator('img').scrollIntoViewIfNeeded();
  await p.waitForFunction(i=>{const campo=document.querySelectorAll('#camposQuestaoCompleta .ck-content')[i];return !TeoriaImagensEditor.estados.get(campo.ckeditorInstance).pendente&&campo.querySelector('img')?.naturalWidth>0},i).catch(async e=>{throw new Error(width+'px/campo '+i+': '+await p.locator('#camposQuestaoCompleta .teoria-imagens-controles').nth(i).textContent()+'; '+await p.locator('#camposQuestaoCompleta .ck-content').nth(i).evaluate(el=>el.ckeditorInstance.getData()+'; DOM: '+el.querySelector('img')?.outerHTML))});
 }
 const antes=await p.evaluate(()=>QuestaoEditores.dados());
 for(const html of [antes.enunciado,antes.comentario,...antes.alternativas.map(a=>a.texto)]){assert.match(html,/\/midias\/imagens\//);assert.match(html,/ro-math-display/);assert.ok(!html.includes('assinatura='));}
 assert.ok(antes.enunciado.includes('$$literal$$'));assert.ok(antes.enunciado.includes('R$ 100,00'));
 const salvar=p.waitForResponse(r=>new URL(r.url()).pathname==='/questoes/1'&&r.request().method()==='PUT');
 await p.getByRole('button',{name:'Salvar edição',exact:true}).click();const r=await salvar;assert.equal(r.status(),200,await r.text());
 await p.waitForFunction(()=>document.querySelector('#textoBotaoSalvarQuestao')?.textContent!=='Salvar edição');
 await p.locator('#cardQuestao_1').getByRole('button',{name:'Editar',exact:true}).click();
 await p.waitForFunction(()=>document.querySelectorAll('#camposQuestaoCompleta .ck-content[contenteditable="true"]').length===7);
 await p.waitForFunction(()=>[...document.querySelectorAll('#camposQuestaoCompleta .ck-content img')].length===7&&[...document.querySelectorAll('#camposQuestaoCompleta .ck-content img')].every(i=>i.complete&&i.naturalWidth===1000));
 const depois=await p.evaluate(()=>QuestaoEditores.dados());
 assert.equal(canon(depois.enunciado),canon(antes.enunciado));assert.equal(canon(depois.comentario),canon(antes.comentario));
 assert.deepEqual(depois.alternativas.map(a=>canon(a.texto)),antes.alternativas.map(a=>canon(a.texto)));
 assert.ok(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Overflow no editor');
 await p.getByRole('button',{name:'Descartar e fechar edição',exact:true}).click();
 await p.goto(origem+'/__preview/entrar?perfil=aluno');
 await p.waitForFunction(()=>document.querySelector('#questao_1 .sprint-questao-enunciado img')?.naturalWidth===1000);
 assert.equal(await p.locator('#questao_1 .sprint-questao-enunciado .katex').count(),5);
 assert.equal(await p.locator('#questao_1 .alternativa-opcao img').count(),5);
 await p.waitForFunction(()=>[...document.querySelectorAll('#questao_1 img')].every(i=>i.naturalWidth===1000));
 assert.ok(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Overflow na leitura');
 const medidas=await p.locator('#questao_1 img').evaluateAll(els=>els.map(i=>({largura:i.getBoundingClientRect().width,altura:i.getBoundingClientRect().height,natural:i.naturalWidth})));
 assert.ok(medidas.every(i=>i.largura>0&&Math.abs(i.altura/i.largura-0.6)<0.02));
 if(capturas){fs.mkdirSync(capturas,{recursive:true});await p.locator('#questao_1').screenshot({path:path.join(capturas,'graficos-'+width+'.png')});await p.locator('#questao_1 .sprint-questao-enunciado img').screenshot({path:path.join(capturas,'grafico-detalhe-'+width+'.png')});}
 const legado=await p.evaluate(()=>{
  const box=document.createElement('div');box.innerHTML=QuestaoConteudo.renderizar('<p>Antigo $$\\frac{1}{2}$$ e \\(x\\)</p>','html_v1',1);
  document.body.appendChild(box);QuestaoConteudo.preparar();
  const resultado={formulas:box.querySelectorAll('.katex').length,texto:box.textContent};box.remove();return resultado;
 });assert.equal(legado.formulas,0);assert.ok(legado.texto.includes('$$\\frac{1}{2}$$'));
 await p.evaluate(()=>revisarAgora());
 await p.waitForFunction(()=>document.querySelector('.sprint-revisao-comentario-texto img')?.naturalWidth===1000);
 assert.equal(await p.locator('.sprint-revisao-comentario-texto').first().locator('.katex').count(),3);
 assert.ok(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Overflow no comentário');
 assert.deepEqual(erros,[]);
 console.log(`${width}px: 7 campos, Markdown, colagem real, PNG/JPEG/WebP, salvamento, reabertura, aluno e comentário OK`);
 await p.close();
 }
 }finally{await b.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
