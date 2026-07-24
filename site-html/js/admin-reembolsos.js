(function () {
  const lista = document.getElementById("listaReembolsos");

  function formatarData(dataISO) {
    if (!dataISO) return "-";
    const data = new Date(dataISO);
    return data.toLocaleDateString("pt-BR");
  }

  function cardReembolso(r) {
    const podeDecidir = r.status === "REFUND_REQUESTED";

    return `
      <div class="assunto">
        <b>${r.curso_nome}</b><br/>

        <span style="opacity:.85;">
          Aluno: ${r.usuario_nome} — ${r.usuario_email}<br/>
          Pagamento ID: ${r.pagamento_id}<br/>
          Data da compra: ${formatarData(r.data_compra)}<br/>
          Solicitação: ${formatarData(r.data_solicitacao)}<br/>
          Status: ${r.status}
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
      </div>
    `;
  }

  async function aprovarReembolso(pagamentoId) {
    const ok = confirm("Confirmar aprovação deste reembolso?");
    if (!ok) return;

    try {
      await apiPostAuth(`/admin/reembolsos/${pagamentoId}/aprovar`, {});
      alert("Reembolso aprovado com sucesso.");
      carregarReembolsos();
    } catch (err) {
      alert("Erro ao aprovar reembolso: " + err.message);
      console.error(err);
    }
  }

  async function recusarReembolso(pagamentoId) {
    const ok = confirm("Confirmar recusa deste reembolso? O acesso do aluno ao curso será reativado.");
    if (!ok) return;

    try {
      await apiPostAuth(`/admin/reembolsos/${pagamentoId}/recusar`, {});
      alert("Reembolso recusado e acesso reativado.");
      carregarReembolsos();
    } catch (err) {
      alert("Erro ao recusar reembolso: " + err.message);
      console.error(err);
    }
  }

  async function carregarReembolsos() {
    try {
      const dados = await apiGetAuth("/admin/reembolsos");

      if (!dados || dados.length === 0) {
        lista.innerHTML = `
          <div class="assunto">
            Nenhuma solicitação de reembolso encontrada.
          </div>
        `;
        return;
      }

      const pendentes = dados.filter(r => r.status === "REFUND_REQUESTED");
      const aprovados = dados.filter(r => r.status === "REFUNDED");
      const outros = dados.filter(r =>
        r.status !== "REFUND_REQUESTED" &&
        r.status !== "REFUNDED"
      );

      lista.innerHTML = `
        <div style="margin-bottom:30px;">
          <h3>Pendentes</h3>
          ${
            pendentes.length === 0
              ? "<p>Nenhum reembolso pendente.</p>"
              : pendentes.map(cardReembolso).join("")
          }
        </div>

        <div style="margin-bottom:30px;">
          <h3>Aprovados</h3>
          ${
            aprovados.length === 0
              ? "<p>Nenhum reembolso aprovado.</p>"
              : aprovados.map(cardReembolso).join("")
          }
        </div>

        <div>
          <h3>Com erro / em processamento</h3>
          ${
            outros.length === 0
              ? "<p>Nenhum reembolso com erro ou em processamento.</p>"
              : outros.map(cardReembolso).join("")
          }
        </div>
      `;

    } catch (err) {
      lista.innerHTML = `
        <div class="assunto">
          Erro ao carregar solicitações de reembolso.<br/>
          ${err.message}
        </div>
      `;
      console.error(err);
    }
  }

  window.aprovarReembolso = aprovarReembolso;
  window.recusarReembolso = recusarReembolso;

  carregarReembolsos();
})();