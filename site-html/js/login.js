// js/login.js
(function () {
  const form = document.getElementById("formLogin");
  const msg = document.getElementById("msg");

  function show(text, ok = false) {
    msg.textContent = text;
    msg.style.padding = "10px";
    msg.style.borderRadius = "6px";
    msg.style.border = "1px solid #ddd";
    msg.style.background = ok ? "#e7f7ee" : "#fde8e8";
  }

  async function redirectDepoisDoLogin() {
    // 1) Redirect explícito recebido pela URL
    const nextUrl =
      new URLSearchParams(
        window.location.search
      ).get("next");

    if (nextUrl) {
      localStorage.removeItem(
        "pos_login_redirect"
      );

      window.location.href =
        nextUrl;

      return;
    }


    // 2) Compra iniciada antes do login
    const continuarCompra =
      localStorage.getItem(
        "continuar_compra_apos_login"
      ) === "1";

    const estadoCompraSalvo =
      localStorage.getItem(
        "estado_compra_curso"
      );

    if (
      continuarCompra &&
      estadoCompraSalvo
    ) {
      let destinoCompra =
        localStorage.getItem(
          "pos_login_redirect"
        );

      // Segurança adicional:
      // se o redirect tiver sido perdido,
      // reconstrói a página pelo curso salvo.
      if (!destinoCompra) {
        try {
          const estadoCompra =
            JSON.parse(
              estadoCompraSalvo
            );

          if (estadoCompra?.curso_id) {
            destinoCompra =
              `curso-info.html?curso_id=${encodeURIComponent(
                estadoCompra.curso_id
              )}`;
          }

        } catch (err) {
          console.error(
            "Erro ao recuperar estado da compra:",
            err
          );
        }
      }

      if (destinoCompra) {
        localStorage.removeItem(
          "pos_login_redirect"
        );

        window.location.href =
          destinoCompra;

        return;
      }
    }


    // 3) Redirect comum salvo
    const next =
      localStorage.getItem(
        "pos_login_redirect"
      ) || "";

    localStorage.removeItem(
      "pos_login_redirect"
    );

    // Só respeita redirect comum
    // quando ele realmente aponta para
    // uma página específica do fluxo.
    //
    // "cursos.html" não deve forçar
    // vendedor ou admin para a área de aluno.
    if (
      next &&
      next !== "cursos.html"
    ) {
      window.location.href =
        next;

      return;
    }

    // 4) Caso normal:
    // decide pelo perfil do usuário
    try {
      const token =
        localStorage.getItem(
          "access_token"
        );

      if (!token) {
        window.location.href =
          "login.html";

        return;
      }

      const r =
        await fetch(
          `${API_BASE}/me`,
          {
            headers: {
              Authorization:
                `Bearer ${token}`
            }
          }
        );

      if (!r.ok) {
        localStorage.removeItem(
          "access_token"
        );

        window.location.href =
          "login.html";

        return;
      }

      const me =
        await r.json();

      const quantidadeAreas =
        Number(!!me?.is_admin) +
        Number(!!me?.is_vendedor) +
        Number(!!me?.is_aluno);


      // Mais de uma área disponível:
      // mostra a tela de escolha.
      if (quantidadeAreas > 1) {
        window.location.href =
          "minha-area.html";

        return;
      }


      // Apenas Admin.
      if (me?.is_admin) {
        window.location.href =
          "admin/index.html";

        return;
      }


      // Apenas Vendedor.
      if (me?.is_vendedor) {
        window.location.href =
          "minhas-vendas.html";

        return;
      }


      // Possui somente área de aluno.
      if (me?.is_aluno) {
        window.location.href =
          "cursos.html";

        return;
      }


      // Sem área disponível.
      window.location.href =
        "index.html";

    } catch (e) {
      console.error(
        "Erro ao identificar o perfil do usuário:",
        e
      );

      localStorage.removeItem(
        "access_token"
      );

      window.location.href =
        "login.html";
    }
    
  }

  // Se já tem token, pode ir direto
  const tokenExistente = localStorage.getItem("access_token");
  if (tokenExistente) {
    show("Você já está logado. Redirecionando...", true);
    setTimeout(() => {
      redirectDepoisDoLogin();
    }, 300);
    return;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const email = document.getElementById("email").value.trim();
    const senha = document.getElementById("senha").value;

    try {
      const body = new URLSearchParams();
      body.append("username", email);
      body.append("password", senha);

      const res = await fetch(`${API_BASE}/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body
      });

      if (!res.ok) {
        const txt = await res.text();
        throw new Error(txt || `Erro HTTP ${res.status}`);
      }

      const data = await res.json();
      if (!data.access_token) throw new Error("Login sem token. Verifique o backend.");

      localStorage.setItem("access_token", data.access_token);
      show("Login efetuado com sucesso! Redirecionando...", true);

      setTimeout(() => {
        redirectDepoisDoLogin();
      }, 200);

    } catch (err) {
      show("Erro no login: " + err.message, false);
    }
  });
})();
