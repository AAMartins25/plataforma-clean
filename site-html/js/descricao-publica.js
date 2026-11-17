(function () {
  const marcador = '<!--resumao:descricao-publica:html:v1-->';
  const tags = ['p', 'br', 'hr', 'span', 'h2', 'h3', 'h4', 'strong', 'b', 'em', 'i', 'ul', 'ol', 'li', 'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td'];
  function separar(valor) {
    const texto = String(valor || '');
    return { html: texto.startsWith(marcador), texto: texto.startsWith(marcador) ? texto.slice(marcador.length) : texto };
  }
  function limpar(html) {
    if (!window.DOMPurify) throw new Error('Proteção do conteúdo indisponível. Recarregue a página.');
    const limpo = DOMPurify.sanitize(html, { ALLOWED_TAGS: tags, ALLOWED_ATTR: ['colspan', 'rowspan', 'style'], ALLOW_DATA_ATTR: false, ALLOW_ARIA_ATTR: false });
    const template = document.createElement('template'); template.innerHTML = limpo;
    for (const no of template.content.querySelectorAll('[style]')) {
      const tamanho = no.getAttribute('style').match(/^\s*font-size\s*:\s*(\d{1,2})px\s*;?\s*$/i);
      if (no.tagName === 'SPAN' && tamanho && +tamanho[1] >= 10 && +tamanho[1] <= 48) no.setAttribute('style', `font-size:${+tamanho[1]}px`);
      else {
        const alinhamento = no.getAttribute('style').match(/^\s*text-align\s*:\s*(left|center|right|justify)\s*;?\s*$/i);
        if (['P', 'H2', 'H3', 'H4', 'LI'].includes(no.tagName) && alinhamento) no.setAttribute('style', `text-align:${alinhamento[1].toLowerCase()}`);
        else no.removeAttribute('style');
      }
    }
    return template.innerHTML;
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
