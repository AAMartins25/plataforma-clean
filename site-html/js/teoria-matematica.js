/* LaTeX é dado; somente a distribuição local do KaTeX produz a visualização. */
(function () {
  "use strict";
  const LIMITE_FONTE = 4096, LIMITE_FORMULAS = 200;
  const seletor = "span.ro-math-inline,figure.ro-math-display";
  const renderizados = new WeakSet();

  function validar(fonte) {
    if (typeof fonte !== "string" || !fonte.trim()) throw new Error("Digite a fórmula em LaTeX.");
    if (fonte.length > LIMITE_FONTE) throw new Error("Cada fórmula pode ter até 4.096 caracteres.");
    if (/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f\ufffd]/u.test(fonte)) throw new Error("A fórmula contém caracteres inválidos.");
  }

  // Somente delimitadores explícitos. Um dólar isolado continua sendo texto.
  function delimitador(texto, pos) {
    const abertura = texto.slice(pos, pos + 2);
    if (abertura !== "\\(" && abertura !== "\\[" && abertura !== "$$") return null;
    let barras = 0;
    for (let p = pos - 1; p >= 0 && texto[p] === "\\"; p--) barras++;
    if (barras % 2) return null;
    if (abertura === "\\(" || abertura === "\\[") {
      return { abertura, fechamento: abertura === "\\(" ? "\\)" : "\\]", bloco: abertura === "\\[" };
    }
    if (abertura === "$$" && texto[pos - 1] !== "$" && texto[pos + 2] !== "$") {
      return { abertura, fechamento: "$$", bloco: true };
    }
    return null;
  }

  function fechamentos(texto, fechamento) {
    const posicoes = [];
    let pos = texto.indexOf(fechamento);
    while (pos !== -1) {
      let barras = 0;
      for (let p = pos - 1; p >= 0 && texto[p] === "\\"; p--) barras++;
      if (barras % 2 === 0 && (fechamento !== "$$" || delimitador(texto, pos))) posicoes.push(pos);
      pos = texto.indexOf(fechamento, pos + 2);
    }
    return posicoes;
  }

  function intervalos(texto) {
    const resultado = [], cache = new Map();
    for (let pos = 0; pos < texto.length - 1;) {
      const info = delimitador(texto, pos);
      if (!info) { pos++; continue; }
      if (!cache.has(info.fechamento)) cache.set(info.fechamento, fechamentos(texto, info.fechamento));
      const lista = cache.get(info.fechamento);
      let a = 0, b = lista.length;
      while (a < b) { const meio = (a + b) >>> 1; if (lista[meio] < pos + 2) a = meio + 1; else b = meio; }
      const fim = lista[a];
      if (fim === undefined) { pos += 2; continue; }
      const fonte = texto.slice(pos + 2, fim);
      validar(fonte);
      resultado.push({ inicio: pos, fim: fim + 2, fonte, bloco: info.bloco });
      if (resultado.length > LIMITE_FORMULAS) throw new Error("Cada conteúdo pode ter até 200 fórmulas.");
      pos = fim + 2;
    }
    return resultado;
  }

  function desenhar(alvo, fonte, bloco) {
    // Erros nunca são interpolados como HTML. A fonte continua disponível.
    alvo.textContent = fonte;
    alvo.classList.remove("ro-math-error");
    try {
      validar(fonte);
      if (!window.katex) throw new Error("Visualização matemática indisponível.");
      window.katex.render(fonte, alvo, {
        displayMode: Boolean(bloco), output: "htmlAndMathml", trust: false,
        strict: "error", throwOnError: true, maxSize: 20, maxExpand: 200,
        macros: {}, globalGroup: false
      });
      return true;
    } catch (_) {
      alvo.textContent = fonte;
      alvo.classList.add("ro-math-error");
      return false;
    }
  }

  function renderizar(raiz) {
    if (!raiz) return;
    const elementos = [...raiz.querySelectorAll(seletor)];
    for (const [indice, no] of elementos.entries()) {
      if (renderizados.has(no)) continue;
      // Marcação recebida deve conter exclusivamente texto, nunca HTML KaTeX.
      if (no.children.length || indice >= LIMITE_FORMULAS) continue;
      const fonte = no.textContent;
      if (desenhar(no, fonte, no.tagName === "FIGURE")) renderizados.add(no);
    }
  }

  window.TeoriaMatematica = { LIMITE_FONTE, LIMITE_FORMULAS, validar, desenhar, renderizar, delimitador, fechamentos, intervalos };
})();
