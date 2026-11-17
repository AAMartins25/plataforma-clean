/* Centraliza o título sem tirá-lo do fluxo que determina a altura do painel. */
(() => {
  function iniciar() {
    const header = document.querySelector('body.admin-shell > header');
    const titulo = header?.querySelector('.admin-titulo-destaque');
    if (!titulo) return;
    let agendado = false;
    function agendar() {
      if (agendado) return;
      agendado = true;
      requestAnimationFrame(() => {
        agendado = false;
        if (!matchMedia('screen').matches) return;
        const faixa = header.getBoundingClientRect(), caixa = titulo.getBoundingClientRect();
        const atual = parseFloat(header.style.getPropertyValue('--painel-titulo-deslocamento')) || 0;
        const deslocamento = atual + (faixa.top + faixa.height / 2) - (caixa.top + caixa.height / 2);
        if (Math.abs(deslocamento - atual) > 0.01) header.style.setProperty('--painel-titulo-deslocamento', `${deslocamento}px`);
      });
    }
    new ResizeObserver(agendar).observe(header);
    new MutationObserver(agendar).observe(header, {childList:true, subtree:true, characterData:true});
    window.addEventListener('resize', agendar);
    document.fonts.ready.then(agendar);
    agendar();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar, {once:true}); else iniciar();
})();
