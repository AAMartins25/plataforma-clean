const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/sprint.html','utf8').match(/<script>\s*([\s\S]*?)<\/script>/)[1].replace(/      carregarBateria\(\);/,'');
async function run(revisao) {
  const calls=[]; const saved=[];
  const win={location:{search:`?bateria_id=3&demonstracao_id=1&pasta_id=1${revisao?'&revisao_id=7':''}`}};
  const sandbox={window:win,URLSearchParams,console,alert:()=>{},history:{back(){}},
    document:{getElementById:()=>({scrollIntoView(){}}),querySelectorAll:()=>[]},
    localStorage:{getItem:()=>null,setItem:(...a)=>saved.push(a)},
    apiPostAuth:async(path,body)=>{calls.push({path,body});return {id:12,feedback:[{questao_id:1,gabarito:'C'}]}}};
  vm.createContext(sandbox);vm.runInContext(source,sandbox);
  vm.runInContext("bateriaId=3; questoes=Array.from({length:10},(_,i)=>({id:i+1,ordem:i+1})); respostasAluno=Object.fromEntries(questoes.map(q=>[q.id,'C'])); questoes.forEach(q=>respostasConfirmadas.add(q.id));",sandbox);
  await sandbox.concluirBateriaAluno('depois');
  return {calls,saved,href:win.location.href};
}
(async()=>{
 const normal=await run(false), review=await run(true);
 assert.equal(normal.calls[0].path,'/baterias/concluir');
 assert.equal(normal.calls[0].body.respostas.length,10);
 assert.equal(review.calls[0].body.respostas.length,10);
 assert.equal(review.calls[0].path,'/me/revisoes/7/baterias/3/respostas?demonstracao_id=1');
 assert.equal(review.saved.length,0);
 assert.match(review.href,/teoria.html\?/);assert.match(review.href,/revisao_id=7/);assert.match(review.href,/demonstracao_id=1/);
 console.log('Revisões frontend: rota isolada, POST normal preservado, retorno e contexto: OK');
})().catch(e=>{console.error(e);process.exitCode=1;});
