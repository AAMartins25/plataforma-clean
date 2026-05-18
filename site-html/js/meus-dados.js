(function () {
  const form = document.getElementById("formMeusDados");
  const msg = document.getElementById("msg");

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

  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const nome = document.getElementById("nome").value.trim();
    const email = document.getElementById("email").value.trim().toLowerCase();
    const cpf = somenteDigitos(document.getElementById("cpf").value);
    const telefone = somenteDigitos(document.getElementById("telefone").value);
    const senha = document.getElementById("senha").value.trim();

    if (!nome) return show("Por favor, preencha este campo: Nome.");
    if (!email) return show("Por favor, preencha este campo: Email.");
    if (!cpf) return show("Por favor, preencha este campo: CPF.");
    if (!telefone) return show("Por favor, preencha este campo: Telefone.");

    if (cpf.length !== 11) return show("CPF inválido.");
    if (telefone.length < 10 || telefone.length > 11) return show("Telefone inválido.");
    if (senha && senha.length < 8) return show("A nova senha deve ter pelo menos 8 caracteres.");

    try {
      await apiPostAuth("/me/dados", {
        nome,
        email,
        cpf,
        telefone,
        senha: senha || null
      });

      show("Atualização realizada com sucesso!", true);

    } catch (err) {
      show("Erro ao atualizar dados: " + err.message, false);
      console.error(err);
    }
  });

  carregarMeusDados();
})();