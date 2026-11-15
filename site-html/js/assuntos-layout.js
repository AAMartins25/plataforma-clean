/* A altura original varia com a quebra do nome do curso. Reduz apenas padding,
   conservando fontes e controles; nomes extremos têm prioridade sobre o corte. */
(() => {
  const iniciar = () => {
    const header = document.querySelector('.assuntos-page[data-page="assuntos"] .assuntos-header');
    if (!header) return;
    let agendado = false;
    const ajustar = () => {
      agendado = false;
      header.style.removeProperty('--assuntos-header-reducao');
      if (!matchMedia('screen').matches) return;
      const altura = header.getBoundingClientRect().height;
      const padding = parseFloat(getComputedStyle(header).paddingTop);
      header.style.setProperty('--assuntos-header-reducao', `${Math.min(padding, altura * 0.065)}px`);
    };
    const agendar = () => {
      if (agendado) return;
      agendado = true;
      requestAnimationFrame(ajustar);
    };
    const observer = new ResizeObserver(agendar);
    header.querySelectorAll('.ro-header-titles, .ro-header-navigation').forEach(el => observer.observe(el));
    window.addEventListener('resize', agendar);
    document.fonts.ready.then(agendar);
    ajustar();
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar, { once: true });
  else iniciar();
})();
