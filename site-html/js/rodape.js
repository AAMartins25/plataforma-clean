/* Ano dos rodapés, inclusive páginas legadas sem atualização própria. */
(() => {
  const ano = String(new Date().getFullYear());
  document.querySelectorAll('footer [data-current-year], footer #ano_atual, footer #anoAtual')
    .forEach(elemento => { elemento.textContent = ano; });
})();
