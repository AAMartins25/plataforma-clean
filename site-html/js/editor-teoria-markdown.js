/* Importador explícito: não intercepta a colagem normal nem salva no banco. */
(function () {
  "use strict";
  const LIMITE = 250000;
  const montagens = new WeakMap();
  const tags = ["p", "br", "h2", "h3", "h4", "strong", "b", "em", "i", "u",
    "ul", "ol", "li", "blockquote", "a", "figure", "figcaption", "table", "thead", "tbody", "tfoot", "tr", "th", "td", "span", "img"];
  let sequencia = 0;
  const temTexto = texto => /[^\s\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]/u.test(texto);

  function urlSegura(valor) {
    if (/[\s\x00-\x1f\\]/.test(valor)) return false;
    if (valor.startsWith("/") && !valor.startsWith("//")) return true;
    try {
      const url = new URL(valor);
      return url.protocol === "https:" && Boolean(url.hostname) && !url.username && !url.password;
    } catch (_) { return false; }
  }

  function converter(entrada, opcoes = {}) {
    if (!window.markdownit || !window.DOMPurify) throw new Error("O importador não foi carregado. Recarregue a página antes de tentar novamente.");
    let texto = String(entrada || "");
    if (!temTexto(texto)) throw new Error("Cole o resumo em Markdown antes de importar.");
    if (texto.length > LIMITE) throw new Error("O resumo excede 250.000 caracteres. Divida-o em teorias menores antes de importar.");
    texto = texto.replace(/^\uFEFF/, "");
    const envelope = texto.match(/^\s*(`{3,}|~{3,})[ \t]*(?:markdown|md)[ \t]*\r?\n([\s\S]*?)\r?\n\1[ \t]*$/i);
    if (envelope) texto = envelope[2];
    if (!temTexto(texto)) throw new Error("O bloco Markdown está vazio.");
    const avisos = new Set();
    const referencias = [];
    const md = window.markdownit({ html: false, linkify: false, typographer: false, maxNesting: 50 });
    let formulas = 0;
    const M = window.TeoriaMatematica;
    const fechamentosPorEstado = new WeakMap();
    const linhasFechamento = new WeakMap();
    // A regra roda antes de escape/backticks: código cercado por crases é
    // consumido pela regra original e nunca é reinterpretado como matemática.
    md.inline.ruler.before("escape", "ro_math", (estado, silencioso) => {
      const inicio = estado.pos, abertura = estado.src.slice(inicio, inicio + 2);
      if (abertura === "\\)" || abertura === "\\]") {
        if (!silencioso) {
          estado.push("text", "", 0).content = abertura;
          avisos.add("Há delimitadores matemáticos sem abertura; foram preservados como texto.");
        }
        estado.pos += 2;
        return true;
      }
      if (abertura !== "\\(" && abertura !== "\\[" && abertura !== "$$") return false;
      if (!M) throw new Error("O suporte matemático não foi carregado. Recarregue a página.");
      const info = M.delimitador(estado.src, inicio);
      if (!info) return false;
      const fechamento = info.fechamento;
      // Indexar uma vez por estado inline evita varreduras quadráticas em uma
      // entrada com milhares de aberturas sem fechamento.
      let cache = fechamentosPorEstado.get(estado);
      if (!cache) { cache = {}; fechamentosPorEstado.set(estado, cache); }
      if (!cache[fechamento]) {
        const posicoes = M.fechamentos(estado.src, fechamento);
        cache[fechamento] = { posicoes };
      }
      const busca = cache[fechamento];
      // O parser pode consultar posições anteriores em modo silencioso; usar
      // busca binária, sem cursor mutável compartilhado entre essas consultas.
      let esquerda = 0, direita = busca.posicoes.length;
      while (esquerda < direita) {
        const meio = (esquerda + direita) >>> 1;
        if (busca.posicoes[meio] < inicio + 2) esquerda = meio + 1;
        else direita = meio;
      }
      const fim = busca.posicoes[esquerda] ?? estado.posMax;
      /* O fechamento deve estar no trecho ativo (por exemplo, dentro de link). */
      if (fim >= estado.posMax) {
        if (!silencioso) {
          estado.push("text", "", 0).content = abertura;
          avisos.add("Há delimitadores matemáticos sem fechamento; foram preservados como texto.");
        }
        estado.pos += 2;
        return true;
      }
      const fonte = estado.src.slice(inicio + 2, fim);
      if (!silencioso) {
        if (!M) throw new Error("O suporte matemático não foi carregado. Recarregue a página.");
        M.validar(fonte);
        if (++formulas > M.LIMITE_FORMULAS) throw new Error("Cada teoria pode ter até 200 fórmulas.");
        const token = estado.push(abertura === "\\(" ? "ro_math_inline" : "ro_math_display", "", 0);
        token.content = fonte;
      }
      estado.pos = fim + 2;
      return true;
    });
    md.renderer.rules.ro_math_inline = (tokens, indice) =>
      '<span class="ro-math-inline">' + md.utils.escapeHtml(tokens[indice].content) + '</span>';
    md.renderer.rules.ro_math_display = (tokens, indice) =>
      '<figure class="ro-math-display">' + md.utils.escapeHtml(tokens[indice].content) + '</figure>';
    // Blocos LaTeX precisam ser consumidos antes da análise Markdown de listas,
    // tabelas e escapes. Aceita abertura/fechamento em linhas próprias ou na mesma.
    md.block.ruler.before("fence", "ro_math_block", (estado, linha, fim, silencioso) => {
      const inicio = estado.bMarks[linha] + estado.tShift[linha];
      const abertura = estado.src.slice(inicio, inicio + 2);
      if (abertura !== "\\[" && abertura !== "$$") return false;
      if (!M) throw new Error("O suporte matemático não foi carregado. Recarregue a página.");
      const info = M.delimitador(estado.src, inicio);
      if (!info) return false;
      let porFechamento = linhasFechamento.get(estado);
      if (!porFechamento) { porFechamento = {}; linhasFechamento.set(estado, porFechamento); }
      let linhas = porFechamento[info.fechamento];
      if (!linhas) {
        linhas = [];
        // lineMax pode estar temporariamente limitado por uma lista/citação.
        // Indexar o documento inteiro e respeitar `fim` somente na consulta.
        for (let n = 0; n < estado.bMarks.length - 1; n++) {
          const trecho = estado.src.slice(estado.bMarks[n], estado.eMarks[n]);
          const fechamentos = M.fechamentos(trecho, info.fechamento);
          if (fechamentos.some(pos => !trecho.slice(pos + 2).trim())) linhas.push(n);
        }
        porFechamento[info.fechamento] = linhas;
      }
      let esquerda = 0, direita = linhas.length;
      while (esquerda < direita) {
        const meio = (esquerda + direita) >>> 1;
        const mesmaAbertura = info.fechamento === "$$" && linhas[meio] === linha &&
          !M.fechamentos(estado.src.slice(inicio + 2, estado.eMarks[linha]), "$$").length;
        if (linhas[meio] < linha || mesmaAbertura) esquerda = meio + 1;
        else direita = meio;
      }
      const ultima = linhas[esquerda] ?? fim;
      if (ultima >= fim) return false;
      // getLines remove apenas o recuo do contêiner (lista/citação).
      const trecho = estado.getLines(linha, ultima + 1, estado.blkIndent, false);
      const inicioFonte = trecho.indexOf(info.abertura) + 2;
      const fechamento = M.fechamentos(trecho, info.fechamento).find(pos => pos >= inicioFonte);
      // Duas fórmulas na mesma linha devem passar pela regra inline, sem que
      // a primeira absorva o texto e os delimitadores da segunda.
      if (fechamento === undefined || trecho.slice(fechamento + 2).trim()) return false;
      if (silencioso) return true;
      const fonte = trecho.slice(inicioFonte, fechamento);
      if (!M) throw new Error("O suporte matemático não foi carregado. Recarregue a página.");
      M.validar(fonte);
      if (++formulas > M.LIMITE_FORMULAS) throw new Error("Cada teoria pode ter até 200 fórmulas.");
      estado.push("ro_math_display", "", 0).content = fonte;
      estado.line = ultima + 1;
      return true;
    }, { alt: ["paragraph", "reference", "blockquote", "list"] });
    // Uma fórmula display dentro de um parágrafo/título se torna um bloco
    // irmão. Nunca emitir <figure> dentro de <p> (o navegador o repartiria).
    md.core.ruler.after("inline", "ro_math_paragrafos", estado => {
      const saida = [];
      for (let i = 0; i < estado.tokens.length; i++) {
        const abrir = estado.tokens[i], inline = estado.tokens[i + 1], fechar = estado.tokens[i + 2];
        if (!/^(paragraph|heading)_open$/.test(abrir.type) || inline?.type !== "inline" ||
            !inline.children.some(t => t.type === "ro_math_display")) { saida.push(abrir); continue; }
        let grupo = [];
        const marcas = [];
        const flush = () => {
          if (!grupo.length) return;
          const a = new estado.Token(abrir.type, abrir.tag, 1);
          a.attrs = abrir.attrs;
          const t = new estado.Token("inline", "", 0); t.children = grupo;
          saida.push(a, t, new estado.Token(fechar.type, fechar.tag, -1));
          grupo = [];
        };
        for (const filho of inline.children) {
          if (filho.type === "ro_math_display") {
            for (const marca of [...marcas].reverse()) grupo.push(new estado.Token(marca.type.replace(/_open$/, "_close"), marca.tag, -1));
            flush(); saida.push(filho);
            grupo = [...marcas];
          } else {
            grupo.push(filho);
            if (filho.nesting === 1) marcas.push(filho);
            if (filho.nesting === -1) marcas.pop();
          }
        }
        flush(); i += 2;
      }
      estado.tokens = saida;
    });
    md.disable("strikethrough");
    const escapar = md.utils.escapeHtml;
    md.renderer.rules.code_inline = (tokens, indice) => {
      avisos.add("Trechos de código serão mantidos como texto, sem estilo de código.");
      return escapar(tokens[indice].content);
    };
    const blocoCodigo = (tokens, indice) => {
      avisos.add("Blocos de código serão mantidos como parágrafos de texto.");
      return "<p>" + escapar(tokens[indice].content.replace(/\n$/, "")).replace(/\n/g, "<br>") + "</p>\n";
    };
    md.renderer.rules.fence = blocoCodigo;
    md.renderer.rules.code_block = blocoCodigo;
    md.renderer.rules.image = (tokens, indice) => {
      const token = tokens[indice], src = token.attrGet("src"), alt = token.content || "";
      if (referencias.length >= 20) throw new Error("Cada teoria pode conter até 20 imagens.");
      referencias.push(src);
      if (opcoes.coletar) return escapar(alt || "Imagem");
      const imagem = opcoes.resolver?.(src);
      if (!imagem || !window.TeoriaImagens?.PADRAO.test(imagem.src)) {
        throw new Error("Imagem não disponível: " + src + ". Forneça o arquivo ou um ZIP completo.");
      }
      return '<img src="' + escapar(imagem.src) + '" alt="' + escapar(alt.slice(0, 2000)) + '"' +
        (imagem.largura ? ' width="' + Number(imagem.largura) + '" height="' + Number(imagem.altura) + '"' : '') + '>';
    };
    md.renderer.rules.hr = () => {
      avisos.add("Separadores serão representados por um traço em um parágrafo.");
      return "<p>—</p>\n";
    };
    md.renderer.rules.blockquote_open = () => {
      avisos.add("Citações serão mantidas como parágrafos, sem recuo especial.");
      return "";
    };
    md.renderer.rules.blockquote_close = () => "";
    md.renderer.rules.table_open = () => '<figure class="table"><table>\n';
    md.renderer.rules.table_close = () => "</table></figure>\n";
    if (/<\/?[a-z][^>]*>/i.test(texto)) avisos.add("HTML escrito no Markdown será exibido como texto; não será executado nem interpretado.");
    if (/~~/.test(texto)) avisos.add("Marcadores de texto riscado serão mantidos literalmente.");
    const ambiente = {};
    const tokens = md.parse(texto, ambiente);
    let total = 0;
    function ajustar(lista) {
      for (const token of lista) {
        if (++total > 15000) throw new Error("O resumo tem muitos blocos. Divida-o em teorias menores antes de importar.");
        if (/^heading_(open|close)$/.test(token.type)) {
          const nivel = Number(token.tag.slice(1));
          if (nivel > 3) avisos.add("Títulos com mais de três níveis serão agrupados no terceiro nível.");
          token.tag = "h" + Math.min(nivel + 1, 4);
        }
        if (token.type === "ordered_list_open" && token.attrGet("start")) {
          avisos.add("Listas numeradas começarão em 1, conforme o formato atual do editor.");
          token.attrs = (token.attrs || []).filter(([nome]) => nome !== "start");
        }
        if (token.children) ajustar(token.children);
      }
    }
    ajustar(tokens);
    const html = md.renderer.render(tokens, md.options, ambiente);
    const limpo = sanitizarHtml(html, avisos);
    const teste = document.createElement("template"); teste.innerHTML = limpo;
    if (!temTexto(teste.content.textContent) && !teste.content.querySelector("img")) throw new Error("O resumo não contém conteúdo para importar.");
    return { html: limpo, avisos: [...avisos], referencias };
  }

  function sanitizarHtml(html, avisos = new Set()) {
    const limpo = window.DOMPurify.sanitize(html, {
      ALLOWED_TAGS: tags, ALLOWED_ATTR: ["href", "class", "style", "colspan", "rowspan", "src", "alt", "width", "height"],
      ALLOW_DATA_ATTR: false, ALLOW_ARIA_ATTR: false, RETURN_TRUSTED_TYPE: false
    });
    const template = document.createElement("template");
    template.innerHTML = limpo;
    for (const img of template.content.querySelectorAll("img")) {
      if (!window.TeoriaImagens?.PADRAO.test(img.getAttribute("src") || "")) throw new Error("Há imagem sem arquivo incorporado.");
      for (const nome of ["width", "height"]) {
        const v = img.getAttribute(nome);
        if (v && (!/^\d+$/.test(v) || Number(v) < 1 || Number(v) > 8192)) img.removeAttribute(nome);
      }
    }
    for (const no of template.content.querySelectorAll("*")) {
      if (no.hasAttribute("href") && (no.tagName !== "A" || !urlSegura(no.getAttribute("href")))) {
        no.removeAttribute("href");
        avisos.add("Alguns endereços de link não são permitidos e serão mantidos apenas como texto.");
      }
      if (no.hasAttribute("class") && !((no.tagName === "FIGURE" && ["table", "ro-math-display", "image"].includes(no.className)) ||
          (no.tagName === "SPAN" && no.className === "ro-math-inline"))) no.removeAttribute("class");
      if (no.hasAttribute("style")) {
        const permitido = ["P", "H2", "H3", "H4", "TH", "TD"].includes(no.tagName);
        const alinhamento = no.getAttribute("style").match(/^\s*text-align\s*:\s*(left|right|center|justify)\s*;?\s*$/i);
        if (permitido && alinhamento) no.setAttribute("style", "text-align:" + alinhamento[1].toLowerCase());
        else no.removeAttribute("style");
      }
      for (const nome of ["colspan", "rowspan"]) {
        if (no.hasAttribute(nome) && (!["TD", "TH"].includes(no.tagName) || !/^\d+$/.test(no.getAttribute(nome)) || Number(no.getAttribute(nome)) < 1 || Number(no.getAttribute(nome)) > 20)) no.removeAttribute(nome);
      }
    }
    return template.innerHTML;
  }

  function instalar(textarea, editor) {
    if (montagens.has(textarea)) return;
    const id = "markdown-teoria-" + (++sequencia);
    const controles = document.createElement("div");
    controles.className = "teoria-markdown-controles";
    const abrir = document.createElement("button");
    abrir.type = "button";
    abrir.className = "btn";
    abrir.textContent = "Importar Markdown";
    const mensagem = document.createElement("span");
    mensagem.setAttribute("role", "status");
    controles.append(abrir, mensagem);
    const dialogo = document.createElement("dialog");
    dialogo.className = "teoria-markdown-dialogo";
    dialogo.setAttribute("aria-labelledby", id + "-titulo");
    dialogo.innerHTML = `
      <div class="teoria-markdown-cabecalho"><h2 id="${id}-titulo">Importar Markdown</h2>
        <button type="button" class="btn" data-md="fechar" aria-label="Fechar importador">Fechar</button></div>
      <p>Cole o resumo em Markdown para importar títulos, negritos, itálicos, listas, tabelas e fórmulas LaTeX.</p>
      <label for="${id}-fonte">Resumo em Markdown</label>
      <textarea id="${id}-fonte" data-md="fonte" rows="9" autocomplete="off" spellcheck="false"></textarea>
      <label for="${id}-zip">Ou importe um ZIP com conteudo.md e a pasta imagens/</label>
      <input id="${id}-zip" data-md="zip" type="file" accept=".zip,application/zip">
      <label for="${id}-arquivos">Imagens do Markdown, se não estiverem em um ZIP</label>
      <input id="${id}-arquivos" data-md="arquivos" type="file" accept="image/png,image/jpeg,image/webp" multiple>
      <p>As figuras serão associadas pelos nomes no Markdown. O pacote precisa conter todos os arquivos referenciados.</p>
      <p>A importação substitui o conteúdo do editor. Revise e use o botão de salvar da teoria para gravar. Ctrl+Z desfaz a importação.</p>
      <div class="teoria-markdown-acoes"><button type="button" class="btn" data-md="aplicar">Importar material</button>
        <button type="button" class="btn" data-md="cancelar">Cancelar</button></div>
      <p data-md="erro" role="alert"></p>`;
    const buscar = nome => dialogo.querySelector(`[data-md="${nome}"]`);
    const fonte = buscar("fonte"), erro = buscar("erro"), aplicar = buscar("aplicar");
    const pacote = buscar("zip"), arquivos = buscar("arquivos");
    let original = null, descartado = false;
    function sincronizar() {
      abrir.disabled = editor.isReadOnly || descartado;
      aplicar.disabled = editor.isReadOnly || descartado;
      fonte.disabled = pacote.disabled = arquivos.disabled = editor.isReadOnly || descartado;
    }
    abrir.addEventListener("click", () => {
      if (editor.isReadOnly || descartado) return;
      erro.textContent = ""; fonte.value = ""; mensagem.textContent = "";
      original = editor.getData();
      dialogo.showModal(); fonte.focus();
    });
    fonte.addEventListener("input", () => { erro.textContent = ""; });
    aplicar.addEventListener("click", async () => {
      if (editor.isReadOnly || descartado) return;
      erro.textContent = "";
      if (editor.getData() !== original) { erro.textContent = "O conteúdo do editor mudou. Cancele a importação, revise o texto e abra o importador novamente."; return; }
      const texto = fonte.value, zipSelecionado = pacote.files[0], lista = [...arquivos.files];
      try {
        if (zipSelecionado && (texto.trim() || lista.length)) throw new Error("Escolha o ZIP ou Markdown com arquivos, sem misturar os dois modos.");
        await window.TeoriaImagensEditor.transacao(editor, async signal => {
          if (zipSelecionado) {
            const resultado = await TeoriaImagens.zip(zipSelecionado, signal);
            return TeoriaImagensEditor.markdown(resultado.markdown, resultado.imagens, signal, true);
          }
          // Conferir todos os nomes antes de enviar arquivos: nenhuma associação
          // depende da ordem da seleção de arquivos.
          const analise = converter(texto, { coletar: true });
          const nomes = new Map();
          for (const file of lista) {
            if (nomes.has(file.name)) throw new Error("Há imagens com nomes repetidos. Use nomes únicos.");
            nomes.set(file.name, file);
          }
          const usadas = new Set();
          for (const src of analise.referencias) {
            if (/^https:\/\//i.test(src) || TeoriaImagens.PADRAO.test(src)) continue;
            let nome; try {nome = decodeURIComponent(src).replace(/^\.\//, "");} catch (_) {throw new Error("Caminho de imagem inválido.");}
            const file = nomes.get(nome) || (nome.startsWith("imagens/") ? nomes.get(nome.slice(8)) : null);
            if (!file) throw new Error("Imagem não encontrada: " + nome + ". Selecione as imagens em lote ou um ZIP completo.");
            usadas.add(file);
          }
          if (lista.some(f => !usadas.has(f))) throw new Error("Há arquivos selecionados sem referência no Markdown. Confira os nomes.");
          const enviadas = lista.length ? await TeoriaImagens.arquivos(lista, signal) : [];
          const conhecidas = enviadas.flatMap((img, n) => [{...img,nome:lista[n].name},{...img,nome:"imagens/"+lista[n].name}]);
          return TeoriaImagensEditor.markdown(texto, conhecidas, signal);
        }, true);
        if (descartado) return;
        mensagem.textContent = "Material importado com imagens. Revise e salve. Desfazer restaura o conteúdo anterior.";
        dialogo.close();
      } catch (falha) {
        if (dialogo.open && !descartado) erro.textContent = falha.message;
      }
    });
    for (const nome of ["fechar", "cancelar"]) buscar(nome).addEventListener("click", () => dialogo.close());
    dialogo.addEventListener("close", () => {
      window.TeoriaImagensEditor.cancelar(editor);
      erro.textContent = ""; fonte.value = ""; pacote.value = ""; arquivos.value = ""; original = null;
      if (!descartado && editor.state !== "destroyed") editor.editing.view.focus();
    });
    editor.on("change:isReadOnly", sincronizar);
    editor.ui.view.element.before(controles);
    document.body.appendChild(dialogo);
    function limpar() {
      if (descartado) return;
      descartado = true;
      if (dialogo.open) dialogo.close();
      editor.off("change:isReadOnly", sincronizar);
      controles.remove(); dialogo.remove(); montagens.delete(textarea);
      original = null; fonte.value = ""; pacote.value = ""; arquivos.value = "";
    }
    montagens.set(textarea, { limpar });
    sincronizar();
  }

  function destruir(textarea) { montagens.get(textarea)?.limpar(); }
  window.TeoriaMarkdown = { instalar, destruir, converter, sanitizarHtml };
})();
