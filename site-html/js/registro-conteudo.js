/* Anotações e conversas: conteúdo textual identificado, sem imagens. */
(function () {
  const tags = ['p','br','h2','h3','h4','strong','b','em','i','u','ul','ol','li','blockquote','a',
    'figure','figcaption','table','thead','tbody','tfoot','tr','th','td','span'];
  function sanitizar(texto) {
    const html = DOMPurify.sanitize(texto || '', {ALLOWED_TAGS: tags,
      ALLOWED_ATTR: ['href','class','style','colspan','rowspan'], ALLOW_DATA_ATTR: false, ALLOW_ARIA_ATTR: false});
    const t = document.createElement('template'); t.innerHTML = html;
    for (const el of t.content.querySelectorAll('*')) {
      const classe = el.getAttribute('class');
      if (!(el.tagName === 'SPAN' && classe === 'ro-math-inline') &&
          !(el.tagName === 'FIGURE' && ['table','ro-math-display'].includes(classe))) el.removeAttribute('class');
      const estilo = el.getAttribute('style');
      if (estilo) {
        const m = estilo.match(/^\s*text-align\s*:\s*(left|right|center|justify)\s*;?\s*$/i);
        el.removeAttribute('style');
        if (m && ['P','H2','H3','H4','TD','TH'].includes(el.tagName)) el.style.textAlign = m[1];
      }
      if (el.hasAttribute('href')) {
        const href = el.getAttribute('href');
        let seguro = false;
        try { const u = new URL(href, location.origin); seguro = !/[\s\\\x00-\x1f\x7f]/.test(href) && !href.startsWith('//') &&
          ((href.startsWith('/') && u.origin === location.origin) || (u.protocol === 'https:' && !u.username && !u.password)); } catch (_) {}
        if (el.tagName !== 'A' || !seguro) el.removeAttribute('href');
      }
    }
    return t.innerHTML;
  }
  const escapar = texto => String(texto ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  function renderizar(texto, formato) {
    return formato === 'html_v1' ? `<div class="registro-conteudo teoria-conteudo-rico">${sanitizar(texto)}</div>`
      : `<span class="registro-legado">${escapar(texto)}</span>`;
  }
  const preparados = new WeakSet();
  function preparar() {
    for (const el of document.querySelectorAll('.registro-conteudo')) {
      if (preparados.has(el)) continue;
      preparados.add(el); TeoriaTabelas.preparar(el); TeoriaMatematica.renderizar(el);
    }
  }
  new MutationObserver(preparar).observe(document.documentElement, {childList:true,subtree:true});
  window.RegistroConteudo = {sanitizar, renderizar, escapar, preparar};
})();
