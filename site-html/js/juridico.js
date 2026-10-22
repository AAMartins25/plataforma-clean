// Evita instâncias duplicadas entre HTML novo e carregamento sob demanda.
window.Juridico = window.Juridico || (() => {
  let estado = null;
  let consulta = null;
  let jaObservouPoliticaAtiva = false;
  const campo = () => document.getElementById("aceiteJuridico");
  const assinatura = e => e?.obrigatorio ? e.documentos.map(d => `${d.tipo}:${d.id}`).sort().join(",") : null;
  function limpar() { if (campo()) campo().checked = false; }
  function indeterminada() {
    return Object.assign(new Error("Não foi possível confirmar a política jurídica. Tente novamente em instantes."),
      {codigo: "POLITICA_INDETERMINADA"});
  }
  function garantirCampo() {
    let box = document.getElementById("boxAceiteJuridico");
    if (box) return box;
    const opcoes = document.getElementById("opcoes_acesso") || document.getElementById("opcoesAcesso");
    if (!opcoes) throw new Error("Atualize esta página para confirmar os documentos.");
    box = document.createElement("div");
    box.id = "boxAceiteJuridico";
    box.hidden = true;
    box.style.cssText = "margin-top:16px;line-height:1.6;overflow-wrap:anywhere;";
    // Marcação estática: nenhum metadado externo é inserido como HTML.
    box.innerHTML = '<input type="checkbox" id="aceiteJuridico" aria-labelledby="textoAceiteJuridico" /> '
      + '<span id="textoAceiteJuridico">Ciente dos <a id="linkTermos" target="_blank" rel="noopener noreferrer">Termos de Contratação</a> e da '
      + '<a id="linkPrivacidade" target="_blank" rel="noopener noreferrer">Política de Privacidade e Proteção de Dados</a>.</span>';
    opcoes.insertAdjacentElement("afterend", box);
    return box;
  }
  function validarEstado(dados) {
    if (!dados || typeof dados.obrigatorio !== "boolean" || !Array.isArray(dados.documentos)) throw indeterminada();
    if (dados.obrigatorio) {
      if (dados.documentos.length !== 2) throw indeterminada();
      for (const tipo of ["TERMOS", "PRIVACIDADE"]) {
        const encontrados = dados.documentos.filter(d => d?.tipo === tipo);
        if (encontrados.length !== 1) throw indeterminada();
        const d = encontrados[0];
        if (!Number.isSafeInteger(d.id) || d.id <= 0 || !(d.pdf_site_url || d.pdf_url || d.url)) throw indeterminada();
        const url = d.pdf_site_url ? new URL(d.pdf_site_url, window.location.href) : new URL(d.pdf_url || d.url, API_BASE);
        if (!["https:", "http:"].includes(url.protocol)) throw indeterminada();
      }
      if (dados.documentos[0].id === dados.documentos[1].id) throw indeterminada();
    }
    return dados;
  }
  async function consultar() {
    const controller = new AbortController();
    const prazo = setTimeout(() => controller.abort(), 10000);
    try {
      const resposta = await fetch(`${API_BASE}/public/juridico/vigente`, {cache: "no-store", signal: controller.signal});
      // 404 é compatibilidade legada, não uma dispensa genérica por indisponibilidade.
      if (resposta.status === 404) {
        if (jaObservouPoliticaAtiva) throw indeterminada();
        return {obrigatorio: false, documentos: [], origem: "BACKEND_ANTIGO"};
      }
      if (resposta.status !== 200) throw indeterminada();
      return validarEstado(await resposta.json());
    } catch (err) {
      throw err?.codigo === "POLITICA_INDETERMINADA" ? err : indeterminada();
    } finally { clearTimeout(prazo); }
  }
  function carregar() {
    if (!consulta) {
      consulta = (async () => {
        try {
          const novo = await consultar();
          if (assinatura(estado) !== assinatura(novo)) limpar();
          if (novo.obrigatorio) {
            const box = garantirCampo();
            for (const [tipo, id] of [["TERMOS", "linkTermos"], ["PRIVACIDADE", "linkPrivacidade"]]) {
              const d = novo.documentos.find(d => d.tipo === tipo);
              const link = document.getElementById(id);
              link.href = d.pdf_site_url ? new URL(d.pdf_site_url, window.location.href).href : new URL(d.pdf_url || d.url, API_BASE).href;
              link.title = `${d.titulo || tipo} — versão ${d.versao || ""}`;
            }
            box.hidden = false;
            jaObservouPoliticaAtiva = true;
          } else {
            limpar();
            const box = document.getElementById("boxAceiteJuridico");
            if (box) box.hidden = true;
          }
          estado = novo;
          return novo;
        } catch (err) {
          estado = null;
          limpar();
          throw err;
        }
      })().finally(() => { consulta = null; });
    }
    return consulta;
  }
  async function payload() {
    const anteriores = assinatura(estado);
    const selecao = document.querySelector("input[name='tipo_acesso']:checked")?.value;
    const atual = await carregar(); // Nunca autorizar por estado desativado em cache.
    if (selecao !== document.querySelector("input[name='tipo_acesso']:checked")?.value) {
      limpar();
      throw new Error("A seleção mudou. Confira a opção de acesso e tente novamente.");
    }
    if (!atual.obrigatorio) return {};
    if (anteriores !== assinatura(atual)) limpar();
    if (!campo()?.checked) {
      document.body.style.visibility = "visible";
      campo()?.focus();
      throw new Error("Confirme a ciência dos Termos de Contratação e da Política de Privacidade e Proteção de Dados.");
    }
    return {aceite_juridico: {aceito: true,
      termos_id: atual.documentos.find(d => d.tipo === "TERMOS").id,
      privacidade_id: atual.documentos.find(d => d.tipo === "PRIVACIDADE").id}};
  }
  document.addEventListener("change", e => {
    if (e.target.matches("input[name='tipo_acesso'], #codigo_cupom_desconto")) limpar();
  });
  window.addEventListener("pageshow", limpar);
  function iniciar() { limpar(); carregar().catch(() => {}); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar, {once: true});
  else iniciar();
  async function erro(e) {
    if (/ACEITE_(DESATUALIZADO|OBRIGATORIO)/.test(String(e?.message))) { limpar(); await carregar(); }
  }
  return {payload, limpar, erro};
})();
