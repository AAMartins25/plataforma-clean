// Somente laboratório local. Não serve app.js nem as páginas apontadas a produção.
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),readline=require('node:readline');
const {spawn}=require('node:child_process');
const root=__dirname;
const dist=process.env.CKEDITOR_TEST_DIST||'/workspaces/resumao-editor-teoria-dev/.local/ckeditor-seguranca-tools/node_modules/ckeditor5/dist/browser';
const liberar=process.argv.includes('--liberar-storage');
const port=8766,origem=`http://127.0.0.1:${port}`;
const scripts=['ckeditor/ckeditor5.umd.js','js/vendor/katex/katex.min.js','js/teoria-matematica.js','js/editor-teoria-matematica.js',
 'js/teoria-imagens.js','js/editor-teoria-imagens.js','js/vendor/markdown-it-15.0.3.min.js','js/vendor/dompurify-3.4.17.min.js','js/editor-teoria-markdown.js','js/editor-teoria.js'];
const estilos=['css/style.css','css/editor-teoria-markdown.css','css/teoria-matematica.css','css/teoria-imagens.css','js/vendor/katex/katex.min.css','ckeditor/ckeditor5.css'];
const teoria=fs.readFileSync(path.join(root,'teoria.html'),'utf8');
const funcoes=teoria.slice(teoria.indexOf('    function limparTextoTeoria('),teoria.indexOf('    async function abrirSecaoTeoria('));
if(!funcoes.includes('TeoriaImagens.renderizar'))throw new Error('Funções de leitura não localizadas.');
let fixture,servidor;const pendentes=[];
const child=spawn(process.env.FASE2_PYTHON||'python',['-u','homologacao_imagens.py','bridge',...(liberar?['--liberar-storage']:[])],
 {cwd:path.join(root,'../backend'),env:process.env,stdio:['pipe','pipe','pipe']});
let readyResolve,readyReject;
const ready=new Promise((r,j)=>{readyResolve=r;readyReject=j;});
const prazo=setTimeout(()=>readyReject(new Error('Ponte PostgreSQL local indisponível.')),20000);
readline.createInterface({input:child.stdout}).on('line',line=>{
 let r;try{r=JSON.parse(line);}catch{return;}
 if(r.ready){fixture=r;clearTimeout(prazo);readyResolve();}
 else pendentes.shift()?.resolve(r);
});
// Não encaminhar stderr bruto: bibliotecas poderiam incluir parâmetros/URLs.
child.stderr.on('data',()=>{});
child.on('exit',()=>{readyReject(new Error('Ponte local encerrada.'));for(const p of pendentes.splice(0))p.resolve({status:503,body:{detail:'Ponte local encerrada.'}});servidor?.close();});
const api=req=>new Promise(resolve=>{pendentes.push({resolve});child.stdin.write(JSON.stringify(req)+'\n');});
function pagina(){return `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Homologação local — Fase 2</title>
${estilos.map(p=>`<link rel="stylesheet" href="/${p}">`).join('')}
<style>body{padding:16px}main{max-width:1000px;margin:auto;min-width:0}.assunto{min-width:0}#leitura{margin-top:20px}#estado{padding:12px;border:2px solid #333}button{margin:5px}</style></head>
<body><main><p id="estado">PostgreSQL local • Storage ${fixture.storageLiberado?'LIBERADO PARA HOMOLOGAÇÃO':'BLOQUEADO'} • manutenção false</p>
<p>Somente dados fictícios. Nenhuma chamada ao backend de produção.</p>
<button id="salvar">Salvar no banco local</button><button id="reabrir">Reabrir material local</button><button id="aluno">Visualizar como aluno fictício</button><button id="admin">Voltar ao administrador</button>
<p id="mensagem" role="status"></p><div class="assunto"><textarea id="editor"></textarea></div>
<section id="leitura" class="teoria-page"><div id="detalhes_aula"></div><span id="paginacao_teoria"></span></section></main>
${scripts.map(p=>`<script src="/${p}"></script>`).join('')}
<script>
const API_BASE=location.origin,tokens=${JSON.stringify(fixture.tokens)};
window.RESUMAO_CKEDITOR_LICENSE_KEY='GPL';
localStorage.setItem('access_token',tokens.admin);
let paginasTeoria=[],paginaTeoriaAtual=0,aulaAtualId=1,materialId=null;
function contextoAcessoQuery(){return 'contratacao_id=1';}
function esc(s){return String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');}
${funcoes}
const campo=document.querySelector('#editor'),mensagem=document.querySelector('#mensagem');
async function requisitar(url,method='GET',body){
 const r=await fetch(API_BASE+url,{method,headers:{'Authorization':'Bearer '+localStorage.getItem('access_token'),...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined});
 const json=await r.json();if(!r.ok)throw new Error(json.detail||'Falha local.');return json;
}
function acao(id,fn){document.querySelector('#'+id).onclick=()=>fn().catch(e=>{mensagem.textContent=e.message;});}
async function lista(){return requisitar('/aulas/1/materiais?contratacao_id=1');}
acao('salvar',async()=>{
 if(!TeoriaEditor.pronto(campo))throw new Error('Aguarde o processamento.');
 const body={aula_id:1,tipo:'TEXTO',titulo:'Material fictício Fase 2',...TeoriaEditor.conteudo(campo)};
 const m=await requisitar(materialId?'/materiais/'+materialId:'/materiais',materialId?'PUT':'POST',body);
 materialId=m.id;mensagem.textContent='Gravado somente no PostgreSQL local.';
});
acao('reabrir',async()=>{
 localStorage.setItem('access_token',tokens.admin);const itens=await lista(),m=itens.find(m=>m.id===materialId)||itens.at(-1);
 if(!m)throw new Error('Ainda não existe material salvo.');
 materialId=m.id;await TeoriaEditor.destruir(campo);window.editor=await TeoriaEditor.iniciar(campo,m.conteudo_formato==='html_v1'?m.conteudo:TeoriaEditor.legadoParaHtml(m.conteudo));mensagem.textContent='Material local reaberto.';
});
acao('aluno',async()=>{
 localStorage.setItem('access_token',tokens.aluno);editor.enableReadOnlyMode('perfil-aluno-homologacao');
 paginasTeoria=construirPaginasTeoria(await lista());paginaTeoriaAtual=0;renderizarPaginaTeoria();mensagem.textContent='Leitura com JWT e contratação fictícios.';
});
acao('admin',async()=>{
 TeoriaImagens.cancelarLeitura(document.querySelector('.teoria-conteudo-rico'));document.querySelector('#detalhes_aula').textContent='';
 localStorage.setItem('access_token',tokens.admin);editor.disableReadOnlyMode('perfil-aluno-homologacao');mensagem.textContent='Administrador fictício.';
});
window.pronto=TeoriaEditor.iniciar(campo,'<p>Material fictício de homologação. Fórmula: <span class="ro-math-inline">P \\land Q</span>.</p>').then(e=>{window.editor=e;});
</script></body></html>`;}

function json(res,status,body){res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});res.end(JSON.stringify(body));}
function rotaAPI(method,url){
 const p=url.pathname;
 return (method==='GET'&&p==='/aulas/1/materiais')||
  (method==='POST'&&['/materiais','/admin/imagens/arquivos','/admin/imagens/zip','/admin/imagens/assinaturas','/aulas/1/imagens/assinaturas'].includes(p))||
  (method==='PUT'&&/^\/materiais\/[1-9][0-9]*$/.test(p));
}
async function atender(req,res){
 try{
  if(req.headers.host!==`127.0.0.1:${port}`)return json(res,403,{detail:'Host externo não autorizado.'});
  const url=new URL(req.url,origem);
  if(req.headers.origin&&req.headers.origin!==origem)return json(res,403,{detail:'Origem externa não autorizada.'});
  if(req.headers['sec-fetch-site']==='cross-site')return json(res,403,{detail:'Requisição externa bloqueada.'});
  if(req.method==='GET'&&url.pathname==='/__estado')return json(res,200,{banco:'PostgreSQL local isolado',storageLiberado:fixture.storageLiberado,manutencao:false,apiBase:'same-origin'});
  if(req.method==='GET'&&url.pathname==='/'){
   res.writeHead(200,{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store',
    'Content-Security-Policy':`default-src 'self'; connect-src 'self'; img-src 'self' ${fixture.storageOrigin}; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'`,
    'Referrer-Policy':'no-referrer'});res.end(pagina());return;
  }
  if(rotaAPI(req.method,url)){
   if(!Object.values(fixture.tokens).some(t=>req.headers.authorization==='Bearer '+t))return json(res,401,{detail:'Token de laboratório obrigatório.'});
   const partes=[];let total=0;
   for await(const chunk of req){total+=chunk.length;if(total>26*1024*1024)return json(res,413,{detail:'Limite local excedido.'});partes.push(chunk);}
   const r=await api({method:req.method.toLowerCase(),path:url.pathname+url.search,
    base64:Buffer.concat(partes).toString('base64'),headers:{authorization:req.headers.authorization,...(req.headers['content-type']?{'content-type':req.headers['content-type']}:{})}});
   return json(res,r.status,r.body);
  }
  // Lista positiva: impede servir .env, fontes da API ou páginas com API_BASE de produção.
  const relativo=url.pathname.slice(1);
  if(req.method!=='GET'||(!scripts.includes(relativo)&&!estilos.includes(relativo)&&!/^js\/vendor\/katex\/fonts\/[A-Za-z0-9_-]+\.(woff2?|ttf)$/.test(relativo)))return json(res,404,{detail:'Rota fora do laboratório.'});
  const base=relativo.startsWith('ckeditor/')?dist:root;
  const nome=path.resolve(base,relativo.replace(/^ckeditor\//,''));
  if(!nome.startsWith(path.resolve(base)+path.sep)||!fs.existsSync(nome))return json(res,404,{detail:'Dependência local ausente.'});
  res.writeHead(200,{'Content-Type':({'.js':'text/javascript','.css':'text/css','.woff2':'font/woff2','.woff':'font/woff'})[path.extname(nome)]||'application/octet-stream'});res.end(fs.readFileSync(nome));
 }catch{return json(res,500,{detail:'Falha local no laboratório.'});}
}
async function encerrar(){child.stdin.end();servidor?.closeAllConnections();servidor?.close();}
process.on('SIGINT',encerrar);process.on('SIGTERM',encerrar);
ready.then(()=>{
 if(!fs.existsSync(path.join(dist,'ckeditor5.umd.js')))throw new Error('CKEditor local não localizado.');
 servidor=http.createServer(atender);servidor.requestTimeout=70000;
 servidor.listen(port,'127.0.0.1',()=>console.log(`Homologação preparada em ${origem} — Storage ${fixture.storageLiberado?'LIBERADO':'BLOQUEADO'}; manutenção false.`));
 servidor.on('error',()=>{console.error('Porta local indisponível.');encerrar();process.exitCode=1;});
}).catch(()=>{clearTimeout(prazo);console.error('Não foi possível iniciar a ponte local. Execute preparar primeiro.');child.stdin.end();process.exitCode=1;});
