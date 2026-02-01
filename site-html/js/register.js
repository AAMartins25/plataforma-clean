// js/register.js
(function () {
  const form = document.getElementById("formRegister");
  const msg = document.getElementById("msg");

  function show(text, ok = false) {
    msg.textContent = text;
    msg.style.padding = "10px";
    msg.style.borderRadius = "6px";
    msg.style.border = "1px solid #ddd";
    msg.style.background = ok ? "#e7f7ee" : "#fde8e8";
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

    if (!nome || !email || !senha) {
      show("Preencha nome, email e senha.");
      return;
    }

    show("Criando conta... aguarde.", true);

    try {
      const res = await fetch(`${API_BASE}/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nome, email, senha })
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

      show("✅ Conta criada! Agora faça login.", true);
      setTimeout(() => (window.location.href = "login.html"), 900);

    } catch (err) {
      show("Erro no cadastro: " + (err?.message || err), false);
      console.error(err);
    }
  });
})();
