const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const fonte=fs.readFileSync(__dirname+'/js/admin-criar-curso-completo.js','utf8');
async function montar(){
 const elementos={},calls=[],alerts=[],confirms=[],edicoes=[];
 let publicado=true,exclusaoBloqueada=false;
 let config={publicado:false,precos_provisorios:true,descricao_publica:'Texto',tempos_acesso:[
  {meses:4,valor_cents:4,valor_provisorio_original_cents:4},
  {meses:8,valor_cents:8,valor_provisorio_original_cents:8},
  {meses:12,valor_cents:12,valor_provisorio_original_cents:12}
 ]};
 let erroAoSalvarConfig=false;
 const document={getElementById(id){return elementos[id]??={value:'',style:{},innerHTML:'',textContent:'',disabled:false,dataset:{},listeners:{},options:[{text:'Selecione'},{text:'Curso teste'}],selectedIndex:1,
  addEventListener(t,f){this.listeners[t]=f},scrollIntoView(){},querySelectorAll(){return[]},classList:{add(){},remove(){},toggle(){}},focus(){}}},querySelectorAll(){return[]},addEventListener(){}};
 const apiGetAuth=async url=>url==='/cursos'?[{id:1,nome:'Curso teste',ativo:true},{id:2,nome:'Inativo',ativo:false}]:url.endsWith('config-publica')?{...structuredClone(config),publicado}:[];
 const apiPutAuth=async(url,dados)=>{calls.push(['put',url,structuredClone(dados)]);if(url.endsWith('/retirar-venda'))publicado=false;if(url.endsWith('/publicar'))publicado=true;if(url.endsWith('/config-publica')){if(erroAoSalvarConfig)throw Error(JSON.stringify({detail:'Substitua cada valor provisório antes de confirmar.'}));config.tempos_acesso=dados.tempos_acesso.map(t=>({...t,valor_provisorio_original_cents:config.tempos_acesso.find(x=>x.meses===t.meses).valor_provisorio_original_cents}));if(dados.confirmar_precos_definitivos)config.precos_provisorios=false;}return{id:1,nome:dados.nome,ativo:true}};
 const apiDeleteAuth=async url=>{calls.push(['delete',url]);if(exclusaoBloqueada)throw Error(JSON.stringify({detail:'Este curso possui vínculos. Utilize Desativar venda.'}));return true};
 const contexto={document,window:{addEventListener(){},apiGetAuth,apiPostAuth:async()=>({}),apiPutAuth,apiDeleteAuth},console:{error(){}},setTimeout(){},clearTimeout(){},URLSearchParams,
  requestAnimationFrame:f=>f(),GestaoCursos:{encerrarEdicao(){},carregar:async()=>[],lerCampos:()=>({}),editar(id,callback){edicoes.push({id,callback})}},
  alert:m=>alerts.push(m),confirm:m=>{confirms.push(m);return true},prompt:()=> 'Nome atualizado',escapeHtml:s=>String(s),
  TeoriaEditor:{destruir:async()=>{}},
  DescricaoPublicaEditor:{carregar:async()=>{},bloquear(){},limpar(){},conteudo:()=>({descricao_publica:'Texto'})}
 };
 vm.runInNewContext(fonte,contexto);await new Promise(setImmediate);
 Object.assign(contexto,elementos); // Propriedades nomeadas dos elementos no window do navegador.
 elementos.cursoExistenteSelect.value='1';await elementos.btnUsarCursoExistente.listeners.click();
 return{elementos,calls,alerts,confirms,edicoes,contexto,config,bloquearExclusao:()=>exclusaoBloqueada=true,setErroAoSalvarConfig:v=>erroAoSalvarConfig=v};
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
test('edição delega ao gestor o curso selecionado e mantém a seleção',async()=>{
 const x=await montar();const antes=x.calls.length;await x.elementos.btnEditarCurso.listeners.click();
 assert.equal(x.edicoes.length,1);assert.equal(x.edicoes[0].id,1);
 assert.equal(typeof x.edicoes[0].callback,'function');
 assert.equal(x.calls.length,antes);
 x.edicoes[0].callback({id:1,nome:'Nome atualizado'});
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

test('confirma preços apenas após trocar os três originais e mantém referência após salvar e recarregar',async()=>{
 const x=await montar(),e=x.elementos,c=e.confirmarPrecosDefinitivos;
 assert.equal(c.disabled,true);
 await e.btnEditarConfigPublicaCurso.listeners.click();
 e.valor4Meses.value='1,00';e.valor4Meses.listeners.input();
 e.valor8Meses.value='2,00';e.valor8Meses.listeners.input();
 e.valor12Meses.value='3,00';e.valor12Meses.listeners.input();
 assert.equal(c.disabled,false);
 c.checked=true;
 e.valor8Meses.value='0,08';e.valor8Meses.listeners.input();
 assert.equal(c.checked,false);assert.equal(c.disabled,true);
 e.valor8Meses.value='2,00';e.valor8Meses.listeners.input();
 assert.equal(c.disabled,false);
 await e.btnSalvarConfigPublicaCurso.listeners.click();
 assert.equal(x.calls.at(-1)[2].confirmar_precos_definitivos,false);
 assert.equal(e.confirmarPrecosDefinitivos.disabled,false);
 assert.equal(Array.from(x.config.tempos_acesso,t=>t.valor_provisorio_original_cents).join(','),'4,8,12');
 await e.btnEditarConfigPublicaCurso.listeners.click();
 assert.equal(c.disabled,false);
 c.checked=true;
 await e.btnSalvarConfigPublicaCurso.listeners.click();
 assert.equal(x.calls.at(-1)[2].confirmar_precos_definitivos,true);
 assert.equal(x.config.precos_provisorios,false);
});
test('exibe a mensagem específica de validação de preços do backend',async()=>{
 const x=await montar(),e=x.elementos;
 await e.btnEditarConfigPublicaCurso.listeners.click();
 e.valor4Meses.value='1,00';e.valor4Meses.listeners.input();
 e.valor8Meses.value='2,00';e.valor8Meses.listeners.input();
 e.valor12Meses.value='3,00';e.valor12Meses.listeners.input();
 e.confirmarPrecosDefinitivos.checked=true;x.setErroAoSalvarConfig(true);
 await e.btnSalvarConfigPublicaCurso.listeners.click();
 assert.equal(e.msgConfigPublicaCurso.textContent,'Substitua cada valor provisório antes de confirmar.');
});
