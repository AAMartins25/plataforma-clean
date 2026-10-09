const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/js/admin-cupons.js','utf8');
async function montar({erro=false,vendedores=[{id:1,nome:'Parceiro',ativo:true}],timeout=false}={}) {
  const elementos={};
  const document={getElementById(id){return elementos[id]??={value:'',style:{display:'none'},innerHTML:'',textContent:'',disabled:false,listeners:{},addEventListener(tipo,fn){this.listeners[tipo]=fn},focus(){this.focado=true}}}};
  const cupons=[{id:1,codigo:'AB001',vendedor_id:null,ativo:false,percentual_desconto:12},{id:2,codigo:'AB002',vendedor_id:1,ativo:true,percentual_desconto:12}];
  const calls=[],alerts=[];
  let falhar=erro,resposta='0';
  const context={document,window:{},console:{error(){}},requireAdmin:async()=>true,escapeHtml:s=>String(s).replaceAll('<','&lt;'),
    confirm:()=>true,prompt:()=>resposta,alert:s=>alerts.push(s),setTimeout:timeout?(fn)=>{queueMicrotask(fn);return 1}:setTimeout,clearTimeout,
    apiGetAuth:async url=>{calls.push(['get',url]);if(timeout)return new Promise(()=>{});if(falhar)throw Error('GET -> 500\n{"detail":"Falha controlada"}');return structuredClone(url.endsWith('vendedores')?vendedores:cupons)},
    apiPostAuth:async(url,dados)=>{calls.push(['post',url,dados]);cupons.push({id:3,codigo:'AB003',vendedor_id:null,ativo:true,percentual_desconto:12})},
    apiPutAuth:async(url,dados)=>{calls.push(['put',url,dados]);const c=cupons.find(c=>c.id===Number(url.split('/')[3]));if(url.includes('/status'))c.ativo=url.endsWith('true');else c.vendedor_id=dados.vendedor_id}
  };
  await vm.runInNewContext(source,context);
  return {elementos,context,calls,alerts,setFalha:v=>falhar=v,setResposta:v=>resposta=v};
}
test('listagens separam vínculo, preservam inativos e pesquisa normaliza todos',async()=>{
 const x=await montar(),e=x.elementos;
 assert.match(e.listaCuponsDisponiveis.innerHTML,/AB001/);assert.doesNotMatch(e.listaCuponsDisponiveis.innerHTML,/AB002/);
 assert.match(e.listaCuponsAtribuidos.innerHTML,/AB002/);
 e.buscaCupom.value=' a-b00!2x';e.buscaCupom.listeners.input();assert.equal(e.buscaCupom.value,'AB002');assert.match(e.listaResultadoBuscaCupom.innerHTML,/AB002/);
 e.buscaCupom.value='zz';e.buscaCupom.listeners.input();assert.match(e.listaResultadoBuscaCupom.innerHTML,/Nenhum/);
 e.btnLocalizarCupom.listeners.click();assert.equal(e.buscaCupom.focado,true);
});
test('falha encerra carregamento nas duas listas e não informa resultado vazio',async()=>{
 const x=await montar({erro:true}),e=x.elementos;
 assert.match(e.listaCuponsDisponiveis.innerHTML,/Falha controlada/);assert.match(e.listaCuponsAtribuidos.innerHTML,/Falha controlada/);
 e.buscaCupom.value='AB';e.buscaCupom.listeners.input();assert.match(e.listaResultadoBuscaCupom.innerHTML,/Não foi possível/);assert.doesNotMatch(e.listaResultadoBuscaCupom.innerHTML,/Nenhum/);
 x.setFalha(false);e.btnLocalizarCupom.listeners.click();await new Promise(setImmediate);assert.match(e.listaCuponsAtribuidos.innerHTML,/AB002/);
});
test('requisição pendente tem prazo e termina em erro',async()=>{
 const {elementos:e}=await montar({timeout:true});assert.match(e.listaCuponsAtribuidos.innerHTML,/demorou demais/);
});
test('geração valida limites, recarrega listas e pesquisa',async()=>{
 const x=await montar(),e=x.elementos;
 for(const v of ['0','101','1.5','abc']){e.quantidadeCupons.value=v;await e.btnGerarCupons.listeners.click()}
 assert.equal(x.calls.filter(c=>c[0]==='post').length,0);
 e.buscaCupom.value='AB003';e.buscaCupom.listeners.input();
 e.quantidadeCupons.value='1';await e.btnGerarCupons.listeners.click();assert.match(e.msgGerarCupons.textContent,/sucesso/);assert.equal(e.btnGerarCupons.disabled,false);assert.match(e.listaResultadoBuscaCupom.innerHTML,/AB003/);
});
test('remoção funciona sem vendedores ativos e atualiza pesquisa',async()=>{
 const x=await montar({vendedores:[{id:1,nome:'Inativo',ativo:false}]}),e=x.elementos;
 e.buscaCupom.value='AB002';e.buscaCupom.listeners.input();await x.context.window.gerenciarVinculoCupom(2);
 assert.match(e.listaCuponsDisponiveis.innerHTML,/AB002/);assert.match(e.listaResultadoBuscaCupom.innerHTML,/Sem vínculo/);
});
test('atribuição e status recarregam todas as representações',async()=>{
 const x=await montar(),e=x.elementos;x.setResposta('1');await x.context.window.gerenciarVinculoCupom(1);
 assert.match(e.listaCuponsAtribuidos.innerHTML,/AB001/);
 e.buscaCupom.value='AB001';e.buscaCupom.listeners.input();await x.context.window.alterarStatusCupom(1,true);assert.match(e.listaResultadoBuscaCupom.innerHTML,/Desativar/);
});
test('erro de mutação mostra detalhe real e libera botão',async()=>{
 const x=await montar(),e=x.elementos;x.context.apiPostAuth=async()=>{throw Error('POST -> 409\n{"detail":"Códigos indisponíveis"}')};
 e.quantidadeCupons.value='1';await e.btnGerarCupons.listeners.click();assert.match(e.msgGerarCupons.textContent,/Códigos indisponíveis/);assert.equal(e.btnGerarCupons.disabled,false);
});
test('listas vazias distinguem disponibilidade e atribuição',async()=>{
 const x=await montar();x.context.apiGetAuth=async()=>[];
 await x.context.window.alterarStatusCupom(1,true);
 assert.match(x.elementos.listaCuponsDisponiveis.innerHTML,/Nenhum/);assert.match(x.elementos.listaCuponsAtribuidos.innerHTML,/Nenhum/);
});
test('troca de vendedor e erro de vínculo são apresentados',async()=>{
 const x=await montar({vendedores:[{id:1,nome:'Primeiro',ativo:true},{id:2,nome:'Segundo',ativo:true}]});
 x.setResposta('2');await x.context.window.gerenciarVinculoCupom(2);assert.match(x.elementos.listaCuponsAtribuidos.innerHTML,/Segundo/);
 x.context.apiPutAuth=async()=>{throw Error('PUT -> 400\n{"detail":"Vendedor inativo"}')};await x.context.window.gerenciarVinculoCupom(2);assert.match(x.alerts.at(-1),/Vendedor inativo/);
});
test('resposta incompatível termina carregamento em erro',async()=>{
 const x=await montar();x.context.apiGetAuth=async()=>({});await x.context.window.alterarStatusCupom(1,true);
 assert.match(x.elementos.listaCuponsAtribuidos.innerHTML,/Resposta inválida/);
});
