/* Apresentação exclusiva da leitura; não altera sessão, navegação ou conteúdo. */
(() => {
  "use strict";

  function iniciar() {
    const faixa = document.querySelector(".teoria-page .teoria-header.ro-header");
    const referencia = faixa?.querySelector(".teoria-header-identificacao");
    if (!referencia) return;

    const params = new URLSearchParams(location.search);
    let cursoNome = params.get("curso_nome") || "";
    const contexto = document.createElement("div");
    contexto.className = "teoria-contexto";
    const titulos = ["curso", "disciplina", "assunto"].map((tipo, i) => {
      const el = document.createElement(["h1", "h2", "p"][i]);
      el.className = `teoria-contexto-${tipo}`;
      contexto.append(el);
      return el;
    });
    referencia.setAttribute("aria-hidden", "true");
    faixa.classList.add("teoria-header--contexto");

    function atualizar() {
      [cursoNome, referencia.querySelector("#titulo_disciplina")?.textContent || "",
        referencia.querySelector("#titulo_assunto_header")?.textContent || ""]
        .forEach((texto, i) => {
          if (titulos[i].textContent !== texto) titulos[i].textContent = texto;
          titulos[i].hidden = !texto;
          titulos[i].style.removeProperty("font-size");
        });

      // Fora do fluxo do grid: a referência invisível preserva a geometria original,
      // inclusive ao redimensionar a janela e após carregar o nome do aluno.
      contexto.classList.add("teoria-contexto--interno");
      if (contexto.parentElement !== faixa) faixa.append(contexto);
      const rect = faixa.getBoundingClientRect();
      const estilo = getComputedStyle(faixa);
      const esquerda = parseFloat(estilo.paddingLeft);
      const topo = parseFloat(estilo.paddingTop);
      const controles = [...faixa.querySelectorAll(".teoria-header-acoes .btn, .ro-header-identity")]
        .map(el => el.getBoundingClientRect()).filter(r => r.width && r.height);
      const limite = Math.min(rect.right - parseFloat(estilo.paddingRight),
        ...controles.map(r => r.left - 8));
      const largura = Math.max(0, limite - rect.left - esquerda);
      const altura = rect.height - topo - parseFloat(estilo.paddingBottom)
        - parseFloat(estilo.borderTopWidth) - parseFloat(estilo.borderBottomWidth);
      contexto.style.width = `${largura}px`;
      contexto.style.left = `${esquerda}px`;
      contexto.style.top = `${topo}px`;
      const tamanhos = titulos.map(el => parseFloat(getComputedStyle(el).fontSize));
      const cabe = () => contexto.getBoundingClientRect().height <= altura && largura > 0;
      const reduzir = escala => titulos.forEach((el, i) => {
        el.style.fontSize = `${Math.max(12, tamanhos[i] * escala)}px`;
      });

      if (!cabe()) {
        reduzir(0);
        if (!cabe()) {
          // Nomes excepcionais ficam completos, em tamanho original e no fluxo.
          contexto.classList.remove("teoria-contexto--interno");
          contexto.removeAttribute("style");
          titulos.forEach(el => el.style.removeProperty("font-size"));
          faixa.after(contexto);
          return;
        }
        let minimo = 0;
        let maximo = 1;
        for (let i = 0; i < 12; i++) {
          const escala = (minimo + maximo) / 2;
          reduzir(escala);
          if (cabe()) minimo = escala;
          else maximo = escala;
        }
        reduzir(minimo);
      }
      contexto.style.top = `${topo + (altura - contexto.getBoundingClientRect().height) / 2}px`;
    }

    let agendado = false;
    function agendar() {
      if (agendado) return;
      agendado = true;
      requestAnimationFrame(() => { agendado = false; atualizar(); });
    }
    new MutationObserver(agendar).observe(referencia, {childList: true, subtree: true});
    const observador = new ResizeObserver(agendar);
    observador.observe(faixa);
    const aluno = faixa.querySelector("#nome_aluno_logado");
    if (aluno) observador.observe(aluno);
    window.addEventListener("resize", agendar);
    document.fonts.ready.then(agendar);
    atualizar();

    // Links antigos que têm contexto, mas não carregam o nome na URL.
    if (!cursoNome && (params.has("curso_id") || params.has("contratacao_id") || params.has("demonstracao_id"))) {
      window.apiGet("/me/cursos").then(acessos => {
        const acesso = acessos.find(item => ["curso_id", "contratacao_id", "demonstracao_id"]
          .filter(chave => params.has(chave))
          .every(chave => String(item[chave]) === params.get(chave)));
        if (acesso?.nome_curso) { cursoNome = acesso.nome_curso; agendar(); }
      }).catch(() => { /* Uma falha no nome não interrompe a leitura. */ });
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar, {once: true});
  else iniciar();
})();
