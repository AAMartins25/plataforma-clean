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

  async function carregarCompras() {
    try {
        const resposta = await apiGetAuth("/me/compras/reembolso");

        const tipo = resposta.tipo;
        const compras = resposta.compras || [];

        if (!compras || compras.length === 0) {
        lista.innerHTML = `
            <div class="assunto">
            Nenhuma compra elegível para reembolso no momento.
            </div>
        `;
        return;
        }

        let avisoInicial = "";

        if (tipo === "mais_recente") {
            avisoInicial = `
                <div class="assunto">
                    Não há compras elegíveis para reembolso.
                    <br/> 
                    Sua compra mais recente foi:
                </div>
            `;
        }

        lista.innerHTML = avisoInicial + compras.map(c => {
          const dataLimite = adicionarDias(c.data_compra, 7);

          const reembolsoJaSolicitado = [
            "REFUND_IN_PROCESS",
            "REFUNDED",
            "REFUND_ERROR"
          ].includes(c.status);

          const infoCancelamento = reembolsoJaSolicitado
            ? `
              <b style="color:#8a5a00;">
                Reembolso já solicitado para este curso.
                ${c.data_solicitacao ? `(EM ${formatarData(c.data_solicitacao)})` : ""}
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
      `;

    } catch (err) {
      alert("Erro ao solicitar reembolso: " + err.message);
      console.error(err);
    }
  };

  carregarCompras();
})();