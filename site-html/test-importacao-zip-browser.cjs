const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), http = require('node:http');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const root = __dirname;
const scripts = ['js/vendor/markdown-it-15.0.3.min.js','js/vendor/dompurify-3.4.17.min.js',
  'js/teoria-matematica.js','js/editor-teoria-matematica.js','js/teoria-imagens.js',
  'js/editor-teoria-imagens.js','js/editor-teoria-markdown.js','js/editor-teoria.js'];
const ufTeste = process.env.UF_TEST || 'NACIONAL';
const q = {tipo:'MULTIPLA_5',enunciado_markdown:'Texto ![figura](imagens/a.png)',alternativas:{A:'1920.', B:'1940.', C:'1970.', D:'2017.', E:'1936.'},gabarito:'A',comentario_markdown:'Comentário'};
const doc = {versao:1,curso:{nome:'Curso',banca:'B',cargo:'C',orgao:'O',ano:2026,uf:ufTeste,descricao_publica_markdown:'Descrição'},disciplinas:[{nome:'D',assuntos:[{nome:'A',aula_titulo:'Aula',resumos:[{titulo:'Resumo',texto_markdown:'## Título\n\n![figura](imagens/a.png)'}],baterias:[{titulo:'B',tipo:'MULTIPLA',questoes:Array(10).fill(q)}]}]}]};
const estilos = 'Normal <u>sublinhado</u> **<u>duplo</u>** *<u>italico</u>* ***<u>triplo</u>***';
doc.disciplinas[0].assuntos[0].resumos[0].texto_markdown += '\n\n' + estilos;
q.enunciado_markdown += ' ' + estilos;
q.comentario_markdown = estilos;
q.alternativas.A = estilos;
const html = `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body>
<main style="max-width:100%"><label for="arquivoImportacao">Arquivo JSON ou ZIP</label><input id="arquivoImportacao" type="file" style="max-width:100%"><button id="importarCurso">Importar curso</button><p id="statusImportacao"></p></main>
<script src="/ckeditor.js"></script>${scripts.map(p=>`<script src="/${p}"></script>`).join('')}
<script>window.RESUMAO_CKEDITOR_LICENSE_KEY='GPL';window.original=${JSON.stringify(doc)};
TeoriaImagens.api=async (url,form)=>{if(url.endsWith('/preparar'))return {original:window.original,imagens:{'imagens/a.png':'12345678-1234-4234-8234-123456789abc'}};
if(window.falhar)throw Error('Falha simulada de rede');
window.convertido=JSON.parse(await form.get('convertido').text());return {curso_id:1,repetida:false};};
window.apiPostAuth=async (url,body)=>{window.jsonEnviado=body;return url.endsWith('/validar')?{valido:true}:{curso_id:2,repetida:false};};</script>
<script src="/js/admin-importar-curso.js"></script></body></html>`;
const server=http.createServer((req,res)=>{const p=new URL(req.url,'http://localhost').pathname;
  if(p==='/'){res.setHeader('Content-Type','text/html; charset=utf-8');return res.end(html);}
  const file=p==='/ckeditor.js'?process.env.CKEDITOR_TEST_JS:path.join(root,p);
  try{res.setHeader('Content-Type','text/javascript');res.end(fs.readFileSync(file));}catch{res.writeHead(404);res.end();}});
(async()=>{let browser;try{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 browser=await chromium.launch({executablePath:process.env.CHROMIUM_BIN,args:['--no-sandbox']});
 for(const width of [320,768,1366]){
  const page=await browser.newPage({viewport:{width,height:900}}), errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  await page.locator('#arquivoImportacao').setInputFiles({name:'curso.zip',mimeType:'application/zip',buffer:Buffer.from('zip')});
  await page.locator('#importarCurso').click();
  await page.waitForFunction(()=>document.querySelector('#statusImportacao').textContent.includes('importado com sucesso'),null,{timeout:30000}).catch(async e=>{throw Error((await page.locator('#statusImportacao').textContent())+'; '+e.message)});
  const result=await page.evaluate(()=>({documento:window.convertido,overflow:document.documentElement.scrollWidth>innerWidth}));
  assert.equal(result.documento.curso.uf, ufTeste);
  assert.match(result.documento.disciplinas[0].assuntos[0].resumos[0].texto_markdown,/midias\/imagens\/12345678/);
  assert.match(result.documento.disciplinas[0].assuntos[0].baterias[0].questoes[0].enunciado_markdown,/midias\/imagens\/12345678/);
  const verificar = html => { for (const palavra of ['sublinhado','duplo','italico','triplo']) assert.match(html,new RegExp('<u>[^<]*'+palavra+'</u>')); assert.match(html,/<strong>/); assert.match(html,/<i>/); };
  const assunto = result.documento.disciplinas[0].assuntos[0], questao = assunto.baterias[0].questoes[0];
  for (const campo of [assunto.resumos[0].texto_markdown,questao.enunciado_markdown,questao.comentario_markdown,questao.alternativas.A]) verificar(campo);
  assert.equal(result.overflow,false);assert.deepEqual(errors,[]);
  const simples=JSON.parse(JSON.stringify(doc));
  simples.disciplinas[0].assuntos[0].resumos[0].texto_markdown=estilos;
  for(const questao of simples.disciplinas[0].assuntos[0].baterias[0].questoes)questao.enunciado_markdown=estilos;
  await page.locator('#arquivoImportacao').setInputFiles({name:'curso.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(simples))});
  await page.locator('#importarCurso').click();
  await page.waitForFunction(()=>document.querySelector('#statusImportacao').textContent.includes('Curso 2 importado com sucesso'),null,{timeout:30000});
  assert.equal(await page.evaluate(()=>window.jsonEnviado.original.curso.nome),'Curso');
  assert.equal(await page.evaluate(()=>window.jsonEnviado.convertido.curso.uf),ufTeste);
  const convertido = await page.evaluate(()=>window.jsonEnviado.convertido.disciplinas[0].assuntos[0]);
  for (const campo of [convertido.resumos[0].texto_markdown,convertido.baterias[0].questoes[0].enunciado_markdown,convertido.baterias[0].questoes[0].comentario_markdown,convertido.baterias[0].questoes[0].alternativas.A]) verificar(campo);
  const seguranca = await page.evaluate(() => {
    const conv = (s, op={}) => TeoriaMarkdown.converter(s,{sublinhado:true,...op}).html;
    return [conv('<u>seguro</u> <script>alert(1)</script>'),conv('`<u>literal</u>`'),conv('\\<u>literal</u>'),conv('<u>sem fim'),conv('<u>x</u>',{descricaoPublica:true})];
  });
  assert.match(seguranca[0],/<u>seguro<\/u>/); assert.doesNotMatch(seguranca[0],/<script>/);
  for (const literal of seguranca.slice(1)) assert.doesNotMatch(literal,/<u>/);
  const combinacoes = await page.evaluate(() => ['<u>**negrito**</u>', '<u>*italico*</u>', '<u>***triplo***</u>', '**<u>duplo</u>**', '<u onmouseover="alert(1)">hostil</u>'].map(s => TeoriaMarkdown.converter(s,{sublinhado:true}).html));
  for (const html of combinacoes.slice(0,4)) assert.match(html,/<u>/);
  assert.match(combinacoes[0],/<strong>/); assert.match(combinacoes[1],/<em>/);
  assert.match(combinacoes[2],/<strong>/); assert.match(combinacoes[2],/<em>/);
  assert.doesNotMatch(combinacoes[4],/<u/);
  const casos = await page.evaluate(() => ['1.', '42)', '1920.\n1940.', '1. Primeiro\n2. Segundo', '1. Primeiro\n2.', '**2026**', '| Ano | Valor |\n| --- | --- |\n| 1920 | 1 |'].map(s=>TeoriaMarkdown.converter(s).html));
  assert.match(casos[0], /1\./); assert.match(casos[1], /42\)/);
  assert.match(casos[2], /1920\./); assert.match(casos[2], /1940\./);
  assert.match(casos[3], /<ol>/); assert.match(casos[3], /<li>Primeiro<\/li>/);
  assert.match(casos[4], /<ol>/); assert.match(casos[4], /2\./);
  assert.match(casos[5], /<strong>2026<\/strong>/); assert.match(casos[6], /<table>/);
  await page.evaluate(()=>{window.falhar=true;});
  await page.locator('#arquivoImportacao').setInputFiles({name:'curso.zip',mimeType:'application/zip',buffer:Buffer.from('zip')});
  await page.locator('#importarCurso').click();
  await page.waitForFunction(()=>document.querySelector('#statusImportacao').textContent.includes('Falha ao importar'),null,{timeout:30000});
  await page.waitForFunction(()=>!document.querySelector('#importarCurso').disabled);
  await page.evaluate(()=>{window.falhar=false;});
  await page.locator('#importarCurso').click();
  await page.waitForFunction(()=>document.querySelector('#statusImportacao').textContent.includes('Curso 1 importado com sucesso'),null,{timeout:30000});
  assert.deepEqual(errors,[]);await page.close();
  console.log(`Importação ZIP no navegador: ${width}px aprovada`);
 }
}finally{await browser?.close();server.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
