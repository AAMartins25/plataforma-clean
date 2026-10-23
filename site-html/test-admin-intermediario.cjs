const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/js/admin.js','utf8');
function contexto(){
 const calls=[],c={API_BASE:'https://api.example.invalid',location:{},alert(){},
  document:{addEventListener(){},getElementById(){return null}},localStorage:{getItem(){return 'token-ficticio'}},
  Sessao:{fetch:async(url,options)=>{calls.push({url,options});return {ok:true,status:200,json:async()=>({is_admin:true}),text:async()=>'{}'}}}};
 c.window=c;vm.createContext(c);vm.runInContext(source,c);return {c,calls};
}
test('somente os dois consumidores sem Bearer foram alterados',()=>{
 assert.match(source,/await apiPostAuth\("\/cursos", \{ nome, ativo \}\)/);
 assert.match(source,/await apiPostAuth\(`\/cursos\/\$\{cursoId\}\/disciplinas\/\$\{disciplinaId\}`, \{\}\)/);
 assert.match(source,/apiPostAuth\("\/disciplinas"/);assert.match(source,/apiPostAuth\("\/assuntos"/);
});
test('quatro rotas enviam Bearer, método e payload compatíveis',async()=>{
 for(const p of ['/cursos','/disciplinas','/cursos/1/disciplinas/1','/assuntos']){
  const {c,calls}=contexto();await c.apiPostAuth(p,{nome:'Teste'});
  assert.equal(calls[0].options.method,'POST');assert.equal(calls[0].options.headers.Authorization,'Bearer token-ficticio');
  assert.equal(calls[0].options.headers['Content-Type'],'application/json');assert.equal(calls[0].options.body,JSON.stringify({nome:'Teste'}));
 }
});
test('sem token não envia gravação',async()=>{
 const {c,calls}=contexto();c.localStorage.getItem=()=>null;await assert.rejects(c.apiPostAuth('/cursos',{}));assert.equal(calls.length,0);
});
