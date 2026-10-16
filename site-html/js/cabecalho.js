/* Apresentação compartilhada. Não consulta APIs nem altera links, sessão ou handlers. */
(() => {
  "use strict";

  function organizar(cabecalho) {
    if (cabecalho.classList.contains("ro-header")) return;

    const titulos = document.createElement("div");
    titulos.className = "ro-header-titles";
    const navegacao = document.createElement("div");
    navegacao.className = "ro-header-navigation";

    for (const filho of Array.from(cabecalho.children)) {
      if (filho.matches("#nomeUsuarioLogadoGlobal, #nome_aluno_logado")) continue;
      const temControles = filho.matches("a, button, nav") || filho.querySelector("a, button");
      if (temControles && !filho.querySelector("h1, h2")) {
        filho.classList.add("ro-header-action-group");
        navegacao.appendChild(filho);
      } else {
        titulos.appendChild(filho);
      }
    }

    cabecalho.classList.add("ro-header");
    cabecalho.append(titulos, navegacao);
    for (const controle of navegacao.querySelectorAll("a, button")) {
      if (!controle.hasAttribute("aria-label") && controle.title) {
        controle.setAttribute("aria-label", controle.title);
      }
    }
  }

  function identificar(cabecalho, origem) {
    if (origem.querySelector(":scope > .ro-identity")) return;
    const primeiroNome = Array.from(origem.childNodes)
      .filter(no => no.nodeType === Node.TEXT_NODE)
      .map(no => no.textContent).join("").trim();
    if (!primeiroNome) return;

    // Reutiliza a identificação ampliada já produzida pela página.
    const ampliado = origem.title || origem.querySelector("div")?.textContent.trim() || primeiroNome;
    const detalhes = document.createElement("details");
    detalhes.className = "ro-identity";
    const resumo = document.createElement("summary");
    resumo.textContent = primeiroNome;
    resumo.setAttribute("aria-label", `Identificação de ${primeiroNome}`);
    const nome = document.createElement("div");
    nome.className = "ro-identity-expanded";
    nome.textContent = ampliado;
    detalhes.append(resumo, nome);
    origem.replaceChildren(detalhes);
    origem.classList.add("ro-header-identity");
    cabecalho.prepend(origem);
    cabecalho.classList.add("ro-header--identified");
  }

  function atualizar() {
    const cabecalho = document.querySelector("body > header");
    if (!cabecalho) return;
    organizar(cabecalho);
    for (const origem of document.querySelectorAll("#nomeUsuarioLogadoGlobal, #nome_aluno_logado")) {
      identificar(cabecalho, origem);
    }
  }

  function iniciar() {
    atualizar();
    // As páginas atuais inserem o nome depois de suas consultas já existentes.
    let agendado = false;
    new MutationObserver(() => {
      if (agendado) return;
      agendado = true;
      requestAnimationFrame(() => {
        agendado = false;
        atualizar();
      });
    }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["title"] });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar, { once: true });
  else iniciar();
})();
