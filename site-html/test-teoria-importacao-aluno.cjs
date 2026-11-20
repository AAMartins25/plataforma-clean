const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

const teoria=fs.readFileSync(__dirname+'/teoria.html','utf8');
const app=fs.readFileSync(__dirname+'/js/app.js','utf8');

test('renderizador mostra HTML atual e mantém texto puro legado',()=>{
 const inicio=teoria.indexOf('    function esc(s)');
 const fim=teoria.indexOf('    function getToken()',inicio);
 const contexto={window:{TeoriaImagens:{paraLeitura:html=>html}}};
 vm.runInNewContext(teoria.slice(inicio,fim)+';globalThis.render=renderizarMaterialTeoria;',contexto);
 assert.match(contexto.render({conteudo:'<p><strong>Resumo</strong></p>',conteudo_formato:'html_v1'}),/<strong>Resumo<\/strong>/);
 assert.equal(contexto.render({texto:'Resumo antigo'}),'<pre style="white-space:pre-wrap">Resumo antigo</pre>');
 assert.match(teoria, /\$\{renderizarMaterialTeoria\(m\)\}/);
});

test('retorno usa assuntos próprios e só cai na rota legada plural em 404',async()=>{
 const inicio=app.indexOf('async function carregarAssuntosDaDisciplina(');
 const fim=app.indexOf('async function pageAssuntos()',inicio);
 const chamadas=[];
 let erroProprio=null;
 const contexto={
  apiGetAuth:async url=>{chamadas.push(url);if(erroProprio)throw erroProprio;return [{id:4,nome:'Assunto próprio'}]},
  apiGet:async url=>{chamadas.push(url);return [{id:5,nome:'Assunto legado'}]}
 };
 vm.runInNewContext(app.slice(inicio,fim)+';globalThis.carregar=carregarAssuntosDaDisciplina;',contexto);
 let assuntos=await contexto.carregar(10,null,22);
 assert.equal(assuntos[0].id,4);
 assert.deepEqual(chamadas,['/disciplinas-proprias/10/assuntos-proprios?demonstracao_id=22']);
 chamadas.length=0;erroProprio=Object.assign(new Error('Not Found'),{status:404});
 assuntos=await contexto.carregar(11,null,null);
 assert.equal(assuntos[0].id,5);
 assert.deepEqual(chamadas,['/disciplinas-proprias/11/assuntos-proprios','/disciplinas/11/assuntos']);
 assert.ok(!chamadas.some(url=>/\/assunto$/.test(url)));
 chamadas.length=0;erroProprio=Object.assign(new Error('Forbidden'),{status:403});
 await assert.rejects(contexto.carregar(12,null,null),/Forbidden/);
 assert.deepEqual(chamadas,['/disciplinas-proprias/12/assuntos-proprios']);
});
