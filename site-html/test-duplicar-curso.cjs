const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/js/admin-criar-curso-completo.js','utf8');
const part=source.slice(source.indexOf('    btnDuplicarCurso.addEventListener'),source.indexOf('    btnExcluirCurso.addEventListener'));
async function run(falha,lista){let handler;const msg={};let calls=0;
 const sandbox={btnDuplicarCurso:{addEventListener(_,fn){handler=fn}},cursoExistenteSelect:{value:'1',options:[{text:'Curso'}],selectedIndex:0},prompt:()=> 'Cópia',confirm:()=>true,alert(){},console:{error(){}},msgCurso:msg,apiPostAuth:async()=>{calls++;if(falha)throw Error(falha);return {novo_curso_id:2,novo_curso_nome:'Cópia'}},carregarCursosExistentes:async()=>{if(lista)throw Error('lista');}};
 msg.style={};vm.createContext(sandbox);vm.runInContext(part,sandbox);await handler();return {msg:msg.textContent,calls};}
(async()=>{assert.match((await run()).msg,/sucesso/);assert.match((await run('{"detail":"Já existe um curso com este nome."}')).msg,/Já existe/);assert.match((await run('{"detail":"Origem não encontrada"}')).msg,/Origem não encontrada/);const r=await run(null,true);assert.match(r.msg,/sucesso.*Não foi possível atualizar/);assert.equal(r.calls,1);console.log('Duplicação frontend: sucesso, erro real, nome repetido e falha após cópia OK');})().catch(e=>{console.error(e);process.exitCode=1});
