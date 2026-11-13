// APIs simuladas; nenhum acesso aos serviços de produção.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=__dirname;
const server=http.createServer((req,res)=>{const f=path.resolve(root,'.'+new URL(req.url,'http://local').pathname);if(!f.startsWith(root+'/')||!fs.existsSync(f)){res.writeHead(404).end();return;}res.setHeader('Content-Type',f.endsWith('.js')?'text/javascript':f.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(f));});
(async()=>{let browser;try{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin=`http://127.0.0.1:${server.address().port}`;
 browser=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE,args:['--no-sandbox']});const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{
  window.cursos=[{id:1,nome:'Curso A legado',ativo:true},{id:2,nome:'Curso B',ativo:true,banca:'Banca',cargo:'Cargo',orgao:'Órgão',ano:2026,uf:'AM'}];
  window.calls=[];window.alertas=[];window.pending=[];window.delay=null;window.fail=null;
  window.alert=x=>alertas.push(x);window.confirm=()=>true;window.prompt=()=> 'Cópia B';window.requireAdmin=async()=>true;
  const api=async(method,url,data)=>{calls.push({method,url,data});if(delay===method+' '+url){await new Promise((resolve,reject)=>pending.push({resolve,reject}));}if(fail===method+' '+url)throw Error('Failed to fetch');
   if(url==='/admin/ckeditor-chave')return {licenseKey:'GPL'};
   if(url==='/admin/cursos')return structuredClone(cursos);
   if(method==='POST'&&url==='/cursos'){const c={id:3,...data};cursos.push(c);return structuredClone(c);}
   if(url.endsWith('/duplicar')){cursos.push({id:4,nome:data.novo_nome,ativo:true});return {novo_curso_id:4,novo_curso_nome:data.novo_nome};}
   const id=Number(url.split('/')[url.startsWith('/admin/')?3:2]);
   if(method==='DELETE'){cursos.find(c=>c.id===id).ativo=false;return {};}
   if(method==='PUT'&&/^\/cursos\/\d+$/.test(url)){const c=cursos.find(c=>c.id===id);Object.assign(c,data);return structuredClone(c);}
   if(url.endsWith('/config-publica'))return {publicado:false,descricao_publica:'Descrição '+id,tempos_acesso:[4,8,12].map(meses=>({meses,valor_cents:id*1000}))};
   if(method==='POST'&&url.endsWith('/disciplinas-proprias'))return {id:11,nome:data.nome};
   if(url.endsWith('/disciplinas-proprias'))return [{id:id*10,nome:'Disciplina '+id}];
   if(url.endsWith('/pasta-teoria'))return {id:101};
   if(url.endsWith('/aulas'))return [];
   if(url.endsWith('/assuntos-proprios'))return [{id:100,nome:'Assunto A'}];
   return {};
  };
  window.apiGetAuth=url=>api('GET',url);window.apiPostAuth=(url,data)=>api('POST',url,data);window.apiPutAuth=(url,data)=>api('PUT',url,data);window.apiDeleteAuth=url=>api('DELETE',url);
 });
 await page.route('**/*',route=>{const u=new URL(route.request().url());if(u.origin===origin){if(/\/(app|admin|sessao|admin-acesso)\.js$/.test(u.pathname))return route.fulfill({contentType:'text/javascript',body:''});return route.continue();}if(u.hostname==='cdn.ckeditor.com'){if(u.pathname.endsWith('.umd.js'))return route.fulfill({contentType:'text/javascript',body:fs.readFileSync(process.env.CKEDITOR_TEST_BUNDLE)});if(u.pathname.endsWith('.css'))return route.fulfill({contentType:'text/css',body:fs.readFileSync(process.env.CKEDITOR_TEST_CSS)});return route.fulfill({body:''});}return route.abort();});
 const js=code=>page.evaluate(code);const check=async code=>assert.ok(await js(code),code);
 async function ready(id){await page.waitForFunction(id=>document.getElementById('boxConfigPublicaCurso').style.display==='block'&&document.getElementById('cursoDescricaoPublica').value===`Descrição ${id}`&&!document.getElementById('avisoDescricaoPublica').textContent,id);}
 async function activate(id){const mutations=await js('calls.filter(c=>c.method!=="GET").length');await js(`cursoExistenteSelect.value='${id}';btnUsarCursoExistente.click()`);await ready(id);assert.equal(await js('calls.filter(c=>c.method!=="GET").length'),mutations,"Trocar curso não deve salvar");}
 await page.goto(origin+'/admin/criar-curso-completo.html');await page.waitForFunction(()=>document.getElementById('cursoExistenteSelect').options.length===3);
 await activate(1);await js('btnEditarCurso.click()');await check('!formEditarCurso.hidden');
 await js(`cursoNome.value='RESUMÃO ASSISTENTE ADMINISTRATIVO SEDUC-AM 2026';for(const [k,v] of Object.entries({banca:'Banca',cargo:'Cargo',orgao:'Órgão',ano:2026,uf:'AM'}))document.getElementById('novo-'+k).value=v;formCurso.requestSubmit()`);
 await page.waitForFunction(()=>document.getElementById('cursoExistenteSelect').value==='3');await check(`formEditarCurso.hidden && document.getElementById('editar-nome').value==='' && !listaDisciplinasCurso.textContent.includes('Disciplina 1')`);
 const before=await js('calls.filter(c=>c.method==="PUT").length');await js('formEditarCurso.dispatchEvent(new Event("submit",{cancelable:true}))');assert.equal(await js('calls.filter(c=>c.method==="PUT").length'),before);
 await activate(1);await js('btnEditarCurso.click()');await activate(2);await check(`formEditarCurso.hidden && listaDisciplinasCurso.textContent.includes('Disciplina 2') && valor4Meses.value==='20,00'`);
 // Changing the dropdown alone must not retarget editing away from the active course.
 await js(`cursoExistenteSelect.value='1';btnEditarCurso.click()`);await check(`document.getElementById('editar-nome').value==='Curso B'`);await js('cancelarEdicaoCurso.click()');
 // Late success and late network failure from editing A cannot touch B.
 for(const reject of [false,true]){
  await activate(1);await js(`btnEditarCurso.click();delay='PUT /cursos/1';document.getElementById('editar-nome').value='A atualizado';formEditarCurso.requestSubmit()`);await page.waitForFunction(()=>pending.length===1);await activate(2);
  await js(`delay=null;pending.shift().${reject?"reject(Error('Failed to fetch'))":"resolve()"}`);await page.waitForTimeout(100);
  await check(`formEditarCurso.hidden && erroEditarCurso.textContent==='' && cursoExistenteSelect.value==='2' && !msgCurso.textContent.includes('atualizado')`);
 }
 // Real errors in the current context remain visible.
 await js(`btnEditarCurso.click();fail='PUT /cursos/2';formEditarCurso.requestSubmit()`);await page.waitForFunction(()=>document.getElementById('erroEditarCurso').textContent.includes('Failed to fetch'));await check('!formEditarCurso.hidden');await js('fail=null;cancelarEdicaoCurso.click()');
 // A newly opened B edit must survive an old A response, even its error/finally.
 await activate(1);await js(`btnEditarCurso.click();delay='PUT /cursos/1';formEditarCurso.requestSubmit()`);await page.waitForFunction(()=>pending.length===1);await activate(2);await js(`btnEditarCurso.click();delay=null;pending.shift().reject(Error('Failed to fetch'))`);await page.waitForTimeout(100);await check(`!formEditarCurso.hidden && document.getElementById('editar-nome').value==='Curso B' && erroEditarCurso.textContent===''`);await js('cancelarEdicaoCurso.click()');
 // Pending subject/lesson reads must not reopen A or auto-create a lesson in B.
 await activate(1);await js(`delay='GET /disciplinas-proprias/10/assuntos-proprios';trabalharNestaDisciplina(10);void 0`);await page.waitForFunction(()=>pending.length===1);await activate(2);await js('delay=null;pending.shift().resolve()');await page.waitForTimeout(100);await check(`areaAssuntos.style.display==='none' && !listaAssuntos.textContent.includes('Assunto A')`);
 await activate(1);await js(`delay='GET /assuntos-proprios/100/pasta-teoria';abrirAulasDoAssunto(100);void 0`);await page.waitForFunction(()=>pending.length===1);await activate(2);const mutationsBefore=await js('calls.filter(c=>c.method!=="GET").length');await js('delay=null;pending.shift().resolve()');await page.waitForTimeout(100);assert.equal(await js('calls.filter(c=>c.method!=="GET").length'),mutationsBefore);await check(`areaAulas.style.display==='none'`);
 // A list refresh started by a successful edit also belongs to that context.
 await activate(1);await js(`btnEditarCurso.click();delay='GET /admin/cursos';formEditarCurso.requestSubmit()`);await page.waitForFunction(()=>pending.length===1);await activate(2);await js('delay=null;pending.shift().resolve()');await page.waitForTimeout(100);await check(`cursoExistenteSelect.value==='2' && !msgCurso.textContent.includes('atualizado')`);
 // A discipline write already sent keeps A as its destination; its result never enters B.
 await activate(1);await js(`disciplinaNome.value='Disciplina pendente A';delay='POST /cursos/1/disciplinas-proprias';btnAdicionarDisciplina.click()`);await page.waitForFunction(()=>pending.length===1);await activate(2);await js('delay=null;pending.shift().resolve()');await page.waitForTimeout(100);await check(`!listaDisciplinasCurso.textContent.includes('pendente A') && calls.some(c=>c.method==='POST'&&c.url==='/cursos/1/disciplinas-proprias'&&c.data.curso_id===1)`);
 // Delayed reads and public saves cannot overwrite the new course or redirect writes.
 for(const reject of [false,true])for(const url of ['/cursos/1/disciplinas-proprias','/admin/cursos/1/config-publica']){
  await js(`delay='GET ${url}';cursoExistenteSelect.value='1';btnUsarCursoExistente.click()`);await page.waitForFunction(()=>pending.length===1);await activate(2);await js(`delay=null;pending.shift().${reject?"reject(Error('Failed to fetch'))":"resolve()"}`);await page.waitForTimeout(100);await check(`listaDisciplinasCurso.textContent.includes('Disciplina 2') && valor4Meses.value==='20,00' && cursoDescricaoPublica.value==='Descrição 2'`);
 }
 await activate(1);await js(`btnEditarConfigPublicaCurso.click();delay='PUT /admin/cursos/1/config-publica';btnSalvarConfigPublicaCurso.click()`);await page.waitForFunction(()=>pending.length===1);await activate(2);await js(`delay=null;pending.shift().reject(Error('Failed to fetch'))`);await page.waitForTimeout(100);await check(`msgConfigPublicaCurso.textContent==='' && valor4Meses.value==='20,00'`);
 await js(`btnEditarConfigPublicaCurso.click();document.querySelector('.ck-editor__editable').ckeditorInstance.setData('<p><strong>Descrição B editada</strong></p>');btnSalvarConfigPublicaCurso.click()`);await page.waitForFunction(()=>document.getElementById('msgConfigPublicaCurso').textContent.includes('sucesso'));await check(`calls.some(c=>c.method==='PUT'&&c.url==='/admin/cursos/2/config-publica'&&c.data.descricao_publica.includes('<strong>Descrição B editada</strong>'))`);
 // Legacy course remains editable with null metadata.
 await activate(1);await js(`btnEditarCurso.click();formEditarCurso.requestSubmit()`);await page.waitForFunction(()=>document.getElementById('formEditarCurso').hidden);await check(`calls.some(c=>c.method==='PUT'&&c.url==='/cursos/1'&&c.data.ano===null)`);
 await activate(2);await js('btnEditarCurso.click();btnDuplicarCurso.click()');await page.waitForFunction(()=>document.getElementById('cursoExistenteSelect').value==='4');await ready(4);await check('formEditarCurso.hidden && listaDisciplinasCurso.textContent.includes("Disciplina 4")');await js('btnEditarCurso.click();btnExcluirCurso.click()');await page.waitForFunction(()=>document.getElementById('cursoExistenteSelect').value==='');await check(`formEditarCurso.hidden && boxConfigPublicaCurso.style.display==='none' && boxDisciplinas.style.display==='none'`);
 // Search and filters still work.
 await js(`cursoPesquisa.value='curso b';cursoPesquisa.dispatchEvent(new Event('input'))`);await check(`cursoExistenteSelect.options.length===2 && cursoExistenteSelect.options[1].value==='2'`);await js(`limparFiltrosCursos.click();document.getElementById('filtro-uf').value='AM';document.getElementById('filtro-uf').dispatchEvent(new Event('change'))`);await check(`![...cursoExistenteSelect.options].some(o=>o.value==='1')`);await js('limparFiltrosCursos.click()');
 await activate(2);
 for(const width of [320,390,768,1366]){await page.setViewportSize({width,height:900});await js('btnEditarCurso.click()');await check('document.documentElement.scrollWidth<=innerWidth && document.body.scrollWidth<=innerWidth');await check(`!document.body.innerText.includes('Metadados ausentes') && !document.querySelector('label[for="cursoDescricaoPublica"]')`);await js('cancelarEdicaoCurso.click()');}
 await page.reload();await page.waitForFunction(()=>document.getElementById('cursoExistenteSelect').options.length===3);await check(`formEditarCurso.hidden && cursoExistenteSelect.value==='' && boxConfigPublicaCurso.style.display==='none'`);
 assert.deepEqual(errors,[]);console.log('OK: criação A→B, ativação, edição explícita, legado, duplicação, exclusão, reload, filtros, pesquisa, CKEditor/salvamento, respostas atrasadas/erros e larguras 320/390/768/1366; API inteiramente simulada.');
 }finally{if(browser)await browser.close();await new Promise(r=>server.close(r));}})().catch(e=>{console.error(e);process.exitCode=1});
