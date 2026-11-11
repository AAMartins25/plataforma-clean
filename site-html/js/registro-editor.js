/* Reutiliza as ferramentas textuais do editor existente, sem plugins de imagem. */
(function () {
  const estados = new Map();
  async function iniciar(campo, texto = '', formato = 'texto_puro', aoMudar) {
    if (!campo || estados.has(campo)) return;
    const estado = {carregando:true, erro:null, formato}; estados.set(campo, estado);
    campo.value = texto; campo.readOnly = true; campo.classList.add('registro-editor-fonte');
    const host = campo.parentElement; host.classList.add('registro-editor-host');
    const aviso = document.createElement('p'); aviso.setAttribute('role','status'); aviso.textContent = 'Abrindo editor…'; campo.after(aviso);
    try {
      const html = formato === 'html_v1' ? RegistroConteudo.sanitizar(texto) : TeoriaEditor.legadoParaHtml(texto);
      const ed = await TeoriaEditor.iniciar(campo, html, {semImagens:true, chaveEndpoint:'/me/ckeditor-chave'});
      if (!campo.isConnected) {await TeoriaEditor.destruir(campo); return;}
      ed.ui.view.editable.element.setAttribute('aria-label', campo.getAttribute('aria-label') || campo.getAttribute('placeholder') || 'Texto');
      if (estado.bloqueado) ed.enableReadOnlyMode('registro-envio');
      ed.model.document.on('change:data', () => {
        campo.value = ed.getData(); campo.dispatchEvent(new Event('input',{bubbles:true}));
        if (aoMudar) aoMudar();
      });
      aviso.remove(); campo.readOnly = false;
    } catch (erro) {
      estado.erro = erro; campo.readOnly = formato === 'html_v1' || !!estado.bloqueado;
      aviso.textContent = 'Editor indisponível. ' + (campo.readOnly ? 'Reabra o conteúdo antes de salvar.' : 'Você pode escrever texto simples.') ;
    } finally {estado.carregando = false; if (!campo.isConnected) estados.delete(campo);}
  }
  function ler(campo, validar = true) {
    const estado = estados.get(campo);
    if (!campo || estado?.carregando) throw new Error('Aguarde a abertura do editor.');
    if (estado?.erro && estado.formato === 'html_v1') throw new Error('Reabra o editor antes de salvar o conteúdo formatado.');
    const dado = TeoriaEditor.conteudo(campo);
    const texto = dado.conteudo_formato === 'html_v1' ? RegistroConteudo.sanitizar(dado.conteudo) : dado.conteudo.trim();
    const t = document.createElement('template');
    let visivel = texto;
    if (dado.conteudo_formato === 'html_v1') {
      t.innerHTML = texto;
      for (const el of t.content.querySelectorAll('p,br,li,tr,td,th,h2,h3,h4,figure')) el.appendChild(document.createTextNode(' '));
      visivel = t.content.textContent;
    }
    if (validar && !visivel.trim()) throw new Error('Escreva o texto antes de salvar.');
    if (validar && visivel.trim().split(/\s+/).length > 300) throw new Error('O texto deve ter no máximo 300 palavras.');
    return {texto, texto_formato:dado.conteudo_formato};
  }
  function bloquear(campo, valor) {
    const estado = estados.get(campo); if (estado) estado.bloqueado = valor;
    campo.readOnly = valor;
    const el = campo.parentElement.querySelector('.ck-content');
    const ed = el?.ckeditorInstance;
    if (ed) valor ? ed.enableReadOnlyMode('registro-envio') : ed.disableReadOnlyMode('registro-envio');
  }
  new MutationObserver(() => {
    for (const [campo, estado] of estados) if (!campo.isConnected && !estado.carregando) {
      estados.delete(campo); void TeoriaEditor.destruir(campo);
    }
  }).observe(document.documentElement,{childList:true,subtree:true});
  window.RegistroEditor = {iniciar, ler, bloquear};
})();
