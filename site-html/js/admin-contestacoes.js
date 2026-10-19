(function () {
  const lista = document.getElementById('listaContestacoes');
  let autorizado = false, ocupado = false, pagina = 1;
  const esc = v => String(v ?? '-').replace(/[&<>"']/g, c =>
    ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  const data = v => {
    if (!v) return '-';
    const s = String(v), d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(s) ? s : s + 'Z');
    return Number.isNaN(d.getTime()) ? '-' : d.toLocaleString('pt-BR');
  };
  const dinheiro = v => (Number(v)/100).toLocaleString('pt-BR', {style:'currency', currency:'BRL'});
  const aviso = 'O bloqueio afeta somente os direitos da compra contestada e preserva outras compras, renovações e concessões válidas.';

  function card(c) {
    if (!Number.isSafeInteger(c.id) || c.id <= 0) return '<p>Identificação inválida; atualize a consulta.</p>';
    const confirmado = !!c.devolucao_confirmada_em;
    return `<div class="assunto"><h3>${esc(c.curso)}</h3>
      <p>Aluno: ${esc(c.aluno)} — ${esc(c.email)}<br>
      Pagamento: ${esc(c.pagamento_id)} • Transação MP: ${esc(c.mp_payment_id)}<br>
      Contestação MP: ${esc(c.mp_dispute_id)} • Valor da compra: ${esc(dinheiro(c.valor_cents))}<br>
      Situação do caso: ${esc(c.status)} • Pagamento: ${esc(c.status_pagamento)} • MP: ${esc(c.mp_status)}<br>
      Motivo: ${esc(c.motivo)}<br>Aprovação da compra: ${esc(data(c.aprovado_em))}<br>
      Registro do caso na plataforma: ${esc(data(c.criada_em))}<br>
      Devolução confirmada: ${esc(data(c.devolucao_confirmada_em))} • Administrador: ${esc(c.devolucao_confirmada_por)}<br>
      Comprovante/extrato: ${esc(c.referencia_devolucao)}<br>
      Bloqueio manual: ${esc(data(c.bloqueio_executado_em))} • Administrador: ${esc(c.bloqueio_executado_por)}<br>
      Situação do acesso: <b>${esc(c.situacao_acesso)}</b></p>
      ${c.situacao_acesso === 'CONFERENCIA_NECESSARIA' ? '<p>CONFERENCIA_NECESSARIA: os vínculos ou períodos históricos não permitem um bloqueio seguro. Nenhum bloqueio presumido será executado.</p>' : ''}
      ${!confirmado ? `<form data-confirmar="${c.id}"><p>Este registro não realiza devolução nem bloqueia acesso.</p>
        <label>Referência do comprovante ou extrato <input name="referencia" required maxlength="255"></label>
        <label><input type="checkbox" name="conferido" required> Conferi no extrato a devolução integral do valor desta compra ao cartão do cliente.</label>
        <button class="btn" type="submit">Confirmar devolução</button></form>` : ''}
      ${confirmado && !c.bloqueio_executado_em ? `<p>${aviso}</p><button class="btn" data-bloquear="${c.id}"
        ${c.situacao_acesso !== 'BLOQUEIO_DISPONIVEL' ? 'disabled' : ''}>Bloquear acesso</button>` : ''}</div>`;
  }
  function pendencia(p) {
    return `<div class="assunto"><h3>CONFERENCIA_NECESSARIA</h3>
      <p>Evento preservado: ${esc(p.notificacao_id)} • Caso MP: ${esc(p.caso_mp)}<br>
      Recebido em: ${esc(data(p.recebida_em))} • Tentativas: ${esc(p.tentativas)}<br>
      Pagamentos informados pelo caso: ${esc((p.pagamentos_mp || []).join(', '))}<br>
      Motivo: ${esc(p.motivo)}</p><p>Sem bloqueio disponível. Conferir no Mercado Pago e recuperar a notificação pelo controle financeiro administrativo quando aplicável.</p></div>`;
  }
  async function carregar() {
    const r = await apiGetAuth(`/admin/contestacoes?pagina=${pagina}`);
    if (!Array.isArray(r.contestacoes)) throw new Error('Resposta de consulta inválida.');
    lista.innerHTML = `<p>Contestação ou CHARGED_BACK não bloqueiam acesso automaticamente. Confirmação financeira e bloqueio são ações separadas.</p>` +
      (r.contestacoes.length ? r.contestacoes.map(card).join('') : '<p>Nenhuma contestação registrada nesta página.</p>') +
      ((r.pendencias || []).length ? '<h2>Pendências de recebimento</h2>' + r.pendencias.map(pendencia).join('') : '') +
      `<button class="btn" data-pagina="${pagina-1}" ${pagina === 1 ? 'disabled' : ''}>Anterior</button>
       <button class="btn" data-pagina="${pagina+1}" ${!r.tem_proxima ? 'disabled' : ''}>Próxima</button>`;
  }
  async function operar(caminho, payload) {
    if (ocupado || !autorizado) return;
    ocupado = true;
    lista.querySelectorAll('button').forEach(b => {b.disabled = true;});
    try {
      const r = await apiPostAuth(caminho, payload);
      alert(r.message || 'Operação registrada.');
    } catch (err) {
      alert('Resultado não confirmado. Confira a listagem antes de tentar novamente. ' + err.message);
    }
    // Nunca repetir POST automaticamente, nem após resposta perdida.
    try {await carregar();}
    catch (_) {lista.innerHTML = '<p>Consulta indisponível. Recarregue a página para conferir o resultado antes de outra ação.</p>';}
    finally {ocupado = false;}
  }
  lista.addEventListener('submit', event => {
    const form = event.target, id = Number(form.dataset.confirmar);
    event.preventDefault();
    if (ocupado || !autorizado || !Number.isSafeInteger(id) || id <= 0) return;
    const referencia = form.elements.referencia.value.trim();
    if (!referencia || !form.elements.conferido.checked) return;
    if (!confirm('Confirma a devolução integral do valor desta compra ao cartão? Esta ação não bloqueia acesso.')) return;
    operar(`/admin/contestacoes/${id}/confirmar-devolucao`, {referencia_devolucao:referencia, confirmacao_devolucao:true});
  });
  lista.addEventListener('click', async event => {
    const b = event.target.closest('button');
    if (!b || b.disabled || ocupado || !autorizado) return;
    if (b.dataset.pagina) {
      ocupado = true; pagina = Number(b.dataset.pagina);
      try {await carregar();} catch (_) {lista.innerHTML = '<p>Falha na consulta. Recarregue a página.</p>';}
      finally {ocupado = false;}
      return;
    }
    const id = Number(b.dataset.bloquear);
    if (!Number.isSafeInteger(id) || id <= 0) return;
    if (!confirm(aviso + ' Confirma executar o bloqueio manual?')) return;
    operar(`/admin/contestacoes/${id}/bloquear-acesso?confirmacao_bloqueio=true`, {});
  });
  (async () => {
    try {
      const usuario = await apiGetAuth('/me');
      if (!usuario.is_admin) {lista.innerHTML = '<p>Acesso restrito ao administrador.</p>'; return;}
      autorizado = true; await carregar();
    } catch (_) {lista.innerHTML = '<p>Não foi possível autenticar ou consultar. Recarregue a página.</p>';}
  })();
})();
