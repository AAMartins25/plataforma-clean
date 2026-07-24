(function () {
  const form = document.getElementById("formMeusDados");
  const msg = document.getElementById("msg");
  const historicoCompras = document.getElementById("historicoCompras");

  function show(text, ok = false) {
    msg.textContent = text;
    msg.style.padding = "10px";
    msg.style.borderRadius = "6px";
    msg.style.border = "1px solid #ddd";
    msg.style.background = ok ? "#e7f7ee" : "#fde8e8";
  }

  function somenteDigitos(valor) {
    return String(valor || "").replace(/\D/g, "");
  }

  function formatarData(dataISO) {
    if (!dataISO) return "-";
    return new Date(dataISO).toLocaleDateString("pt-BR");
  }

  function formatarCpf(valor) {
    let v = somenteDigitos(valor).slice(0, 11);
    v = v.replace(/^(\d{3})(\d)/, "$1.$2");
    v = v.replace(/^(\d{3})\.(\d{3})(\d)/, "$1.$2.$3");
    v = v.replace(/\.(\d{3})(\d)/, ".$1-$2");
    return v;
  }

  function formatarTelefone(valor) {
    let v = somenteDigitos(valor).slice(0, 11);

    if (v.length <= 10) {
      v = v.replace(/^(\d{2})(\d)/g, "($1) $2");
      v = v.replace(/(\d{4})(\d)/, "$1-$2");
    } else {
      v = v.replace(/^(\d{2})(\d)/g, "($1) $2");
      v = v.replace(/(\d{5})(\d)/, "$1-$2");
    }

    return v;
  }

  function traduzirStatus(status) {
    const s = String(status || "").toUpperCase();

    const mapa = {
      APPROVED: "Compra aprovada",
      PAGO: "Compra aprovada",
      REFUND_REQUESTED: "Reembolso solicitado",
      REFUNDED: "Reembolso aprovado",
      REFUND_IN_PROCESS: "Reembolso em processamento",
      REFUND_ERROR: "Erro no reembolso",
      REFUND_DENIED: "Reembolso recusado",
      PENDENTE: "Pagamento pendente"
    };

    return mapa[s] || s || "-";
  }

  document.getElementById("cpf").addEventListener("input", (e) => {
    e.target.value = formatarCpf(e.target.value);
  });

  document.getElementById("telefone").addEventListener("input", (e) => {
    e.target.value = formatarTelefone(e.target.value);
  });

  async function carregarMeusDados() {
    try {
      const me = await apiGetAuth("/me");

      document.getElementById("nome").value = me.nome || "";
      document.getElementById("email").value = me.email || "";
      document.getElementById("cpf").value = me.cpf ? formatarCpf(me.cpf) : "";
      document.getElementById("telefone").value = me.telefone ? formatarTelefone(me.telefone) : "";

    } catch (err) {
      show("Erro ao carregar seus dados. Faça login novamente.", false);
      console.error(err);
    }
  }

  async function carregarHistoricoCompras() {
    if (!historicoCompras) return;

    try {
      const historico = await apiGetAuth("/me/compras/historico");

      if (!historico || historico.length === 0) {
        historicoCompras.innerHTML = `
          <div class="assunto">
            Nenhum histórico de compras encontrado.
          </div>
        `;
        return;
      }

      historicoCompras.innerHTML = historico.map(c => `
        <div class="assunto">
          <b>${c.nome_curso} (${c.situacao})</b><br/>

          <span style="opacity:.85;">
            Data de aquisição: ${formatarData(c.data_aquisicao)}<br/>
            Início do acesso: ${formatarData(c.data_inicio)}<br/>
            ${
              c.data_fim
                ? `Cessação do acesso: ${formatarData(c.data_fim)}<br/>`
                : ""
            }
            Status interno: ${traduzirStatus(c.pagamento_status)}
          </span>
        </div>
      `).join("");

    } catch (err) {
      historicoCompras.innerHTML = `
        <div class="assunto">
          Erro ao carregar histórico de compras.<br/>
          ${err.message}
        </div>
      `;
      console.error(err);
    }
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const nome = document.getElementById("nome").value.trim();
    const email = document.getElementById("email").value.trim().toLowerCase();
    const cpf = somenteDigitos(document.getElementById("cpf").value);
    const telefone = somenteDigitos(document.getElementById("telefone").value);

    if (!nome) return show("Por favor, preencha este campo: Nome.");
    if (!email) return show("Por favor, preencha este campo: Email.");
    if (!cpf) return show("Por favor, preencha este campo: CPF.");
    if (!telefone) return show("Por favor, preencha este campo: Telefone.");

    if (cpf.length !== 11) return show("CPF inválido.");
    if (telefone.length < 10 || telefone.length > 11) return show("Telefone inválido.");

    try {
      await apiPostAuth("/me/dados", {
        nome,
        email,
        cpf,
        telefone
      });

      show("Atualização realizada com sucesso!", true);

    } catch (err) {
      show("Erro ao atualizar dados: " + err.message, false);
      console.error(err);
    }
  });

  let historicoJaCarregado = false;

  window.mostrarHistoricoCompras = async function () {
    const box = document.getElementById("historicoCompras");

    if (box.style.display === "none") {
      box.style.display = "block";

      if (!historicoJaCarregado) {
        box.innerHTML = "<p>Carregando histórico...</p>";
        await carregarHistoricoCompras();
        historicoJaCarregado = true;
      }

    } else {
      box.style.display = "none";
    }
  };

  carregarMeusDados();
})();