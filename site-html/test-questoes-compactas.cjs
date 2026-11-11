const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright-core');
const origin='http://127.0.0.1:8771',out=path.resolve(__dirname,'../evidencias/questoes-compactas');
const ready=p=>p.waitForFunction(()=>document.querySelectorAll('#camposQuestaoCompleta .ck-content[contenteditable=true]').length===7);
async function entrar(p){
 await p.goto(origin+'/__preview/entrar?perfil=admin');await p.selectOption('#cursoExistenteSelect','1');await p.click('#btnUsarCursoExistente');
 await p.getByRole('button',{name:'Trabalhar nesta disciplina',exact:true}).click();await p.getByRole('button',{name:'Aulas',exact:true}).first().click();await p.getByRole('button',{name:'🏁 Questões',exact:true}).click();
 await p.getByRole('button',{name:'Abrir / editar questões',exact:true}).first().click();
 await p.locator('#cardQuestao_1').getByRole('button',{name:'Editar',exact:true}).click();await ready(p);
}
async function limpar(p){await p.locator('#camposQuestaoCompleta .ck-content').evaluateAll(els=>els.forEach(el=>el.ckeditorInstance.setData('')));}
async function medir(p){return p.evaluate(()=>({altura:document.querySelector('#camposQuestaoCompleta').getBoundingClientRect().height,overflow:document.documentElement.scrollWidth-innerWidth,editores:[...document.querySelectorAll('#camposQuestaoCompleta .ck-content[contenteditable=true]')].map(el=>({altura:el.getBoundingClientRect().height,scroll:el.scrollHeight,placeholder:el.querySelector("[data-placeholder]")?.dataset.placeholder,toolbar:el.ckeditorInstance.config.get('toolbar'),plugins:[...el.ckeditorInstance.plugins].map(([p])=>p.pluginName).filter(Boolean)}))}));}
(async()=>{const b=await chromium.launch({executablePath:'/home/codespace/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell',args:['--no-sandbox']});const results=[];try{
for(const width of (process.env.TEST_WIDTH?[Number(process.env.TEST_WIDTH)]:[320,390,768,1366])){
 const p=await b.newPage({viewport:{width,height:900}}),errors=[];p.on('pageerror',e=>errors.push(e.message));p.on('dialog',d=>d.accept(d.type()==='prompt'?'Compactação '+Date.now():undefined));
 await p.route('**/*',r=>r.request().url().startsWith(origin)?r.continue():r.abort());
 // Base original, sem a folha de compactação, na mesma largura e navegador.
 await p.route('**/questao-editor.css*',r=>r.fulfill({contentType:'text/css',body:''}));
 await p.route('**/admin-criar-curso-completo.js*',r=>r.fulfill({contentType:'text/javascript',body:fs.readFileSync('/tmp/resumao-compactas-antes.js','utf8')}));
 await entrar(p);await limpar(p);const antes=await medir(p);
 await p.unroute('**/questao-editor.css*');await p.unroute('**/admin-criar-curso-completo.js*');
 await entrar(p);await limpar(p);const vazio=await medir(p);
 await p.locator('#camposQuestaoCompleta').screenshot({path:path.join(out,`vazio-${width}.png`)});
 assert.equal(vazio.overflow,0);assert.ok(vazio.altura<antes.altura*0.9);
 assert.deepEqual(vazio.editores.map(e=>e.placeholder),['Enunciado','Alternativa A','Alternativa B','Alternativa C','Alternativa D','Alternativa E','Comentário']);
 assert.ok(vazio.editores.slice(1,6).every(e=>e.altura>=60&&e.altura<=80));
 vazio.editores.forEach((e,i)=>{assert.deepEqual(e.toolbar,antes.editores[i].toolbar);assert.deepEqual(e.plugins,antes.editores[i].plugins)});
 assert.equal(await p.locator('#camposQuestaoCompleta .teoria-markdown-controles button').count(),7);
 assert.equal(await p.locator('#camposQuestaoCompleta label').filter({hasText:/^Alternativas$/}).count(),0);
 // Abrir todos os importadores, inclusive os de alternativas.
 for(let i=0;i<7;i++){
 const button=p.locator('#camposQuestaoCompleta .teoria-markdown-controles button').nth(i);await button.scrollIntoViewIfNeeded();assert.ok(await button.isVisible());await button.click();
 const dlg=p.locator('dialog[open]');await dlg.locator('[data-md="fonte"]').fill('**Campo '+i+'** com *itálico* e fórmula \\(x^2\\).\n\n| A | B |\n|---|---|\n| 1 | 2 |');await dlg.getByRole('button',{name:'Importar material',exact:true}).click();await dlg.waitFor({state:'hidden'});
 }
 const importados=await p.evaluate(()=>QuestaoEditores.dados());assert.ok(importados.alternativas.every(a=>a.texto.includes('<strong>')&&a.texto.includes('ro-math-inline')&&a.texto.includes('<table>')));
 // Barra agrupada mantém todos os itens alcançáveis pelo menu em telas estreitas.
 const toolbar=p.locator('#camposQuestaoCompleta .ck-toolbar').first();await toolbar.scrollIntoViewIfNeeded();
 const mais=toolbar.locator('.ck-toolbar__grouped-dropdown > button');if(await mais.isVisible()){await mais.click();assert.ok(await p.locator('.ck-dropdown__panel-visible').count());await p.keyboard.press('Escape');}
 await p.locator('#camposQuestaoCompleta .ck-content').evaluateAll(els=>els.forEach((el,i)=>{
 const ed=el.ckeditorInstance;ed.model.change(w=>w.setSelection(ed.model.document.getRoot(),'end'));
 const dt=new DataTransfer();dt.setData('text/html','<p><strong>Colagem formatada</strong> <i>itálico</i> <u>sublinhado</u></p>');dt.setData('text/plain','Colagem formatada');
 el.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));
 if(i>0&&i<6)ed.setData(ed.getData()+'<p>'+('Alternativa longa com conteúdo. '.repeat(160))+'</p>');
 }));
 assert.match((await p.evaluate(()=>QuestaoEditores.dados())).comentario,/<strong>Colagem formatada/);
 const png=fs.readFileSync(path.resolve(__dirname,'../evidencias/questoes-editor/figura-fixture.png'));
 for(let i=0;i<7;i++)await p.locator('#camposQuestaoCompleta .teoria-imagens-controles input[type=file]').nth(i).setInputFiles({name:'figura.png',mimeType:'image/png',buffer:png});
 await p.locator('#camposQuestaoCompleta img').evaluateAll(imgs=>imgs.forEach(i=>i.loading='eager'));
 await p.waitForFunction(()=>[...document.querySelectorAll('#camposQuestaoCompleta .ck-content')].every(e=>{const img=e.querySelector('img');return img&&img.complete&&img.naturalWidth>0})).catch(async error=>{console.log(await p.locator('#camposQuestaoCompleta').evaluate(e=>({avisos:[...e.querySelectorAll('[role=status],[role=alert]')].map(e=>e.textContent),imagens:[...e.querySelectorAll('img')].map(i=>({src:i.src,complete:i.complete,width:i.naturalWidth})),dados:QuestaoEditores.dados()})));throw error});
 const longo=await medir(p);assert.equal(longo.overflow,0);assert.ok(longo.editores.slice(1,6).every(e=>e.altura<=241&&e.scroll>e.altura));
 // Conteúdo no fim continua editável e alcançável por rolagem interna.
 await p.locator('#camposQuestaoCompleta .questao-editor-alternativa .ck-content').evaluateAll(els=>els.forEach(el=>{el.scrollTop=el.scrollHeight}));
 assert.ok(await p.locator('#camposQuestaoCompleta .questao-editor-alternativa .ck-content').evaluateAll(els=>els.every(el=>el.scrollTop>0)));
 await p.locator('#camposQuestaoCompleta').screenshot({path:path.join(out,`preenchido-${width}.png`)});
 await limpar(p);
 // Mesmo layout em criação, sem salvar nem modificar os registros de edição.
 await p.getByRole('button',{name:'Descartar e fechar edição',exact:true}).click();
 await p.evaluate(async()=>{
 const headers={Authorization:'Bearer isolado-admin','Content-Type':'application/json'};
 let r=await fetch('/disciplinas-proprias/1/assuntos-proprios',{method:'POST',headers,body:JSON.stringify({curso_disciplina_propria_id:1,nome:'Compactação '+Date.now(),ativo:true})});assertResponse(r);const assunto=await r.json();
 r=await fetch('/assuntos-proprios/'+assunto.id+'/pasta-teoria',{headers});assertResponse(r);const pasta=await r.json();await abrirQuestoesAula(pasta.aula_id,'Prévia compacta');
 function assertResponse(r){if(!r.ok)throw new Error('Fixture: '+r.status)}
 });
 await p.getByRole('button',{name:'Criar bateria de questões',exact:true}).click();
 await p.locator('#listaBateriasAula').getByRole('button',{name:'Abrir / editar questões',exact:true}).last().click();await ready(p);const novo=await medir(p);assert.equal(novo.overflow,0);assert.deepEqual(novo.editores.map(e=>e.altura),vazio.editores.map(e=>e.altura));
 assert.deepEqual(errors,[]);
 results.push({width,antes:antes.altura,depois:vazio.altura,reducaoPercentual:Math.round((1-vazio.altura/antes.altura)*100),alternativaAltura:vazio.editores[1].altura,overflow:0,criacaoEdicao:'OK',markdown7Campos:'OK',colagemFormatada:'OK',formulaTabela:'OK',imagens7Campos:'OK',rolagemAlternativas:'OK',toolbarPluginsIdenticos:'OK'});await p.close();
}
fs.writeFileSync(path.join(out,'resultados.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await b.close()}})().catch(e=>{console.error(e);process.exitCode=1});
