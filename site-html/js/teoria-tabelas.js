/* Só a apresentação da leitura muda; o HTML salvo e a paginação permanecem intactos. */
(() => {
  function preparar(raiz) {
    for (const tabela of raiz.querySelectorAll('table')) {
      const grade = [];
      const cabecalhos = [];
      let colunas = 0;
      const linhas = Array.from(tabela.rows);
      linhas.forEach((linha, y) => {
        grade[y] ||= [];
        let x = 0;
        for (const celula of linha.cells) {
          while (grade[y][x]) x++;
          const largura = celula.colSpan;
          const altura = celula.getAttribute('rowspan') === '0' ? linhas.length - y : celula.rowSpan;
          const titulo = celula.textContent.trim();
          const cabecalho = linha.parentElement.tagName === 'THEAD' ||
            (y === 0 && Array.from(linha.cells).every(c => c.tagName === 'TH'));
          const rotulos = [];
          for (let c = x; c < x + largura; c++) {
            if (cabecalho && titulo) (cabecalhos[c] ||= []).push(titulo);
            rotulos.push(cabecalhos[c]?.join(' / ') || `Coluna ${c + 1}`);
          }
          if (!cabecalho) {
            // Repetir o contexto de células mescladas nas linhas seguintes.
            const contexto = [...new Set(grade[y].filter(Boolean))]
              .filter(item => item.linha < y).map(item => item.texto).filter(Boolean);
            celula.dataset.teoriaRotulo = [...new Set([...contexto, ...rotulos])].join(' — ');
          }
          const item = {linha: y, texto: titulo};
          for (let r = y; r < Math.min(y + altura, linhas.length); r++) {
            grade[r] ||= [];
            for (let c = x; c < x + largura; c++) grade[r][c] = item;
          }
          x += largura;
          colunas = Math.max(colunas, x);
        }
      });
      // Habilita a apresentação por linha quando a área de leitura for estreita.
      tabela.dataset.teoriaColunas = colunas >= 7 ? 'extensas' : colunas >= 3 ? 'muitas' : 'poucas';
    }
  }
  window.TeoriaTabelas = {preparar};
})();
