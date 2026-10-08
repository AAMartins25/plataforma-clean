const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
(async()=>{
for(const file of ['dashboard.html','desempenho-expirado.html']){
 const html=fs.readFileSync(__dirname+'/'+file,'utf8');
 const source=html.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/    carregar(?:Dashboard|DesempenhoExpirado)\(\);/g,'');
 const elements={};const sandbox={URLSearchParams,console,localStorage:{getItem(){return 'token'}},window:{location:{search:'?curso_id=1&demonstracao_id=2',replace(url){this.href=url}}},document:{getElementById(id){return elements[id]??={}},createElement(){return {style:{},appendChild(){},addEventListener(){}}}},Date};
 vm.createContext(sandbox);vm.runInContext(source,sandbox);
 vm.runInContext("desempenhoAtual={disciplinas:[{id:1,assuntos:[{id:1,baterias:[{status_aluno:'FEITA',percentual_acerto:80},{status_aluno:'FEITA',percentual_acerto:20}]}]}]}",sandbox);
 assert.equal(await sandbox.calcularNotaAssunto(1),5);
 vm.runInContext("desempenhoAtual.disciplinas[0].assuntos[0].baterias[1].status_aluno=null",sandbox);
 assert.equal(await sandbox.calcularNotaAssunto(1),null);
 assert.equal(sandbox.contextoDesempenho(),'demonstracao_id=2');
 if(file==='dashboard.html'){sandbox.voltarParaCurso();assert.match(sandbox.window.location.href,/demonstracao_id=2/);assert.match(source,/Math.ceil\([\s\S]*?totalAssuntosDisciplina \* 0.5/);}
 else{sandbox.voltarCursoExpirado();assert.match(sandbox.window.location.href,/demonstracao_id=2/);}
}
console.log('Desempenho: notas, ausência de conclusão, critérios e retorno com contexto OK');
})().catch(e=>{console.error(e);process.exitCode=1});
