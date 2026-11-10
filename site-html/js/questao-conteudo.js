/* HTML identificado e sanitizado no servidor; texto legado permanece literal. */
(function () {
  const escapar = valor => String(valor ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  function renderizar(texto, formato, bateriaId, admin = false) {
    if (formato !== "html_v1") return `<span class="questao-texto-legado">${escapar(texto)}</span>`;
    // Mesma allowlist de conteúdo da teoria; defesa adicional no navegador.
    const html = DOMPurify.sanitize(texto || "", {ADD_TAGS: ["figure", "figcaption"], ADD_ATTR: ["class", "colspan", "rowspan"]});
    return `<div class="questao-conteudo-rico teoria-conteudo-rico" data-bateria-id="${escapar(bateriaId || "")}" data-admin="${admin}">${TeoriaImagens.paraLeitura(html)}</div>`;
  }
  const preparados = new WeakSet();
  const ativos = new Set();
  function preparar() {
    for (const raiz of ativos) if (!raiz.isConnected) { TeoriaImagens.cancelarLeitura(raiz); ativos.delete(raiz); }
    for (const raiz of document.querySelectorAll(".questao-conteudo-rico")) {
      if (preparados.has(raiz)) continue;
      preparados.add(raiz); ativos.add(raiz);
      TeoriaTabelas.preparar(raiz);
      TeoriaMatematica.renderizar(raiz);
      const query = new URLSearchParams(location.search);
      const contexto = new URLSearchParams();
      for (const chave of ["contratacao_id", "demonstracao_id"]) if (query.has(chave)) contexto.set(chave, query.get(chave));
      void TeoriaImagens.renderizar(raiz, raiz.dataset.admin === "true" ? null : {bateriaId: raiz.dataset.bateriaId, query: contexto.toString()});
    }
  }
  const observer = new MutationObserver(preparar);
  observer.observe(document.documentElement, {childList: true, subtree: true});
  window.QuestaoConteudo = {renderizar, preparar, escapar};
})();
