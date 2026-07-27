// js/register.js
(function () {
  const form = document.getElementById("formRegister");
  const msg = document.getElementById("msg");
  const campoCpf = document.getElementById("cpf");
  const campoTelefone = document.getElementById("telefone");

  const campoConfirmarSenha =
    document.getElementById("confirmarSenha");

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

  function validarCpf(valor) {
    const cpf = somenteDigitos(valor);

    // CPF precisa ter exatamente 11 dígitos
    if (cpf.length !== 11) {
      return false;
    }

    // Rejeita sequências com todos os dígitos iguais
    if (/^(\d)\1{10}$/.test(cpf)) {
      return false;
    }

    // Primeiro dígito verificador
    let soma = 0;

    for (let i = 0; i < 9; i++) {
      soma += Number(cpf.charAt(i)) * (10 - i);
    }

    let resto = (soma * 10) % 11;

    if (resto === 10) {
      resto = 0;
    }

    if (resto !== Number(cpf.charAt(9))) {
      return false;
    }

    // Segundo dígito verificador
    soma = 0;

    for (let i = 0; i < 10; i++) {
      soma += Number(cpf.charAt(i)) * (11 - i);
    }

    resto = (soma * 10) % 11;

    if (resto === 10) {
      resto = 0;
    }

    if (resto !== Number(cpf.charAt(10))) {
      return false;
    }

    return true;
  }

  function validarSenha(senha) {
    const temTamanhoValido =
      senha.length >= 4 &&
      senha.length <= 23;

    const temMaiuscula =
      /[A-Z]/.test(senha);

    const temNumero =
      /\d/.test(senha);

    return (
      temTamanhoValido &&
      temMaiuscula &&
      temNumero
    );
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
    const confirmarSenha =
      (
        document.getElementById(
          "confirmarSenha"
        ).value || ""
      ).trim();
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
      show(
        "Por favor, preencha o campo Senha."
      );
      return;
    }

    if (!validarSenha(senha)) {
      show(
        "A senha deve ter entre 4 e 23 caracteres, conter pelo menos uma letra maiúscula e pelo menos um número."
      );
      return;
    }

    if (!confirmarSenha) {
      show(
        "Por favor, preencha o campo Confirmar senha."
      );
      return;
    }

    if (senha !== confirmarSenha) {
      show(
        "As senhas informadas não coincidem."
      );
      return;
    }

    if (!validarCpf(cpf)) {
      show(
        "CPF inválido. Verifique o número informado e tente novamente."
      );
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
        localStorage.setItem(
          "access_token",
          accessToken
        );

        show(
          "✅ Conta criada e login efetuado! Redirecionando...",
          true
        );

        const destino =
          localStorage.getItem(
            "pos_login_redirect"
          );

        setTimeout(
          () => {
            window.location.href =
              destino ||
              "cursos.html";
          },
          700
        );

        return;
      }

      const btnCriarConta = document.getElementById("btnCriarConta");

      if (btnCriarConta) {
        btnCriarConta.style.display = "none";
      }

      const destinoAposLogin =
      localStorage.getItem(
        "pos_login_redirect"
      ) || "";

      msg.innerHTML = `
        <div
          style="
            padding:12px;
            border:1px solid #cfe8d8;
            background:#e7f7ee;
            border-radius:8px;
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:14px;
            flex-wrap:wrap;
          "
        >

          <div
            style="
              font-weight:700;
              font-size:1.08rem;
            "
          >
            ✅ Conta criada com sucesso!
          </div>

          <div
            style="
              margin-left:auto;
              display:flex;
              align-items:center;
              justify-content:flex-end;
              gap:8px;
              flex-wrap:wrap;
              position:relative;
              top:5px;
            "
          >
            <a
              class="btn"
              href="${
                destinoAposLogin
                  ? `login.html?next=${encodeURIComponent(destinoAposLogin)}`
                  : "login.html"
              }"
              style="
                min-width:120px;
                height:34px;
                display:inline-flex;
                align-items:center;
                justify-content:center;
                padding:0 14px;
                margin:0;
                font-size:.92rem;
                line-height:1;
                box-sizing:border-box;
                text-align:center;
              "
            >
              <span
                style="
                  display:inline-block;
                  transform:translateY(-6px);
                "
              >
                Fazer login
              </span>
            </a>

            <a
              class="btn"
              href="index.html"
              style="
                min-width:120px;
                height:34px;
                display:inline-flex;
                align-items:center;
                justify-content:center;
                padding:0 14px;
                margin:0;
                font-size:.92rem;
                line-height:1;
                box-sizing:border-box;
                text-align:center;
              "
            >
              <span
                style="
                  display:inline-block;
                  transform:translateY(-6px);
                "
              >
                Voltar ao início
              </span>
            </a>
          </div>

        </div>
      `;

    } catch (err) {
      const erroTexto = String(
        err?.message || err || ""
      );

      if (
        erroTexto.includes(
          "E-mail ou CPF já cadastrado"
        )
      ) {
        show(
          "Já há um cadastro com esse e-mail e/ou CPF. " +
          "Por favor, verifique se esses dados estão corretos e tente novamente!",
          false
        );

      } else if (
        erroTexto.includes(
          "E-mail já cadastrado"
        )
      ) {
        show(
          "Já há um cadastro com esse e-mail. " +
          "Por favor, verifique se esse dado está correto e tente novamente!",
          false
        );

      } else if (
        erroTexto.includes(
          "CPF já cadastrado"
        )
      ) {
        show(
          "Já há um cadastro com esse CPF. " +
          "Por favor, verifique se esse dado está correto e tente novamente!",
          false
        );

      } else {
        show(
          "Não foi possível criar a conta. " +
          "Verifique os dados informados e tente novamente!",
          false
        );
      }

      console.error(err);
    }
  });
})();
