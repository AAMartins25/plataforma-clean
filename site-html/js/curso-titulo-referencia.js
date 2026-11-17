/* Reutiliza o cabeçalho de Disciplinas como referência visual do título. */
(() => {
  'use strict';
  function iniciar() {
    const header = document.querySelector('.curso-page .curso-header');
    const original = header?.querySelector('h1');
    if (!original) return;
    const copia = document.createElement('div');
    copia.className = 'curso-titulo-referencia';
    copia.setAttribute('aria-hidden', 'true');
    header.append(copia);
    const frame = document.createElement('iframe');
    frame.title = 'Referência visual de Disciplinas';
    frame.setAttribute('aria-hidden', 'true');
    frame.inert = true;
    frame.tabIndex = -1;
    Object.assign(frame.style, {position:'fixed', left:'-100000px', top:'0', height:'1px', border:'0', visibility:'hidden', pointerEvents:'none'});
    const url = p => new URL(p, document.baseURI).href;
    frame.srcdoc = `<!DOCTYPE html><html lang="pt-BR" class="disciplinas-assuntos-root" style="overflow:hidden"><head><meta charset="UTF-8">
      <link rel="stylesheet" href="${url('css/style.css')}"><link rel="stylesheet" href="${url('css/disciplinas-assuntos.css')}"><link rel="stylesheet" href="${url('css/disciplinas-layout.css?v=2')}">
      <script src="${url('js/cabecalho.js?v=altura6-1')}" defer><\/script><script src="${url('js/cabecalhos-altura.js?v=altura6-1')}" defer><\/script><script src="${url('js/disciplinas-layout.js?v=2')}" defer><\/script></head>
      <body class="disciplinas-page" data-page="disciplinas"><header class="disciplinas-header"><div style="margin-top:0"><h1 id="titulo_pagina" style="margin-bottom:0.0625rem"></h1></div><div class="disciplinas-header-acoes"><a class="btn" title="Voltar">⇦</a><a class="btn" title="Página inicial">⌂</a><a class="btn" title="Sair">⎋</a></div></header></body></html>`;
    let pronto = false, agendado = false;
    function agendar() {
      if (!pronto || agendado) return;
      agendado = true;
      requestAnimationFrame(() => { agendado = false; ajustar(); });
    }
    function ajustar() {
      if (!header.isConnected || !matchMedia('screen').matches) return;
      frame.style.width = `${document.documentElement.clientWidth}px`;
      const doc = frame.contentDocument, refHeader = doc.querySelector('header'), refTitulo = doc.querySelector('h1');
      if (refTitulo.textContent !== original.textContent) refTitulo.textContent = original.textContent;
      const identidade = header.querySelector('.ro-header-identity .ro-identity');
      let refIdentidade = doc.getElementById('nomeUsuarioLogadoGlobal');
      if (identidade && !refIdentidade) {
        refIdentidade = doc.createElement('div'); refIdentidade.id = 'nomeUsuarioLogadoGlobal';
        refIdentidade.textContent = identidade.textContent;
        refIdentidade.title = identidade.dataset.nomeAmpliado || identidade.textContent;
        doc.body.append(refIdentidade);
      } else if (identidade && refIdentidade) {
        const refNome = refIdentidade.querySelector('.ro-identity') || refIdentidade;
        if (refNome.textContent !== identidade.textContent) refNome.textContent = identidade.textContent;
      } else if (refIdentidade) refIdentidade.remove();
      doc.defaultView.CabecalhosAltura.ajustar(refHeader, refTitulo);
      // Recupera a altura natural antes de calcular qualquer ampliação necessária.
      if (window.Cabecalho?.comAlturaOriginal) window.Cabecalho.comAlturaOriginal(header, () => {});
      const faixa = header.getBoundingClientRect(), alvo = refTitulo.getBoundingClientRect(), estilo = doc.defaultView.getComputedStyle(refTitulo);
      if (copia.textContent !== original.textContent) copia.textContent = original.textContent;
      Object.assign(copia.style, {left:`${alvo.left - refHeader.getBoundingClientRect().left}px`, top:`${alvo.top - refHeader.getBoundingClientRect().top}px`, width:`${alvo.width}px`, font:estilo.font, lineHeight:estilo.lineHeight, letterSpacing:estilo.letterSpacing, color:estilo.color, textAlign:estilo.textAlign, overflowWrap:estilo.overflowWrap});
      const linhasReferencia = doc.createRange();
      linhasReferencia.selectNodeContents(refTitulo);
      const quantidade = [...linhasReferencia.getClientRects()].filter(r => r.width && r.height).length;
      if (quantidade > 1) copia.style.lineHeight = `${alvo.height / quantidade}px`;
      header.classList.add('curso-titulo-alinhado');
      const botoes = [...header.querySelectorAll('.ro-header-navigation a, .ro-header-navigation button')];
      for (const botao of botoes) botao.style.removeProperty('top');
      const range = document.createRange(); range.selectNodeContents(copia);
      const linhas = [...range.getClientRects()].filter(r => r.width && r.height);
      const colideHorizontal = (a,b) => a.left < b.right && a.right > b.left;
      let alturaNecessaria = Math.max(faixa.height, ...linhas.map(r => r.bottom - faixa.top));
      const posicoes = botoes.map(botao => {
        const caixa = botao.getBoundingClientRect();
        let topo = caixa.top;
        // Mover um botão pode aproximá-lo de outra linha: repete até não colidir.
        for (let i = 0; i <= linhas.length; i++) {
          const conflitos = linhas.filter(l => colideHorizontal(caixa,l) && topo < l.bottom && topo + caixa.height > l.top);
          if (!conflitos.length) break;
          topo = Math.max(...conflitos.map(l => l.bottom)) + 1 / 64;
        }
        alturaNecessaria = Math.max(alturaNecessaria, topo + caixa.height - faixa.top);
        return {botao, topo};
      });
      if (alturaNecessaria > faixa.height + 0.01) header.style.setProperty('height', `${alturaNecessaria}px`, 'important');
      // A grade pode redistribuir espaço ao crescer; conserva a posição calculada.
      for (const {botao, topo} of posicoes) {
        const diferenca = topo - botao.getBoundingClientRect().top;
        if (Math.abs(diferenca) > 0.001) botao.style.top = `${diferenca}px`;
      }
    }
    frame.addEventListener('load', () => {
      frame.contentWindow.CabecalhosAltura.pronto.then(() => {
        pronto = true;
        new MutationObserver(agendar).observe(frame.contentDocument.querySelector('header'), {childList:true, subtree:true, characterData:true});
        agendar();
      });
    }, {once:true});
    document.body.append(frame);
    new MutationObserver(agendar).observe(original, {childList:true, characterData:true, subtree:true});
    new MutationObserver(mutations => {
      if (mutations.some(m => m.target !== copia && !copia.contains(m.target))) agendar();
    }).observe(header, {childList:true, subtree:true, characterData:true});
    window.addEventListener('resize', agendar);
    document.fonts.ready.then(agendar);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar, {once:true}); else iniciar();
})();
