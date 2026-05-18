// js/register.js
(function () {
  const form = document.getElementById("formRegister");
  const msg = document.getElementById("msg");
  const campoCpf = document.getElementById("cpf");
  const campoTelefone = document.getElementById("telefone");

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

  campoCpf.addEventListener("input", (e) => {
    e.target.value = formatarCpf(e.target.value);
  });

  campoTelefone.addEventListener("input", (e) => {
    e.target.value = formatarTelefone(e.target.value);
  });

  function show(text, ok = false) {
    msg.textContent = text;
    msg.style.padding = "10px";
    msg.style.borderRadius = "6px";
    msg.style.border = "1px solid #ddd";
    msg.style.background = ok ? "#e7f7ee" : "#fde8e8";
    msg.style.whiteSpace = "pre-line";
  }

  // se já está logado, manda direto
  const token = localStorage.getItem("access_token");
  if (token) {
    show("Você já está logado. Redirecionando...", true);
    setTimeout(() => (window.location.href = "cursos.html"), 600);
    return;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const nome = (document.getElementById("nome").value || "").trim();
    const email = (document.getElementById("email").value || "").trim().toLowerCase();
    const senha = (document.getElementById("senha").value || "").trim();
    const cpf = somenteDigitos(document.getElementById("cpf").value);
    const telefone = somenteDigitos(document.getElementById("telefone").value);
    if (!nome) {
      show("Por favor, preencha o campo Nome.");
      return;
    }

    if (!email) {
      show("Por favor, preencha o campo Email.");
      return;
    }

    if (!cpf) {
      show("Por favor, preencha o campo CPF.");
      return;
    }

    if (!telefone) {
      show("Por favor, preencha o campo Telefone.");
      return;
    }

    if (!senha) {
      show("Por favor, preencha o campo Senha.");
      return;
    }

    if (cpf.length !== 11) {
      show("CPF inválido.");
      return;
    }

    if (telefone.length < 10 || telefone.length > 11) {
      show("Telefone inválido.");
      return;
    }

    show("Criando conta... aguarde.", true);

    try {
      const res = await fetch(`${API_BASE}/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nome, email, cpf, telefone, senha })
      });

      const txt = await res.text();
      let data = null;
      try { data = txt ? JSON.parse(txt) : null; } catch { data = txt; }

      if (!res.ok) {
        throw new Error(typeof data === "string" ? data : JSON.stringify(data, null, 2));
      }

      // Alguns backends retornam access_token no register.
      // Outros retornam apenas dados do usuário.
      const accessToken = data?.access_token;

      if (accessToken) {
        localStorage.setItem("access_token", accessToken);
        show("✅ Conta criada e login efetuado! Redirecionando...", true);
        setTimeout(() => (window.location.href = "cursos.html"), 700);
        return;
      }

      const btnCriarConta = document.getElementById("btnCriarConta");

      if (btnCriarConta) {
        btnCriarConta.style.display = "none";
      }

      msg.innerHTML = `
        <div style="
          padding:12px;
          border:1px solid #cfe8d8;
          background:#e7f7ee;
          border-radius:8px;

          display:flex;
          align-items:center;
          justify-content:space-between;
          gap:14px;
          flex-wrap:wrap;
        ">

          <div style="font-weight:700; font-size:1.08rem;">
            ✅ Conta criada com sucesso!
          </div>

          <div style="
            display:flex;
            gap:10px;
            flex-wrap:wrap;
            margin-top:-4px;
          ">
            <a class="btn" href="index.html">
              Voltar para inicial
            </a>

            <a class="btn" href="login.html">
              Fazer login
            </a>
          </div>
        </div>
      `;

    } catch (err) {
      const erroTexto = String(err?.message || err || "");

      if (erroTexto.includes("E-mail já cadastrado")) {
        show(
          "Já há um cadastro com esse e-mail. Por favor, verifique se esse dado está correto.\n\nPara recuperar a senha, acesse a área de Login.",
          false
        );

      } else if (erroTexto.includes("CPF já cadastrado")) {
        show(
          "Já há um cadastro com esse CPF. Por favor, verifique se esse dado está correto.\n\nPara recuperar a senha, acesse a área de Login.",
          false
        );

      } else if (erroTexto.includes("E-mail ou CPF já cadastrado")) {
        show(
          "Já há um cadastro com esse e-mail e/ou CPF. Por favor, verifique se esses dados estão corretos.\n\nPara recuperar a senha, acesse a área de Login.",
          false
        );
      }
      console.error(err);
    }
  });
})();
