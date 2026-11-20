const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');

test('reenvio conserva chave; nova ação explícita recebe outra',async()=>{
 const armazenamento=new Map(),sessao=new Map(),chamadas=[];let sequence=0,erro=true,handler,nova;
 const botao={disabled:false};
 const elementos={formConcederAcesso:{addEventListener(_,fn){handler=fn},querySelector(){return botao}},
  concessaoAlunoId:{value:'1'},concessaoCurso:{value:'2'},concessaoDataFim:{value:'2099-01-01'},
  msgConcederAcesso:{textContent:'',style:{}}, situacaoContratacoesAdmin:{textContent:'',style:{}},
  novaOperacaoAdmin:{addEventListener(_,fn){nova=fn}}};
 const ctx={console,Date,Number,String,JSON,crypto:{randomUUID:()=>`chave-operacao-teste-${++sequence}`},
  sessionStorage:{getItem:k=>sessao.get(k)||null,setItem:(k,v)=>sessao.set(k,v)},
  document:{getElementById:id=>elementos[id]||null,addEventListener(){}},window:{},
  localStorage:{getItem:k=>armazenamento.get(k)||null,setItem:(k,v)=>armazenamento.set(k,v)},
  confirm:()=>true,AdminAcesso:{exigir:async()=>true}};
 ctx.window=ctx;vm.createContext(ctx);vm.runInContext(fs.readFileSync(__dirname+'/js/admin.js','utf8'),ctx);
 vm.runInContext('requireAdmin=async()=>true',ctx);
 vm.runInContext('apiPostAuth=async (url,payload)=>{ chamadas.push(payload); if(erro) throw Error("rede"); return {ok:true}; }',Object.assign(ctx,{chamadas,get erro(){return erro}}));
 await vm.runInContext('AdminAlunos.init()',ctx);
 await handler({preventDefault(){}});assert.equal(chamadas.length,1);
 erro=false;ctx.erro=false;await handler({preventDefault(){}});
 assert.equal(chamadas[0].chave_idempotencia,chamadas[1].chave_idempotencia);
 elementos.concessaoCurso.value='2';elementos.concessaoDataFim.value='2099-01-01';
 nova();
 await handler({preventDefault(){}});
 assert.notEqual(chamadas[1].chave_idempotencia,chamadas[2].chave_idempotencia);
});

test('impede duplo envio e conserva chave após fechar e reabrir a aba',async()=>{
 const dados=new Map(),chamadas=[]; let sequencia=0, resolver;
 function abrir(){
  let envio; const botao={disabled:false};
  const elementos={formConcederAcesso:{addEventListener(_,fn){envio=fn},querySelector(){return botao}},
   concessaoAlunoId:{value:'1'},concessaoCurso:{value:'2'},concessaoDataFim:{value:'2099-01-01'},
   msgConcederAcesso:{textContent:'',style:{}}};
  const ctx={console,Date,Number,String,JSON,crypto:{randomUUID:()=>`chave-operacao-teste-${++sequencia}`},
   localStorage:{getItem:k=>dados.get(k)||null,setItem:(k,v)=>dados.set(k,v)},
   sessionStorage:{getItem:()=>null,setItem(){}},
   document:{getElementById:id=>elementos[id]||null,addEventListener(){}},window:{},AdminAcesso:{exigir:async()=>true}};
  ctx.window=ctx;vm.createContext(ctx);vm.runInContext(fs.readFileSync(__dirname+'/js/admin.js','utf8'),ctx);
  ctx.chamadas=chamadas;ctx.aguardar=()=>new Promise(r=>resolver=r);
  vm.runInContext('requireAdmin=async()=>true; apiPostAuth=async (_,p)=>{chamadas.push(p);return aguardar()}',ctx);
  return vm.runInContext('AdminAlunos.init()',ctx).then(()=>({envio,elementos}));
 }
 const a=await abrir(),primeiro=a.envio({preventDefault(){}});
 await a.envio({preventDefault(){}});assert.equal(chamadas.length,1);
 resolver(Promise.reject(Error('rede')));await primeiro;
 const b=await abrir(),segundo=b.envio({preventDefault(){}});
 assert.equal(chamadas.length,2);assert.equal(chamadas[0].chave_idempotencia,chamadas[1].chave_idempotencia);
 resolver({ok:true});await segundo;
});

test('consulta autorizada exibe prazo e descarta resposta de seleção antiga',async()=>{
 let consulta, resolver;const saida={textContent:'',style:{}};
 const botao={disabled:false,addEventListener(_,fn){consulta=fn}};
 const elementos={formConcederAcesso:{addEventListener(){},querySelector(){return {disabled:false}}},
  consultarContratacoesAdmin:botao,situacaoContratacoesAdmin:saida,
  concessaoAlunoId:{value:'1'},concessaoCurso:{value:'2'}};
 const ctx={console,Date,Number,String,JSON,window:{},localStorage:{getItem:()=>null},
  sessionStorage:{getItem:()=>null},document:{getElementById:id=>elementos[id]||null,addEventListener(){}},
  AdminAcesso:{exigir:async()=>true}};
 ctx.window=ctx;vm.createContext(ctx);vm.runInContext(fs.readFileSync(__dirname+'/js/admin.js','utf8'),ctx);
 vm.runInContext('requireAdmin=async()=>true',ctx);
 ctx.carregar=()=>new Promise(r=>resolver=r);
 vm.runInContext('apiGetAuth=async path=>{ if(path!=="/admin/alunos/1/contratacoes-admin?curso_id=2") throw Error("rota"); return carregar(); }',ctx);
 await vm.runInContext('AdminAlunos.init()',ctx);
 const primeira=consulta();resolver([{id:7,vigente:true,data_inicio:'2026-01-01',data_fim:'2027-01-01'}]);await primeira;
 assert.match(saida.textContent,/Contrato 7: vigente/);assert.match(saida.textContent,/2027-01-01/);
 const segunda=consulta();elementos.concessaoCurso.value='3';resolver([{id:8,vigente:true}]);await segunda;
 assert.match(saida.textContent,/Seleção alterada/);assert.doesNotMatch(saida.textContent,/Contrato 8/);
});
