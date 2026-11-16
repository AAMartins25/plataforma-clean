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
      // Só os três controles existentes aderem ao padrão; links de seção e
      // o acesso circular da Home conservam sua apresentação e seus eventos.
      const rotulo = (controle.getAttribute("aria-label") || controle.title || controle.textContent).trim();
      const simbolos = { "Voltar": "⇦", "Voltar para cursos": "⇦", "Início": "⌂", "Página inicial": "⌂", "Sair": "⎋" };
      if (Object.hasOwn(simbolos, rotulo)) {
        controle.classList.add("ro-nav-control");
        if (!controle.hasAttribute("aria-label")) controle.setAttribute("aria-label", rotulo);
        if (!controle.title) controle.title = rotulo;
        controle.dataset.roSimbolo = simbolos[rotulo];
        const texto = document.createElement("span");
        texto.className = "ro-nav-label";
        texto.append(...controle.childNodes);
        controle.append(texto);
      }
    }
  }

  const espacosOriginais = new WeakMap();
  function restaurarEspacos(cabecalho) {
    // Mede o layout próprio da página antes de aplicar a aparência comum.
    // Conserva o texto original para que a referência inclua links por extenso.
    // Tudo ocorre no mesmo frame, inclusive ao redimensionar ou receber o nome.
    const propriedades = ["padding-top", "padding-bottom", "row-gap"];
    if (!espacosOriginais.has(cabecalho)) {
      espacosOriginais.set(cabecalho, propriedades.map(p => [p,
        cabecalho.style.getPropertyValue(p), cabecalho.style.getPropertyPriority(p)]));
    }
    cabecalho.removeAttribute("data-navegacao-padrao");
    for (const [p, valor, prioridade] of espacosOriginais.get(cabecalho)) {
      if (valor) cabecalho.style.setProperty(p, valor, prioridade);
      else cabecalho.style.removeProperty(p);
    }
  }

  function padronizar(cabecalho) {
    restaurarEspacos(cabecalho);
    const propriedades = ["padding-top", "padding-bottom", "row-gap"];
    const altura = cabecalho.getBoundingClientRect().height;
    const identidade = cabecalho.querySelector(":scope > .ro-header-identity");
    if (identidade) cabecalho.style.setProperty("--ro-identidade-largura", `${identidade.getBoundingClientRect().width}px`);
    const estilo = getComputedStyle(cabecalho);
    const espacos = propriedades.map(p => parseFloat(estilo.getPropertyValue(p)) || 0);
    cabecalho.setAttribute("data-navegacao-padrao", "");
    let diferenca = cabecalho.getBoundingClientRect().height - altura;
    // Usa primeiro o respiro inferior, preservando a posição do título sempre
    // que possível. Não fixa a altura: títulos longos continuam com reflow.
    for (const indice of [1, 0, 2]) {
      if (Math.abs(diferenca) < 0.02) break;
      const ajuste = Math.min(espacos[indice], diferenca);
      cabecalho.style.setProperty(propriedades[indice], `${espacos[indice] - ajuste}px`, "important");
      diferenca = cabecalho.getBoundingClientRect().height - altura;
    }
  }
  // Os títulos calculados por script usam a área original de conteúdo,
  // independentemente do respiro consumido pelos controles padronizados.
  window.Cabecalho = {
    comAparenciaOriginal(cabecalho, calcular) {
      restaurarEspacos(cabecalho);
      try { return calcular(); }
      finally { padronizar(cabecalho); }
    }
  };

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
    padronizar(cabecalho);
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
    const espaco = parseFloat(getComputedStyle(document.documentElement).fontSize) / 4;
    const logo = marca.getBoundingClientRect();
    const direita = origem.getBoundingClientRect().right;
    const aoLado = largura <= direita - logo.right - espaco;
    const limite = direita - livro.getBoundingClientRect().right - espaco;
    nome.style.left = "";
    nome.style.width = `${Math.min(largura, Math.max(1, limite))}px`;
    const altura = nome.getBoundingClientRect().height;
    const topo = aoLado ? logo.top + (logo.height - altura) / 2 : logo.bottom + espaco;
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
      const topoAbaixo = Math.max(logo.bottom, livro.getBoundingClientRect().bottom) + espaco;
      for (const controle of controles) {
        const caixa = controle.getBoundingClientRect();
        if (caixa.left < botao.left - espaco && caixa.bottom > topoAbaixo) esquerda = Math.max(esquerda, caixa.right + espaco);
      }
      nome.style.width = `${Math.min(largura, Math.max(1, botao.left - esquerda - espaco))}px`;
      const caixa = origem.getBoundingClientRect();
      nome.style.left = `${botao.left - espaco - nome.getBoundingClientRect().width - caixa.left}px`;
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
