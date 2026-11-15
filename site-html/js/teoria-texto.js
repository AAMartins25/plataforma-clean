/* Somente apresentação das seções Texto, Vídeo e Questões; não altera conteúdo ou navegação. */
(() => {
  "use strict";
  const raiz = document.documentElement;

  window.TeoriaTexto = {
    ativar(secao) {
      raiz.classList.toggle("teoria-texto-root", secao === "teoria");
      raiz.classList.toggle("teoria-secoes-root", ["teoria", "video", "questoes"].includes(secao));
      raiz.dataset.secaoEstudo = secao;
    }
  };
})();
