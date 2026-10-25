const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const script=fs.readFileSync(path.join(__dirname,'js/admin-acesso.js'),'utf8');
const producao=['criar-curso-completo.html','admin-questoes-aluno.html','admin-questoes-pratica.html','cursos.html','curso-disciplinas.html','disciplinas.html','assuntos.html','aulas.html','aula-conteudo.html'];
const alunos=['pagamentos.html','atendimento.html','admin-mensagens-questoes.html'];
const geral=['alunos.html','vendedores.html','cupons.html','reembolsos.html','contestacoes.html','perfis.html'];
function contexto(pagina,tipo,{ativo=true,flag=tipo==='admin_geral',token='token',resposta=200}={}) {
 const classes=new Set(),eventos={},calls=[],redirects=[];
 const sections=['producao','alunos','geral','geral'].map(area=>({dataset:{adminArea:area},hidden:false}));
 const store={access_token:token,auth_generation:'1'};
 const c={location:{pathname:'/admin/'+pagina,replace:p=>redirects.push(p)},
  localStorage:{getItem:k=>store[k]??null},
  document:{documentElement:{classList:{add:k=>classes.add(k),remove:k=>classes.delete(k)}},
   head:{appendChild(){}},createElement:()=>({}),querySelectorAll:()=>sections,
   addEventListener:(k,f)=>eventos[k]=f},
  API_BASE:'https://api.example.invalid',Sessao:{fetch:async(url,options)=>{
   calls.push({url,options});return {ok:resposta===200,json:async()=>({ativo,is_admin:flag,tipo_admin:tipo})};
  }},addEventListener:(k,f)=>eventos[k]=f};
 c.window=c;vm.createContext(c);vm.runInContext(script,c);
 return {c,classes,eventos,calls,redirects,sections,store};
}
for(const tipo of ['admin_geral','admin_prod','admin_adm',null]) {
 test(`URLs diretas e painel: ${tipo}`,async()=>{
  for(const pagina of ['index.html',...producao,...alunos,...geral]) {
   const x=contexto(pagina,tipo);
   assert(x.classes.has('admin-validando'));
   const permitida=tipo==='admin_geral'||tipo==='admin_prod'&&producao.includes(pagina)||tipo==='admin_adm'&&alunos.includes(pagina)||pagina==='index.html'&&!!tipo;
   assert.equal(await x.c.AdminAcesso.exigir(),permitida,`${tipo}: ${pagina}`);
   assert.equal(x.classes.has('admin-validando'),!permitida);
   assert.equal(x.redirects.length,permitida?0:1);
   assert.equal(x.calls[0].options.headers.Authorization,'Bearer token');
   if(pagina==='index.html'&&permitida)assert.deepEqual(x.sections.map(s=>!s.hidden),tipo==='admin_geral'?[true,true,true,true]:tipo==='admin_prod'?[true,false,false,false]:[false,true,false,false]);
  }
 });
}
test('combinações inválidas, inativo, sem token e falha de sessão bloqueiam',async()=>{
 for(const [tipo,options] of [['admin_prod',{flag:true}],['admin_geral',{flag:false}],['admin_geral',{ativo:false}],['admin_geral',{token:null}],['admin_geral',{resposta:401}],[undefined,{flag:false}],['root',{flag:false}]]){
  const x=contexto('perfis.html',tipo,options);
  assert.equal(await x.c.AdminAcesso.exigir(),false);
  assert(x.classes.has('admin-validando'));
 }
});
test('troca de sessão e retorno pelo histórico revalidam /me',async()=>{
 const x=contexto('index.html','admin_prod');
 await Promise.all([x.c.AdminAcesso.exigir(),x.c.AdminAcesso.exigir()]);assert.equal(x.calls.length,1);
 x.store.auth_generation='2';await x.c.AdminAcesso.exigir();assert.equal(x.calls.length,2);
 x.eventos.pageshow({persisted:true});await x.c.AdminAcesso.exigir();assert.equal(x.calls.length,3);
});
test('todas as páginas administrativas carregam a guarda antes dos scripts funcionais',()=>{
 for(const nome of fs.readdirSync(path.join(__dirname,'admin')).filter(n=>n.endsWith('.html'))){
  const html=fs.readFileSync(path.join(__dirname,'admin',nome),'utf8');
  assert(html.includes('admin-acesso.js?v=perfis-1'),nome);
  assert(html.indexOf('admin-acesso.js')<html.indexOf('../js/app.js'),nome);
 }
 const html=fs.readFileSync(path.join(__dirname,'admin/index.html'),'utf8');
 const alunosSection=html.match(/data-admin-area="alunos"[\s\S]*?<\/section>/)[0];
 const comercialSection=html.match(/<!-- COMERCIAL -->[\s\S]*?<\/section>/)[0];
 assert(!alunosSection.includes('alunos.html'));assert(comercialSection.includes('alunos.html'));
});
