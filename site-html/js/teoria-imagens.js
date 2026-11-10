/* Referências permanentes são dados; URLs assinadas existem somente na visualização. */
(function () {
  "use strict";
  const PADRAO = /^\/midias\/imagens\/([0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})$/;
  const MAX_IMAGENS = 20, MAX_ARQUIVO = 5 * 1024 * 1024, MAX_LOTE = 25 * 1024 * 1024;
  const cache = new Map(), leituras = new WeakMap();
  let tokenCache = null;

  async function api(caminho, corpo, signal) {
    signal?.throwIfAborted();
    const token = typeof getToken === "function" ? getToken() : localStorage.getItem("access_token");
    if (!token) throw new Error("Faça login novamente para acessar as imagens.");
    if (token !== tokenCache) { cache.clear(); tokenCache = token; }
    const multipart = corpo instanceof FormData;
    const base = typeof API_BASE === "string" ? API_BASE : location.origin;
    const requisitar = window.Sessao ? window.Sessao.fetch.bind(window.Sessao) : window.fetch.bind(window);
    const resposta = await requisitar(base + caminho, {
      method: "POST", signal, headers: { Authorization: "Bearer " + token,
        ...(multipart ? {} : {"Content-Type": "application/json"}) },
      body: multipart ? corpo : JSON.stringify(corpo)
    });
    signal?.throwIfAborted();
    if (token !== (typeof getToken === "function" ? getToken() : localStorage.getItem("access_token"))) {
      cache.clear(); throw new Error("A sessão mudou durante o envio. Reabra o editor.");
    }
    let resultado;
    try { resultado = await resposta.json(); } catch (_) { throw new Error("Resposta inválida do serviço de imagens."); }
    if (!resposta.ok) throw new Error(typeof resultado.detail === "string" ? resultado.detail : "Não foi possível processar as imagens.");
    return resultado;
  }

  function ids(raiz) {
    const elementos = [...raiz.querySelectorAll("img")];
    if (elementos.length > MAX_IMAGENS) throw new Error("Cada teoria pode conter até 20 imagens.");
    return [...new Set(elementos.map(img => {
      const match = PADRAO.exec(img.getAttribute("src") || "");
      if (!match) throw new Error("Uma imagem ainda não foi incorporada ao armazenamento próprio.");
      return match[1];
    }))];
  }

  function documento(html) {
    const molde = document.createElement("template");
    molde.innerHTML = html || "";
    return molde;
  }

  async function assinar(identificadores, contexto = null, signal) {
    if (!identificadores.length) return new Map();
    const caminho = contexto
      ? `${contexto.bateriaId ? "/baterias/" + encodeURIComponent(contexto.bateriaId) : "/aulas/" + encodeURIComponent(contexto.aulaId)}/imagens/assinaturas${contexto.query ? "?" + contexto.query : ""}`
      : "/admin/imagens/assinaturas";
    const resultado = await api(caminho, { ids: identificadores }, signal);
    const mapa = new Map();
    for (const imagem of resultado.imagens || []) {
      const url = String(imagem.url || "");
      if (!url.startsWith("https://") && !(url.startsWith("/") && !url.startsWith("//"))) throw new Error("Endereço de exibição inválido.");
      mapa.set(imagem.src, url);
      if (!contexto) cache.set(imagem.src, url);
    }
    if (mapa.size !== new Set(identificadores).size) throw new Error("Nem todas as imagens estão disponíveis.");
    return mapa;
  }

  async function preparar(html, signal) { await assinar(ids(documento(html).content), null, signal); }
  const previa = src => cache.get(src) || "";
  function paraLeitura(html) {
    const molde = documento(html);
    for (const img of molde.content.querySelectorAll("img")) {
      img.setAttribute("data-ro-src", img.getAttribute("src") || ""); img.removeAttribute("src");
    }
    return molde.innerHTML;
  }

  function validarArquivos(arquivos) {
    if (!arquivos.length || arquivos.length > MAX_IMAGENS) throw new Error("Selecione entre 1 e 20 imagens.");
    let total = 0;
    for (const arquivo of arquivos) {
      total += arquivo.size;
      if (!arquivo.size || arquivo.size > MAX_ARQUIVO) throw new Error("Cada imagem deve ter até 5 MB.");
    }
    if (total > MAX_LOTE) throw new Error("O lote excede 25 MB.");
  }

  async function arquivos(lista, signal) {
    validarArquivos(lista);
    const form = new FormData();
    lista.forEach((file, i) => form.append("arquivos", file, file.name || `imagem-${i}.png`));
    return (await api("/admin/imagens/arquivos", form, signal)).imagens;
  }

  async function zip(file, signal) {
    if (!file || file.size > MAX_LOTE) throw new Error("Selecione um ZIP de até 25 MB.");
    const form = new FormData(); form.append("arquivo", file);
    return api("/admin/imagens/zip", form, signal);
  }

  async function remotas(urls, signal) {
    if (!urls.length) return [];
    return (await api("/admin/imagens/remotas", { urls: [...new Set(urls)] }, signal)).imagens;
  }

  // Só altera o DOM da leitura após resolver todos os endereços. Os dados das
  // páginas continuam canônicos e nunca recebem tokens de download.
  async function renderizar(raiz, contexto) {
    if (!raiz) return;
    const anterior = leituras.get(raiz);
    if (anterior) { anterior.controller.abort(); clearTimeout(anterior.timer); }
    const imagens = [...raiz.querySelectorAll("img")];
    if (!imagens.length) return;
    const fontes = imagens.map(img => img.getAttribute("data-ro-src") || img.getAttribute("src"));
    const controller = new AbortController();
    const estado = { controller, timer: null }; leituras.set(raiz, estado);
    const aviso = document.createElement("p"); aviso.className = "teoria-imagens-aviso"; aviso.setAttribute("role", "status");
    imagens.forEach((img, i) => {img.setAttribute("data-ro-src", fontes[i]);img.removeAttribute("src");});
    try {
      const identificadores = fontes.map(src => {
        const match = PADRAO.exec(src || ""); if (!match) throw new Error("Referência de imagem inválida."); return match[1];
      });
      const mapa = await assinar([...new Set(identificadores)], contexto, controller.signal);
      if (!raiz.isConnected || controller.signal.aborted) return;
      let falhou = false;
      imagens.forEach((img, i) => {
        img.referrerPolicy = "no-referrer";
        img.onerror = () => {
          if (falhou || !raiz.isConnected) return;
          falhou = true; aviso.textContent = "Uma imagem não pôde ser exibida. Reabra o texto para tentar novamente.";
          raiz.appendChild(aviso);
        };
        img.src = mapa.get(fontes[i]);
      });
      estado.timer = setTimeout(() => {
        if (raiz.isConnected) void renderizar(raiz, contexto);
      }, 12 * 60 * 1000);
    } catch (erro) {
      if (controller.signal.aborted || !raiz.isConnected) return;
      aviso.textContent = "Imagens indisponíveis: " + erro.message;
      const tentar = document.createElement("button"); tentar.type = "button"; tentar.className = "btn"; tentar.textContent = "Tentar novamente";
      tentar.onclick = () => {aviso.remove(); void renderizar(raiz, contexto);};
      aviso.appendChild(tentar); raiz.appendChild(aviso);
    }
  }

  function cancelarLeitura(raiz) {
    const estado = raiz && leituras.get(raiz);
    if (estado) {estado.controller.abort(); clearTimeout(estado.timer);leituras.delete(raiz);}
  }
  window.TeoriaImagens = { PADRAO, MAX_IMAGENS, api, ids, documento, preparar, previa,
    arquivos, validarArquivos, zip, remotas, assinar, renderizar, cancelarLeitura, paraLeitura };
})();
