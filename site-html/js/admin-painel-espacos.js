/* Conserva a altura do card para cada largura e conjunto de áreas permitidas. */
(() => {
  function iniciar() {
    const card = document.querySelector('body.admin-shell main > .card');
    if (!card) return;
    let agendado = false;
    function ajustar() {
      agendado = false;
      const rolagem = {left: window.scrollX, top: window.scrollY};
      card.classList.remove('painel-compacto');
      card.style.removeProperty('--painel-espaco-final');
      const alturaOriginal = card.getBoundingClientRect().height;
      card.classList.add('painel-compacto');
      const alturaCompacta = card.getBoundingClientRect().height;
      card.style.setProperty('--painel-espaco-final', `${Math.max(0, alturaOriginal - alturaCompacta)}px`);
      if (window.scrollX !== rolagem.left || window.scrollY !== rolagem.top) {
        window.scrollTo({...rolagem, behavior: 'instant'});
      }
    }
    function agendar() {
      if (agendado) return;
      agendado = true;
      requestAnimationFrame(ajustar);
    }
    ajustar();
    new MutationObserver(mudancas => {
      if (mudancas.some(m => m.target !== card)) agendar();
    }).observe(card, {childList:true, subtree:true, attributes:true, attributeFilter:['style','hidden','class']});
    new ResizeObserver(agendar).observe(card);
    window.addEventListener('resize', agendar);
    document.fonts.ready.then(agendar);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar, {once:true}); else iniciar();
})();
