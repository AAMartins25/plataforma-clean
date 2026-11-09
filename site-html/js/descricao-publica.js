(function () {
  const marcador = '<!--resumao:descricao-publica:html:v1-->';
  const tags = ['p', 'br', 'h2', 'h3', 'h4', 'strong', 'b', 'em', 'i', 'ul', 'ol', 'li'];
  function separar(valor) {
    const texto = String(valor || '');
    return { html: texto.startsWith(marcador), texto: texto.startsWith(marcador) ? texto.slice(marcador.length) : texto };
  }
  function limpar(html) {
    if (!window.DOMPurify) throw new Error('Proteção do conteúdo indisponível. Recarregue a página.');
    return DOMPurify.sanitize(html, { ALLOWED_TAGS: tags, ALLOWED_ATTR: [], ALLOW_DATA_ATTR: false, ALLOW_ARIA_ATTR: false });
  }
  function renderizar(elemento, valor, html) {
    const dados = typeof html === "string" ? { html: true, texto: html } : { html: false, texto: String(valor || "") };
    elemento.classList.add('descricao-publica');
    elemento.style.whiteSpace = dados.html ? 'normal' : 'pre-wrap';
    if (!dados.html) elemento.textContent = dados.texto || 'Informações ainda não cadastradas.';
    else {
      try { elemento.innerHTML = limpar(dados.texto); }
      catch (_) { elemento.textContent = 'Não foi possível exibir a descrição formatada. Recarregue a página.'; }
    }
  }
  window.DescricaoPublica = { separar, limpar, renderizar };
})();
