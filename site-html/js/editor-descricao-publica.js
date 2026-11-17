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
    if (editor) { const anterior = editor; editor = null; window.TeoriaMarkdown?.destruir(textarea); await anterior.destroy(); }
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
      class TamanhoDescricao extends C.Plugin {
        init() {
          const instancia = this.editor;
          const comando = instancia.commands.get('fontSize');
          const selecao = instancia.model.document.selection;
          for (const [nome, rotulo, delta] of [['diminuirFonteDescricao', 'Diminuir fonte', -1], ['tamanhoFonteDescricao', 'Tamanho da fonte', 0], ['aumentarFonteDescricao', 'Aumentar fonte', 1]]) {
            instancia.ui.componentFactory.add(nome, locale => {
              const botao = new C.ButtonView(locale);
              botao.set({ label: delta ? rotulo : '16 px', tooltip: delta ? rotulo : false, withText: true });
              const atualizar = () => {
                const tamanho = Number.parseInt(comando.value, 10) || 16;
                botao.isEnabled = Boolean(delta && comando.isEnabled && !selecao.isCollapsed && tamanho + delta >= 10 && tamanho + delta <= 48);
                if (!delta) botao.label = `${tamanho} px`;
              };
              this.listenTo(comando, 'change:value', atualizar);
              this.listenTo(comando, 'change:isEnabled', atualizar);
              this.listenTo(selecao, 'change:range', atualizar);
              this.listenTo(botao, 'execute', () => {
                if (!delta || selecao.isCollapsed) return;
                const tamanho = Number.parseInt(comando.value, 10) || 16;
                instancia.execute('fontSize', { value: `${tamanho + delta}px` });
                instancia.editing.view.focus();
              });
              if (delta) botao.label = delta < 0 ? '−' : '+';
              atualizar();
              return botao;
            });
          }
        }
      }
      // O plugin nativo trata "left" como ausência de formato. Como o
      // padrão visual aqui é justificado, uma escolha explícita precisa
      // sobreviver à conversão, ao salvamento e à próxima abertura.
      class AlinhamentoDescricao extends C.Plugin {
        init() {
          const instancia = this.editor;
          const comando = instancia.commands.get('alignment');
          instancia.conversion.for('upcast').attributeToAttribute({
            view: { key: 'style', value: { 'text-align': 'left' } },
            model: { key: 'alignment', value: 'left' }
          });
          instancia.conversion.for('downcast').attributeToAttribute({
            model: { key: 'alignment', values: ['left'] },
            view: { left: { key: 'style', value: { 'text-align': 'left' } } }
          });
          this.listenTo(comando, 'execute', (evento, [opcoes]) => {
            if (opcoes?.value !== 'left') return;
            evento.stop();
            const modelo = instancia.model;
            modelo.change(writer => {
              for (const bloco of modelo.document.selection.getSelectedBlocks()) {
                if (modelo.schema.checkAttribute(bloco, 'alignment')) writer.setAttribute('alignment', 'left', bloco);
              }
            });
          }, { priority: 'high' });
          const atualizarAlinhamento = comando.refresh.bind(comando);
          comando.refresh = () => {
            atualizarAlinhamento();
            const bloco = instancia.model.document.selection.getSelectedBlocks().next().value;
            if (bloco?.is('element', 'paragraph') && !bloco.hasAttribute('alignment')) comando.value = 'justify';
          };
          comando.refresh();
        }
      }
      const novo = await C.ClassicEditor.create(textarea, {
        licenseKey: window.RESUMAO_CKEDITOR_LICENSE_KEY,
        plugins: [C.Essentials, C.Paragraph, C.Bold, C.Italic, C.Heading, C.List, C.Table, C.TableToolbar, C.FontSize, C.Alignment, C.HorizontalLine, TamanhoDescricao, AlinhamentoDescricao],
        toolbar: ['undo', 'redo', '|', 'heading', '|', 'bold', 'italic', '|', 'diminuirFonteDescricao', 'tamanhoFonteDescricao', 'aumentarFonteDescricao', '|', 'alignment', '|', 'bulletedList', 'numberedList', '|', 'insertTable'],
        fontSize: { options: Array.from({ length: 39 }, (_, i) => i + 10) },
        table: { contentToolbar: ['tableColumn', 'tableRow', 'mergeTableCells'] },
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
      window.TeoriaMarkdown?.instalar(textarea, editor, { descricaoPublica: true });
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
