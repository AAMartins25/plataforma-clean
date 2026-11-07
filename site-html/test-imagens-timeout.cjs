// Testes direcionados de prazo/cancelamento: relógio virtual, sem navegador/rede.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const codigo=fs.readFileSync(path.join(__dirname,'js/editor-teoria-imagens.js'),'utf8');
function ambiente(){
 let agora=0,comits=0;const timers=new Map();let id=0;
 const window={TeoriaImagens:{MAX_IMAGENS:20,documento:()=>({content:{querySelectorAll:()=>[]}})}};
 vm.runInNewContext(codigo,{window,AbortController,DOMException,Date:{now:()=>agora},
  setTimeout:fn=>{timers.set(++id,fn);return id;},clearTimeout:id=>timers.delete(id)});
 const editor={state:'ready',isReadOnly:false,html:'<p>Original</p>',getData(){return this.html;},
  enableReadOnlyMode(){this.isReadOnly=true;},disableReadOnlyMode(){this.isReadOnly=false;},
  data:{parse:html=>({html})},model:{document:{selection:{},getRoot:()=>({})},
   createSelection:()=>({getRanges:()=>[]}),createRangeIn:()=>({getItems:()=>[]}),
   change:fn=>fn({setSelection(){}}),insertContent:f=>{editor.html=f.html;comits++;}}};
 const estado={pendente:false,mensagem:{textContent:''}};
 window.TeoriaImagensEditor.estados.set(editor,estado);
 return {api:window.TeoriaImagensEditor,editor,estado,comits:()=>comits,
  expirar(){agora=60000;for(const fn of [...timers.values()])fn();},avancar:ms=>{agora=ms;}};
}
for(const etapa of ['arrayBuffer','processamento','upload'])test(`timeout libera ${etapa} pendente e ignora resposta tardia`,async()=>{
 const a=ambiente();let concluir;
 const pendente=new Promise(resolve=>{concluir=resolve;});
 const file={arrayBuffer:()=>pendente};
 const tarefa=a.api.transacao(a.editor,async signal=>{
  if(etapa==='arrayBuffer')await file.arrayBuffer();else await pendente;
  return {html:'<p>Resposta tardia</p>'};
 });
 assert.equal(a.editor.isReadOnly,true);a.expirar();
 await assert.rejects(tarefa,/tempo excedido/);
 assert.equal(a.editor.isReadOnly,false);assert.equal(a.estado.pendente,false);
 assert.equal(a.editor.html,'<p>Original</p>');
 await a.api.transacao(a.editor,async()=>({html:'<p>Operação seguinte</p>'}));
 concluir();await new Promise(resolve=>setImmediate(resolve));
 assert.equal(a.editor.html,'<p>Operação seguinte</p>');assert.equal(a.comits(),1);
});
test('cancelamento libera imediatamente mesmo sem resposta do trabalho',async()=>{
 const a=ambiente();const p=a.api.transacao(a.editor,()=>new Promise(()=>{}));
 a.api.cancelar(a.editor);await assert.rejects(p,/cancelada/);
 assert.equal(a.editor.isReadOnly,false);assert.equal(a.comits(),0);
});
test('rejeição tardia não gera unhandledRejection nem bloqueia operação seguinte',async()=>{
 const a=ambiente();let falhar;const p=a.api.transacao(a.editor,()=>new Promise((_,r)=>{falhar=r;}));
 a.expirar();await assert.rejects(p);falhar(new Error('Falha tardia'));
 await new Promise(r=>setImmediate(r));assert.equal(a.editor.isReadOnly,false);
});
test('processamento síncrono que excede prazo não altera conteúdo ao retornar',async()=>{
 const a=ambiente();a.editor.data.parse=html=>{a.avancar(61000);return {html};};
 await assert.rejects(a.api.transacao(a.editor,async()=>({html:'<p>Novo</p>'})),/tempo excedido/);
 assert.equal(a.editor.html,'<p>Original</p>');assert.equal(a.editor.isReadOnly,false);
});
test('API não inicia upload com signal já abortado',async()=>{
 let chamadas=0;const window={fetch:()=>{chamadas++;}};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'js/teoria-imagens.js'),'utf8'),{window});
 const controller=new AbortController();controller.abort();
 await assert.rejects(window.TeoriaImagens.api('/admin/imagens/arquivos',{},controller.signal));
 assert.equal(chamadas,0);
});
