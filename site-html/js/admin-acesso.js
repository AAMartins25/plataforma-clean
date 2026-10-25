/* A API decide as permissões. Esta guarda protege a navegação e a inicialização. */
(() => {
  "use strict";
  const producao = new Set([
    "criar-curso-completo.html", "admin-questoes-aluno.html", "admin-questoes-pratica.html",
    "cursos.html", "curso-disciplinas.html", "disciplinas.html", "assuntos.html",
    "aulas.html", "aula-conteudo.html"
  ]);
  const alunos = new Set(["pagamentos.html", "atendimento.html", "admin-mensagens-questoes.html"]);
  const pagina = location.pathname.split("/").pop() || "index.html";
  document.documentElement.classList.add("admin-validando");
  const estilo = document.createElement("style");
  estilo.textContent = ".admin-validando body { visibility: hidden !important; }";
  document.head.appendChild(estilo);
  let pendente;
  let identidade;

  function permite(me, area) {
    if (!me || me.ativo !== true) return false;
    if (me.is_admin === true && me.tipo_admin === "admin_geral") return true;
    if (me.is_admin !== false) return false;
    if (area === "painel") return ["admin_prod", "admin_adm"].includes(me.tipo_admin);
    const tipo = ({producao: "admin_prod", alunos: "admin_adm"})[area];
    return !!tipo && me.tipo_admin === tipo;
  }

  function filtrarPainel(me) {
    document.querySelectorAll("[data-admin-area]").forEach(el => {
      el.hidden = !permite(me, el.dataset.adminArea);
    });
  }

  async function validar() {
    const token = localStorage.getItem("access_token");
    const geracao = localStorage.getItem("auth_generation");
    if (!token) { location.replace("../login.html"); return false; }
    try {
      const res = await Sessao.fetch(`${API_BASE}/me`, {headers: {Authorization: `Bearer ${token}`}});
      if (!res.ok) throw new Error("Sessão indisponível");
      const me = await res.json();
      if (token !== localStorage.getItem("access_token") || geracao !== localStorage.getItem("auth_generation")) return false;
      const area = pagina === "index.html" ? "painel" : producao.has(pagina) ? "producao" : alunos.has(pagina) ? "alunos" : "geral";
      if (!permite(me, area)) { location.replace("../minha-area.html"); return false; }
      filtrarPainel(me);
      document.documentElement.classList.remove("admin-validando");
      return true;
    } catch (_) {
      location.replace("../login.html");
      return false;
    }
  }

  function exigir() {
    const atual = `${localStorage.getItem("auth_generation")}:${localStorage.getItem("access_token")}`;
    if (!pendente || identidade !== atual) {
      document.documentElement.classList.add("admin-validando");
      identidade = atual;
      pendente = validar();
    }
    return pendente;
  }
  window.AdminAcesso = {exigir, permite};
  document.addEventListener("DOMContentLoaded", exigir);
  window.addEventListener("pageshow", event => {
    if (event.persisted) { pendente = null; exigir(); }
  });
  window.addEventListener("storage", event => {
    if (["access_token", "auth_generation"].includes(event.key)) { pendente = null; exigir(); }
  });
})();
