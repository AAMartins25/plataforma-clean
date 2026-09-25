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
    const ok = confirm(
      "Aprovar esta solicitação? A devolução financeira ainda precisará ser realizada e confirmada."
    );
    if (!ok) return;

    try {
      await apiPostAuth(
        `/admin/reembolsos/${pagamentoId}/aprovar`,
        {}
      );

      alert(
        "Solicitação aprovada. Aguardando devolução financeira. O aluno permanece com acesso."
      );

      carregarReembolsos();
    } catch (err) {
      alert("Erro ao aprovar solicitação: " + err.message);
      console.error(err);
    }
  }

  async function recusarReembolso(pagamentoId) {
    const ok = confirm(
      "Confirmar a recusa desta solicitação de reembolso?"
    );
    if (!ok) return;

    try {
      await apiPostAuth(
        `/admin/reembolsos/${pagamentoId}/recusar`,
        {}
      );

      alert(
        "Solicitação recusada. O acesso do aluno permanece inalterado."
      );

      carregarReembolsos();
    } catch (err) {
      alert("Erro ao recusar solicitação: " + err.message);
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