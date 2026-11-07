/* Importação atômica de imagens: nenhuma rede acontece durante o model.change. */
(function () {
  "use strict";
  const I = window.TeoriaImagens;
  const estados = new WeakMap();
  const escapar = s => String(s).replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
  const figura = img => `<figure class="image"><img src="${escapar(img.src)}" alt="" width="${img.largura}" height="${img.altura}"></figure>`;

  function chaveLocal(src) {
    if (I.PADRAO.test(src) || /^https:\/\//i.test(src)) return src;
    let nome;
    try { nome = decodeURIComponent(src).replace(/^\.\//, ""); } catch (_) { throw new Error("Nome de imagem inválido."); }
    if (!nome || nome.split("/").some(p => !p || p === "." || p === "..") || /[\\:%\x00-\x1f]/.test(nome)) throw new Error("Caminho de imagem inválido.");
    return nome;
  }

  async function markdown(texto, conhecidas = [], signal, pacote = false) {
    const analise = TeoriaMarkdown.converter(texto, { coletar: true });
    const mapa = new Map(conhecidas.map(i => [i.nome, i]));
    const urls = [];
    for (const src of analise.referencias) {
      if (I.PADRAO.test(src)) {mapa.set(src, {src}); continue;}
      const chave = chaveLocal(src);
      if (mapa.has(chave)) continue;
      if (!pacote && /^https:\/\//i.test(src)) urls.push(src);
      else throw new Error("Imagem não encontrada no pacote/arquivos: " + chave + ". Nenhum conteúdo foi substituído.");
    }
    for (const img of await I.remotas(urls, signal)) mapa.set(img.nome, img);
    const resultado = TeoriaMarkdown.converter(texto, { resolver: src => mapa.get(chaveLocal(src)) });
    await I.preparar(resultado.html, signal);
    return resultado;
  }

  function validarFragmento(editor, html) {
    const contagem = I.documento(html).content.querySelectorAll("img").length;
    const fragmento = editor.data.parse(html);
    let convertidas = 0;
    for (const item of editor.model.createRangeIn(fragmento).getItems()) {
      if (item.name === "imageInline" || item.name === "imageBlock") convertidas++;
    }
    if (contagem !== convertidas) throw new Error("O editor não conseguiu preservar todas as imagens. Use um ZIP com Markdown.");
    return fragmento;
  }

  async function transacao(editor, trabalho, substituir = false) {
    const estado = estados.get(editor);
    if (!estado || estado.pendente || editor.isReadOnly) throw new Error("Aguarde a operação atual do editor.");
    const original = editor.getData(), selecao = editor.model.createSelection(editor.model.document.selection);
    const controller = new AbortController(), signal = controller.signal;
    const limite = Date.now() + 60000;
    const verificarPrazo = () => {
      if (Date.now() >= limite) controller.abort();
      signal.throwIfAborted();
    };
    estado.pendente = true; estado.controller = controller;
    estado.mensagem.textContent = "Preparando conteúdo e imagens. O conteúdo atual permanece preservado.";
    editor.enableReadOnlyMode("imagens-em-processamento");
    const prazo = setTimeout(() => controller.abort(), 60000);
    let aoAbortar;
    try {
      const cancelada = new Promise((_, rejeitar) => {
        aoAbortar = () => rejeitar(new DOMException("Operação cancelada.", "AbortError"));
        signal.addEventListener("abort", aoAbortar, {once:true});
      });
      // O prazo encerra a espera mesmo para promessas que não aceitam signal,
      // como File.arrayBuffer(). Resultados tardios nunca chegam ao model.change.
      const resultado = await Promise.race([cancelada, new Promise(resolve => resolve(trabalho(signal)))]);
      verificarPrazo();
      if (editor.state !== "ready") throw new Error("Importação cancelada.");
      if (editor.getData() !== original) throw new Error("O conteúdo mudou durante a importação. Reabra o importador.");
      const fragmento = validarFragmento(editor, resultado.html);
      verificarPrazo();
      if (!substituir) {
        const imagem = item => item.name === "imageInline" || item.name === "imageBlock";
        const novas = [...editor.model.createRangeIn(fragmento).getItems()].filter(imagem).length;
        const permanecem = [...editor.model.createRangeIn(editor.model.document.getRoot()).getItems()]
          .filter(item => imagem(item) && ![...selecao.getRanges()].some(range => {
            const alvo = editor.model.createRangeOn(item);
            return !range.isCollapsed && !range.start.isAfter(alvo.start) && !range.end.isBefore(alvo.end);
          })).length;
        if (novas + permanecem > I.MAX_IMAGENS) throw new Error("Cada teoria pode conter até 20 imagens. Divida o material em mais textos.");
      }
      editor.model.change(writer => {
        verificarPrazo();
        writer.setSelection(substituir ? editor.model.document.getRoot() : selecao, substituir ? "in" : undefined);
        editor.model.insertContent(fragmento);
      });
      estado.mensagem.textContent = ["Conteúdo e imagens preparados. Revise e salve a teoria.", ...(resultado.avisos || [])].join(" ");
      return resultado;
    } catch (erro) {
      const mensagem = erro.name === "AbortError" ? "Importação cancelada ou tempo excedido. Tente novamente." : erro.message;
      if (editor.state !== "destroyed") estado.mensagem.textContent = mensagem + " O conteúdo anterior foi preservado.";
      throw new Error(mensagem);
    } finally {
      clearTimeout(prazo);
      signal.removeEventListener("abort", aoAbortar);
      if (estado.controller === controller) {
        estado.pendente = false; estado.controller = null;
        if (editor.state !== "destroyed") editor.disableReadOnlyMode("imagens-em-processamento");
      }
    }
  }

  function fonteMatematica(raiz) {
    // HTML renderizado pode transportar duas representações da mesma fórmula.
    // Extrair a anotação LaTeX e descartar todo o DOM de apresentação da origem.
    for (const no of [...raiz.querySelectorAll(".katex")]) {
      if (!raiz.contains(no)) continue;
      const anotacao = no.querySelector('annotation[encoding="application/x-tex"]');
      if (!anotacao) throw new Error("Uma fórmula copiada não contém LaTeX recuperável. Use Markdown ou ZIP.");
      const alvo = no.closest(".katex-display") || no;
      const novo = document.createElement(alvo.classList.contains("katex-display") ? "figure" : "span");
      novo.className = novo.tagName === "FIGURE" ? "ro-math-display" : "ro-math-inline";
      TeoriaMatematica.validar(anotacao.textContent);novo.textContent = anotacao.textContent;alvo.replaceWith(novo);
    }
    for (const math of [...raiz.querySelectorAll("math")]) {
      const anotacao = math.querySelector('annotation[encoding="application/x-tex"]');
      if (!anotacao) throw new Error("Uma fórmula copiada não contém LaTeX recuperável. Use Markdown ou ZIP.");
      const bloco = math.getAttribute("display") === "block", novo = document.createElement(bloco ? "figure" : "span");
      novo.className = bloco ? "ro-math-display" : "ro-math-inline";
      TeoriaMatematica.validar(anotacao.textContent);novo.textContent = anotacao.textContent;math.replaceWith(novo);
    }
    // Reconhecer delimitadores também no texto de uma colagem HTML, preservando
    // a formatação dos elementos vizinhos. Código e fórmulas já marcadas são literais.
    const walker = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT);
    const textos = [];while(walker.nextNode()) textos.push(walker.currentNode);
    for (const no of textos) {
      if (no.parentElement?.closest("code,pre,.ro-math-inline,.ro-math-display")) continue;
      const texto = no.data, fragmento = document.createDocumentFragment();let pos = 0, cursor = 0, mudou = false;
      while (pos < texto.length - 1) {
        const abertura = texto.slice(pos, pos + 2);
        if (abertura !== "\\(" && abertura !== "\\[") {pos++;continue;}
        let barras = 0; for(let p=pos-1;p>=0&&texto[p]==="\\";p--)barras++;
        if (barras % 2) {pos+=2;continue;}
        const fechar = abertura === "\\(" ? "\\)" : "\\]";
        let fim = texto.indexOf(fechar, pos + 2);
        while(fim!==-1){let n=0;for(let p=fim-1;p>=pos+2&&texto[p]==="\\";p--)n++;if(n%2===0)break;fim=texto.indexOf(fechar,fim+2);}
        if (fim === -1) break;
        const fonte = texto.slice(pos + 2, fim);TeoriaMatematica.validar(fonte);
        fragmento.appendChild(document.createTextNode(texto.slice(cursor, pos)));
        const elemento = document.createElement(abertura === "\\(" ? "span" : "figure");
        elemento.className = elemento.tagName === "SPAN" ? "ro-math-inline" : "ro-math-display";
        elemento.textContent = fonte;fragmento.appendChild(elemento);
        cursor = pos = fim + 2;mudou = true;
      }
      if (mudou) {fragmento.appendChild(document.createTextNode(texto.slice(cursor)));no.replaceWith(fragmento);}
    }
  }

  function destaques(raiz) {
    for (const span of raiz.querySelectorAll("span")) {
      if (span.matches(".ro-math-inline")) continue;
      const regras = [
        ["strong", [...span.classList].some(c => ["font-semibold","font-bold","font-extrabold","font-black"].includes(c)) || span.style.fontWeight === "bold" || Number(span.style.fontWeight) >= 600],
        ["em", span.classList.contains("italic") || span.style.fontStyle === "italic"],
        ["u", /\bunderline\b/.test(span.style.textDecoration + " " + span.style.textDecorationLine)]
      ];
      for (const [tag, ativa] of regras) if(ativa){const novo=document.createElement(tag);novo.append(...span.childNodes);span.appendChild(novo);}
    }
  }

  function dataFile(src) {
    if (src.length > 7 * 1024 * 1024) throw new Error("Imagem incorporada muito grande.");
    const match = /^data:(image\/(?:png|jpeg|webp));base64,([a-zA-Z0-9+/=\s]+)$/.exec(src);
    if (!match) throw new Error("Imagem incorporada em formato não permitido.");
    const dados = atob(match[2]);
    return new File([Uint8Array.from(dados, c => c.charCodeAt(0))], "clipboard.png", { type: match[1] });
  }

  async function colagem(html, texto, arquivos, signal) {
    if (html.length > 8 * 1024 * 1024 || texto.length > 250000) throw new Error("O conteúdo copiado excede o limite. Use um ZIP.");
    // Markdown copiado como texto continua usando exatamente o importador atual.
    if (!html && texto.trim()) {
      const analise = TeoriaMarkdown.converter(texto, {coletar:true});
      if (!analise.referencias.length && arquivos.length) throw new Error("A colagem não informa a posição das imagens. Use um ZIP com Markdown.");
      const enviadas = arquivos.length ? await I.arquivos(arquivos, signal) : [];
      const conhecidas = enviadas.map((i,n)=>({...i,nome:arquivos[n].name}));
      return markdown(texto, conhecidas, signal);
    }
    const molde = I.documento(html);
    const raiz = molde.content;
    raiz.querySelectorAll("script,style,link,meta,base,iframe,object,embed").forEach(n=>n.remove());
    const imgs = [...raiz.querySelectorAll("img")];
    if (imgs.length > I.MAX_IMAGENS) throw new Error("Cada colagem pode conter até 20 imagens.");
    if (!imgs.length && arquivos.length) {
      if (raiz.textContent.trim()) throw new Error("A colagem não informa a posição das imagens. Use um ZIP com Markdown.");
      const enviadas = await I.arquivos(arquivos, signal);
      const resultado = {html:enviadas.map(figura).join(""),avisos:[]};
      await I.preparar(resultado.html,signal);return resultado;
    }
    const uploads = [], usadas = new Set(), remotas = [], planos = [];
    for (const img of imgs) {
      const src = img.getAttribute("src") || "";
      if (I.PADRAO.test(src)) {planos.push({img, propria:{src}});continue;}
      let file = null;
      if (src.startsWith("data:")) file = dataFile(src);
      else {
        let nome = "";
        try {nome=decodeURIComponent(src.split(/[?#]/)[0].split(/[\\/]/).pop());} catch(_) {}
        const candidatas = arquivos.filter(f=>f.name===nome);
        if (candidatas.length===1) file=candidatas[0];
        else if(imgs.length===1 && arquivos.length===1) file=arquivos[0];
        if (candidatas.length>1) throw new Error("Há arquivos com nomes ambíguos na colagem. Use um ZIP.");
      }
      if(file){let indice=uploads.indexOf(file);if(indice===-1){indice=uploads.length;uploads.push(file);}usadas.add(file);planos.push({img,indice});}
      else if(/^https:\/\//i.test(src)){remotas.push(src);planos.push({img,remota:src});}
      else throw new Error("Uma imagem não veio como arquivo recuperável. Use um ZIP com as imagens.");
    }
    if (arquivos.some(f=>!usadas.has(f))) throw new Error("Não foi possível associar todos os arquivos às posições copiadas. Use um ZIP.");
    const enviadas = uploads.length ? await I.arquivos(uploads, signal) : [];
    const baixadas = new Map((await I.remotas(remotas,signal)).map(i=>[i.nome,i]));
    for(const plano of planos){
      const imagem = plano.propria || (plano.remota ? baixadas.get(plano.remota) : enviadas[plano.indice]);
      if(!imagem)throw new Error("Nem todas as imagens foram incorporadas.");
      plano.img.setAttribute("src",imagem.src);
      if(imagem.largura){plano.img.setAttribute("width",imagem.largura);plano.img.setAttribute("height",imagem.altura);}
    }
    fonteMatematica(raiz);destaques(raiz);
    let preparado = window.TeoriaEditor.normalizarListasWordHtml(molde.innerHTML);
    preparado = TeoriaMarkdown.sanitizarHtml(preparado);
    const resultado = {html:preparado,avisos:[]};
    await I.preparar(preparado,signal);return resultado;
  }

  window.TeoriaImagensEditor = { estados, transacao, markdown, colagem, validarFragmento,
    cancelar(editor) {estados.get(editor)?.controller?.abort();} };

  window.criarPluginTeoriaImagens = function(C) {
    return class TeoriaImagensPlugin extends C.Plugin {
      static get pluginName(){return "TeoriaImagens";}
      static get requires(){return [C.Image,C.ImageCaption,C.ImageTextAlternative,C.ImageToolbar];}
      init(){
        const editor = this.editor;
        const controles = document.createElement("div");controles.className="teoria-imagens-controles";
        const entrada = document.createElement("input");entrada.type="file";entrada.accept="image/png,image/jpeg,image/webp";entrada.multiple=true;entrada.hidden=true;
        const mensagem = document.createElement("span");mensagem.setAttribute("role","status");controles.append(entrada,mensagem);
        this.estado={pendente:false,controller:null,mensagem};estados.set(editor,this.estado);this.controles=controles;
        editor.ui.componentFactory.add("imagemPropria",locale=>{
          const botao = new C.ButtonView(locale);botao.set({label:"Inserir imagens",withText:true,tooltip:true});
          botao.bind("isEnabled").to(editor,"isReadOnly",v=>!v);
          this.listenTo(botao,"execute",()=>entrada.click());return botao;
        });
        entrada.addEventListener("change",()=>{
          const arquivos=[...entrada.files];entrada.value="";if(!arquivos.length)return;
          void transacao(editor,async signal=>{
            const imagens=await I.arquivos(arquivos,signal),html=imagens.map(figura).join("");
            await I.preparar(html,signal);return {html,avisos:[]};
          }).catch(()=>{});
        });
        for (const tipo of ["imageBlock","imageInline"]) {
          editor.conversion.for("editingDowncast").add(dispatcher=>{
            dispatcher.on("attribute:src:"+tipo,(evt,dados,api)=>{
              if(!api.consumable.consume(dados.item,evt.name))return;
              const elemento=api.mapper.toViewElement(dados.item);
              const img=editor.plugins.get("ImageUtils").findViewImgElement(elemento);
              api.writer.setAttribute("src",I.previa(dados.attributeNewValue),img);
              api.writer.setAttribute("referrerpolicy","no-referrer",img);
            },{priority:"high"});
          });
        }
        this.listenTo(editor.editing.view.document,"clipboardInput",(evt,dados)=>{
          if(dados.content && typeof dados.content !== "string")return;
          const html=dados.dataTransfer.getData("text/html")||"",texto=dados.dataTransfer.getData("text/plain")||"";
          const arquivos=[...(dados.dataTransfer.files||[])];
          const temImagens=/<img\b/i.test(html)||arquivos.length||/!\[[^\]]*\]\s*\(/.test(texto);
          // Também tratar LaTeX/KaTeX de uma colagem mista sem imagens.
          if(!temImagens && !/\\[([]|class=["'][^"']*katex|<math\b/i.test(html||texto))return;
          evt.stop();
          if(editor.isReadOnly || this.estado.pendente){mensagem.textContent="Aguarde a importação em andamento.";return;}
          void transacao(editor,async signal=>{
            // Materializar os bytes enquanto o evento paste ainda está ativo.
            // O envio assíncrono não depende do armazenamento do DataTransfer.
            if(arquivos.length)I.validarArquivos(arquivos);
            const copias=await Promise.all(arquivos.map(async file=>new File(
              [await file.arrayBuffer()],file.name||"clipboard.png",{type:file.type}
            )));
            signal.throwIfAborted();
            return colagem(html,texto,copias,signal);
          }).catch(()=>{});
        },{priority:"highest"});
        this.timer=setInterval(()=>{
          if(this.estado.pendente||editor.state!=="ready")return;
          void I.preparar(editor.getData()).then(()=>{
            if(editor.state!=="ready")return;
            for(const item of editor.model.createRangeIn(editor.model.document.getRoot()).getItems()) {
              if(item.name==="imageBlock"||item.name==="imageInline")editor.editing.reconvertItem(item);
            }
          }).catch(erro=>{mensagem.textContent="Imagens indisponíveis: "+erro.message;});
        },12*60*1000);
      }
      afterInit(){this.editor.ui.on("ready",()=>this.editor.ui.view.element.before(this.controles));}
      destroy(){
        clearInterval(this.timer);this.estado.controller?.abort();this.controles.remove();estados.delete(this.editor);
        return super.destroy();
      }
    };
  };
})();
