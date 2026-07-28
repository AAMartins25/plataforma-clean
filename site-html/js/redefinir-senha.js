// js/redefinir-senha.js
(function () {
  const form =
    document.getElementById(
      "formRedefinirSenha"
    );

  const msg =
    document.getElementById("msg");

  const campoNovaSenha =
    document.getElementById(
      "novaSenha"
    );

  const campoConfirmar =
    document.getElementById(
      "confirmarNovaSenha"
    );

  function show(text, ok = false) {
    msg.textContent = text;
    msg.style.padding = "10px";
    msg.style.borderRadius = "6px";
    msg.style.border = "1px solid #ddd";
    msg.style.background =
      ok ? "#e7f7ee" : "#fde8e8";
    msg.style.whiteSpace = "pre-line";
  }

  function senhaValida(senha) {
    const tamanhoValido =
      senha.length >= 4 &&
      senha.length <= 23;

    const temMaiuscula =
      /[A-Z]/.test(senha);

    const temNumero =
      /\d/.test(senha);

    return (
      tamanhoValido &&
      temMaiuscula &&
      temNumero
    );
  }

  const parametros =
    new URLSearchParams(
      window.location.search
    );

  const token =
    parametros.get("token");

  if (!token) {
    show(
      "Link de redefinição inválido."
    );

    if (form) {
      form.style.display = "none";
    }

    return;
  }

  form.addEventListener(
    "submit",
    async (e) => {
      e.preventDefault();

      const novaSenha =
        campoNovaSenha.value || "";

      const confirmarSenha =
        campoConfirmar.value || "";

      if (!novaSenha) {
        show(
          "Informe a nova senha."
        );
        return;
      }

      if (!senhaValida(novaSenha)) {
        show(
          "Ajuste a Senha. " +
          "A senha deve ter entre 4 e 23 caracteres, " +
          "conter ao menos uma letra maiúscula " +
          "e ao menos um número."
        );
        return;
      }

      if (
        novaSenha !==
        confirmarSenha
      ) {
        show(
          "As senhas devem ser iguais."
        );
        return;
      }

      show(
        "Redefinindo senha...",
        true
      );

      try {
        const res = await fetch(
          `${API_BASE}/redefinir-senha`,
          {
            method: "POST",

            headers: {
              "Content-Type":
                "application/json"
            },

            body: JSON.stringify({
              token: token,
              nova_senha: novaSenha
            })
          }
        );

        const data =
          await res.json();

        if (!res.ok) {
          throw new Error(
            data.detail ||
            "Não foi possível redefinir a senha."
          );
        }

        show(
          data.message ||
          "Senha redefinida com sucesso!",
          true
        );

        form.reset();

        setTimeout(
          () => {
            window.location.href =
              "login.html";
          },
          1500
        );

      } catch (err) {
        show(
          err.message ||
          "Não foi possível redefinir a senha."
        );
      }
    }
  );
})();