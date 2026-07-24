(function () {
  const lista = document.getElementById("listaReembolsos");

  function formatarData(dataISO) {
    if (!dataISO) return "-";
    const data = new Date(dataISO);
    return data.toLocaleDateString("pt-BR");
  }

  function adicionarDias(dataISO, dias) {
    const data = new Date(dataISO);
    data.setDate(data.getDate() + dias);
    return data;
  }

  function data72h() {
    const data = new Date();
    data.setHours(data.getHours() + 72);
    return data.toLocaleDateString("pt-BR");
  }

  function traduzirStatus(status) {
    const s = String(status || "").toUpperCase();

    const mapa = {
      REFUND_REQUESTED: "Em análise",
      REFUNDED: "Aprovado",
      REFUND_DENIED: "Recusado",
      REFUND_IN_PROCESS: "Em processamento",
      REFUND_ERROR: "Erro no processamento"
    };

    return mapa[s] || s || "-";
  }

  function montarAreaHistorico() {
    return `
      <div class="assunto" style="margin-top:16px;">
        <button class="btn" type="button" onclick="toggleReembolsosSolicitados()">
          Reembolsos solicitados
        </button>

        <div
          id="historicoReembolsos"
          class="list"
          style="display:none; margin-top:14px;"
        ></div>
      </div>
    `;
  }

  async function carregarCompras() {
    try {
      const resposta = await apiGetAuth("/me/compras/reembolso");

      const tipo = resposta.tipo;
      const compras = resposta.compras || [];

      let html = "";

      if (!compras || compras.length === 0) {
        html += `
          <div class="assunto">
            Nenhuma compra elegível para reembolso no momento.
          </div>
        `;
      } else {
        let avisoInicial = "";

        if (tipo === "mais_recente") {
          avisoInicial = `
            <div class="assunto">
              Não há compras elegíveis para reembolso.
            </div>
          `;
        }

        html += avisoInicial + compras.map(c => {
          const dataLimite = adicionarDias(c.data_compra, 7);
          const dataSolicitacao = c.data_solicitacao || c.atualizado_em;

          const reembolsoJaSolicitado = [
            "REFUND_REQUESTED",
            "REFUND_IN_PROCESS",
            "REFUNDED",
            "REFUND_ERROR"
          ].includes(c.status);

          const infoCancelamento = reembolsoJaSolicitado
            ? `
              <b style="color:#8a5a00;">
                Reembolso já solicitado para este curso
                ${dataSolicitacao ? `(EM ${formatarData(dataSolicitacao)}).` : "."}
                O prazo para estorno do valor é de até 72hs.
              </b>
            `
            : `
              Data-limite para cancelamento: ${formatarData(dataLimite)}
            `;

          const botaoCancelar = tipo === "elegiveis" && !reembolsoJaSolicitado
            ? `
              <button class="btn" onclick="confirmarCancelamento(${c.pagamento_id}, '${c.nome_curso}')">
                Cancelar esta compra
              </button>
            `
            : "";

          return `
            <div class="assunto">
              <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap;">
                <div>
                  ${tipo === "mais_recente"
                    ? `<div style="margin-bottom:8px;">
                        Sua compra mais recente foi:
                    </div>`
                    : ""
                  }

                  <b>${c.nome_curso}</b><br/>
                  <span style="opacity:.85;">
                    Data da compra: ${formatarData(c.data_compra)}<br/>
                    ${infoCancelamento}<br/>
                  </span>
                </div>

                ${botaoCancelar}
              </div>

              <div id="confirmacao_${c.pagamento_id}" style="margin-top:10px;"></div>
            </div>
          `;
        }).join("");
      }

      html += montarAreaHistorico();

      lista.innerHTML = html;

    } catch (err) {
      lista.innerHTML = `
        <div class="assunto">
          <b>Erro ao carregar compras para reembolso.</b><br/>
          <pre style="white-space:pre-wrap; margin-top:8px;">${err.message}</pre>
        </div>
      `;
      console.error(err);
    }
  }

  window.confirmarCancelamento = function (pagamentoId, nomeCurso) {
    const box = document.getElementById(`confirmacao_${pagamentoId}`);

    box.innerHTML = `
      <div style="margin-top:10px;">
        <p>Confirmar cancelamento de <b>${nomeCurso}</b>?</p>

        <button class="btn" onclick="executarCancelamento(${pagamentoId})">
          Confirmar cancelamento
        </button>
      </div>
    `;
  };

  window.executarCancelamento = async function (pagamentoId) {
    try {
      await apiPostAuth(`/me/reembolso/${pagamentoId}`, {});

      lista.innerHTML = `
        <div class="assunto">
          <b>Obrigado pela confiança!</b><br/>
          Seu valor será reembolsado em até 72hs (${data72h()}).
        </div>

        ${montarAreaHistorico()}
      `;

    } catch (err) {
      alert("Erro ao solicitar reembolso: " + err.message);
      console.error(err);
    }
  };

  let historicoReembolsosAberto = false;

  window.toggleReembolsosSolicitados = async function () {
    const box = document.getElementById("historicoReembolsos");
    if (!box) return;

    historicoReembolsosAberto = !historicoReembolsosAberto;

    if (!historicoReembolsosAberto) {
      box.style.display = "none";
      return;
    }

    box.style.display = "block";
    box.innerHTML = "<p>Carregando reembolsos solicitados...</p>";

    try {
      const dados = await apiGetAuth("/me/reembolsos");

      if (!dados || dados.length === 0) {
        box.innerHTML = `
          <div class="assunto">
            Ainda não há reembolsos solicitados.
          </div>
        `;
        return;
      }

      box.innerHTML = dados.map(r => `
        <div class="assunto">
          <b>${r.curso_nome}</b><br/>
          <span style="opacity:.85;">
            Data da compra: ${formatarData(r.data_compra)}<br/>
            Atualização: ${formatarData(r.data_atualizacao)}<br/>
            Status: ${traduzirStatus(r.status)}
          </span>
        </div>
      `).join("");

    } catch (err) {
      console.error(err);
      box.innerHTML = `
        <div class="assunto">
          Erro ao carregar reembolsos solicitados.
        </div>
      `;
    }
  };

  carregarCompras();
})();