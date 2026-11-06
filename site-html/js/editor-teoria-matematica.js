/* Plugin próprio: utiliza apenas APIs do pacote CKEditor 5 core. */
(function () {
  "use strict";
  let sequencia = 0;
  window.criarPluginTeoriaMatematica = function (C) {
    const M = window.TeoriaMatematica;
    const nomes = ["roMathInline", "roMathDisplay"];
    const selecionada = editor => {
      const no = editor.model.document.selection.getSelectedElement();
      return no && nomes.includes(no.name) ? no : null;
    };
    class FormulaCommand extends C.Command {
      refresh() {
        const pos = this.editor.model.document.selection.getFirstPosition();
        this.isEnabled = Boolean(pos && (selecionada(this.editor) ||
          this.editor.model.schema.findAllowedParent(pos, "roMathInline")));
      }
      execute({ fonte, bloco }) {
        M.validar(fonte);
        const editor = this.editor, atual = selecionada(editor);
        if (!atual) {
          let quantidade = 0;
          for (const item of editor.model.createRangeIn(editor.model.document.getRoot()).getItems()) {
            if (nomes.includes(item.name)) quantidade++;
          }
          if (quantidade >= M.LIMITE_FORMULAS) throw new Error("Cada teoria pode ter até 200 fórmulas.");
        }
        const nome = bloco ? "roMathDisplay" : "roMathInline";
        const pos = editor.model.document.selection.getFirstPosition();
        const criarParagrafo = atual?.name === "roMathDisplay" && nome === "roMathInline" &&
          editor.model.schema.checkChild(atual.parent, "paragraph");
        if (!criarParagrafo && !editor.model.schema.findAllowedParent(pos, nome)) throw new Error("Esta posição não aceita a fórmula neste formato.");
        editor.model.change(writer => {
          if (atual?.name === nome) {
            writer.setAttribute("latex", fonte, atual);
          } else {
            if (atual) {
              const antes = writer.createPositionBefore(atual);
              writer.remove(atual);
              if (criarParagrafo) {
                const p = writer.createElement("paragraph");
                writer.insert(p, antes);
                writer.setSelection(p, 0);
              } else writer.setSelection(antes);
            }
            const elemento = writer.createElement(nome, { latex: fonte });
            editor.model.insertObject(elemento, null, null, { setSelection: "on" });
          }
        });
      }
    }

    return class TeoriaFormula extends C.Plugin {
      static get pluginName() { return "TeoriaFormula"; }
      static get requires() { return [C.Widget]; }
      init() {
        const editor = this.editor;
        editor.model.schema.register("roMathInline", {
          inheritAllFrom: "$inlineObject", allowAttributes: ["latex"]
        });
        editor.model.schema.register("roMathDisplay", {
          inheritAllFrom: "$blockObject", allowAttributes: ["latex"]
        });
        for (const [nome, tag, classe] of [
          ["roMathInline", "span", "ro-math-inline"],
          ["roMathDisplay", "figure", "ro-math-display"]
        ]) {
          // Evitar a normalização de espaços/quebras do processador HTML.
          editor.data.registerRawContentMatcher({ name: tag, classes: classe });
          editor.conversion.for("upcast").elementToElement({
            view: { name: tag, classes: classe },
            model: (view, { writer }) => {
              const molde = document.createElement("template");
              molde.innerHTML = view.getCustomProperty("$rawContent") || "";
              if ([...molde.content.childNodes].some(no => no.nodeType !== Node.TEXT_NODE)) {
                throw new Error("A fonte da fórmula deve conter somente texto LaTeX.");
              }
              const fonte = molde.content.textContent;
              M.validar(fonte);
              return writer.createElement(nome, { latex: fonte });
            }
          });
          editor.conversion.for("dataDowncast").elementToElement({
            model: { name: nome, attributes: ["latex"] },
            view: (model, { writer }) => {
              // RawElement também na saída: não converter espaços consecutivos
              // em NBSP, nem normalizar quebras da fonte LaTeX.
              return writer.createRawElement(tag, { class: classe }, dom => {
                dom.textContent = model.getAttribute("latex");
              });
            }
          });
          editor.conversion.for("editingDowncast").elementToElement({
            model: { name: nome, attributes: ["latex"] },
            view: (model, { writer }) => {
              const fonte = model.getAttribute("latex");
              const no = writer.createContainerElement(tag, { class: classe });
              const previa = writer.createRawElement("span", {}, dom => M.desenhar(dom, fonte, nome === "roMathDisplay"));
              writer.insert(writer.createPositionAt(no, 0), previa);
              return C.toWidget(no, writer, { label: "Fórmula: " + fonte });
            }
          });
        }
        editor.commands.add("formula", new FormulaCommand(editor));
        this.criarDialogo();
        editor.ui.componentFactory.add("formula", locale => {
          const botao = new C.ButtonView(locale);
          botao.set({ label: "Fórmula", withText: true, tooltip: "Inserir ou editar fórmula LaTeX" });
          botao.bind("isEnabled").to(editor.commands.get("formula"), "isEnabled");
          this.listenTo(botao, "execute", () => this.abrir());
          return botao;
        });
        editor.keystrokes.set("Ctrl+Alt+m", (_dados, cancelar) => {
          if (editor.commands.get("formula").isEnabled) { this.abrir(); cancelar(); }
        });
      }

      criarDialogo() {
        const editor = this.editor, id = "ro-formula-" + (++sequencia);
        const dialogo = this.dialogo = document.createElement("dialog");
        dialogo.className = "ro-math-dialogo";
        dialogo.setAttribute("aria-labelledby", id + "-titulo");
        dialogo.innerHTML = `<h2 id="${id}-titulo">Fórmula matemática ou lógica</h2>
          <label for="${id}-fonte">Código LaTeX, sem os delimitadores externos</label>
          <textarea id="${id}-fonte" rows="5" spellcheck="false" maxlength="4096"></textarea>
          <label for="${id}-modo">Apresentação</label>
          <select id="${id}-modo"><option value="inline">Na linha do texto</option><option value="display">Em bloco</option></select>
          <p>Prévia</p><div class="ro-math-previa" aria-live="polite"></div>
          <p role="alert"></p><div class="ro-math-acoes">
          <button type="button" class="btn" data-formula="aplicar">Aplicar fórmula</button>
          <button type="button" class="btn" data-formula="cancelar">Cancelar</button></div>`;
        document.body.appendChild(dialogo);
        this.fonte = dialogo.querySelector("textarea");
        this.modo = dialogo.querySelector("select");
        this.erro = dialogo.querySelector('[role="alert"]');
        this.aplicar = dialogo.querySelector('[data-formula="aplicar"]');
        const previa = dialogo.querySelector(".ro-math-previa");
        const atualizar = () => {
          clearTimeout(this.temporizador);
          this.temporizador = setTimeout(() => {
            previa.classList.toggle("ro-math-display", this.modo.value === "display");
            const valido = M.desenhar(previa, this.fonte.value, this.modo.value === "display");
            this.erro.textContent = valido ? "" : "Não foi possível visualizar esta expressão. A fonte pode ser preservada para revisão.";
          }, 150);
        };
        this.fonte.addEventListener("input", atualizar);
        this.modo.addEventListener("change", atualizar);
        this.aplicar.addEventListener("click", () => {
          if (editor.isReadOnly) return;
          if (editor.model.document.version !== this.versao) {
            this.erro.textContent = "O conteúdo mudou. Cancele e reabra a edição da fórmula.";
            return;
          }
          try {
            M.validar(this.fonte.value);
            editor.model.change(writer => writer.setSelection(this.selecao));
            editor.execute("formula", { fonte: this.fonte.value, bloco: this.modo.value === "display" });
            dialogo.close();
          } catch (erro) { this.erro.textContent = erro.message; }
        });
        dialogo.querySelector('[data-formula="cancelar"]').addEventListener("click", () => dialogo.close());
        dialogo.addEventListener("close", () => {
          clearTimeout(this.temporizador);
          this.selecao = null;
          this.fonte.value = "";
          previa.textContent = "";
          if (editor.state !== "destroyed") editor.editing.view.focus();
        });
        this.listenTo(editor, "change:isReadOnly", () => {
          this.aplicar.disabled = editor.isReadOnly;
          if (editor.isReadOnly && dialogo.open) dialogo.close();
        });
        this.atualizarPrevia = atualizar;
      }

      abrir() {
        const editor = this.editor;
        if (editor.isReadOnly || this.dialogo.open) return;
        const atual = selecionada(editor);
        this.versao = editor.model.document.version;
        this.selecao = editor.model.createSelection(editor.model.document.selection);
        this.fonte.value = atual?.getAttribute("latex") || "";
        this.modo.value = atual?.name === "roMathDisplay" ? "display" : "inline";
        this.erro.textContent = "";
        this.dialogo.showModal();
        this.fonte.focus();
        this.atualizarPrevia();
      }

      destroy() {
        clearTimeout(this.temporizador);
        this.dialogo.remove();
        return super.destroy();
      }
    };
  };
})();
