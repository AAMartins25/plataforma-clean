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
    // 1) prioridade: redirect explícito (ex: veio do botão Comprar)
    const next = localStorage.getItem("pos_login_redirect") || "";
    localStorage.removeItem("pos_login_redirect");
    if (next) {
      window.location.href = next;
      return;
    }

    // 2) Se existe intenção de compra pendente, segue pro checkout
    const cursoCompra = localStorage.getItem("ultimo_curso_id_compra");
    if (cursoCompra) {
      window.location.href = "checkout.html";
      return;
    }

    // 3) Caso normal: decide por perfil (admin → painel / aluno → cursos)
    try {
      const token = localStorage.getItem("access_token");
      if (!token) {
        window.location.href = "login.html";
        return;
      }

      const r = await fetch(`${API_BASE}/me`, {
        headers: { Authorization: `Bearer ${token}` }
      });

      if (!r.ok) {
        // token inválido/expirado
        localStorage.removeItem("access_token");
        window.location.href = "login.html";
        return;
      }

      const me = await r.json();

      if (me && me.is_admin) {
        window.location.href = "admin/index.html";
      } else {
        window.location.href = "cursos.html";
      }
    } catch (e) {
      // fallback seguro
      window.location.href = "cursos.html";
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
