(function () {
  const lista = document.getElementById("listaReembolsos");

  function formatarData(dataISO) {
    if (!dataISO) return "-";
    const data = new Date(dataISO);
    return data.toLocaleDateString("pt-BR");
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

      lista.innerHTML = dados.map(r => `
        <div class="assunto">
          <b>${r.curso_nome}</b><br/>
          <span style="opacity:.85;">
            Aluno: ${r.usuario_nome} — ${r.usuario_email}<br/>
            Pagamento ID: ${r.pagamento_id}<br/>
            Data da compra: ${formatarData(r.data_compra)}<br/>
            Solicitação: ${formatarData(r.data_solicitacao)}<br/>
            Status: ${r.status}
          </span>
        </div>
      `).join("");

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

  carregarReembolsos();
})();