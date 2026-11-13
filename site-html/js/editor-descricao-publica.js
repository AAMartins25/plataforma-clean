(function () {
  let editor, original = '', inicial = '', bloqueado = true, geracao = 0, campo;
  function bloquear(valor) {
    bloqueado = valor;
    if (editor) {
      if (valor) editor.enableReadOnlyMode('descricao-publica');
      else editor.disableReadOnlyMode('descricao-publica');
    }
    if (campo) campo.disabled = valor || (!editor && DescricaoPublica.separar(original).html);
  }
  async function carregar(textarea, valor) {
    const atual = ++geracao;
    campo = textarea;
    if (editor) { const anterior = editor; editor = null; await anterior.destroy(); }
    if (atual !== geracao) return;
    original = valor;
    const dados = DescricaoPublica.separar(valor);
    textarea.value = dados.texto;
    bloquear(true);
    let aviso = document.getElementById('avisoDescricaoPublica');
    if (!aviso) {
      aviso = document.createElement('p'); aviso.id = 'avisoDescricaoPublica';
      aviso.setAttribute('role', 'status'); textarea.after(aviso);
    }
    aviso.textContent = 'Carregando editor de formatação…';
    try {
      const C = await TeoriaEditor.carregarCKEditor();
      if (atual !== geracao) return;
      const html = dados.html ? DescricaoPublica.limpar(dados.texto) : TeoriaEditor.legadoParaHtml(dados.texto);
      // O CKEditor copia o bloqueio do textarea na criação. O bloqueio visual
      // passa a ser controlado pela instância, com uma única chave de leitura.
      textarea.disabled = false;
      textarea.readOnly = false;
      const novo = await C.ClassicEditor.create(textarea, {
        licenseKey: window.RESUMAO_CKEDITOR_LICENSE_KEY,
        plugins: [C.Essentials, C.Paragraph, C.Bold, C.Italic, C.Heading, C.List],
        toolbar: ['undo', 'redo', '|', 'heading', '|', 'bold', 'italic', '|', 'bulletedList', 'numberedList'],
        heading: { options: [
          {model: 'paragraph', title: 'Parágrafo', class: 'ck-heading_paragraph'},
          {model: 'heading2', view: 'h2', title: 'Título 1', class: 'ck-heading_heading2'},
          {model: 'heading3', view: 'h3', title: 'Título 2', class: 'ck-heading_heading3'},
          {model: 'heading4', view: 'h4', title: 'Título 3', class: 'ck-heading_heading4'}
        ] },
        initialData: html
      });
      if (atual !== geracao) { await novo.destroy(); return; }
      editor = novo;
      inicial = editor.getData();
      editor.ui.view.editable.element.setAttribute('aria-label', 'Descrição pública e valores de acesso');
      bloquear(bloqueado);
      aviso.textContent = '';
    } catch (erro) {
      if (atual !== geracao) return;
      textarea.value = dados.texto;
      bloquear(bloqueado);
      aviso.textContent = dados.html
        ? 'Editor indisponível. A descrição formatada foi preservada. Recarregue para editar. ' + erro.message
        : 'Editor de formatação indisponível. Você pode editar o texto simples. ' + erro.message;
    }
  }
  function limpar() {
    geracao++;
    original = inicial = '';
    if (campo) campo.value = '';
    if (editor) editor.setData('');
    bloquear(true);
  }
  function conteudo(textarea) {
    if (editor && editor.getData() !== inicial) {
      return { descricao_publica: editor.getData(), descricao_publica_formato: 'html_v1' };
    }
    return { descricao_publica: editor || DescricaoPublica.separar(original).html ? original : textarea.value };
  }
  window.DescricaoPublicaEditor = { carregar, bloquear, conteudo, limpar };
})();
