/* Somente apresentação da seção Texto; não altera conteúdo ou navegação. */
(() => {
  "use strict";
  const raiz = document.documentElement;
  const cabecalho = document.querySelector(".teoria-header");

  function atualizarAltura() {
    const altura = Math.ceil(cabecalho.getBoundingClientRect().height);
    raiz.style.setProperty("--texto-altura-cabecalho", `${altura}px`);
  }

  window.TeoriaTexto = {
    ativar(secao) {
      raiz.classList.toggle("teoria-texto-root", secao === "teoria");
      atualizarAltura();
    }
  };
  new ResizeObserver(atualizarAltura).observe(cabecalho);
})();
