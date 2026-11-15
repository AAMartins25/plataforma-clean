/* Conserva fontes e controles, usando a altura efetiva de Funcionalidades. */
(() => {
  const iniciar = () => {
    const header = document.querySelector('.disciplinas-page[data-page="disciplinas"] .disciplinas-header');
    if (!header) return;
    let agendado = false;
    const ajustar = () => {
      agendado = false;
      window.CabecalhosAltura.ajustar(header, header.querySelector('h1'));
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
    window.CabecalhosAltura.pronto.then(agendar);
    ajustar();
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar, { once: true });
  else iniciar();
})();
