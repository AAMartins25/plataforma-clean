const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const fonte=fs.readFileSync(__dirname+'/js/admin-criar-curso-completo.js','utf8');
async function montar(){
 const elementos={},calls=[],alerts=[],confirms=[];
 let publicado=true,exclusaoBloqueada=false;
 const document={getElementById(id){return elementos[id]??={value:'',style:{},innerHTML:'',textContent:'',disabled:false,dataset:{},listeners:{},options:[{text:'Selecione'},{text:'Curso teste'}],selectedIndex:1,
  addEventListener(t,f){this.listeners[t]=f},scrollIntoView(){},querySelectorAll(){return[]},classList:{add(){},remove(){},toggle(){}},focus(){}}},querySelectorAll(){return[]},addEventListener(){}};
 const contexto={document,window:{addEventListener(){}},console:{error(){}},setTimeout(){},clearTimeout(){},URLSearchParams,
  alert:m=>alerts.push(m),confirm:m=>{confirms.push(m);return true},prompt:()=> 'Nome atualizado',escapeHtml:s=>String(s),
  TeoriaEditor:{destruir:async()=>{}},
  apiGetAuth:async url=>url==='/cursos'?[{id:1,nome:'Curso teste',ativo:true},{id:2,nome:'Inativo',ativo:false}]:url.endsWith('config-publica')?{publicado,descricao_publica:'Texto',tempos_acesso:[]}:[],
  apiPutAuth:async(url,dados)=>{calls.push(['put',url,structuredClone(dados)]);if(url.endsWith('/retirar-venda'))publicado=false;if(url.endsWith('/publicar'))publicado=true;return{id:1,nome:dados.nome,ativo:true}},
  apiDeleteAuth:async url=>{calls.push(['delete',url]);if(exclusaoBloqueada)throw Error(JSON.stringify({detail:'Este curso possui vínculos. Utilize Desativar venda.'}));return true}
 };
 vm.runInNewContext(fonte,contexto);await new Promise(setImmediate);
 Object.assign(contexto,elementos); // Propriedades nomeadas dos elementos no window do navegador.
 elementos.cursoExistenteSelect.value='1';await elementos.btnUsarCursoExistente.listeners.click();
 return{elementos,calls,alerts,confirms,contexto,bloquearExclusao:()=>exclusaoBloqueada=true};
}
test('desativar e ativar venda usam rotas e alternam botões sem excluir o curso',async()=>{
 const x=await montar(),e=x.elementos;
 assert.doesNotMatch(e.cursoExistenteSelect.innerHTML,/Inativo/);
 assert.equal(e.btnRetirarCursoVenda.style.display,'inline-block');
 await e.btnRetirarCursoVenda.listeners.click();
 assert.deepEqual(x.calls.at(-1),['put','/admin/cursos/1/retirar-venda',{}]);
 assert.equal(e.btnPublicarCurso.style.display,'inline-block');
 assert.match(x.alerts.at(-1),/direitos dos alunos/);
 await e.btnPublicarCurso.listeners.click();
 assert.deepEqual(x.calls.at(-1),['put','/admin/cursos/1/publicar',{}]);
 assert.equal(e.btnRetirarCursoVenda.style.display,'inline-block');
 assert.equal(x.calls.some(c=>c[0]==='delete'),false);
});
test('edição do nome não envia ativo e mantém a seleção',async()=>{
 const x=await montar();await x.elementos.btnEditarCurso.listeners.click();
 assert.deepEqual(x.calls.at(-1),['put','/cursos/1',{nome:'Nome atualizado'}]);
 assert.equal(x.elementos.cursoExistenteSelect.value,'1');
});
test('409 da exclusão exibe orientação e preserva o painel selecionado',async()=>{
 const x=await montar();x.bloquearExclusao();await x.elementos.btnExcluirCurso.listeners.click();
 assert.deepEqual(x.calls.at(-1),['delete','/cursos/1']);
 assert.match(x.alerts.at(-1),/Utilize Desativar venda/);
 assert.doesNotMatch(x.alerts.at(-1),/\{"detail"/);
 assert.equal(x.elementos.cursoExistenteSelect.value,'1');
 assert.equal(x.elementos.btnRetirarCursoVenda.style.display,'inline-block');
 assert.match(x.confirms.at(-1),/sem apagar seu conteúdo/);
 assert.doesNotMatch(x.confirms.at(-1),/não poderá ser desfeita/);
});
test('exclusão permitida limpa seleção e informa preservação do conteúdo',async()=>{
 const x=await montar();await x.elementos.btnExcluirCurso.listeners.click();
 assert.equal(x.elementos.cursoExistenteSelect.value,'');
 assert.match(x.elementos.msgCurso.textContent,/conteúdo foi preservado/);
 assert.equal(x.elementos.btnPublicarCurso.style.display,'none');
});
test('botão de reativação comercial tem rótulo Ativar venda',()=>{
 assert.match(fs.readFileSync(__dirname+'/admin/criar-curso-completo.html','utf8'),/id="btnPublicarCurso"[^>]*>\s*Ativar venda/);
});
