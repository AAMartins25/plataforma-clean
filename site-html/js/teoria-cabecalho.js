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

    function compactar() {
      const referenciaFuncionalidades = window.CabecalhosAltura.medir(cursoNome);
      if (!referenciaFuncionalidades) return;
      // Conserva inclusive os tamanhos efetivos escolhidos pelo ajuste anterior.
      // Preserva a ampliação vigente do assunto ao recompor esses tamanhos.
      const assunto = titulos[2];
      assunto.style.fontSize = `${parseFloat(getComputedStyle(assunto).fontSize) * 1.13}px`;
      contexto.classList.add("teoria-contexto--interno");
      if (contexto.parentElement !== faixa) faixa.append(contexto);
      faixa.style.setProperty("--teoria-header-padding", `${referenciaFuncionalidades.padding}px`);
      faixa.style.setProperty("--teoria-header-altura", `${referenciaFuncionalidades.altura}px`);
      faixa.classList.add("teoria-header--compacto");
      const ajustarTopo = () => {
        const rect = faixa.getBoundingClientRect();
        const box = contexto.getBoundingClientRect();
        const linhas = titulos.filter(el => !el.hidden).flatMap(el => {
          const range = document.createRange();
          range.selectNodeContents(el);
          return [...range.getClientRects()];
        });
        let minimo = 1;
        let maximo = rect.height - box.height
          - parseFloat(getComputedStyle(faixa).borderBottomWidth);
        for (const controle of faixa.querySelectorAll(".ro-header-identity, .teoria-header-acoes .btn")) {
          const r = controle.getBoundingClientRect();
          if (!r.width || !r.height) continue;
          for (const linha of linhas) {
            if (linha.right <= r.left - 4 || linha.left >= r.right + 4) continue;
            if (controle.matches(".ro-header-identity")) {
              minimo = Math.max(minimo, r.bottom - rect.top + 4 - (linha.top - box.top));
            } else {
              maximo = Math.min(maximo, r.top - rect.top - 6 - (linha.bottom - box.top));
            }
          }
        }
        contexto.style.top = `${Math.max(minimo, Math.min((rect.height - box.height) / 2 - 4, maximo))}px`;
        return Math.max(0, minimo - maximo);
      };
      // As ações ficam na última linha do grid; ampliar a faixa abre espaço entre elas e o aluno.
      for (let i = 0; i < 4; i++) {
        const falta = ajustarTopo();
        if (falta < 0.02) break;
        faixa.style.setProperty("--teoria-header-altura", `${faixa.getBoundingClientRect().height + falta + 0.0625}px`);
      }
      ajustarTopo();
    }

    function atualizar() {
      faixa.classList.remove("teoria-header--compacto");
      [cursoNome, referencia.querySelector("#titulo_disciplina")?.textContent || "",
        referencia.querySelector("#titulo_assunto_header")?.textContent || ""]
        .forEach((texto, i) => {
          if (titulos[i].textContent !== texto) titulos[i].textContent = texto;
          titulos[i].hidden = !texto;
          titulos[i].removeAttribute("style");
        });

      // Fora do fluxo do grid: a referência invisível preserva a geometria original,
      // inclusive ao redimensionar a janela e após carregar o nome do aluno.
      contexto.classList.add("teoria-contexto--interno");
      contexto.removeAttribute("style");
      if (contexto.parentElement !== faixa) faixa.append(contexto);
      const rect = faixa.getBoundingClientRect();
      const estilo = getComputedStyle(faixa);
      const topo = parseFloat(estilo.paddingTop);
      const folha = (document.querySelector("#detalhes_aula > .card") || document.querySelector(".teoria-assunto-faixa")).getBoundingClientRect();
      const centro = folha.left + folha.width / 2;
      const largura = Math.max(0, Math.min(folha.width, 2 * (centro - rect.left - parseFloat(estilo.paddingLeft)),
        2 * (rect.right - parseFloat(estilo.paddingRight) - centro)));
      const esquerda = centro - rect.left - largura / 2;
      const controles = [...faixa.querySelectorAll(".teoria-header-acoes .btn, .ro-header-identity")]
        .map(el => el.getBoundingClientRect()).filter(r => r.width && r.height);
      const altura = rect.height - topo - parseFloat(estilo.paddingBottom)
        - parseFloat(estilo.borderTopWidth) - parseFloat(estilo.borderBottomWidth);
      const acoes = [...faixa.querySelectorAll(".teoria-header-acoes .btn")].map(el => el.getBoundingClientRect());
      const limiteInferior = rect.top + topo + altura;
      const alunoRect = faixa.querySelector(".ro-header-identity")?.getBoundingClientRect();
      if (alunoRect?.width) {
        // O curso pode quebrar em linhas centralizadas sem invadir o nome do aluno.
        titulos[0].style.maxWidth = `${Math.max(1, Math.min(largura, 2 * (alunoRect.left - 8 - centro)))}px`;
        titulos[0].style.marginInline = "auto";
      }
      contexto.style.width = `${largura}px`;
      contexto.style.left = `${esquerda}px`;
      contexto.style.top = `${topo}px`;
      const tamanhos = titulos.map(el => parseFloat(getComputedStyle(el).fontSize));
      const cabe = () => {
        const atual = contexto.getBoundingClientRect();
        const linhas = () => titulos.filter(el => !el.hidden).flatMap(el => {
          const range = document.createRange();
          range.selectNodeContents(el);
          return [...range.getClientRects()];
        });
        // Só reserve espaço acima das ações onde uma linha cruza sua coluna.
        const limiteAcoes = Math.min(Infinity, ...linhas().flatMap(r => acoes
          .filter(c => r.right > c.left - 4 && r.left < c.right + 4)
          .map(c => c.top - 6 - (r.bottom - atual.top) - rect.top)));
        // Elevação de 4 px, respeitando os controles e o limite superior da faixa.
        contexto.style.top = `${Math.max(topo, Math.min(topo + (altura - atual.height) / 2 - 4, limiteAcoes))}px`;
        if (contexto.getBoundingClientRect().bottom > limiteInferior || largura <= 0) return false;
        return linhas().every(r => controles.every(c =>
          r.right <= c.left - 4 || r.left >= c.right + 4 || r.bottom <= c.top - 4 || r.top >= c.bottom + 4));
      };
      const reduzir = escala => titulos.forEach((el, i) => {
        el.style.fontSize = `${Math.max(12, tamanhos[i] * escala)}px`;
      });

      if (!cabe()) {
        reduzir(0);
        if (!cabe()) {
          // A apresentação anterior usava o tamanho original nestes casos.
          // Conserva essas fontes, agora acomodadas dentro da faixa compacta.
          contexto.classList.remove("teoria-contexto--interno");
          contexto.removeAttribute("style");
          titulos.forEach(el => el.removeAttribute("style"));
          faixa.after(contexto);
          contexto.style.width = `${folha.width}px`;
          contexto.style.left = `${folha.left - rect.left}px`;
          compactar();
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
      cabe();
      compactar();
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
    window.CabecalhosAltura.pronto.then(agendar);
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
