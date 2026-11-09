// CKEditor é carregado somente quando o administrador abre um editor de Texto.
// A chave comercial do plano Cloud deve ser fornecida em window.RESUMAO_CKEDITOR_LICENSE_KEY.
(function () {
  const VERSAO = "49.1.0";
  const BASE = `https://cdn.ckeditor.com/ckeditor5/${VERSAO}`;
  let carregamento;
  const instancias = new WeakMap();

  async function carregar() {
    if (!window.RESUMAO_CKEDITOR_LICENSE_KEY && window.apiGetAuth) {
      const config = await window.apiGetAuth("/admin/ckeditor-chave");
      window.RESUMAO_CKEDITOR_LICENSE_KEY = config.licenseKey || "";
    }
    if (!window.RESUMAO_CKEDITOR_LICENSE_KEY) {
      throw new Error("Configure a chave comercial Cloud do CKEditor para usar o editor visual.");
    }
    if (window.CKEDITOR) return Promise.resolve(window.CKEDITOR);
    if (!carregamento) {
      carregamento = new Promise((resolve, reject) => {
        const estilo = document.createElement("link");
        estilo.rel = "stylesheet";
        estilo.href = `${BASE}/ckeditor5.css`;
        document.head.appendChild(estilo);
        const script = document.createElement("script");
        script.src = `${BASE}/ckeditor5.umd.js`;
        script.onload = () => window.CKEDITOR ? resolve(window.CKEDITOR) : reject(new Error("CKEditor não inicializou."));
        script.onerror = () => reject(new Error("Não foi possível carregar o CKEditor."));
        document.head.appendChild(script);
      }).catch(erro => { carregamento = null; throw erro; });
    }
    return carregamento;
  }

  async function iniciar(textarea, html) {
    if (!textarea) throw new Error("Campo de texto indisponível.");
    if (instancias.has(textarea)) return instancias.get(textarea);
    const C = await carregar();
    if (!window.TeoriaImagens || !window.criarPluginTeoriaImagens) throw new Error("O suporte a imagens não foi carregado. Recarregue a página.");
    await window.TeoriaImagens.preparar(html || "");
    const TeoriaImagensPlugin = window.criarPluginTeoriaImagens(C);
    if (!window.criarPluginTeoriaMatematica || !window.TeoriaMatematica) {
      throw new Error("O suporte a fórmulas não foi carregado. Recarregue a página.");
    }
    const TeoriaFormula = window.criarPluginTeoriaMatematica(C);
    if (!textarea.isConnected) throw new Error("O formulário foi fechado antes da abertura do editor.");
    const { ClassicEditor, Essentials, Paragraph, Bold, Italic, Underline, Heading,
      List, Indent, Table, TableToolbar, TableCaption, Alignment,
      Link } = C;
    const anterior = textarea.value;
    const somenteLeituraAnterior = textarea.readOnly;
    textarea.value = html || "";
    // O estado readOnly do elemento de origem é copiado na criação do editor.
    // O formulário pode bloqueá-lo enquanto a CDN carrega, mas o editor deve
    // nascer editável; liberar o textarea depois não altera editor.isReadOnly.
    textarea.readOnly = false;
    let editor;
    try {
      editor = await ClassicEditor.create(textarea, {
      licenseKey: window.RESUMAO_CKEDITOR_LICENSE_KEY,
      plugins: [Essentials, Paragraph, Bold, Italic, Underline, Heading, List,
        Indent, Table, TableToolbar, TableCaption, Alignment,
        Link, TeoriaFormula, TeoriaImagensPlugin],
      toolbar: ["undo", "redo", "|", "heading", "|", "bold", "italic", "underline",
        "|", "bulletedList", "numberedList", "outdent", "indent", "|",
        "alignment", "insertTable", "link", "|", "formula", "imagemPropria"],
      table: { contentToolbar: ["tableColumn", "tableRow", "mergeTableCells", "toggleTableCaption"] },
      image: { toolbar: ["imageTextAlternative", "toggleImageCaption"] }
      });
    } catch (erro) {
      textarea.value = anterior;
      textarea.readOnly = somenteLeituraAnterior;
      throw erro;
    }
    // Classes de destaque usadas por conteúdo web não levam suas folhas CSS
    // junto com a colagem. Convertemos somente estes spans conhecidos em
    // atributos semânticos; nenhuma classe ou CSS arbitrário é autorizado.
    for (const classe of ["font-semibold", "font-bold", "font-extrabold", "font-black"]) {
      editor.conversion.for("upcast").elementToAttribute({
        view: { name: "span", classes: classe }, model: { key: "bold", value: true }
      });
    }
    editor.conversion.for("upcast").elementToAttribute({
      view: { name: "span", classes: "italic" }, model: { key: "italic", value: true }
    });
    // O Chromium serializa sublinhado copiado como text-decoration-line.
    // Underline 49.1.0 reconhece <u> e text-decoration, mas não esse longhand.
    // Converter apenas a presença de underline para o atributo já existente.
    editor.conversion.for("upcast").elementToAttribute({
      view: { styles: { "text-decoration-line": /\bunderline\b/ } },
      model: { key: "underline", value: true }
    });
    instalarListasWord(editor);
    instalarDiagnosticoColagem(editor);
    if (window.TeoriaMarkdown) window.TeoriaMarkdown.instalar(textarea, editor);
    instancias.set(textarea, editor);
    return editor;
  }

  function normalizarListasWordHtml(html) {
    if (!/\bmso-list\s*:/i.test(html)) return html;
      const template = document.createElement("template");
      template.innerHTML = html;
      const estilos = [...template.content.querySelectorAll("style")].map(no => no.textContent).join("\n");
      let convertidos = 0;

      function informacao(no) {
        if (no.nodeType !== 1 || no.tagName !== "P") return null;
        const lista = (no.getAttribute("style") || "").match(/(?:^|;)\s*mso-list\s*:\s*l(\d+)\s+level(\d+)\s+lfo(\d+)/i);
        if (!lista) return null;
        const [, id, nivel, grupo] = lista;
        const regra = estilos.match(new RegExp("@list\\s+l" + id + ":level" + nivel + "\\s*\\{([^}]*)\\}", "i"));
        const formato = regra?.[1].match(/mso-level-number-format\s*:\s*([^;]+)/i)?.[1].trim().toLowerCase();
        const marcadores = [...no.querySelectorAll("span[style]")].filter(span =>
          /(?:^|;)\s*mso-list\s*:\s*ignore\s*(?:;|$)/i.test(span.getAttribute("style")));
        const marcador = marcadores.map(span => span.textContent).join("").trim();
        const tipo = formato ? (/^(bullet|image)$/.test(formato) ? "ul" : "ol")
          : (/^[•·●○▪■\uF0B7]/.test(marcador) ? "ul" : "ol");
        return { id, grupo, nivel: Math.min(9, Math.max(1, Number(nivel))), tipo, marcadores };
      }

      function percorrer(pai) {
        const pilha = [];
        for (const no of [...pai.childNodes]) {
          const info = informacao(no);
          if (!info) {
            if (no.nodeType === 1 || (no.nodeType === 3 && no.textContent.trim())) pilha.length = 0;
            if (no.nodeType === 1) percorrer(no);
            continue;
          }
          while (pilha.length && pilha.at(-1).nivel > info.nivel) pilha.pop();
          let atual = pilha.at(-1);
          if (atual?.nivel === info.nivel &&
              (atual.id !== info.id || atual.grupo !== info.grupo || atual.tipo !== info.tipo)) {
            pilha.pop();
            atual = pilha.at(-1);
          }
          if (!atual || atual.nivel < info.nivel) {
            const lista = document.createElement(info.tipo);
            if (atual?.ultimoItem) atual.ultimoItem.appendChild(lista);
            else pai.insertBefore(lista, no);
            atual = { ...info, lista, ultimoItem: null };
            pilha.push(atual);
          }
          info.marcadores.forEach(marcador => marcador.remove());
          const item = document.createElement("li");
          // Manter o parágrafo e seus elementos internos para os conversores
          // existentes de negrito, itálico, links, alinhamento e tabelas.
          item.appendChild(no);
          atual.lista.appendChild(item);
          atual.ultimoItem = item;
          convertidos++;
        }
      }
      percorrer(template.content);
      if (!convertidos) return html;
      // O template é inerte. Não transportar folhas ou conteúdo ativo da origem.
      template.content.querySelectorAll("script,style,link,meta,base,iframe,object,embed").forEach(no => no.remove());
      // O pipeline normal do CKEditor ainda filtra o HTML; o backend continua
      // aplicando a mesma allowlist de sanitização antes de qualquer gravação.
    return template.innerHTML;
  }

  function instalarListasWord(editor) {
    editor.listenTo(editor.editing.view.document, "clipboardInput", (_evento, dados) => {
      if (dados.content && typeof dados.content !== "string") return;
      const html = typeof dados.content === "string" ? dados.content : dados.dataTransfer.getData("text/html");
      if (/\bmso-list\s*:/i.test(html)) dados.content = normalizarListasWordHtml(html);
    }, { priority: "highest" });
  }

  let ultimaColagem = null;
  let capturaAte = 0;
  let diagnosticoExpiraEm = 0;
  const diagnosticosPorEditor = new WeakMap();

  function resumirHtml(html) {
    // Template inerte: nenhum texto, atributo arbitrário, URL ou folha externa
    // é inserido no documento, registrado ou enviado a outro serviço.
    const template = document.createElement("template");
    template.innerHTML = html || "";
    const doc = template.content;
    const qtd = seletor => doc.querySelectorAll(seletor).length;
    const estilos = [...doc.querySelectorAll("[style]")];
    const valores = (propriedade, permitidos) => Object.fromEntries(permitidos.map(valor =>
      [valor, estilos.filter(no => no.style.getPropertyValue(propriedade).trim() === valor).length]));
    const classesPermitidas = ["font-semibold", "font-bold", "font-extrabold", "font-black", "italic", "underline", "not-italic", "no-underline"];
    const classesConhecidas = Object.fromEntries(classesPermitidas.map(classe =>
      [classe, qtd("." + classe)]));
    const folhas = [...doc.querySelectorAll("style")].map(no => no.textContent).join("\n");
    return {
      htmlDisponivel: Boolean(html), tamanhoHtml: (html || "").length,
      tagsNegrito: qtd("strong,b"), tagsItalico: qtd("em,i"), tagsSublinhado: qtd("u"),
      estilosNegrito: estilos.filter(no => no.style.fontWeight === "bold" || Number(no.style.fontWeight) >= 600).length,
      estilosItalico: estilos.filter(no => no.style.fontStyle === "italic").length,
      estilosSublinhado: estilos.filter(no => /\bunderline\b/.test(no.style.textDecoration + " " + no.style.textDecorationLine)).length,
      valoresPeso: valores("font-weight", ["normal", "bold", "bolder", "lighter", "400", "500", "600", "700", "800", "900"]),
      valoresEstilo: valores("font-style", ["normal", "italic", "oblique"]),
      classesConhecidas,
      classesNegrito: qtd("span.font-semibold,span.font-bold,span.font-extrabold,span.font-black"),
      classesItalico: qtd("span.italic"), classesSublinhado: qtd("span.underline"),
      elementosComOutrasClasses: [...doc.querySelectorAll("[class]")].filter(no =>
        [...no.classList].some(classe => !classesPermitidas.includes(classe))).length,
      folhasEstilo: qtd("style"),
      destaquesEmFolhas: (folhas.match(/font-weight\s*:|font-style\s*:|text-decoration(?:-line)?\s*:/gi) || []).length,
      listas: qtd("ul,ol"), itens: qtd("li"), tabelas: qtd("table"), paragrafos: qtd("p")
    };
  }

  function diagnosticarProximaColagem() {
    ultimaColagem = null;
    capturaAte = Date.now() + 120000;
    diagnosticoExpiraEm = capturaAte;
    return { ativo: true, validadeSegundos: 120, captura: "somente a próxima colagem; sem texto integral" };
  }

  function cancelarDiagnosticoColagem() {
    capturaAte = 0;
    diagnosticoExpiraEm = 0;
    ultimaColagem = null;
    window.RESUMAO_DIAGNOSTICO_COLAGEM = false;
  }

  function instalarDiagnosticoColagem(editor) {
    let diagnostico;
    editor.listenTo(editor.editing.view.document, "clipboardInput", (_evento, dados) => {
      if (!window.RESUMAO_DIAGNOSTICO_COLAGEM && Date.now() > capturaAte) {
        diagnostico = null;
        return;
      }
      capturaAte = 0;
      const html = dados.dataTransfer.getData("text/html");
      const texto = dados.dataTransfer.getData("text/plain");
      const tipos = [...(dados.dataTransfer.types || [])];
      diagnostico = {
        formatos: { html: tipos.includes("text/html"), texto: tipos.includes("text/plain"), rtf: tipos.includes("text/rtf") },
        textoPuro: { disponivel: Boolean(texto), tamanho: texto.length,
          paresAsteriscosDuplos: (texto.match(/\*\*/g) || []).length,
          paresUnderlinesDuplos: (texto.match(/__/g) || []).length },
        clipboard: resumirHtml(html), entradaConversor: null, modelo: null,
        atributosModelo: null, documentoAposColagem: null, antesSalvar: null
      };
      ultimaColagem = diagnostico;
      diagnosticoExpiraEm = Date.now() + 300000;
      diagnosticosPorEditor.set(editor, diagnostico);
    }, { priority: "high" });
    const pipeline = editor.plugins.get("ClipboardPipeline");
    editor.listenTo(pipeline, "inputTransformation", (_evento, dados) => {
      if (diagnostico) diagnostico.entradaConversor = resumirHtml(editor.data.htmlProcessor.toData(dados.content));
    }, { priority: "high" });
    editor.listenTo(pipeline, "contentInsertion", (_evento, dados) => {
      if (!diagnostico) return;
      diagnostico.modelo = resumirHtml(editor.data.stringify(dados.content));
      const caracteres = { negrito: 0, italico: 0, sublinhado: 0 };
      for (const item of editor.model.createRangeIn(dados.content).getItems()) {
        if (!item.is("$textProxy") && !item.is("$text")) continue;
        for (const [nome, atributo] of [["negrito", "bold"], ["italico", "italic"], ["sublinhado", "underline"]]) {
          if (item.getAttribute(atributo)) caracteres[nome] += item.data.length;
        }
      }
      diagnostico.atributosModelo = caracteres;
      const atual = diagnostico;
      queueMicrotask(() => {
        if (ultimaColagem === atual && editor.state !== "destroyed") atual.documentoAposColagem = resumirHtml(editor.getData());
      });
    }, { priority: "high" });
  }

  function diagnosticoColagem() {
    if (Date.now() > diagnosticoExpiraEm) ultimaColagem = null;
    return ultimaColagem ? JSON.parse(JSON.stringify(ultimaColagem)) : null;
  }

  function conteudo(textarea) {
    const editor = instancias.get(textarea);
    if (editor && window.TeoriaImagensEditor.estados.get(editor)?.pendente) throw new Error("Aguarde a conclusão da importação de imagens antes de salvar.");
    const diagnostico = editor && diagnosticosPorEditor.get(editor);
    if (diagnostico && diagnostico === ultimaColagem && Date.now() <= diagnosticoExpiraEm) {
      diagnostico.antesSalvar = resumirHtml(editor.getData());
    }
    return editor
      ? { conteudo: editor.getData(), conteudo_formato: "html_v1" }
      : { conteudo: textarea.value, conteudo_formato: "texto_puro" };
  }

  async function destruir(textarea) {
    const editor = textarea && instancias.get(textarea);
    if (editor) {
      if (window.TeoriaMarkdown) window.TeoriaMarkdown.destruir(textarea);
      instancias.delete(textarea);
      await editor.destroy();
    }
  }

  function legadoParaHtml(texto) {
    const escapar = valor => valor.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    return String(texto || "").split(/\n\s*\n/).map(bloco =>
      `<p>${escapar(bloco).replace(/\n/g, "<br>")}</p>`
    ).join("");
  }

  function pronto(textarea) {
    const editor = instancias.get(textarea);
    return !editor || !window.TeoriaImagensEditor.estados.get(editor)?.pendente;
  }
  window.TeoriaEditor = { carregarCKEditor: carregar, pronto, normalizarListasWordHtml, iniciar, conteudo, destruir, legadoParaHtml, diagnosticoColagem, diagnosticarProximaColagem, cancelarDiagnosticoColagem };
})();
