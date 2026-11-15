/* A altura original varia com a quebra do nome do curso. Reduz apenas padding,
   conservando fontes e controles; nomes extremos têm prioridade sobre o corte. */
(() => {
  const iniciar = () => {
    const header = document.querySelector('.assuntos-page[data-page="assuntos"] .assuntos-header');
    if (!header) return;
    const main = document.querySelector('.assuntos-page main.container');
    // Mede a apresentação anterior fora do fluxo para conservar suas alturas
    // quando a largura maior ou o rótulo menor eliminarem quebras de linha.
    const preservarAlturas = () => {
      if (!main) return;
      const referencia = main.cloneNode(true);
      Object.assign(referencia.style, {
        position: 'absolute', left: '-100000px', top: '0',
        width: `${main.getBoundingClientRect().width}px`, maxWidth: 'none',
        margin: '0', visibility: 'hidden', pointerEvents: 'none'
      });
      referencia.setAttribute('aria-hidden', 'true');
      referencia.inert = true;
      const seletor = ':scope > .card, .assunto-curso-card';
      const cards = referencia.querySelectorAll(seletor);
      cards.forEach(card => card.style.removeProperty('min-height'));
      referencia.querySelectorAll(':scope > .card').forEach(card => {
        card.style.width = matchMedia('(min-width: 1024px)').matches ? '85%' : '100%';
      });
      const nome = new URLSearchParams(location.search).get('disciplina_nome');
      const identificacao = referencia.querySelector('#card_disciplina_titulo');
      if (nome && identificacao) identificacao.textContent = `Disciplina: ${nome}`;
      main.after(referencia);
      const alturas = Array.from(cards, card => card.getBoundingClientRect().height);
      referencia.remove();
      main.querySelectorAll(seletor).forEach((card, i) => {
        card.style.minHeight = `${alturas[i]}px`;
      });
    };
    let agendado = false;
    const ajustar = () => {
      agendado = false;
      header.style.removeProperty('--assuntos-header-reducao');
      if (!matchMedia('screen').matches) return;
      const altura = header.getBoundingClientRect().height;
      const padding = parseFloat(getComputedStyle(header).paddingTop);
      header.style.setProperty('--assuntos-header-reducao', `${Math.min(padding, altura * 0.065)}px`);
      preservarAlturas();
    };
    const agendar = () => {
      if (agendado) return;
      agendado = true;
      requestAnimationFrame(ajustar);
    };
    const observer = new ResizeObserver(agendar);
    header.querySelectorAll('.ro-header-titles, .ro-header-navigation').forEach(el => observer.observe(el));
    const lista = main?.querySelector('#lista');
    if (lista) new MutationObserver(agendar).observe(lista, { childList: true });
    window.addEventListener('resize', agendar);
    document.fonts.ready.then(agendar);
    ajustar();
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar, { once: true });
  else iniciar();
})();
