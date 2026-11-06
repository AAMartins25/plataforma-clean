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

  window.TeoriaMatematica = { LIMITE_FONTE, LIMITE_FORMULAS, validar, desenhar, renderizar };
})();
