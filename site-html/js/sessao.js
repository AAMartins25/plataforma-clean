/* Ciclo de sessão do frontend. Não decide permissões nem destinos de navegação. */
(() => {
  "use strict";
  const tokenKey = "access_token";
  const generationKey = "auth_generation";
  const snapshot = () => ({ token: localStorage.getItem(tokenKey), generation: localStorage.getItem(generationKey) });
  const same = (a, b = snapshot()) => a.token === b.token && a.generation === b.generation;
  let observed = snapshot();

  // Compartilhado entre formulários e abas: somente a tentativa mais recente vence.
  function iniciarAutenticacao() {
    const id = crypto.randomUUID();
    localStorage.setItem("auth_attempt", id);
    return { id, sessao: snapshot() };
  }

  function autenticacaoAtual(tentativa) {
    return tentativa.id === localStorage.getItem("auth_attempt") && same(tentativa.sessao);
  }

  function aceitarAutenticacao(tentativa, token) {
    if (!autenticacaoAtual(tentativa)) return null;
    definirToken(token);
    return { id: tentativa.id, sessao: snapshot() };
  }

  function limparIdentificacao() {
    document.querySelectorAll('[id="nomeUsuarioLogadoGlobal"], [id="nome_aluno_logado"]').forEach(el => {
      el.replaceChildren();
      el.removeAttribute("title");
      el.removeAttribute("aria-label");
      el.classList.remove("ro-header-identity");
      if (el.id === "nomeUsuarioLogadoGlobal") el.remove();
    });
    document.querySelectorAll(".ro-header--identified").forEach(el => el.classList.remove("ro-header--identified"));
  }

  function sincronizar() {
    const current = snapshot();
    if (!same(observed, current)) {
      limparIdentificacao();
      observed = current;
    }
    return current;
  }

  function encerrar(expected = snapshot()) {
    if (!same(expected)) return false;
    localStorage.removeItem(tokenKey);
    localStorage.removeItem("me_cache");
    localStorage.setItem(generationKey, crypto.randomUUID());
    observed = snapshot();
    limparIdentificacao();
    return true;
  }

  function definirToken(token) {
    localStorage.removeItem("me_cache");
    limparIdentificacao();
    localStorage.setItem(generationKey, crypto.randomUUID());
    localStorage.setItem(tokenKey, token);
    observed = snapshot();
  }

  function exigirAtual(expected) {
    if (!same(expected)) {
      const erro = new Error("Resposta de uma sessão anterior ignorada.");
      erro.name = "SessaoAlteradaError";
      throw erro;
    }
  }

  async function requisitar(url, options) {
    sincronizar();
    const expected = snapshot();
    const bearer = new Headers(options?.headers).get("Authorization");
    // Somente o Bearer da sessão atual pode invalidá-la.
    const autenticada = !!expected.token && bearer === `Bearer ${expected.token}`;
    if (bearer?.startsWith("Bearer ") && !autenticada && !["Bearer null", "Bearer undefined"].includes(bearer)) {
      const erro = new Error("Requisição de uma sessão anterior ignorada.");
      erro.name = "SessaoAlteradaError";
      throw erro;
    }
    const response = await fetch(url, options);
    if (!autenticada) return response;
    exigirAtual(expected);
    if (response.status === 401) encerrar(expected);
    const afterResponse = snapshot();
    // Verifica também a leitura assíncrona do corpo, antes de entregar dados à página.
    for (const method of ["json", "text"]) {
      const original = response[method].bind(response);
      response[method] = async () => {
        const data = await original();
        exigirAtual(response.status === 401 ? afterResponse : expected);
        return data;
      };
    }
    return response;
  }

  async function chave(expected) {
    const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(`${expected.generation || ""}:${expected.token}`));
    return Array.from(new Uint8Array(bytes), b => b.toString(16).padStart(2, "0")).join("");
  }

  async function obterMe(url) {
    const expected = sincronizar();
    if (!expected.token) { localStorage.removeItem("me_cache"); limparIdentificacao(); return null; }
    const session = await chave(expected);
    exigirAtual(expected);
    try {
      const cached = JSON.parse(localStorage.getItem("me_cache"));
      const age = Date.now() - cached?.ts;
      if (cached?.session === session && age >= 0 && age < 30000 && cached.me) return cached.me;
    } catch (_) { /* Cache inválido não impede a consulta. */ }
    localStorage.removeItem("me_cache");
    const response = await requisitar(url, { headers: { Authorization: `Bearer ${expected.token}` } });
    if (!response.ok) return null;
    const me = await response.json();
    exigirAtual(expected);
    // Somente os dados usados pela identificação ficam no cache.
    const identity = { nome: me.nome };
    try { localStorage.setItem("me_cache", JSON.stringify({ session, ts: Date.now(), me: identity })); } catch (_) { /* Armazenamento cheio não invalida sessão. */ }
    return identity;
  }

  window.Sessao = { fetch: requisitar, obterMe, encerrar, definirToken, snapshot, mesma: same, limparIdentificacao,
    iniciarAutenticacao, autenticacaoAtual, aceitarAutenticacao };
  window.addEventListener("storage", event => {
    if (event.key === tokenKey || event.key === generationKey || event.key === null) sincronizar();
  });
})();
