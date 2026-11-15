/* Referência visual isolada: usa o CSS de Funcionalidades sem executar a página. */
(() => {
  "use strict";
  const referencia = document.createElement("iframe");
  referencia.setAttribute("aria-hidden", "true");
  referencia.inert = true;
  referencia.tabIndex = -1;
  referencia.title = "Referência de altura do cabeçalho";
  Object.assign(referencia.style, {position: "fixed", left: "-100000px", top: "0",
    height: "1px", border: "0", visibility: "hidden", pointerEvents: "none"});
  let carregada = false;
  const pronto = new Promise(resolve => referencia.addEventListener("load", () => {
    referencia.contentDocument.fonts.ready.then(() => { carregada = true; resolve(); });
  }, {once: true}));
  const estilos = ["css/style.css", "css/curso-funcionalidades.css?v=5"]
    .map(url => `<link rel="stylesheet" href="${new URL(url, document.baseURI).href}">`).join("");
  referencia.srcdoc = `<!DOCTYPE html><html lang="pt-BR" class="curso-funcionalidades-root" style="overflow:hidden">
    <head><meta charset="UTF-8">${estilos}</head><body class="curso-page" data-page="curso">
    <header class="curso-header ro-header ro-header--identified">
      <div class="ro-header-titles"><div class="curso-header-titulo"><h1></h1></div></div>
      <div class="ro-header-navigation"><div class="curso-header-acoes">
        <a class="btn">⇦</a><a class="btn">⌂</a><a class="btn">⎋</a>
      </div></div>
      <div class="ro-header-identity"><span class="ro-identity">Aluno</span></div>
    </header></body></html>`;
  document.body.append(referencia);

  function medir(nome) {
    if (!carregada || !matchMedia("screen").matches) return null;
    referencia.style.width = `${document.documentElement.clientWidth}px`;
    const doc = referencia.contentDocument;
    doc.querySelector("h1").textContent = nome;
    const header = doc.querySelector("header");
    // A altura já inclui o respiro da referência. Libera esse espaço para
    // acomodar as fontes e os controles preservados das páginas de destino.
    return {altura: header.getBoundingClientRect().height, padding: 0};
  }

  function ajustar(header, titulo) {
    const medidas = medir(titulo.textContent);
    if (!medidas) return;
    header.style.setProperty("height", `${medidas.altura}px`, "important");
    header.style.setProperty("padding-block", `${medidas.padding}px`, "important");
    header.style.gridTemplateRows = "minmax(0, 1fr) auto";
    header.querySelector(".ro-header-titles").style.minHeight = "0";
    titulo.style.top = "0px";
    // Mantém a largura e a centralização originais. Só reposiciona verticalmente.
    for (let i = 0; i < 4; i++) {
      const faixa = header.getBoundingClientRect();
      const bloco = titulo.getBoundingClientRect();
      const range = document.createRange();
      range.selectNodeContents(titulo);
      const linhas = [...range.getClientRects()].filter(r => r.width && r.height);
      let minimo = 1;
      let maximo = faixa.height - bloco.height - 1;
      for (const controle of header.querySelectorAll(".ro-header-identity, .ro-header-navigation a")) {
        const r = controle.getBoundingClientRect();
        if (!r.width || !r.height) continue;
        for (const linha of linhas) {
          if (linha.right <= r.left - 4 || linha.left >= r.right + 4) continue;
          if (controle.matches(".ro-header-identity")) {
            minimo = Math.max(minimo, r.bottom - faixa.top + 4 - (linha.top - bloco.top));
          } else {
            maximo = Math.min(maximo, r.top - faixa.top - 4 - (linha.bottom - bloco.top));
          }
        }
      }
      const topo = Math.max(minimo, Math.min((faixa.height - bloco.height) / 2 - 4, maximo));
      titulo.style.top = `${parseFloat(titulo.style.top) + topo - (bloco.top - faixa.top)}px`;
      if (minimo <= maximo + 0.02) break;
      header.style.setProperty("height", `${faixa.height + minimo - maximo + 0.0625}px`, "important");
    }
  }
  window.CabecalhosAltura = {pronto, medir, ajustar};
})();
