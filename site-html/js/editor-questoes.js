/* Uma instância do editor de teoria por campo; nenhuma configuração alternativa. */
(function () {
  const estados = new Map();
  const seletor = "#questaoEnunciado, #questaoComentario, textarea[id^='alternativa_']";
  function ler(campo) {
    const estado = estados.get(campo);
    if (estado?.carregando) throw new Error("Aguarde a abertura dos editores.");
    if (estado?.erro && estado.formato === "html_v1") throw new Error("Reabra a questão para carregar o editor antes de salvar o conteúdo formatado.");
    if (!TeoriaEditor.pronto(campo)) throw new Error("Aguarde a importação das imagens antes de salvar.");
    return TeoriaEditor.conteudo(campo);
  }
  async function iniciar(raiz, dados = {}) {
    await Promise.all([...raiz.querySelectorAll(seletor)].map(async campo => {
      let valor, formato;
      if (campo.id === "questaoEnunciado") {valor = dados.enunciado; formato = dados.enunciado_formato;}
      else if (campo.id === "questaoComentario") {valor = dados.comentario; formato = dados.comentario_formato;}
      else {const alt = (dados.alternativas || []).find(a => a.letra === campo.id.slice(-1)); valor = alt?.texto; formato = alt?.texto_formato;}
      campo.value = valor || "";
      const estado = {carregando: true, formato, erro: null}; estados.set(campo, estado);
      campo.readOnly = true;
      const aviso = document.createElement("p"); aviso.className = "questao-editor-aviso"; aviso.setAttribute("role", "status"); aviso.textContent = "Abrindo editor…"; campo.after(aviso);
      try {
        const editor = await TeoriaEditor.iniciar(campo, formato === "html_v1" ? campo.value : TeoriaEditor.legadoParaHtml(campo.value));
        if (!campo.isConnected) { await TeoriaEditor.destruir(campo); return; }
        const rotulo = campo.id === "questaoEnunciado" ? "Enunciado da questão" : campo.id === "questaoComentario" ? "Comentário da questão" : "Alternativa " + campo.id.slice(-1);
        editor.ui.view.editable.element.setAttribute("aria-label", rotulo);
        aviso.remove(); campo.readOnly = false;
      } catch (erro) {
        estado.erro = erro;
        campo.readOnly = formato === "html_v1";
        aviso.textContent = "Editor indisponível: " + erro.message + (campo.readOnly ? " Reabra a questão para tentar novamente." : " O campo continua disponível como texto simples.");
      } finally {estado.carregando = false; if (!campo.isConnected) estados.delete(campo); }
    }));
  }
  function dados() {
    const obter = id => ler(document.getElementById(id));
    const enunciado = obter("questaoEnunciado"), comentario = obter("questaoComentario");
    return {enunciado: enunciado.conteudo, enunciado_formato: enunciado.conteudo_formato,
      comentario: comentario.conteudo, comentario_formato: comentario.conteudo_formato,
      alternativas: [...document.querySelectorAll("#camposQuestaoCompleta textarea[id^='alternativa_']")].map(campo => {
        const valor = ler(campo); return {letra: campo.id.slice(-1), texto: valor.conteudo, texto_formato: valor.conteudo_formato};
      })};
  }
  new MutationObserver(() => {
    for (const [campo, estado] of estados) if (!campo.isConnected && !estado.carregando) {
      estados.delete(campo); void TeoriaEditor.destruir(campo);
    }
  }).observe(document.documentElement, {childList: true, subtree: true});
  window.QuestaoEditores = {iniciar, dados};
})();
