/* Apresentação compartilhada. Não consulta APIs nem altera links, sessão ou handlers. */
(() => {
  "use strict";

  const mouse = window.matchMedia("(hover: hover) and (pointer: fine)");
  function atualizarHover() {
    for (const nome of document.querySelectorAll(".ro-identity")) {
      if (mouse.matches) nome.title = nome.dataset.nomeAmpliado;
      else nome.removeAttribute("title");
    }
  }
  mouse.addEventListener("change", atualizarHover);

  function organizar(cabecalho) {
    if (cabecalho.classList.contains("ro-header")) return;

    // O acesso à área do usuário é independente das ações Voltar/Sair da Home.
    const acesso = cabecalho.matches(".home-header") ? cabecalho.querySelector(".home-nav-center") : null;
    acesso?.remove();

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
    if (acesso) {
      acesso.classList.add("ro-header-access");
      cabecalho.append(acesso);
    }
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
    const partes = (origem.title || origem.querySelector("div")?.textContent.trim() || primeiroNome).trim().split(/\s+/);
    const ampliado = partes.length > 1 ? `${partes[0]} ${partes[partes.length - 1]}` : partes[0];
    const nome = document.createElement("span");
    nome.className = "ro-identity";
    nome.textContent = primeiroNome;
    nome.dataset.nomeAmpliado = ampliado;
    if (mouse.matches) nome.title = ampliado;
    origem.removeAttribute("title");
    origem.replaceChildren(nome);
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
