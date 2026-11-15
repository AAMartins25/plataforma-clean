/* Somente apresentação: mede Disciplinas sem executar consultas ou regras de negócio. */
(() => {
  "use strict";
  function iniciar() {
    if (!document.body.matches(".questoes-criticas-page, .revisoes-programadas-page, .minhas-anotacoes-page, .mensagens-prof-page, .dashboard-aluno-page")) return;
    const header = document.querySelector("body > header.ro-header");
    const bloco = header?.querySelector(".ro-header-titles > div");
    if (!bloco) return;

    // O documento isolado usa os próprios estilos e o ajuste visual aprovado
    // de Disciplinas. Nenhum script de conteúdo, autenticação ou API é carregado.
    const referencia = document.createElement("iframe");
    referencia.title = "Referência de altura de Disciplinas";
    referencia.setAttribute("aria-hidden", "true");
    referencia.inert = true;
    referencia.tabIndex = -1;
    Object.assign(referencia.style, {position: "fixed", left: "-100000px", top: "0",
      height: "1px", border: "0", visibility: "hidden", pointerEvents: "none"});
    const url = caminho => new URL(caminho, document.baseURI).href;
    const estilos = ["css/style.css", "css/disciplinas-assuntos.css", "css/disciplinas-layout.css?v=2"]
      .map(caminho => `<link rel="stylesheet" href="${url(caminho)}">`).join("");
    let pronta = false;
    referencia.addEventListener("load", () => {
      referencia.contentWindow.CabecalhosAltura.pronto.then(() => { pronta = true; agendar(); });
    }, {once: true});
    referencia.srcdoc = `<!DOCTYPE html><html lang="pt-BR" class="disciplinas-assuntos-root" style="overflow:hidden">
      <head><meta charset="UTF-8">${estilos}<script src="${url("js/cabecalhos-altura.js?v=1")}" defer></script></head>
      <body class="disciplinas-page" data-page="disciplinas">
      <header class="disciplinas-header ro-header ro-header--identified">
        <div class="ro-header-titles"><div><h1 id="titulo_pagina"></h1></div></div>
        <div class="ro-header-navigation"><div class="disciplinas-header-acoes">
          <a class="btn">⇦</a><a class="btn">⌂</a><a class="btn">⎋</a>
        </div></div>
        <div class="ro-header-identity"><span class="ro-identity"></span></div>
      </header></body></html>`;

    function medirLayout() {
      if (!pronta || !matchMedia("screen").matches) return;
      header.removeAttribute("data-altura-disciplinas");
      const original = bloco.getBoundingClientRect();
      const faixa = header.getBoundingClientRect();
      referencia.style.width = `${document.documentElement.clientWidth}px`;
      const janela = referencia.contentWindow;
      const doc = referencia.contentDocument;
      const titulo = doc.querySelector("h1");
      titulo.textContent = header.querySelector("h1")?.textContent.trim()
        || new URLSearchParams(location.search).get("curso_nome") || "Curso";
      doc.querySelector(".ro-identity").textContent = header.querySelector(".ro-identity")?.textContent || "";
      janela.CabecalhosAltura.ajustar(doc.querySelector("header"), titulo);
      const altura = doc.querySelector("header").getBoundingClientRect().height;
      if (Math.abs(faixa.height - altura) < 0.02) return;
      header.style.setProperty("--funcionalidade-header-altura", `${altura}px`);
      header.style.setProperty("--funcionalidade-titulo-width", `${original.width}px`);
      header.style.setProperty("--funcionalidade-titulo-left", `${original.left - faixa.left}px`);
      header.setAttribute("data-altura-disciplinas", "");
      for (let tentativa = 0; tentativa < 4; tentativa++) {
        const atual = header.getBoundingClientRect();
        const caixa = bloco.getBoundingClientRect();
        const linhas = [...bloco.querySelectorAll("h1, h2")].flatMap(nome => {
          const range = document.createRange();
          range.selectNodeContents(nome);
          return [...range.getClientRects()].filter(r => r.width && r.height);
        });
        let minimo = 1;
        let maximo = atual.height - caixa.height - parseFloat(getComputedStyle(header).borderBottomWidth);
        for (const controle of header.querySelectorAll(".ro-header-identity, .ro-header-navigation a")) {
          const r = controle.getBoundingClientRect();
          if (!r.width || !r.height) continue;
          for (const linha of linhas) {
            if (linha.right <= r.left - 4 || linha.left >= r.right + 4) continue;
            if (controle.matches(".ro-header-identity")) {
              minimo = Math.max(minimo, r.bottom - atual.top + 4 - (linha.top - caixa.top));
            } else {
              maximo = Math.min(maximo, r.top - atual.top - 4 - (linha.bottom - caixa.top));
            }
          }
        }
        header.style.setProperty("--funcionalidade-titulo-top", `${Math.max(minimo, Math.min((atual.height - caixa.height) / 2 - 4, maximo))}px`);
        if (minimo <= maximo + 0.02) break;
        header.style.setProperty("--funcionalidade-header-altura", `${atual.height + minimo - maximo + 0.0625}px`);
      }
    }
    function ajustar() {
      if (!document.body.matches(".dashboard-aluno-page, .mensagens-prof-page, .minhas-anotacoes-page, .revisoes-programadas-page")) return medirLayout();
      // Conserva a geometria aprovada; a fonte maior usa a mesma altura de linha.
      header.setAttribute("data-medir-cabecalho", "");
      try { medirLayout(); }
      finally { header.removeAttribute("data-medir-cabecalho"); }
    }
    let agendado = false;
    function agendar() {
      if (agendado) return;
      agendado = true;
      requestAnimationFrame(() => { agendado = false; ajustar(); });
    }
    new MutationObserver(agendar).observe(header, {childList: true, subtree: true, characterData: true});
    const observador = new ResizeObserver(agendar);
    observador.observe(bloco);
    observador.observe(header.querySelector(".ro-header-navigation"));
    window.addEventListener("resize", agendar);
    document.fonts.ready.then(agendar);
    document.body.append(referencia);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar, {once: true});
  else iniciar();
})();
