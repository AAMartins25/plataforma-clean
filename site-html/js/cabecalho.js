/* Apresentação compartilhada. Não consulta APIs nem altera links, sessão ou handlers. */
(() => {
  "use strict";

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
    alinharNomeNaMarca(cabecalho);
  }

  function alinharNomeNaMarca(cabecalho) {
    if (!cabecalho.matches(".home-header.ro-header--identified")) return;
    const marca = cabecalho.querySelector(".home-brand-name");
    const livro = cabecalho.querySelector(".home-brand-symbol");
    const origem = cabecalho.querySelector(".ro-header-identity");
    const nome = origem?.querySelector(".ro-identity");
    if (!marca || !livro || !nome) return;

    nome.style.whiteSpace = "nowrap";
    const texto = document.createRange();
    texto.selectNodeContents(nome);
    const largura = Math.ceil(texto.getBoundingClientRect().width * 64) / 64;
    nome.style.whiteSpace = "";
    const logo = marca.getBoundingClientRect();
    const direita = origem.getBoundingClientRect().right;
    const aoLado = largura <= direita - logo.right - 4;
    const limite = direita - livro.getBoundingClientRect().right - 4;
    nome.style.left = "";
    nome.style.width = `${Math.min(largura, Math.max(1, limite))}px`;
    const altura = nome.getBoundingClientRect().height;
    const topo = aoLado ? logo.top + (logo.height - altura) / 2 : logo.bottom + 4;
    nome.style.top = `${topo - origem.getBoundingClientRect().top}px`;
    const acesso = cabecalho.querySelector(".ro-header-access a");
    const navegacao = cabecalho.querySelector(".ro-header-navigation");
    const controles = Array.from(navegacao?.querySelectorAll("a, button") || [])
      .filter(elemento => elemento.getClientRects().length);
    const sobrepoe = (a, b) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
    // Se um nome precisar de várias linhas, usa o espaço abaixo do livro e ao lado do acesso.
    if (!aoLado && acesso && [livro, acesso, ...controles]
      .some(elemento => sobrepoe(nome.getBoundingClientRect(), elemento.getBoundingClientRect()))) {
      const botao = acesso.getBoundingClientRect();
      let esquerda = cabecalho.getBoundingClientRect().left + parseFloat(getComputedStyle(cabecalho).paddingLeft);
      const topoAbaixo = Math.max(logo.bottom, livro.getBoundingClientRect().bottom) + 4;
      for (const controle of controles) {
        const caixa = controle.getBoundingClientRect();
        if (caixa.left < botao.left - 4 && caixa.bottom > topoAbaixo) esquerda = Math.max(esquerda, caixa.right + 4);
      }
      nome.style.width = `${Math.min(largura, Math.max(1, botao.left - esquerda - 4))}px`;
      const caixa = origem.getBoundingClientRect();
      nome.style.left = `${botao.left - 4 - nome.getBoundingClientRect().width - caixa.left}px`;
      nome.style.top = `${topoAbaixo - caixa.top}px`;
    }
    cabecalho.dataset.nomePosicao = aoLado ? "direita" : "abaixo";
    // O nome completo continua disponível sem uma cópia sobrepor a marca no hover.
    if (nome.title !== nome.dataset.nomeAmpliado) nome.title = nome.dataset.nomeAmpliado;
  }

  function iniciar() {
    atualizar();
    // As páginas atuais inserem o nome depois de suas consultas já existentes.
    let agendado = false;
    const agendar = () => {
      if (agendado) return;
      agendado = true;
      requestAnimationFrame(() => {
        agendado = false;
        atualizar();
      });
    };
    new MutationObserver(agendar).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["title"] });
    window.addEventListener("resize", agendar);
    const cabecalho = document.querySelector("body > header.home-header");
    if (cabecalho) new ResizeObserver(agendar).observe(cabecalho);
    document.fonts.ready.then(agendar);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar, { once: true });
  else iniciar();
})();
