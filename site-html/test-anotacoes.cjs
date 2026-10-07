const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const page = fs.readFileSync(__dirname+'/minhas-anotacoes.html','utf8');
const helper = page.match(/function comContexto\(path\) \{[\s\S]*?\n\}/)[0];
for (const query of ['curso_id=1&demonstracao_id=1','curso_id=1&contratacao_id=2']) {
  const ctx={URLSearchParams,window:{location:{search:'?'+query}}};
  vm.createContext(ctx);vm.runInContext(helper,ctx);
  assert.equal(ctx.comContexto('/me/minhas-anotacoes'),'/me/minhas-anotacoes?'+query);
  assert.equal(ctx.comContexto('/me/anotacoes-questoes/1'),'/me/anotacoes-questoes/1?'+query);
}
const source=fs.readFileSync(__dirname+'/sprint.html','utf8').match(/<script>\s*([\s\S]*?)<\/script>/)[1].replace(/      carregarBateria\(\);/,'');
(async()=>{
 const calls=[];const field={value:'texto teste'};
 const button={dataset:{},style:{}};
 const ctx={window:{location:{search:'?bateria_id=1&demonstracao_id=1'}},URLSearchParams,console,Set,alert(){},
 document:{getElementById:id=>id.startsWith('anotacao_')?field:id.startsWith('btn_salvar_mim_')?button:null},
 apiPostAuth:async(path,body)=>{calls.push({path,body});},
 apiGetAuth:async()=>[{questao_id:1,tentativa_id:3}]};
 vm.createContext(ctx);vm.runInContext(source,ctx);
 vm.runInContext('bateriaId=1;tentativaAnotacaoId=3;',ctx);
 await ctx.salvarAnotacaoParaMim(1);
 assert.equal(calls[0].body.tentativa_id,3);assert.equal(calls[0].body.demonstracao_id,1);
 await ctx.salvarAnotacaoParaMim(1);assert.equal(calls.length,1);
 button.dataset={};await ctx.recuperarAnotacoesTentativa();assert.equal(button.dataset.bloqueado,'1');
 console.log('Anotações frontend: contextos, tentativa, bloqueio e recuperação: OK');
})().catch(e=>{console.error(e);process.exitCode=1;});
