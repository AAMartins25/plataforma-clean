const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const codigo = fs.readFileSync(__dirname+'/js/admin-reembolsos.js','utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));
async function tela(dados, autorizado=true) {
  const lista={innerHTML:'',querySelectorAll:()=>[]};
  const chamadas=[]; const alertas=[];
  const contexto={document:{getElementById:()=>lista},window:{},console,
    requireAdmin:async()=>autorizado,confirm:()=>true,alert:m=>alertas.push(m),
    apiGetAuth:async url=>{chamadas.push(['GET',url]);return dados;},
    apiPostAuth:async(url,payload)=>{chamadas.push(['POST',url,payload]);return {message:'Registrado'};}};
  vm.runInNewContext(codigo,contexto); await flush();
  return {lista,chamadas,alertas,contexto};
}
const base={pagamento_id:20,curso_nome:'Curso',usuario_nome:'Aluno',usuario_email:'teste@local',valor_cents:4990};
test('navegação Comercial contém apenas um link para reembolsos',()=>{
 const html=fs.readFileSync(__dirname+'/admin/index.html','utf8');
 assert.equal((html.match(/href="reembolsos.html"/g)||[]).length,1);
 assert.ok(html.indexOf('href="reembolsos.html"')>html.indexOf('href="cupons.html"'));
});
test('sem autorização não carrega solicitações',async()=>{
 const t=await tela([],false);assert.equal(t.chamadas.length,0);
});
test('solicitação permite decisão; não registra Pix antes da aprovação',async()=>{
 const t=await tela([{...base,status:'REFUND_REQUESTED'}]);
 assert.match(t.lista.innerHTML,/Aprovar reembolso/);assert.match(t.lista.innerHTML,/Recusar reembolso/);
 assert.doesNotMatch(t.lista.innerHTML,/Registrar Pix manual/);
 await t.contexto.window.aprovarReembolso(20);
 assert.ok(t.chamadas.some(c=>c[1]==='/admin/reembolsos/20/aprovar'));
});
test('aprovação permite registro; valores e texto são protegidos',async()=>{
 const t=await tela([{...base,status:'REFUND_IN_PROCESS',curso_nome:'<img onerror=alert(1)>'}]);
 assert.match(t.lista.innerHTML,/Registrar Pix manual/);assert.doesNotMatch(t.lista.innerHTML,/<img/);
 const event={preventDefault(){},target:{elements:{valor:{value:'49,90'},comprovante:{value:' recibo '}}}};
 await t.contexto.window.registrarPixManual(event,20);
 const c=t.chamadas.find(c=>c[0]==='POST');assert.equal(c[1],'/admin/reembolsos/20/pix-manual');
 assert.equal(c[2].valor_cents,4990);assert.equal(c[2].referencia_comprovante,'recibo');
 assert.equal(c[2].confirmado_por,undefined);
});
test('registro pendente só oferece confirmação após conferência',async()=>{
 const t=await tela([{...base,status:'REFUND_IN_PROCESS',reembolso_id:33,reembolso_status:'PENDENTE',reembolso_metodo:'PIX_MANUAL'}]);
 assert.match(t.lista.innerHTML,/Confirmar devolução/);assert.doesNotMatch(t.lista.innerHTML,/Registrar Pix manual/);
 const event={preventDefault(){},target:{elements:{extrato:{checked:false}}}};
 await t.contexto.window.confirmarPixManual(event,33);assert.equal(t.chamadas.filter(c=>c[0]==='POST').length,0);
 event.target.elements.extrato.checked=true;await t.contexto.window.confirmarPixManual(event,33);
 assert.ok(t.chamadas.some(c=>c[1]==='/admin/reembolsos/33/pix-manual/confirmar?confirmacao_extrato=true'));
});
test('reembolso concluído não oferece ação financeira',async()=>{
 const t=await tela([{...base,status:'REFUNDED',reembolso_id:33,reembolso_status:'CONFIRMADO',confirmado_por:2,mp_status:'APPROVED'}]);
 assert.doesNotMatch(t.lista.innerHTML,/Registrar Pix manual|Confirmar devolução/);
 assert.match(t.lista.innerHTML,/Administrador ID: 2/);assert.match(t.lista.innerHTML,/Mercado Pago: APPROVED/);
});
test('duplo clique envia uma operação por vez',async()=>{
 const t=await tela([{...base,status:'REFUND_IN_PROCESS'}]);let liberar;
 t.contexto.apiPostAuth=async(url,payload)=>{t.chamadas.push(['POST',url,payload]);await new Promise(r=>{liberar=r;});return {};};
 const e={preventDefault(){},target:{elements:{valor:{value:'49.90'},comprovante:{value:'recibo'}}}};
 const primeira=t.contexto.window.registrarPixManual(e,20);
 await t.contexto.window.registrarPixManual(e,20);assert.equal(t.chamadas.filter(c=>c[0]==='POST').length,1);
 liberar();await primeira;
});
test('erros de operação são apresentados e relidos sem repetir escrita',async()=>{
 const t=await tela([{...base,status:'REFUND_REQUESTED'}]);
 t.contexto.apiPostAuth=async()=>{throw new Error('Já processado');};
 await t.contexto.window.recusarReembolso(20);assert.match(t.alertas[0],/Já processado/);assert.equal(t.chamadas.filter(c=>c[0]==='GET').length,2);
});

test('aviso explica preservação de direitos antes da confirmação financeira',async()=>{
 const t=await tela([{...base,status:'REFUND_IN_PROCESS',reembolso_id:33,reembolso_status:'PENDENTE',reembolso_metodo:'PIX_MANUAL'}]);
 assert.match(t.lista.innerHTML,/poderá encerrar o acesso/);
 assert.match(t.lista.innerHTML,/Outros direitos de acesso válidos serão preservados/);
 let aviso; t.contexto.confirm=m=>{aviso=m;return false;};
 await t.contexto.window.confirmarPixManual({preventDefault(){},target:{elements:{extrato:{checked:true}}}},33);
 assert.match(aviso,/preservando outros direitos válidos/);
 assert.equal(t.chamadas.filter(c=>c[0]==='POST').length,0);
});
test('data após análise é identificada como atualização, sem inventar data de solicitação',async()=>{
 const t=await tela([{...base,status:'REFUND_IN_PROCESS',data_compra:'2026-10-01T12:00:00',data_solicitacao:'2026-10-19T15:30:00'}]);
 assert.match(t.lista.innerHTML,/Última atualização:/);assert.doesNotMatch(t.lista.innerHTML,/Solicitação:/);
 assert.doesNotMatch(t.lista.innerHTML,/Invalid Date/);
});
test('todos os campos textuais externos são escapados',async()=>{
 const malicioso='<img src=x onerror=alert(1)>';
 const t=await tela([{...base,status:'REFUNDED',usuario_nome:malicioso,usuario_email:malicioso,mp_payment_id:malicioso,
  ocorrencia_financeira:malicioso,reembolso_id:33,referencia_comprovante:malicioso,confirmado_por:malicioso}]);
 assert.doesNotMatch(t.lista.innerHTML,/<img/);assert.match(t.lista.innerHTML,/&lt;img/);
});
test('identificador inválido não gera botões nem código inline',async()=>{
 const t=await tela([{...base,status:'REFUND_REQUESTED',pagamento_id:'20);alert(1)'}]);
 assert.match(t.lista.innerHTML,/Identificação inválida/);assert.doesNotMatch(t.lista.innerHTML,/onclick|alert\(1\)/);
});
test('resposta perdida após commit relê estado concluído sem repetir POST',async()=>{
 const t=await tela([{...base,status:'REFUND_IN_PROCESS'}]);let posts=0;
 t.contexto.apiPostAuth=async()=>{posts++;throw new Error('Conexão encerrada');};
 t.contexto.apiGetAuth=async()=>[{...base,status:'REFUNDED',reembolso_id:33,reembolso_status:'CONFIRMADO'}];
 await t.contexto.window.registrarPixManual({preventDefault(){},target:{elements:{valor:{value:'49,90'},comprovante:{value:'recibo'}}}},20);
 assert.equal(posts,1);assert.doesNotMatch(t.lista.innerHTML,/Registrar Pix manual|Confirmar devolução/);
});
test('falha ao reler remove ações financeiras até atualização manual bem sucedida',async()=>{
 const t=await tela([{...base,status:'REFUND_REQUESTED'}]);let posts=0;
 t.contexto.apiPostAuth=async()=>{posts++;throw new Error('Falha');};
 t.contexto.apiGetAuth=async()=>{throw new Error('<script>erro</script>');};
 await t.contexto.window.aprovarReembolso(20);
 assert.equal(posts,1);assert.match(t.lista.innerHTML,/Atualizar listagem/);
 assert.doesNotMatch(t.lista.innerHTML,/Aprovar reembolso|Registrar Pix manual|<script>/);
 t.contexto.apiGetAuth=async()=>[{...base,status:'REFUND_IN_PROCESS'}];
 await t.contexto.window.atualizarReembolsos();assert.match(t.lista.innerHTML,/Registrar Pix manual/);
 assert.equal(posts,1);
});
