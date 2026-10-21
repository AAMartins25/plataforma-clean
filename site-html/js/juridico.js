// Compartilhado pelas duas interfaces. Aceite nunca é restaurado do localStorage.
window.Juridico = (() => {
  let estado = null;
  let carregamento;
  const campo = () => document.getElementById("aceiteJuridico");
  function limpar() { if (campo()) campo().checked = false; }
  async function carregar() {
    const resposta = await fetch(`${API_BASE}/public/juridico/vigente`, {cache: "no-store"});
    // Compatibilidade temporária com backend anterior à implantação desta funcionalidade.
    if (resposta.status === 404) estado = {obrigatorio: false, documentos: []};
    else {
      if (!resposta.ok) throw new Error("Não foi possível carregar os documentos. Tente novamente.");
      estado = await resposta.json();
    }
    const box = document.getElementById("boxAceiteJuridico");
    if (!box) throw new Error("Atualize esta página para confirmar os documentos.");
    box.hidden = !estado.obrigatorio;
    if (estado.obrigatorio) {
      for (const [tipo, id] of [["TERMOS", "linkTermos"], ["PRIVACIDADE", "linkPrivacidade"]]) {
        const d = estado.documentos.find(d => d.tipo === tipo);
        if (!d) throw new Error("Documentos jurídicos incompletos.");
        const link = document.getElementById(id);
        link.href = d.pdf_site_url
          ? new URL(d.pdf_site_url, window.location.href).href
          : new URL(d.pdf_url || d.url, API_BASE).href;
        link.title = `${d.titulo} — versão ${d.versao}`;
      }
    }
    return estado;
  }
  async function payload() {
    if (!carregamento) carregamento = carregar().catch(e => { carregamento = null; throw e; });
    await carregamento;
    if (!estado || !estado.obrigatorio) await carregar();
    if (!estado.obrigatorio) return {};
    if (!campo()?.checked) {
      document.body.style.visibility = "visible";
      campo()?.focus();
      throw new Error("Confirme a ciência dos Termos de Contratação e da Política de Privacidade e Proteção de Dados.");
    }
    const selecao = document.querySelector("input[name=tipo_acesso]:checked")?.value;
    const anteriores = estado.documentos.map(d => d.id).join(",");
    await carregar();
    if (!estado.obrigatorio) { limpar(); return {}; }
    if (anteriores !== estado.documentos.map(d => d.id).join(",")) {
      limpar();
      throw new Error("Os documentos foram atualizados. Leia as novas versões e confirme novamente.");
    }
    if (!campo()?.checked || selecao !== document.querySelector("input[name=tipo_acesso]:checked")?.value) {
      limpar();
      throw new Error("A seleção mudou. Confirme novamente os documentos.");
    }
    return {aceite_juridico: {aceito: true,
      termos_id: estado.documentos.find(d => d.tipo === "TERMOS").id,
      privacidade_id: estado.documentos.find(d => d.tipo === "PRIVACIDADE").id}};
  }
  document.addEventListener("change", e => {
    if (e.target.matches("input[name='tipo_acesso'], #codigo_cupom_desconto")) limpar();
  });
  window.addEventListener("pageshow", limpar);
  document.addEventListener("DOMContentLoaded", () => {
    carregamento = carregar().catch(() => { carregamento = null; });
  });
  async function erro(e) {
    if (/ACEITE_DESATUALIZADO/.test(String(e?.message))) {
      limpar();
      await carregar();
    }
  }
  return {payload, limpar, erro};
})();
