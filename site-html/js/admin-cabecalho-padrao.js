/* Usa o cabeçalho real do painel como referência, sem executar sua página. */
(() => {
  'use strict';
  async function iniciar() {
    const header = document.querySelector('body.admin-cabecalho-padrao > header');
    if (!header) return;
    const resposta = await fetch(new URL('index.html', location.href)).catch(() => null);
    if (!resposta?.ok) return;
    const painel = new DOMParser().parseFromString(await resposta.text(), 'text/html');
    const modelo = painel.querySelector('body > header');
    if (!modelo) return;
    const url = p => new URL(`../${p}`, location.href).href;
    const referencia = document.createElement('iframe');
    referencia.title = 'Referência do cabeçalho administrativo';
    referencia.setAttribute('aria-hidden', 'true');
    referencia.inert = true;
    referencia.tabIndex = -1;
    Object.assign(referencia.style, {position:'fixed',left:'-100000px',top:'0',height:'1px',border:'0',visibility:'hidden',pointerEvents:'none'});
    referencia.srcdoc = `<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8">
      <link rel="stylesheet" href="${url('css/style.css')}"><link rel="stylesheet" href="${url('css/admin-shell.css')}"><link rel="stylesheet" href="${url('css/admin-painel-cabecalho.css')}">
      <script defer src="${url('js/cabecalho.js')}" ><\/script><script defer src="${url('js/admin-painel-cabecalho.js')}" ><\/script></head>
      <body class="admin-shell">${modelo.outerHTML}</body></html>`;
    referencia.style.width = `${document.documentElement.clientWidth}px`;
    let pronto=false, agendado=false;
    function agendar() {
      if (!pronto || agendado) return;
      agendado=true;
      requestAnimationFrame(() => {agendado=false; ajustar();});
    }
    function ajustar() {
      if (!matchMedia('screen').matches || !header.classList.contains('ro-header')) return;
      const rolagem={left:window.scrollX,top:window.scrollY};
      const ref = referencia.contentDocument.querySelector('header');
      const titulo = header.querySelector('h1'), nav=header.querySelector('.ro-header-navigation');
      if (!ref || !titulo || !nav) return;
      const texto=header.querySelector('.ro-header-titles > p');
      for (const prop of ['--admin-titulo-x','--admin-titulo-y','--admin-navegacao-y','--admin-texto-y']) header.style.removeProperty(prop);
      header.style.removeProperty('margin-bottom');
      // Recalcula a aparência comum sem os deslocamentos anteriores, evitando
      // acúmulo quando a identificação ou a janela muda.
      if (window.Cabecalho?.comAlturaOriginal) window.Cabecalho.comAlturaOriginal(header, () => {});
      let altura = ref.getBoundingClientRect().height;
      const alturaTitulo = titulo.getBoundingClientRect().height;
      // O deslocamento de 5 px é o aprovado no painel. Um título mais alto
      // expande somente o necessário para que seu início permaneça na faixa.
      altura = Math.max(altura, alturaTitulo + 10);
      header.style.setProperty('height', `${altura}px`, 'important');
      let faixa = header.getBoundingClientRect();
      const bloco=titulo.getBoundingClientRect();
      header.style.setProperty('--admin-titulo-x', `${faixa.left + faixa.width/2 - (bloco.left + bloco.width/2)}px`);
      header.style.setProperty('--admin-titulo-y', `${faixa.top + faixa.height/2 - 5 - (bloco.top + bloco.height/2)}px`);
      const range=document.createRange();range.selectNodeContents(titulo);
      const intercepta=(a,b)=>a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
      const identidade=header.querySelector('.ro-identity');
      if (identidade && identidade.getClientRects().length) {
        // A identificação é texto, não uma área clicável: usa a parte visível
        // após o recorte para evitar colisões sem reservar sua caixa vazia.
        for (let i=0;i<8;i++) {
          const r=document.createRange();r.selectNodeContents(identidade);
          const nome=r.getBoundingClientRect(), caixa=identidade.getBoundingClientRect();
          const visivel={left:Math.max(nome.left,caixa.left),right:Math.min(nome.right,caixa.right),top:nome.top,bottom:nome.bottom};
          const conflitos=[...range.getClientRects()].filter(l=>l.width && l.height && intercepta(l,visivel));
          if (!conflitos.length) break;
          const aumento=2*Math.max(...conflitos.map(l=>visivel.bottom-l.top)) + 1/32;
          altura += aumento;
          header.style.setProperty('height', `${altura}px`, 'important');
          faixa=header.getBoundingClientRect();
          const atual=titulo.getBoundingClientRect();
          const dy=parseFloat(header.style.getPropertyValue('--admin-titulo-y')) || 0;
          header.style.setProperty('--admin-titulo-y', `${dy + faixa.top + faixa.height/2 - 5 - (atual.top + atual.height/2)}px`);
        }
      }
      const linhas=[...range.getClientRects()].filter(r=>r.width && r.height);
      const controles=[...nav.querySelectorAll('a,button')].filter(e=>e.getClientRects().length);
      const limite = header.getBoundingClientRect();
      let cursor=limite.bottom, realocou=false;
      const caixas=controles.map(e=>e.getBoundingClientRect());
      if (caixas.some(r => r.top < limite.top || r.bottom > limite.bottom || linhas.some(l=>intercepta(l,r)))) {
        if (caixas.length) {
          const inicio=Math.min(...caixas.map(r=>r.top)), fim=Math.max(...caixas.map(r=>r.bottom));
          header.style.setProperty('--admin-navegacao-y', `${limite.bottom - inicio}px`);
          cursor=limite.bottom + fim - inicio;
          realocou=true;
        }
      }
      if (texto && texto.getClientRects().length) {
        const r=texto.getBoundingClientRect();
        const colisao=linhas.some(l=>intercepta(l,r)) || caixas.some(b=>intercepta(b,r));
        if (realocou || r.top < limite.top || r.bottom > limite.bottom || colisao) {
          const gap=parseFloat(getComputedStyle(header).rowGap) || 0;
          const topo=cursor + (realocou ? gap : 0);
          header.style.setProperty('--admin-texto-y', `${topo-r.top}px`);
          cursor=topo+r.height;
          realocou=true;
        }
      }
      if (realocou) {
        let margem=Math.max(0,cursor-limite.bottom);
        header.style.setProperty('margin-bottom', `${margem}px`);
        // Em páginas sem layout flex, margens verticais podem colapsar. Mantém
        // o intervalo original entre os controles deslocados e o conteúdo.
        const main=document.querySelector('body > main');
        if (main) {
          const espaco=parseFloat(getComputedStyle(main).marginTop) || 0;
          const falta=espaco-(main.getBoundingClientRect().top-cursor);
          if (falta>0) header.style.setProperty('margin-bottom', `${margem+falta}px`);
        }
      }
      if (window.scrollX !== rolagem.left || window.scrollY !== rolagem.top) {
        window.scrollTo({...rolagem,behavior:'instant'});
      }
    }
    referencia.addEventListener('load', async () => {
      await referencia.contentDocument.fonts.ready;
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
      pronto=true;
      new ResizeObserver(agendar).observe(referencia.contentDocument.querySelector('header'));
      agendar();
    }, {once:true});
    document.body.append(referencia);
    new ResizeObserver(agendar).observe(header);
    new MutationObserver(agendar).observe(header,{childList:true,subtree:true,characterData:true});
    window.addEventListener('resize', () => {
      referencia.style.width = `${document.documentElement.clientWidth}px`;
      requestAnimationFrame(() => requestAnimationFrame(agendar));
    });
    document.fonts.ready.then(agendar);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',iniciar,{once:true});else iniciar();
})();
