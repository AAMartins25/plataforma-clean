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

// O título deve estar disponível mesmo com /me e as notas ainda pendentes.
for (const contexto of ['contratacao_id=10', 'demonstracao_id=20']) {
 for (const [id, nome] of [[1, 'Direito Constitucional'], [2, 'Outro curso']]) {
  const elements = {}, pedidos = [], pendentes = [];
  const elemento = id => elements[id] ??= {
   textContent: '', innerHTML: '',
   get innerText() { return this.textContent; },
   set innerText(value) { this.textContent = value; }
  };
  const sandbox = {
   URLSearchParams, Date, console,
   localStorage: {getItem() { return 'token'; }},
   window: {location: {search: `?curso_id=${id}&curso_nome=${encodeURIComponent(nome)}&${contexto}`}},
   document: {
    getElementById: elemento,
    querySelector() { return elemento('main'); },
    createElement() { return {appendChild() {}}; },
    body: {appendChild() {}}
   },
   Sessao: {
    snapshot() { return 'sessao'; }, mesma() { return true; },
    fetch(url) {
     pedidos.push(url);
     return new Promise(resolve => pendentes.push(dados => resolve({ok: true, json: async () => dados})));
    }
   }
  };
  vm.createContext(sandbox);
  const source = fs.readFileSync(__dirname + '/dashboard.html', 'utf8')
   .match(/<script>([\s\S]*?)<\/script>/)[1]
   .replace('    carregarDashboard();', '    window.carga = carregarDashboard();');
  vm.runInContext(source, sandbox);
  assert.equal(elemento('titulo_curso_dashboard').textContent, nome);
  assert.equal(pedidos.length, 1);
  pendentes.shift()({nome: 'Aluno correto'});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(elemento('titulo_curso_dashboard').textContent, nome);
  assert.equal(pedidos.length, 2);
  assert.ok(pedidos[1].endsWith(`/me/cursos/${id}/desempenho?${contexto}`));
  pendentes.shift()({curso_id: id, nome_curso: nome + ' atualizado', disciplinas: []});
  await sandbox.window.carga;
  assert.equal(elemento('titulo_curso_dashboard').textContent, nome + ' atualizado');
  assert.equal(pedidos.length, 2);
  assert.match(elemento('lista_disciplinas').innerHTML, /Nenhuma disciplina encontrada/);
 }
}
console.log('Desempenho: nome imediato, confirmação pelo servidor, cursos e contextos isolados, sem consultas extras OK');
})().catch(e=>{console.error(e);process.exitCode=1});
