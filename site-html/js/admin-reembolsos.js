(function () {
  const lista = document.getElementById("listaReembolsos");
  let ocupado = false;
  let autorizado = false;
  const escape = valor => String(valor ?? "-").replace(/[&<>"']/g,
    c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[c]));
  const moeda = cents => (Number(cents) / 100).toLocaleString("pt-BR", {style:"currency", currency:"BRL"});

  async function executarOperacao(acao) {
    if (ocupado || !autorizado) return;
    ocupado = true;
    lista.querySelectorAll("button").forEach(b => { b.disabled = true; });
    try {
      const resposta = await acao();
      alert(resposta.message || "Operação concluída.");
      await carregarReembolsos();
    } catch (err) {
      alert("Não foi possível confirmar o resultado. Confira a listagem antes de tentar novamente. " + err.message);
      // Uma resposta perdida pode ocorrer após o commit; reler, sem repetir a escrita.
      await carregarReembolsos();
    } finally {
      ocupado = false;
      lista.querySelectorAll("button").forEach(b => { b.disabled = false; });
    }
  }

  function controlesPix(r) {
    if (r.status !== "REFUND_IN_PROCESS") return "";
    if (!r.reembolso_id) return `
      <form onsubmit="registrarPixManual(event, ${Number(r.pagamento_id)}); return false;" style="margin-top:12px;">
        <p>Registro de transferência já realizada. Este formulário não transfere dinheiro. Registre somente após realizar a transferência externa. O registro ainda não confirma a devolução.</p>
        <label>Valor devolvido (R$)
          <input name="valor" required inputmode="decimal" value="${(Number(r.valor_cents) / 100).toFixed(2).replace('.', ',')}" />
        </label>
        <label>Referência do comprovante
          <input name="comprovante" required maxlength="1000" />
        </label>
        <button class="btn" type="submit">Registrar Pix manual</button>
      </form>`;
    if (r.reembolso_metodo === "PIX_MANUAL" && r.reembolso_status === "PENDENTE") return `
      <form onsubmit="confirmarPixManual(event, ${Number(r.reembolso_id)}); return false;" style="margin-top:12px;">
        <p>A confirmação poderá encerrar o acesso correspondente a esta compra. Outros direitos de acesso válidos serão preservados.</p>
        <label><input name="extrato" type="checkbox" required /> Conferi o extrato e confirmei a efetiva devolução.</label>
        <button class="btn" type="submit">Confirmar devolução</button>
      </form>`;
    return "<p>Operação já registrada. Confira o status do reembolso antes de prosseguir.</p>";
  }

  window.registrarPixManual = async function(event, pagamentoId) {
    event.preventDefault();
    const form = event.target;
    const valor = form.elements.valor.value.trim();
    const referencia = form.elements.comprovante.value.trim();
    if (!/^\d+(?:[,.]\d{1,2})?$/.test(valor) || !referencia) {
      alert("Informe um valor válido e a referência do comprovante."); return;
    }
    const [inteiro, decimal = ""] = valor.replace(',', '.').split('.');
    const cents = Number(inteiro) * 100 + Number(decimal.padEnd(2, '0'));
    if (!Number.isSafeInteger(cents) || cents <= 0) { alert("Informe um valor válido."); return; }
    if (!confirm("A transferência externa já foi realizada para esta transação?")) return;
    await executarOperacao(() => apiPostAuth(`/admin/reembolsos/${pagamentoId}/pix-manual`,
      {valor_cents:cents, referencia_comprovante:referencia}));
  };

  window.confirmarPixManual = async function(event, reembolsoId) {
    event.preventDefault();
    if (!event.target.elements.extrato.checked) { alert("Confirme a conferência do extrato."); return; }
    if (!confirm("Confirme somente após conferir a devolução efetiva no extrato. Esta operação poderá encerrar o acesso correspondente à compra, preservando outros direitos válidos. Confirmar devolução?")) return;
    await executarOperacao(() => apiPostAuth(`/admin/reembolsos/${reembolsoId}/pix-manual/confirmar?confirmacao_extrato=true`, {}));
  };

  function formatarData(dataISO) {
    if (!dataISO) return "-";
    // Os timestamps sem fuso retornados pelo backend representam UTC.
    const iso = String(dataISO);
    const data = new Date(/(?:Z|[+-]\d{2}:\d{2})$/i.test(iso) ? iso : iso + "Z");
    return Number.isNaN(data.getTime()) ? "-" : data.toLocaleString("pt-BR");
  }

  function cardReembolso(r) {
    const podeDecidir = r.status === "REFUND_REQUESTED";
    if (!Number.isSafeInteger(r.pagamento_id) || r.pagamento_id <= 0 ||
        (r.reembolso_id != null && (!Number.isSafeInteger(r.reembolso_id) || r.reembolso_id <= 0))) {
      return '<div class="assunto">Identificação inválida. Atualize a listagem antes de prosseguir.</div>';
    }

    return `
      <div class="assunto">
        <b>${escape(r.curso_nome)}</b><br/>

        <span style="opacity:.85;">
          Aluno: ${escape(r.usuario_nome)} — ${escape(r.usuario_email)}<br/>
          Pagamento ID: ${r.pagamento_id}<br/>
          Data da compra: ${formatarData(r.data_compra)}<br/>
          ${podeDecidir ? "Solicitação (última atualização)" : "Última atualização"}: ${escape(formatarData(r.data_solicitacao))}<br/>
          Status: ${escape(r.status)}<br/>
          Estado informado pelo Mercado Pago: ${escape(r.mp_status)}<br/>
          Transação Mercado Pago: ${escape(r.mp_payment_id)}<br/>
          Valor: ${escape(moeda(r.valor_cents))}<br/>
          Ocorrência: ${escape(r.ocorrencia_financeira)}
          ${r.reembolso_id ? `<br/>Reembolso ${Number(r.reembolso_id)}: ${escape(r.reembolso_status)}<br/>
            Meio: ${escape(r.reembolso_metodo)} • Valor: ${escape(moeda(r.reembolso_valor_cents))}<br/>
            Comprovante: ${escape(r.referencia_comprovante)}<br/>
            Confirmado em: ${escape(formatarData(r.confirmado_em))} • Administrador ID: ${escape(r.confirmado_por)}` : ""}
        </span>

        ${
          podeDecidir
            ? `
              <div style="margin-top:12px; display:flex; gap:10px; flex-wrap:wrap;">
                <button class="btn" onclick="aprovarReembolso(${r.pagamento_id})">
                  Aprovar reembolso
                </button>

                <button class="btn" onclick="recusarReembolso(${r.pagamento_id})">
                  Recusar reembolso
                </button>
              </div>
            `
            : ""
        }
        ${controlesPix(r)}
      </div>
    `;
  }

  async function aprovarReembolso(pagamentoId) {
    const ok = confirm(
      "Aprovar esta solicitação? A devolução financeira ainda precisará ser realizada e confirmada."
    );
    if (!ok) return;

    await executarOperacao(() => apiPostAuth(`/admin/reembolsos/${pagamentoId}/aprovar`, {}));
  }

  async function recusarReembolso(pagamentoId) {
    if (!confirm("Confirmar a recusa desta solicitação de reembolso?")) return;
    await executarOperacao(() => apiPostAuth(`/admin/reembolsos/${pagamentoId}/recusar`, {}));
  }

  async function carregarReembolsos() {
    try {
      const dados = await apiGetAuth("/admin/reembolsos");

      if (!Array.isArray(dados)) throw new Error("Resposta inválida ao consultar solicitações.");
      if (dados.length === 0) {
        lista.innerHTML = `
          <div class="assunto">
            Nenhuma solicitação de reembolso encontrada.
          </div>
        `;
        return;
      }

      const pendentes = dados.filter(
        r => r.status === "REFUND_REQUESTED"
      );

      const emProcessamento = dados.filter(
        r => r.status === "REFUND_IN_PROCESS"
      );

      const concluidos = dados.filter(
        r => r.status === "REFUNDED"
      );

      const recusados = dados.filter(
        r => r.status === "REFUND_DENIED"
      );

      const comErro = dados.filter(
        r => r.status === "REFUND_ERROR"
      );

      lista.innerHTML = `
        <div style="margin-bottom:30px;">
          <h3>Pendentes de análise</h3>
          ${
            pendentes.length === 0
              ? "<p>Nenhuma solicitação pendente.</p>"
              : pendentes.map(cardReembolso).join("")
          }
        </div>

        <div style="margin-bottom:30px;">
          <h3>Aprovados — aguardando devolução financeira</h3>
          ${
            emProcessamento.length === 0
              ? "<p>Nenhuma devolução pendente.</p>"
              : emProcessamento.map(cardReembolso).join("")
          }
        </div>

        <div style="margin-bottom:30px;">
          <h3>Reembolsos concluídos</h3>
          ${
            concluidos.length === 0
              ? "<p>Nenhum reembolso concluído.</p>"
              : concluidos.map(cardReembolso).join("")
          }
        </div>

        <div style="margin-bottom:30px;">
          <h3>Solicitações recusadas</h3>
          ${
            recusados.length === 0
              ? "<p>Nenhuma solicitação recusada.</p>"
              : recusados.map(cardReembolso).join("")
          }
        </div>

        <div>
          <h3>Reembolsos com erro</h3>
          ${
            comErro.length === 0
              ? "<p>Nenhum reembolso com erro.</p>"
              : comErro.map(cardReembolso).join("")
          }
        </div>
      `;

    } catch (err) {
      lista.innerHTML = `
        <div class="assunto">
          Erro ao carregar solicitações de reembolso.<br/>
          ${escape(err.message)}
          <button class="btn" type="button" onclick="atualizarReembolsos()">Atualizar listagem</button>
        </div>
      `;
      console.error(err);
    }
  }

  window.aprovarReembolso = aprovarReembolso;
  window.recusarReembolso = recusarReembolso;

  window.atualizarReembolsos = async function () {
    if (ocupado || !autorizado) return;
    ocupado = true;
    try { await carregarReembolsos(); } finally { ocupado = false; }
  };

  requireAdmin().then(ok => {
    autorizado = Boolean(ok);
    if (autorizado) return carregarReembolsos();
    lista.textContent = "Acesso restrito ao administrador.";
  }).catch(() => { lista.textContent = "Não foi possível validar o acesso administrativo. Recarregue a página."; });
})();