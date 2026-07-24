// js/app.js
const API_BASE = "https://reimagined-waffle-4jv4jw9pqpwjfqqp4-8000.app.github.dev";

// helpers
function qs(name) {
  return new URLSearchParams(window.location.search).get(name);
}

async function apiGet(path) {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url);
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`Erro ${res.status} em ${url}\n${txt}`);
  }
  return res.json();
}

// ======= AUTH HELPERS =======

function getToken() {
  return localStorage.getItem("access_token");
}

function setToken(token) {
  localStorage.setItem("access_token", token);
}

function clearToken() {
  localStorage.removeItem("access_token");
}

// GET com Bearer token
async function apiGetAuth(path) {
  const token = getToken();
  if (!token) throw new Error("Você não está logado. Faça login novamente.");

  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Authorization": `Bearer ${token}`
    }
  });

  if (!res.ok) {
    const txt = await res.text();
    throw new Error(txt || `Erro HTTP ${res.status}`);
  }
  return res.json();
}

// POST com Bearer token
async function apiPostAuth(path, body) {
  const token = getToken();
  if (!token) throw new Error("Você não está logado. Faça login novamente.");

  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`
    },
    body: JSON.stringify(body || {})
  });

  if (!res.ok) {
    const txt = await res.text();
    throw new Error(txt || `Erro HTTP ${res.status}`);
  }
  return res.json();
}

// POST público, sem Bearer token
async function apiPost(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(body || {})
  });

  if (!res.ok) {
    const txt = await res.text();
    throw new Error(
      txt || `Erro HTTP ${res.status}`
    );
  }

  return res.json();
}

async function aplicarCupomCursoInfo() {
  const campo =
    document.getElementById(
      "codigo_cupom_desconto"
    );

  const msg =
    document.getElementById(
      "msgCupomDesconto"
    );

  const resumo =
    document.getElementById(
      "resumoCupomDesconto"
    );

  const selecionado =
    document.querySelector(
      "input[name='tipo_acesso']:checked"
    );

  if (!campo || !msg || !selecionado) {
    return;
  }

  if (selecionado.value === "demo") {
    return;
  }

  const codigo =
    campo.value
      .trim()
      .toUpperCase();

  if (!codigo) {
    msg.textContent =
      "Informe o Cupom de Desconto.";

    msg.style.color =
      "#8a1f1f";

    if (resumo) {
      resumo.style.display = "none";
    }

    return;
  }

  try {
    msg.textContent =
      "Validando cupom...";

    msg.style.color = "";

    const resultado =
      await apiPost(
        "/cupons-desconto/validar",
        {
          codigo_cupom: codigo
        }
      );

    const valorOriginalCents =
      Number(
        selecionado.dataset.valorCents
      );

    const percentual =
      Number(
        resultado.percentual_desconto
      );

    const valorDescontoCents =
      Math.round(
        valorOriginalCents *
        percentual /
        100
      );

    const valorFinalCents =
      valorOriginalCents -
      valorDescontoCents;

    cupomAplicadoCursoInfo = {
      codigo_cupom:
        resultado.codigo_cupom,

      percentual_desconto:
        percentual,

      vendedor_id:
        resultado.vendedor_id,

      valor_original_cents:
        valorOriginalCents,

      valor_desconto_cents:
        valorDescontoCents,

      valor_final_cents:
        valorFinalCents
    };

    document.getElementById(
      "valorOriginalCupom"
    ).textContent =
      formatarValorCursoInfo(
        valorOriginalCents
      );

    document.getElementById(
      "valorDescontoCupom"
    ).textContent =
      `${formatarValorCursoInfo(
        valorDescontoCents
      )} (${percentual}%)`;

    document.getElementById(
      "valorFinalCupom"
    ).textContent =
      formatarValorCursoInfo(
        valorFinalCents
      );

    if (resumo) {
      resumo.style.display =
        "block";
    }

    msg.textContent =
      "Cupom aplicado com sucesso!";

    msg.style.color =
      "#2f5e46";

    salvarEstadoCompraCursoInfo();

  } catch (err) {
    console.error(err);

    cupomAplicadoCursoInfo = null;

    if (resumo) {
      resumo.style.display =
        "none";
    }

    let mensagem =
      String(
        err?.message ||
        "Não foi possível validar o cupom."
      );

    try {
      const json =
        JSON.parse(mensagem);

      if (json?.detail) {
        mensagem =
          json.detail;
      }

    } catch {
      // Mantém a mensagem original.
    }

    msg.textContent =
      mensagem;

    msg.style.color =
      "#8a1f1f";
  }
}

async function apiPutAuth(path, body) {

  const token = getToken();

  if (!token) {
    throw new Error("Você não está logado.");
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`
    },
    body: JSON.stringify(body || {})
  });

  if (!res.ok) {
    const txt = await res.text();
    throw new Error(txt || `Erro HTTP ${res.status}`);
  }

  return res.json();
}

async function apiDeleteAuth(path) {

  const token = getToken();

  if (!token) {
    throw new Error("Você não está logado.");
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method: "DELETE",
    headers: {
      "Authorization": `Bearer ${token}`
    }
  });

  if (!res.ok) {
    const txt = await res.text();
    throw new Error(txt || `Erro HTTP ${res.status}`);
  }

  return true;
}

function setHTML(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = html;
}

function escapeHtml(str) {
  return String(str ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

/**
 * Render: lista simples de links
 * items: [{title, href, subtitle?}]
 */
function renderList(containerId, items) {
  const html = items.map(it => `
    <div class="disciplina" style="padding:6px 14px;">
      <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap">
        <div>
          <div style="font-weight:bold">${escapeHtml(it.title)}</div>
          ${it.subtitle ? `<div style="opacity:.85">${escapeHtml(it.subtitle)}</div>` : ""}
        </div>
        <a class="btn" href="${it.href}">Abrir</a>
      </div>
    </div>
  `).join("");
  setHTML(containerId, html || `<p>Nenhum item encontrado.</p>`);
}

function showError(containerId, err) {
  setHTML(containerId, `
    <div class="card" style="border-top-color:#6B4F3F">
      <h2>Erro</h2>
      <pre style="white-space:pre-wrap">${escapeHtml(err.message)}</pre>
    </div>
  `);
}

// ===============================
// ✅ NOVO: “Quem sou eu?” + redirect inteligente (admin vs aluno)
// ===============================

async function getMeSafe() {
  const token = getToken();
  if (!token) return null;

  // cache simples (30s) para não bater no /me a cada clique
  try {
    const cached = localStorage.getItem("me_cache");
    if (cached) {
      const obj = JSON.parse(cached);
      if (obj && obj.ts && (Date.now() - obj.ts) < 30_000 && obj.me) {
        return obj.me;
      }
    }
  } catch { /* ignore */ }

  try {
    const res = await fetch(`${API_BASE}/me`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    if (!res.ok) return null;

    const me = await res.json();
    try {
      localStorage.setItem("me_cache", JSON.stringify({ ts: Date.now(), me }));
    } catch { /* ignore */ }
    return me;
  } catch {
    return null;
  }
}

async function exibirNomeUsuarioLogado() {
  const token =
    getToken();

  if (!token) {
    return;
  }

  try {
    const me =
      await getMeSafe();

    if (!me || !me.nome) {
      return;
    }

    const partesNome =
      String(me.nome)
        .trim()
        .split(/\s+/)
        .filter(Boolean);

    if (partesNome.length === 0) {
      return;
    }

    const primeiroNome =
      partesNome[0];

    const ultimoNome =
      partesNome.length > 1
        ? partesNome[
            partesNome.length - 1
          ]
        : "";

    const nomeTooltip =
      ultimoNome
        ? `${primeiroNome} ${ultimoNome}`
        : primeiroNome;

    let identificacao =
      document.getElementById(
        "nomeUsuarioLogadoGlobal"
      );

    if (!identificacao) {
      identificacao =
        document.createElement("div");

      identificacao.id =
        "nomeUsuarioLogadoGlobal";

      identificacao.style.position =
        "fixed";

      identificacao.style.top =
        "9px";

      identificacao.style.right =
        "47px";

      identificacao.style.zIndex =
        "9999";

      identificacao.style.fontSize =
        "0.68rem";

      identificacao.style.fontWeight =
        "600";

      identificacao.style.letterSpacing =
        "0.4px";

      identificacao.style.color =
        "#4b5563";

      identificacao.style.opacity =
        "0.78";

      identificacao.style.cursor =
        "default";

      identificacao.style.userSelect =
        "none";

      identificacao.style.whiteSpace =
        "nowrap";

      document.body.appendChild(
        identificacao
      );
    }

    identificacao.textContent =
      primeiroNome.toUpperCase();

    const tooltip =
      document.createElement("div");

    tooltip.textContent =
      nomeTooltip.toUpperCase();

    tooltip.style.position =
      "absolute";

    tooltip.style.right =
      "calc(100% + 8px)";

    tooltip.style.top =
      "50%";

    tooltip.style.transform =
      "translateY(-50%)";

    tooltip.style.padding =
      "0";

    tooltip.style.background =
      "transparent";

    tooltip.style.color =
      "#4b5563";

    tooltip.style.fontSize =
      "0.68rem";

    tooltip.style.fontWeight =
      "500";

    tooltip.style.borderRadius =
      "4px";

    tooltip.style.whiteSpace =
      "nowrap";

    tooltip.style.opacity =
      "0";

    tooltip.style.visibility =
      "hidden";

    tooltip.style.pointerEvents =
      "none";

    tooltip.style.transition =
      "opacity 0.15s";

    identificacao.appendChild(
      tooltip
    );

    identificacao.addEventListener(
      "mouseenter",
      () => {
        tooltip.style.opacity = "1";
        tooltip.style.visibility = "visible";
      }
    );

    identificacao.addEventListener(
      "mouseleave",
      () => {
        tooltip.style.opacity = "0";
        tooltip.style.visibility = "hidden";
      }
    );

  } catch (err) {
    console.warn(
      "Não foi possível exibir o nome do usuário logado:",
      err
    );
  }
}

// Função global usada no botão 👤 da página inicial.
window.entrarEEstudar = async function entrarEEstudar() {

  // Limpa estados antigos relacionados à compra.
  localStorage.removeItem(
    "ultimo_curso_id_compra"
  );

  localStorage.removeItem(
    "ultimo_checkout_curso_id"
  );


  const token =
    getToken();


  // Não está logado:
  // envia para o login.
  if (!token) {

    localStorage.setItem(
      "pos_login_redirect",
      "cursos.html"
    );

    window.location.href =
      "login.html";

    return;
  }


  // Está logado:
  // verifica todas as áreas disponíveis.
  try {

    const me =
      await apiGetAuth(
        "/me"
      );


    const quantidadeAreas =
      Number(!!me?.is_admin) +
      Number(!!me?.is_vendedor) +
      Number(!!me?.is_aluno);


    // Mais de uma área disponível:
    // mostra a página de escolha.
    if (quantidadeAreas > 1) {

      window.location.href =
        "minha-area.html";

      return;
    }


    // Apenas Admin.
    if (me?.is_admin) {

      window.location.href =
        "admin/index.html";

      return;
    }


    // Apenas Vendedor.
    if (me?.is_vendedor) {

      window.location.href =
        "minhas-vendas.html";

      return;
    }


    // Possui somente área de aluno.
    if (me?.is_aluno) {

      window.location.href =
        "cursos.html";

      return;
    }


    // Usuário autenticado,
    // mas sem nenhuma área disponível.
    window.location.href =
      "index.html";


  } catch (err) {

    console.warn(
      "Falha ao obter /me:",
      err
    );


    // Token inválido ou expirado.
    clearToken();


    localStorage.setItem(
      "pos_login_redirect",
      "cursos.html"
    );


    window.location.href =
      "login.html";
  }
};

// Tenta “pegar” automaticamente um botão comum na HOME, sem precisar mexer no HTML.
// Se não achar, não faz nada (mas você pode usar o onclick="entrarEEstudar()").

function bindBotaoEntrarEEstudarSeExistir() {
  const candidates = [
    "btnEntrarEstudar",
    "btnComecarEstudar",
    "btnEntrarComecar",
    "btnEntrar",
    "btnComecar",
    "btnLogin"
  ];

  for (const id of candidates) {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener("click", async (e) => {
        // evita comportamento padrão se for <a href="...">
        e.preventDefault?.();
        await window.entrarEEstudar();
      });
      return;
    }
  }
}

// ===============================
// 1) Cursos (somente os cursos liberados para o aluno logado)
// ===============================

const PRECO_CURSO_CENTS = 1990; // ajuste depois se quiser

async function tentarConfirmarPagamentoAoVoltar() {
  const paymentId = qs("payment_id");
  if (!paymentId) return;

  const cursoId = Number(localStorage.getItem("ultimo_checkout_curso_id") || "0");
  if (!cursoId) return;

  try {
    await apiPostAuth("/pagamentos/confirmar", {
      payment_id: Number(paymentId),
      curso_id: cursoId
    });

    localStorage.removeItem("ultimo_checkout_curso_id");
    window.history.replaceState({}, document.title, "cursos.html");
  } catch (e) {
    console.warn("Falha ao confirmar pagamento:", e);
  }
}

async function comprarCurso(cursoId) {
  try {
    // ✅ Guarda o curso_id que está sendo comprado
    // (será usado no pagamento_sucesso.html)
    localStorage.setItem("ultimo_curso_id_compra", String(cursoId));

    // 🔹 Ajuste solicitado: salvar também na outra chave
    localStorage.setItem("ultimo_checkout_curso_id", String(cursoId));

    const r = await apiPostAuth("/checkout/mercadopago", {
      curso_id: cursoId,
      valor_cents: PRECO_CURSO_CENTS
    });

    const url = r.sandbox_init_point || r.init_point;
    if (!url) throw new Error("Checkout não retornou init_point.");

    // Abre o checkout
    window.open(url, "_blank");
    alert("Checkout aberto em outra aba. Após pagar, volte para esta página.");
  } catch (err) {
    alert("Erro ao iniciar checkout: " + err.message);
    console.error(err);
  }
}

async function calcularProgressoCurso(cursoId) {
  try {
    const disciplinas = await apiGet(`/cursos/${cursoId}/disciplinas`);

    let totalAulas = 0;
    let aulasConcluidas = 0;

    for (const disciplina of disciplinas) {
      const prog = await calcularProgressoDisciplina(disciplina.id);
      totalAulas += prog.totalAulas;
      aulasConcluidas += prog.aulasConcluidas;
    }

    const percentual = totalAulas > 0
      ? Math.round((aulasConcluidas / totalAulas) * 100)
      : 0;

    return { percentual, aulasConcluidas, totalAulas };

  } catch {
    return { percentual: 0, aulasConcluidas: 0, totalAulas: 0 };
  }
}

function renderProgressoLinha(percentual, aulasConcluidas) {
  return `
    <div style="
      margin-top:14px;
      display:flex;
      align-items:center;
      gap:6px;
    ">
      <div style="
        font-size:0.95rem;
        color:${aulasConcluidas > 0 ? '#16a34a' : '#c2cad9'};
        font-weight:bold;
        min-width:34px;
      ">
        ${percentual}%
      </div>

      <div style="
        flex:1;
        height:6px;
        background:#d1d5db;
        border-radius:999px;
        overflow:hidden;
      ">
        <div style="
          width:${percentual}%;
          height:100%;
          background:${aulasConcluidas > 0 ? '#16a34a' : '#c2cad9'};
        "></div>
      </div>
    </div>
  `;
}

// 1) Cursos (ÁREA LOGADA: mostra SOMENTE cursos adquiridos)
async function pageCursos() {
  const el = document.getElementById("lista");
  const listaExpirados = document.getElementById("lista_expirados");
  const cardExpirados = document.getElementById("card_cursos_expirados");
  const linhaFinalExpirados = document.getElementById("linha_final_expirados");

  if (!el) throw new Error("Não achei o elemento #lista no cursos.html");

  try {
    const token = getToken();

    if (!token) {
      localStorage.setItem("pos_login_redirect", "cursos.html");
      window.location.href = "login.html";
      return;
    }

    if (typeof tentarConfirmarPagamentoAoVoltar === "function") {
      await tentarConfirmarPagamentoAoVoltar();
    }

    const acessos = await apiGetAuth("/me/cursos");
    const historico = await apiGetAuth("/me/cursos/historico");

    if (cardExpirados && listaExpirados) {
      const expirados = (historico || []).filter(c => c.ativo === false);

      if (expirados.length > 0) {
        cardExpirados.style.display = "block";

        listaExpirados.innerHTML = expirados.map(c => `
          <div class="disciplina" style="padding:15px 14px;">
            <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;">
              <div style="font-size:1.05rem;font-weight:bold;">
                ${escapeHtml(c.nome_curso)}
              </div>

              <a
                class="btn"
                href="javascript:void(0)"
                onclick="
                  localStorage.setItem('curso_expirado_${c.curso_id}_data_inicio', '${escapeHtml(c.data_inicio || '')}');
                  localStorage.setItem('curso_expirado_${c.curso_id}_data_fim', '${escapeHtml(c.data_fim || '')}');
                  window.location.href='curso-expirado.html?curso_id=${encodeURIComponent(c.curso_id)}&curso_nome=${encodeURIComponent(c.nome_curso)}&data_inicio=${encodeURIComponent(c.data_inicio || '')}&data_fim=${encodeURIComponent(c.data_fim || '')}';
                "
              >
                Abrir
              </a>
            </div>
          </div>
        `).join("");

        if (localStorage.getItem("abrir_cursos_expirados") === "1") {
          localStorage.removeItem("abrir_cursos_expirados");

          listaExpirados.style.display = "block";

          if (linhaFinalExpirados) {
            linhaFinalExpirados.style.display = "block";
          }

          setTimeout(() => {
            cardExpirados.scrollIntoView({
              behavior: "smooth",
              block: "start"
            });
          }, 100);
        }
      } else {
        cardExpirados.style.display = "none";
        listaExpirados.innerHTML = "";

        if (linhaFinalExpirados) {
          linhaFinalExpirados.style.display = "none";
        }
      }
    }

    const tituloCursos = document.getElementById("titulo_cursos");

    if (tituloCursos) {
      tituloCursos.style.display = acessos && acessos.length > 0 ? "block" : "none";
    }

    el.innerHTML = "";

    if (!acessos || acessos.length === 0) {
      el.innerHTML = `
        <div class="disciplina">
          <div><strong>Você não possui curso ativo no momento.</strong></div>
        </div>
      `;
      return;
    }

    for (const a of acessos) {
      const div = document.createElement("div");
      div.className = "disciplina";
      div.style.padding = "15px 14px";

      div.innerHTML = `
        <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;">
          <div style="flex:1; min-width:0;">
            <div style="font-size:1.05rem;font-weight:bold;">
              ${escapeHtml(a.nome_curso)}
            </div>
          </div>

          <div style="margin-left:12px;">
            <a
              class="btn"
              href="curso.html?curso_id=${a.curso_id}&curso_nome=${encodeURIComponent(a.nome_curso)}"
            >
              Abrir
            </a>
          </div>
        </div>
      `;

      el.appendChild(div);
    }

  } catch (err) {
    showError("conteudo", err);
  }
}

function alternarCursosExpirados() {
  const lista = document.getElementById("lista_expirados");
  const linhaFinal = document.getElementById("linha_final_expirados");

  if (!lista) return;

  const estavaFechada = lista.style.display === "none";

  lista.style.display = estavaFechada ? "block" : "none";

  if (linhaFinal) {
    linhaFinal.style.display = "block";
  }

  if (estavaFechada) {
    setTimeout(() => {
      lista.scrollIntoView({
        behavior: "smooth",
        block: "start"
      });
    }, 100);
  }
}

function alternarLista(id) {
  const el = document.getElementById(id);
  if (!el) return;

  el.style.display = el.style.display === "none" ? "block" : "none";
}

async function calcularProgressoDisciplina(disciplinaId) {
  try {
    let assuntos;

    try {
      assuntos = await apiGetAuth(`/disciplinas-proprias/${disciplinaId}/assuntos-proprios`);
    } catch {
      assuntos = await apiGet(`/disciplinas/${disciplinaId}/assuntos`);
    }

    if (!assuntos || assuntos.length === 0) {
      return { percentual: 0, aulasConcluidas: 0, totalAulas: 0 };
    }

    let totalBateriasDisciplina = 0;
    let bateriasFeitasDisciplina = 0;

    for (const assunto of assuntos) {
      const progAssunto = await calcularProgressoAssunto(assunto.id);

      totalBateriasDisciplina += progAssunto.totalBaterias || progAssunto.totalAulas || 0;
      bateriasFeitasDisciplina += progAssunto.bateriasFeitas || progAssunto.aulasConcluidas || 0;
    }

    const percentual = totalBateriasDisciplina > 0
      ? Math.round((bateriasFeitasDisciplina / totalBateriasDisciplina) * 100)
      : 0;

    return {
      percentual,
      aulasConcluidas: bateriasFeitasDisciplina,
      totalAulas: totalBateriasDisciplina,
      bateriasFeitas: bateriasFeitasDisciplina,
      totalBaterias: totalBateriasDisciplina
    };

  } catch (err) {
    console.error("Erro ao calcular progresso da disciplina:", err);
    return { percentual: 0, aulasConcluidas: 0, totalAulas: 0 };
  }
}

// 2) Disciplinas do Curso
async function pageDisciplinas() {
  const cursoId = qs("curso_id");
  const cursoNome = qs("curso_nome") || "";
  const titulo = document.getElementById("titulo_pagina");

  if (titulo) {
    titulo.innerText = cursoNome
      ? `📘 ${cursoNome}`
      : "📚 Disciplinas";
  }

  if (!cursoId) {
    showError("conteudo", new Error("Faltou curso_id na URL. Volte e clique no curso novamente."));
    return;
  }

  try {
    const disciplinas = await apiGetAuth(`/cursos/${cursoId}/disciplinas-proprias`);
    const lista = document.getElementById("lista");

    lista.innerHTML = "";

    for (const d of disciplinas) {
      const prog = await calcularProgressoDisciplina(d.id);

      const div = document.createElement("div");
      div.className = "disciplina";
      div.style.padding = "5px 12px";

      div.style.opacity =
        d.bloqueada ? "0.55" : "1";

      div.innerHTML = `
        <div style="
          display:flex;
          justify-content:space-between;
          align-items:center;
          gap:12px;
          flex-wrap:wrap;
        ">

          <div style="flex:1; min-width:240px;">
            <div style="font-weight:bold;">
              ${escapeHtml(d.nome)}
            </div>
          </div>

          <div>
            ${
              d.bloqueada
                ? `
                  <span
                    class="btn"
                    style="
                      opacity:.75;
                      cursor:default;
                    "
                    title="Disponível no acesso completo"
                  >
                    Abrir
                  </span>
                `
                : `
                  <a
                    class="btn"
                    href="javascript:void(0)"
                    onclick="
                      localStorage.setItem(
                        'voltar_para_curso',
                        'curso.html?curso_id=${encodeURIComponent(cursoId)}&curso_nome=${encodeURIComponent(cursoNome)}'
                      );

                      localStorage.setItem(
                        'voltar_para_disciplinas',
                        'disciplinas.html?curso_id=${encodeURIComponent(cursoId)}&curso_nome=${encodeURIComponent(cursoNome)}'
                      );

                      window.location.href='assuntos.html?curso_id=${encodeURIComponent(cursoId)}&disciplina_id=${d.id}&disciplina_nome=${encodeURIComponent(d.nome)}&curso_nome=${encodeURIComponent(cursoNome)}';
                    "
                  >
                    Abrir
                  </a>
                `
            }
          </div>

        </div>

        <div
          title="Quanto já estudei desta disciplina"
          style="
            margin-top:14px;
            display:flex;
            align-items:center;
            gap:12px;
            cursor:default;
          "
        >

          <div style="
            flex:1;
            height:6px;
            background:#d1d5db;
            border-radius:999px;
            overflow:hidden;
          ">
            <div style="
              width:${prog.percentual}%;
              height:100%;
              background:${prog.percentual > 0 ? '#9ca3af' : '#d1d5db'};
            "></div>
          </div>

          <div style="
            font-size:0.9rem;
            color:#4b5563;
            font-weight:bold;
            min-width:38px;
            text-align:right;
          ">
            ${prog.percentual}%
          </div>

        </div>
      `;

      lista.appendChild(div);
    }
  } catch (err) {
    showError("conteudo", err);
  }
}

async function calcularProgressoAssunto(assuntoId) {
  try {
    console.log("Calculando progresso do assunto:", assuntoId);

    let pastaTeoria = null;

    try {
      const pastas = await apiGet(`/assuntos/${assuntoId}/pastas`);
      pastaTeoria = pastas.find(p => p.tipo === "TEORIA");
    } catch {
      pastaTeoria = null;
    }

    if (!pastaTeoria || pastaTeoria.id === 10) {
      try {
        const pastaPropria = await apiGetAuth(`/assuntos-proprios/${assuntoId}/pasta-teoria`);
        if (pastaPropria && pastaPropria.id) {
          pastaTeoria = pastaPropria;
        }
      } catch (e) {
        console.warn("Não encontrou pasta própria do assunto:", e);
      }
    }

    if (!pastaTeoria || !pastaTeoria.id) {
      return { percentual: 0, aulasConcluidas: 0, totalAulas: 0 };
    }

    console.log("Pasta TEORIA usada:", pastaTeoria);

    const aulas = await apiGet(`/pastas/${pastaTeoria.id}/aulas`);
    console.log("Aulas:", aulas);

    let totalBaterias = 0;
    let bateriasFeitas = 0;

    for (const aula of aulas || []) {
      const baterias = await apiGetAuth(`/aulas/${aula.id}/baterias-com-status`);
      console.log("Baterias da aula", aula.id, baterias);

      const bateriasConcluidas = (baterias || []).filter(b =>
        b.status_bateria === "CONCLUIDA" || b.status === "CONCLUIDA"
      );

      totalBaterias += bateriasConcluidas.length;

      bateriasFeitas += bateriasConcluidas.filter(b =>
        b.status_aluno === "FEITA"
      ).length;
    }

    const percentual = totalBaterias > 0
      ? Math.round((bateriasFeitas / totalBaterias) * 100)
      : 0;

    console.log("Resultado progresso assunto:", {
      totalBaterias,
      bateriasFeitas,
      percentual
    });

    return {
      percentual,
      aulasConcluidas: bateriasFeitas,
      totalAulas: totalBaterias,
      bateriasFeitas,
      totalBaterias
    };

  } catch (err) {
    console.error("Erro ao calcular progresso do assunto:", err);
    return { percentual: 0, aulasConcluidas: 0, totalAulas: 0 };
  }
}

async function abrirAssuntoDireto(assuntoId, assuntoNomeEncoded, disciplinaNomeEncoded) {
  const pastaTeoria = await apiGetAuth(`/assuntos-proprios/${assuntoId}/pasta-teoria`);

  if (!pastaTeoria || !pastaTeoria.id) {
    alert("Não encontrei a pasta de Teoria deste assunto.");
    return;
  }

  const disciplinaId = qs("disciplina_id");
  const disciplinaNomeAtual = qs("disciplina_nome") || "";
  const cursoNome = qs("curso_nome") || "";

  window.location.href =
    `teoria.html?pasta_id=${pastaTeoria.id}` +
    `&assunto_id=${encodeURIComponent(assuntoId)}` +
    `&disciplina_id=${encodeURIComponent(disciplinaId || "")}` +
    `&assunto_nome=${assuntoNomeEncoded}` +
    `&disciplina_nome=${disciplinaNomeEncoded}` +
    `&curso_nome=${encodeURIComponent(cursoNome)}`;
  }

// 3) Assuntos da Disciplina
async function pageAssuntos() {
  const disciplinaId = qs("disciplina_id");
  const disciplinaNome = qs("disciplina_nome") || "";
  const cursoNome = qs("curso_nome") || "";

  const tituloCurso = document.getElementById("titulo_curso");
  const cardDisciplina = document.getElementById("card_disciplina_titulo");

  if (tituloCurso) {
    tituloCurso.innerText = cursoNome
      ? `📘 ${cursoNome}`
      : "📘 Curso";
  }

  if (cardDisciplina) {
    cardDisciplina.innerText = disciplinaNome
      ? `Disciplina: ${disciplinaNome}`
      : "Disciplina";
  }

  if (!disciplinaId) {
    showError("conteudo", new Error("Faltou disciplina_id na URL. Volte e clique na disciplina novamente."));
    return;
  }

  try {
    let assuntos;

    try {
      assuntos = await apiGetAuth(`/disciplinas-proprias/${disciplinaId}/assuntos-proprios`);
    } catch (e1) {
      assuntos = await apiGet(`/disciplinas/${disciplinaId}/assunto`);
    }

    const lista = document.getElementById("lista");
    lista.innerHTML = "";

    for (const a of assuntos) {
      const prog = await calcularProgressoAssunto(a.id);

      const div = document.createElement("div");
      div.className = "disciplina";
      div.style.padding = "6px 14px";

      div.innerHTML = `
        <div style="
          display:flex;
          justify-content:space-between;
          align-items:center;
          gap:12px;
          flex-wrap:wrap;
        ">
          <div style="flex:1; min-width:240px;">
            <div style="font-weight:bold;">
              ${escapeHtml(a.nome)}
            </div>
          </div>

          <a class="btn"
            href="javascript:void(0)"
            onclick="abrirAssuntoDireto(${a.id}, '${encodeURIComponent(a.nome)}', '${encodeURIComponent(disciplinaNome)}')">
            Abrir
          </a>
        </div>

        <div
          title=" Quanto já estudei deste assunto"
          style="
            margin-top:6px;
            display:flex;
            align-items:center;
            gap:8px;
            cursor:default;
          "
        >
          <div style="
            flex:1;
            height:5px;
            background:#d1d5db;
            border-radius:999px;
            overflow:hidden;
          ">
            <div style="
              width:${prog.percentual}%;
              height:100%;
              background:${prog.percentual > 0 ? '#9ca3af' : '#d1d5db'};
            "></div>
          </div>

          <div style="
            font-size:0.9rem;
            color:#4b5563;
            font-weight:bold;
            min-width:38px;
            text-align:right;
          ">
            ${prog.percentual}%
          </div>
        </div>
      `;

      lista.appendChild(div);
    }
  } catch (err) {
    showError("conteudo", err);
  }
}

// 4) Pastas do Assunto (Teoria e Questões / Interatividade)
async function pagePastas() {
  const assuntoId = qs("assunto_id");
  const assuntoNome = qs("assunto_nome") || "";
  const disciplinaNome = qs("disciplina_nome") || "";

  const tituloDisciplina = document.getElementById("titulo_disciplina");
  const tituloAssunto = document.getElementById("titulo_assunto");

  if (tituloDisciplina) {
    tituloDisciplina.innerText = disciplinaNome
      ? `📘 ${disciplinaNome}`
      : "📂 Pastas";
  }

  if (tituloAssunto) {
    tituloAssunto.innerText = assuntoNome;
  }

  if (!assuntoId) {
    showError("conteudo", new Error("Faltou assunto_id na URL. Volte e clique no assunto novamente."));
    return;
  }

  try {
    const pastas = await apiGet(`/assuntos/${assuntoId}/pastas`);

    const teoria = pastas.find(p => p.tipo === "TEORIA");
    const inter = pastas.find(p => p.tipo === "INTERATIVIDADE");

    let html = `<div class="list">`;

    if (teoria) {
      html += `
        <div class="disciplina" style="padding-top:12px;padding-bottom:26px;">  
          <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;">

            <div style="font-weight:bold">
              📘 ${escapeHtml(teoria.nome || "Teoria e Questões")}
            </div>

            <a class="btn"
              href="teoria.html?pasta_id=${teoria.id}&assunto_id=${assuntoId}&disciplina_nome=${encodeURIComponent(disciplinaNome)}&assunto_nome=${encodeURIComponent(assuntoNome)}">
              Abrir
            </a>

          </div>
        </div>
      `;
    } else {
      html += `<p>Não achei a pasta TEORIA.</p>`;
    }

    html += `</div>`;
    setHTML("lista", html);
  } catch (err) {
    showError("conteudo", err);
  }
}

// 5) Interatividade (menu)
function pageInteratividade() {
  const pastaId = qs("pasta_id");
  if (!pastaId) {
    showError("conteudo", new Error("Faltou pasta_id na URL."));
    return;
  }

  setHTML("lista", `
    <div class="list">
      <div class="disciplina">
        <div style="font-weight:bold">🧠 QuizIA (5)</div>
        <div style="opacity:.85">GET /pastas/${pastaId}/quiz-ia</div>
        <a class="btn" href="quiz.html?pasta_id=${pastaId}">Abrir</a>
      </div>

      <div class="disciplina">
        <div style="font-weight:bold">🃏 CartõesIA</div>
        <div style="opacity:.85">GET /pastas/${pastaId}/cartoes-ia</div>
        <a class="btn" href="cartoes.html?pasta_id=${pastaId}">Abrir</a>
      </div>

      <div class="disciplina">
        <div style="font-weight:bold">📝 QuestõesIA (10)</div>
        <div style="opacity:.85">GET /pastas/${pastaId}/questoes-ia</div>
        <a class="btn" href="questoesia.html?pasta_id=${pastaId}">Abrir</a>
      </div>
    </div>
  `);
}

// 6) QuizIA (render)
async function pageQuiz() {
  const pastaId = qs("pasta_id");
  if (!pastaId) {
    showError("conteudo", new Error("Faltou pasta_id na URL."));
    return;
  }
  try {
    const quizzes = await apiGet(`/pastas/${pastaId}/quiz-ia`);
    if (!quizzes.length) {
      setHTML("lista", "<p>Nenhum QuizIA encontrado.</p>");
      return;
    }

    const q = quizzes[0];
    let html = `<div class="card"><h2>${escapeHtml(q.titulo)}</h2></div>`;

    html += q.itens.map((it, idx) => {
      const alts = it.alternativas || {};
      return `
        <div class="card">
          <h2>${idx + 1}. ${escapeHtml(it.pergunta)}</h2>
          <div class="list">
            ${["A","B","C","D","E"].map(L => `
              <div class="assunto">
                <b>${L})</b> ${escapeHtml(alts[L] || "")}
              </div>
            `).join("")}
          </div>
          <p style="margin-top:10px"><b>Resposta (para o quiz):</b> ${escapeHtml(it.resposta_correta)}</p>
          <p><b>Comentário:</b> ${escapeHtml(it.comentario_curto)}</p>
        </div>
      `;
    }).join("");

    setHTML("lista", html);
  } catch (err) {
    showError("conteudo", err);
  }
}

// 7) CartõesIA (render com “virar” simples)
async function pageCartoes() {
  const pastaId = qs("pasta_id");
  if (!pastaId) {
    showError("conteudo", new Error("Faltou pasta_id na URL."));
    return;
  }
  try {
    const cartoes = await apiGet(`/pastas/${pastaId}/cartoes-ia`);
    if (!cartoes.length) {
      setHTML("lista", "<p>Nenhum CartãoIA encontrado.</p>");
      return;
    }

    const html = cartoes.map((c) => `
      <div class="card">
        <h2>Cartão ${c.ordem}</h2>
        <div class="assunto">
          <p><b>Frente:</b> ${escapeHtml(c.frente)}</p>
          <button class="btn" onclick="document.getElementById('verso_${c.id}').style.display='block'">Ver verso</button>
          <div id="verso_${c.id}" style="display:none;margin-top:12px;padding:12px;border:1px dashed #ddd;border-radius:6px">
            <b>Verso:</b> ${escapeHtml(c.verso)}
          </div>
        </div>
      </div>
    `).join("");

    setHTML("lista", html);
  } catch (err) {
    showError("conteudo", err);
  }
}

// 8) QuestõesIA (render)
async function pageQuestoesIA() {
  const pastaId = qs("pasta_id");
  if (!pastaId) {
    showError("conteudo", new Error("Faltou pasta_id na URL."));
    return;
  }
  try {
    const listas = await apiGet(`/pastas/${pastaId}/questoes-ia`);
    if (!listas.length) {
      setHTML("lista", "<p>Nenhuma QuestõesIA encontrada.</p>");
      return;
    }

    const pack = listas[0];
    let html = `<div class="card"><h2>${escapeHtml(pack.titulo)}</h2></div>`;

    html += pack.itens.map((it) => {
      const alts = it.alternativas || null;
      const com = it.comentario || null;

      return `
        <div class="card">
          <h2>${it.ordem}. ${escapeHtml(it.enunciado)}</h2>

          ${it.tipo === "MULTIPLA" && alts ? `
            <div class="list">
              ${["A","B","C","D","E"].map(L => `
                <div class="assunto">
                  <b>${L})</b> ${escapeHtml(alts[L] || "")}<br/>
                  <span style="opacity:.9"><b>Coment:</b> ${escapeHtml(com?.[L] || "")}</span>
                </div>
              `).join("")}
            </div>
          ` : ""}

          ${it.tipo === "CERTO_ERRADO" ? `
            <p><b>Comentário:</b> ${escapeHtml(com?.geral || "")}</p>
          ` : ""}

        </div>
      `;
    }).join("");

    setHTML("lista", html);
  } catch (err) {
    showError("conteudo", err);
  }
}

function corDesempenho(percentual) {
  if (percentual <= 59) return "#d32f2f";      // vermelho
  if (percentual <= 69) return "#1F4E79";      // azul normal
  return "#1F4E79";                            // azul destacado
}

function pesoDesempenho(percentual) {
  return percentual >= 70 ? "bold" : "normal";
}

async function calcularDesempenhoAssuntoInteratividade(assuntoId) {
  // Etapa 1: ainda não temos acertos reais salvos no banco.
  // Por enquanto, retorna null para mostrar "Ainda não iniciado".
  return null;
}

async function pageInteratividadeAssuntos() {
  const disciplinaId = qs("disciplina_id");
  const disciplinaNome = qs("disciplina_nome") || "";
  const cursoNome = qs("curso_nome") || "";

  const tituloCurso = document.getElementById("titulo_curso");
  const tituloDisciplina = document.getElementById("titulo_disciplina");
  const lista = document.getElementById("lista");

  if (tituloCurso) tituloCurso.innerText = cursoNome ? `📘 ${cursoNome}` : "";
  if (tituloDisciplina) tituloDisciplina.innerText = disciplinaNome;

  if (!disciplinaId || !lista) return;

  try {
    let assuntos;

    try {
      assuntos = await apiGet(`/disciplinas/${disciplinaId}/assuntos`);
    } catch {
      assuntos = await apiGet(`/disciplinas/${disciplinaId}/assunto`);
    }

    lista.innerHTML = "";

    for (const a of assuntos) {
      const desempenho = await calcularDesempenhoAssuntoInteratividade(a.id);

      const pastas = await apiGet(`/assuntos/${a.id}/pastas`);
      const pastaInteratividade = pastas.find(p => p.tipo === "INTERATIVIDADE");

      const desempenhoHtml = desempenho === null

        ? `<span style="opacity:.65;">Ainda não iniciado</span>`
        : `<span style="
              color:${corDesempenho(desempenho)};
              font-weight:${pesoDesempenho(desempenho)};
            ">${desempenho}%</span>`;

      const div = document.createElement("div");
      div.className = "disciplina";
      div.style.padding = "10px 14px";

      div.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;">
          <div>
            <div style="font-weight:bold;">${escapeHtml(a.nome)}</div>
            <div style="margin-top:4px;">
              Desempenho: ${desempenhoHtml}
            </div>
          </div>

          <a class="btn"
            href="interatividade.html?pasta_id=${pastaInteratividade?.id || ""}&assunto_id=${a.id}&assunto_nome=${encodeURIComponent(a.nome)}&disciplina_nome=${encodeURIComponent(disciplinaNome)}">
            Abrir
          </a>
        </div>
      `;

      lista.appendChild(div);
    }

  } catch (err) {
    lista.innerHTML = "<p>Erro ao carregar assuntos.</p>";
    console.error(err);
  }
}

function pageCurso() {
  const cursoId = qs("curso_id");
  const cursoNome = qs("curso_nome") || "";

  const tituloCurso = document.getElementById("titulo_curso");
  const acoes = document.getElementById("acoes_curso");

  if (tituloCurso) {
    tituloCurso.innerText = cursoNome || "Curso";
  }

  if (!cursoId || !acoes) {
    if (acoes) acoes.innerHTML = "<p>Erro: curso não identificado.</p>";
    return;
  }

  acoes.innerHTML = `
    <div class="disciplina" style="padding:10px 14px; margin-bottom:18px;">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;">
        <div style="font-weight:bold;">📚 Disciplinas</div>
        <a class="btn" href="disciplinas.html?curso_id=${encodeURIComponent(cursoId)}&curso_nome=${encodeURIComponent(cursoNome)}">Abrir</a>
      </div>
    </div>

    <div class="disciplina" style="padding:10px 14px; margin-bottom:18px;">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;">
        <div style="font-weight:bold;">📝 Questões</div>
        <a class="btn" href="questoes-disciplinas.html?curso_id=${encodeURIComponent(cursoId)}&curso_nome=${encodeURIComponent(cursoNome)}">Abrir</a>
      </div>
    </div>

        <div class="disciplina" style="padding:10px 14px; margin-bottom:18px;">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;">
            <div style="font-weight:bold;">🔁 Assuntos importante para rever</div>

            <a
              class="btn"
              href="revisoes-programadas.html?curso_id=${encodeURIComponent(cursoId)}&curso_nome=${encodeURIComponent(cursoNome)}"
            >
              Abrir
            </a>
          </div>
        </div>

        <div class="disciplina" style="padding:10px 14px; margin-bottom:18px;">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;">
            <div style="font-weight:bold;">🚨 Questões diferenciadas (que errei, marquei como difícil, que marquei para rever)</div>

            <a
              class="btn"
              href="questoes-criticas.html?curso_id=${encodeURIComponent(cursoId)}&curso_nome=${encodeURIComponent(cursoNome)}"
            >
              Abrir
            </a>
          </div>
        </div>

    <div class="disciplina" style="padding:10px 14px; margin-bottom:18px;">
      <div style="display:flex;flex-direction:column;gap:2px;">

        <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;">
          <div style="font-weight:bold;">📝 Anotações que fiz nas questões </div>
          <a class="btn" href="minhas-anotacoes.html?curso_id=${encodeURIComponent(cursoId)}&curso_nome=${encodeURIComponent(cursoNome)}">Abrir</a>
        </div>

        <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;">
          <div style="font-weight:bold;">💬 Mensagens que enviei ao prof</div>
          <a class="btn" href="mensagens-prof.html?curso_id=${encodeURIComponent(cursoId)}&curso_nome=${encodeURIComponent(cursoNome)}">Abrir</a>
        </div>

      </div>
    </div>

    <div class="disciplina" style="padding:10px 14px; margin-bottom:24px;">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;">
        <div style="font-weight:bold;">📊 Acessar meu desempenho </div>
        <a class="btn" href="dashboard.html?curso_id=${encodeURIComponent(cursoId)}&curso_nome=${encodeURIComponent(cursoNome)}">Abrir</a>
      </div>
    </div>
  `;
}

let dadosCursoInfo = null;
let disciplinaAbertaCursoInfo = null;
let cupomAplicadoCursoInfo = null;

function salvarEstadoCompraCursoInfo() {
  const selecionado =
    document.querySelector(
      "input[name='tipo_acesso']:checked"
    );

  if (
    !selecionado ||
    selecionado.value === "demo"
  ) {
    localStorage.removeItem(
      "estado_compra_curso"
    );

    return;
  }

  const estado = {
    curso_id:
      dadosCursoInfo?.id || null,

    tempo_acesso_id:
      Number(
        selecionado.dataset.tempoId
      ),

    codigo_cupom:
      cupomAplicadoCursoInfo
        ? cupomAplicadoCursoInfo.codigo_cupom
        : null
  };

  localStorage.setItem(
    "estado_compra_curso",
    JSON.stringify(estado)
  );
}


function limparEstadoCompraCursoInfo() {
  localStorage.removeItem(
    "estado_compra_curso"
  );
}

function formatarValorCursoInfo(cents) {
  return (Number(cents || 0) / 100).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL"
  });
}

function alternarEstruturaCursoInfo() {
  const box = document.getElementById("estrutura_curso");
  if (box) box.style.display = box.style.display === "none" ? "block" : "none";
}

function alternarInformacoesCursoInfo() {
  const box = document.getElementById("informacoes_curso");
  if (box) box.style.display = box.style.display === "none" ? "block" : "none";
}

function alternarDisciplinaCursoInfo(id) {
  disciplinaAbertaCursoInfo = disciplinaAbertaCursoInfo === id ? null : id;
  renderizarEstruturaCursoInfo();
}

function controlarAvisoDemoCursoInfo() {
  const selecionado =
    document.querySelector(
      "input[name='tipo_acesso']:checked"
    );

  const aviso =
    document.getElementById(
      "aviso_demo"
    );

  const btn =
    document.getElementById(
      "btnAdquirirAgora"
    );

  const boxCupom =
    document.getElementById(
      "box_cupom_desconto"
    );

  const ehDemo =
    selecionado &&
    selecionado.value === "demo";


  if (aviso) {
    aviso.style.display =
      ehDemo
        ? "block"
        : "none";
  }


  if (btn) {
    btn.textContent =
      ehDemo
        ? "Acessar agora"
        : "Adquirir agora";
  }


  if (boxCupom) {
    boxCupom.style.display =
      selecionado && !ehDemo
        ? "block"
        : "none";
  }

  limparCupomCursoInfo();

  if (ehDemo) {
    limparEstadoCompraCursoInfo();
  }

}

function limparCupomCursoInfo() {
  cupomAplicadoCursoInfo = null;

  const campo =
    document.getElementById(
      "codigo_cupom_desconto"
    );

  const msg =
    document.getElementById(
      "msgCupomDesconto"
    );

  const resumo =
    document.getElementById(
      "resumoCupomDesconto"
    );

  if (campo) {
    campo.value = "";
  }

  if (msg) {
    msg.textContent = "";
  }

  if (resumo) {
    resumo.style.display = "none";
  }
}

function renderizarEstruturaCursoInfo() {
  const estrutura = document.getElementById("estrutura_curso");
  if (!estrutura || !dadosCursoInfo) return;

  const disciplinas = dadosCursoInfo.disciplinas || [];

  if (disciplinas.length === 0) {
    estrutura.innerHTML = "<p>Nenhuma disciplina cadastrada para este curso.</p>";
    return;
  }

  estrutura.innerHTML = disciplinas.map(d => `
    <div class="disciplina" style="padding:10px 14px;">
      <div
        onclick="alternarDisciplinaCursoInfo(${d.id})"
        style="font-weight:bold;cursor:pointer;"
      >
        ${escapeHtml(d.nome)}
      </div>

      ${
        disciplinaAbertaCursoInfo === d.id
          ? `
            <div class="list" style="margin-top:10px;">
              ${
                (d.assuntos || []).length === 0
                  ? `<p style="opacity:.75;">Nenhum assunto cadastrado.</p>`
                  : d.assuntos.map(a => `
                      <div class="assunto" style="padding:8px 12px;">
                        ${escapeHtml(a.nome)}
                      </div>
                    `).join("")
              }
            </div>
          `
          : ""
      }
    </div>
  `).join("");
}

function renderizarOpcoesAcessoCursoInfo() {
  const box = document.getElementById("opcoes_acesso");
  if (!box || !dadosCursoInfo) return;

  const tempos = dadosCursoInfo.tempos_acesso || [];

  const pagas = tempos.map(t => `
    <label class="assunto" style="display:block;cursor:pointer;">
      <input
        type="radio"
        name="tipo_acesso"
        value="tempo_${t.id}"
        data-tempo-id="${t.id}"
        data-valor-cents="${t.valor_cents}"
        onchange="controlarAvisoDemoCursoInfo()"
        style="margin-right:10px;"
      />
      ${t.meses} meses (${formatarValorCursoInfo(t.valor_cents)})
    </label>
  `).join("");

  box.innerHTML = `
    <label class="assunto" style="display:block;cursor:pointer;">
      <input
        type="radio"
        name="tipo_acesso"
        value="demo"
        onchange="controlarAvisoDemoCursoInfo()"
        style="margin-right:10px;"
      />
      Acesso gratuito (teste)
    </label>

    ${pagas}
  `;
}

async function adquirirAgoraCursoInfo() {
  const msg = document.getElementById("msgCursoInfo");
  const selecionado = document.querySelector("input[name='tipo_acesso']:checked");

  if (!selecionado) {
    alert("Selecione uma opção de acesso.");
    return;
  }

  const token = getToken();

  if (!token) {
    salvarEstadoCompraCursoInfo();

    localStorage.setItem(
      "continuar_compra_apos_login",
      "1"
    );

    localStorage.setItem(
      "pos_login_redirect",
      window.location.pathname
        .split("/")
        .pop() +
      window.location.search
    );

    window.location.href =
      "login.html";

    return;
  }

  try {
    if (selecionado.value === "demo") {
      msg.textContent = "Ativando acesso gratuito...";
      msg.style.color = "";

      await apiPostAuth(`/cursos/${dadosCursoInfo.id}/demonstracao`, {});

      window.location.href = "cursos.html";
      return;
    }

    const tempoId = selecionado.dataset.tempoId;

    msg.textContent = "...";
    msg.style.color = "";

    localStorage.setItem(
      "voltar_para_compra",
      window.location.href
    );

    const r = await apiPostAuth(
      "/checkout/mercadopago",
      {
        tempo_acesso_id:
          Number(tempoId),

        codigo_cupom:
          cupomAplicadoCursoInfo
            ? cupomAplicadoCursoInfo.codigo_cupom
            : null
      }
    );

    localStorage.setItem("ultimo_curso_id_compra", String(dadosCursoInfo.id));
    localStorage.setItem("ultimo_checkout_curso_id", String(dadosCursoInfo.id));

    const url =
      r.sandbox_init_point ||
      r.init_point;

    if (!url) {
      throw new Error(
        "Checkout não retornou link de pagamento."
      );
    }

    localStorage.removeItem(
      "continuar_compra_apos_login"
    );

    window.location.href =
      url;

  } catch (err) {
    console.error(err);

    document.body.style.visibility =
      "visible";

    let mensagemErro =
      String(
        err?.message ||
        "Não foi possível iniciar o acesso."
      );

    // restante do catch...

    try {
      const erroJson = JSON.parse(mensagemErro);

      if (erroJson?.detail) {
        mensagemErro = erroJson.detail;
      }
    } catch {
      // Se não for JSON, mantém a mensagem original.
    }

    msg.textContent =
      "Erro ao iniciar acesso.\n" +
      "Esta modalidade de acesso estará disponível para você novamente, " +
      "para este Curso, após 30 dias do último acesso nesta modalidade.";

    msg.style.whiteSpace = "pre-line";
    msg.style.color = "#8a1f1f";
  }
}

async function pageCursoInfo() {
  const cursoId =
    qs("curso_id");

  const cursoNome =
    qs("curso_nome") || "";

  const continuarCompraPendente =
    localStorage.getItem(
      "continuar_compra_apos_login"
    ) === "1" &&
    !!getToken();

  if (continuarCompraPendente) {
    document.body.style.visibility =
      "hidden";
  }

  const tituloCurso =
    document.getElementById(
      "titulo_curso"
    );

  const informacoes =
    document.getElementById(
      "informacoes_curso"
    );

  const btnAdquirirAgora =
    document.getElementById(
      "btnAdquirirAgora"
    );

  const btnAplicarCupom =
    document.getElementById(
      "btnAplicarCupom"
    );

  if (tituloCurso) {
    tituloCurso.innerText =
      cursoNome || "Curso";
  }

  if (!cursoId) {
    document.body.style.visibility =
      "visible";

    const msg =
      document.getElementById(
        "msgCursoInfo"
      );

    if (msg) {
      msg.textContent =
        "Curso não identificado.";
    }

    return;
  }

  try {
    dadosCursoInfo =
      await apiGet(
        `/public/cursos/${cursoId}/checkout`
      );

    if (tituloCurso) {
      tituloCurso.innerText =
        dadosCursoInfo.nome ||
        cursoNome ||
        "Curso";
    }

    if (informacoes) {
      informacoes.textContent =
        dadosCursoInfo.descricao_publica ||
        "Informações ainda não cadastradas.";
    }

    renderizarEstruturaCursoInfo();

    renderizarOpcoesAcessoCursoInfo();

    if (btnAdquirirAgora) {
      btnAdquirirAgora.onclick =
        adquirirAgoraCursoInfo;
    }

    if (btnAplicarCupom) {
      btnAplicarCupom.onclick =
        aplicarCupomCursoInfo;
    }

    await restaurarEstadoCompraCursoInfo();

    const continuarCompra =
      localStorage.getItem(
        "continuar_compra_apos_login"
      );

    if (
      continuarCompra === "1" &&
      getToken()
    ) {
      localStorage.removeItem(
        "continuar_compra_apos_login"
      );

      await adquirirAgoraCursoInfo();

      return;
    }

    document.body.style.visibility =
      "visible";

  } catch (err) {
    console.error(err);

    document.body.style.visibility =
      "visible";

    const msg =
      document.getElementById(
        "msgCursoInfo"
      );

    if (msg) {
      msg.textContent =
        "Erro ao carregar informações do curso.";

      msg.style.color =
        "#8a1f1f";
    }
  }
}

const anoAtualCursoInfo = document.getElementById("ano_atual");
if (anoAtualCursoInfo) {
  anoAtualCursoInfo.textContent = new Date().getFullYear();
}

// Dispatcher
window.onload = () => {
  const page = document.body.getAttribute("data-page");
  if (page === "cursos") pageCursos();
  if (page === "disciplinas") pageDisciplinas();
  if (page === "assuntos") pageAssuntos();
  if (page === "pastas") pagePastas();
  if (page === "interatividade") pageInteratividade();
  if (page === "quiz") pageQuiz();
  if (page === "cartoes") pageCartoes();
  if (page === "questoesia") pageQuestoesIA();
  if (page === "interatividade-disciplinas") {
    pageInteratividadeDisciplinas();
  }
  if (page === "interatividade-assuntos") pageInteratividadeAssuntos();
  if (page === "curso") pageCurso();
  if (page === "curso-info") pageCursoInfo();
  if (page === "questoes-disciplinas") pageQuestoesDisciplinas();
  if (page === "questoes-assuntos") pageQuestoesAssuntos();
  if (page === "questoes-pratica") pageQuestoesPratica();
  if (page === "admin-questoes-pratica") pageAdminQuestoesPratica();

  // ✅ NOVO: tenta bindar o botão “Entre e comece a estudar” na HOME (se existir)
  bindBotaoEntrarEEstudarSeExistir();
};

function logout() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("me_cache"); 
  // Se estiver dentro de /admin, volta 1 nível
  const inAdmin = window.location.pathname.includes("/admin/");
  window.location.href = inAdmin ? "../login.html" : "login.html";
}

// HOME (pública): lista cursos disponíveis para compra
let cursosPublicosCache = [];
let areaSelecionada = "TODOS";
let mostrarTodosCursos = false;

function identificarAreaCurso(nome) {
  const n = String(nome || "").toUpperCase();

  if (n.includes("PROFESSOR") || n.includes("SEDUC") || n.includes("EDUCAÇÃO") || n.includes("EDUCACAO")) {
    return "EDUCAÇÃO";
  }

  if (n.includes("SAÚDE") || n.includes("SAUDE") || n.includes("AGENTE COMUNITÁRIO") || n.includes("AGENTE COMUNITARIO")) {
    return "SAÚDE";
  }

  if (n.includes("TJ") || n.includes("JUDICIÁRIO") || n.includes("JUDICIARIO")) {
    return "TRIBUNAIS";
  }

  if (n.includes("DPE") || n.includes("DEFENSORIA")) {
    return "DPE";
  }

  if (n.includes("FISCAL") || n.includes("SEFAZ") || n.includes("ISS")) {
    return "FISCAL";
  }

  return "OUTROS";
}

function filtrarCursosPorArea(area) {
  areaSelecionada = area;
  mostrarTodosCursos = false;
  renderizarCursosPublicos();
}

function renderizarCursosPublicos() {
  const el = document.getElementById("lista-cursos-publicos");
  const maisBox = document.getElementById("mais-cursos-box");

  if (!el) return;

  const busca = (document.getElementById("buscaCurso")?.value || "")
    .trim()
    .toUpperCase();

  let cursos = [...cursosPublicosCache]
    .filter(c => c.ativo)
    .sort((a, b) => a.nome.localeCompare(b.nome));

  if (areaSelecionada !== "TODOS") {
    cursos = cursos.filter(c => identificarAreaCurso(c.nome) === areaSelecionada);
  }

  if (busca) {
    cursos = cursos.filter(c => c.nome.toUpperCase().includes(busca));
  }

  const limiteInicial = 15;
  const cursosVisiveis = mostrarTodosCursos
    ? cursos
    : cursos.slice(0, limiteInicial);

  el.style.display = "grid";
  el.style.paddingLeft = "39px";
  el.style.gridTemplateColumns = "repeat(auto-fit, minmax(260px, max-content))";
  el.style.gridAutoFlow = "column";
  el.style.gridTemplateRows = "repeat(5, auto)";
  el.style.gap = "4px 90px";

  el.innerHTML = cursosVisiveis.map(c => `
    <div class="curso-linha" style="
      padding:8px 10px;
      border:1px solid #ddd;
      border-radius:8px;
    ">
      <a
        href="curso-info.html?curso_id=${c.id}&curso_nome=${encodeURIComponent(c.nome)}"
        style="font-weight:bold; text-decoration:none; color:inherit;"
      >
        ${escapeHtml(c.nome)}
      </a>
    </div>
  `).join("") || "<p>Nenhum curso encontrado.</p>";

  if (maisBox) {
    if (cursos.length > limiteInicial && !mostrarTodosCursos) {
      maisBox.innerHTML = `
        <button class="btn" onclick="mostrarTodosCursos = true; renderizarCursosPublicos();">
          Mais cursos
        </button>
      `;
    } else if (cursos.length > limiteInicial && mostrarTodosCursos) {
      maisBox.innerHTML = `
        <button class="btn" onclick="mostrarTodosCursos = false; renderizarCursosPublicos();">
          Mostrar menos
        </button>
      `;
    } else {
      maisBox.innerHTML = "";
    }
  }
}

async function pageHomeCursosPublico() {
  try {
    cursosPublicosCache = await apiGet("/cursos-publicos");
    renderizarCursosPublicos();
  } catch (err) {
    showError("lista-cursos-publicos", err);
  }
}

let checkoutEmAndamento = false;

async function comprarCursoFromHome(cursoId) {
  localStorage.setItem("ultimo_curso_id_compra", String(cursoId));
  localStorage.setItem("ultimo_checkout_curso_id", String(cursoId));

  window.location.href = `checkout.html?curso_id=${encodeURIComponent(cursoId)}`;
}

async function pageInteratividadeDisciplinas() {

  const cursoId = qs("curso_id");
  const cursoNome = qs("curso_nome") || "";

  const titulo = document.getElementById("titulo_curso");

  if (titulo) {
    titulo.innerText = cursoNome;
  }

  const lista = document.getElementById("lista");

  if (!cursoId || !lista) return;

  try {

    const disciplinas = await apiGet(`/cursos/${cursoId}/disciplinas`);

    lista.innerHTML = "";

    disciplinas.forEach(d => {

      const div = document.createElement("div");

      div.className = "disciplina";
      div.style.padding = "10px 14px";

      div.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;">

          <div style="font-weight:bold;">
            ${escapeHtml(d.nome)}
          </div>

          <a class="btn"
            href="interatividade-assuntos.html?disciplina_id=${d.id}&disciplina_nome=${encodeURIComponent(d.nome)}&curso_nome=${encodeURIComponent(cursoNome)}">
            Abrir
          </a>

        </div>
      `;

      lista.appendChild(div);

    });

  } catch (err) {

    lista.innerHTML = `
      <p>Erro ao carregar disciplinas.</p>
    `;

    console.error(err);
  }
}

function voltarParaDisciplinas() {
  const urlSalva = localStorage.getItem("voltar_para_disciplinas");

  if (urlSalva) {
    window.location.href = urlSalva;
    return;
  }

  window.location.href = "cursos.html";
}

function voltarParaCurso() {
  const urlSalva = localStorage.getItem("voltar_para_curso");

  if (urlSalva) {
    window.location.href = urlSalva;
    return;
  }

  const cursoId = qs("curso_id");
  const cursoNome = qs("curso_nome") || "";

  if (cursoId) {
    window.location.href =
      `curso.html?curso_id=${encodeURIComponent(cursoId)}&curso_nome=${encodeURIComponent(cursoNome)}`;
    return;
  }

  window.location.href = "cursos.html";
}

async function pageQuestoesDisciplinas() {
  const cursoId = qs("curso_id");
  const cursoNome = qs("curso_nome") || "";

  const titulo =
    document.getElementById("titulo_curso");

  const lista =
    document.getElementById("lista");

  if (titulo) {
    titulo.innerText = cursoNome
      ? `📝 Questões - ${cursoNome}`
      : "📝 Questões";
  }

  if (!cursoId || !lista) {
    if (lista) {
      lista.innerHTML =
        "<p>Curso não identificado.</p>";
    }

    return;
  }

  try {
    const disciplinas = await apiGetAuth(
      `/cursos/${cursoId}/disciplinas-proprias`
    );

    lista.innerHTML = "";

    if (
      !disciplinas ||
      disciplinas.length === 0
    ) {
      lista.innerHTML =
        "<p>Nenhuma disciplina encontrada para este curso.</p>";

      return;
    }

    disciplinas.forEach(d => {
      const div =
        document.createElement("div");

      div.className = "disciplina";
      div.style.padding = "10px 14px";
      div.style.opacity =
        d.bloqueada ? "0.55" : "1";

      div.innerHTML = `
        <div style="
          display:flex;
          justify-content:space-between;
          align-items:center;
          gap:12px;
          flex-wrap:wrap;
        ">

          <div style="font-weight:bold;">
            ${escapeHtml(d.nome)}
          </div>

          ${
            d.bloqueada
              ? `
                <span
                  class="btn"
                  style="
                    opacity:.75;
                    cursor:default;
                  "
                  title="Disponível no acesso completo"
                >
                  Abrir
                </span>
              `
              : `
                <a
                  class="btn"
                  href="questoes-assuntos.html?curso_id=${encodeURIComponent(cursoId)}&curso_nome=${encodeURIComponent(cursoNome)}&disciplina_id=${encodeURIComponent(d.id)}&disciplina_nome=${encodeURIComponent(d.nome)}"
                >
                  Abrir
                </a>
              `
          }

        </div>
      `;

      lista.appendChild(div);
    });

  } catch (err) {
    console.error(err);

    lista.innerHTML = `
      <div class="card">
        Erro ao carregar disciplinas.
      </div>
    `;
  }
}

async function pageQuestoesAssuntos() {
  const cursoId = qs("curso_id");
  const cursoNome = qs("curso_nome") || "";
  const disciplinaId = qs("disciplina_id");
  const disciplinaNome = qs("disciplina_nome") || "";

  const tituloCurso = document.getElementById("titulo_curso");
  const tituloDisciplina = document.getElementById("titulo_disciplina");
  const lista = document.getElementById("lista");

  if (tituloCurso) {
    tituloCurso.innerText = cursoNome ? `📝 ${cursoNome}` : "📝 Questões";
  }

  if (tituloDisciplina) {
    tituloDisciplina.innerText = disciplinaNome;
  }

  if (!disciplinaId || !lista) {
    if (lista) lista.innerHTML = "<p>Disciplina não identificada.</p>";
    return;
  }

  try {
    const assuntos = await apiGetAuth(
      `/disciplinas-proprias/${disciplinaId}/assuntos-proprios`
    );

    lista.innerHTML = "";

    if (!assuntos || assuntos.length === 0) {
      lista.innerHTML = "<p>Nenhum assunto encontrado para esta disciplina.</p>";
      return;
    }

    assuntos.forEach(a => {
      const div = document.createElement("div");
      div.className = "disciplina";
      div.style.padding = "10px 14px";

      div.innerHTML = `
        <div style="
          display:flex;
          justify-content:space-between;
          align-items:center;
          gap:12px;
          flex-wrap:wrap;
        ">
          <div style="font-weight:bold;">
            ${escapeHtml(a.nome)}
          </div>

          <a
            class="btn"
            href="questoes-pratica.html?curso_id=${encodeURIComponent(cursoId)}&curso_nome=${encodeURIComponent(cursoNome)}&disciplina_id=${encodeURIComponent(disciplinaId)}&disciplina_nome=${encodeURIComponent(disciplinaNome)}&assunto_id=${encodeURIComponent(a.id)}&assunto_nome=${encodeURIComponent(a.nome)}"
          >
            Abrir
          </a>
        </div>
      `;

      lista.appendChild(div);
    });

  } catch (err) {
    console.error(err);
    lista.innerHTML = "<p>Erro ao carregar assuntos.</p>";
  }
}

let questaoPraticaAtual = null;
let filtrosQuestoesPratica = ["TODAS"];
let filtrosQuestoesDisponiveis = null;
let idsQuestoesSessaoPratica = null;

async function pageQuestoesPratica() {
  const cursoNome = qs("curso_nome") || "";
  const assuntoId = qs("assunto_id");
  const assuntoNome = qs("assunto_nome") || "";
  const area = document.getElementById("area_questao");

  document.getElementById("titulo_curso").innerText = cursoNome;
  document.getElementById("titulo_assunto").innerText = assuntoNome;

  if (!assuntoId || !area) return;

  await carregarFiltrosQuestoesPratica();
  await carregarProximaQuestaoPratica();
}

async function carregarProximaQuestaoPratica() {
  const assuntoId = qs("assunto_id");
  const area = document.getElementById("area_questao");

  try {
    const dados = await apiPostAuth(
      `/curso-assuntos-proprios/${assuntoId}/questoes-pratica/proxima`,
      {
        filtros: filtrosQuestoesPratica,
        ids_questoes_sessao: idsQuestoesSessaoPratica
      }
    );

    questaoPraticaAtual = dados.questao;

    if (!idsQuestoesSessaoPratica) {
      idsQuestoesSessaoPratica = dados.ids_questoes_sessao || null;
    }

    const tipo = String(questaoPraticaAtual.tipo || "").toUpperCase();
    const alternativas = questaoPraticaAtual.alternativas || [];

    let opcoesRespostaHtml = "";

    if (tipo === "CERTO_ERRADO") {
      opcoesRespostaHtml = `
        <label style="display:block;margin-bottom:6px;">
          <input type="radio" name="resposta_aluno" value="C">
          CERTO
        </label>

        <label style="display:block;margin-bottom:6px;">
          <input type="radio" name="resposta_aluno" value="E">
          ERRADO
        </label>

        <label style="display:block;margin-bottom:6px;">
          <input type="radio" name="resposta_aluno" value="NAO_SEI">
          Não sei e prefiro não marcar
        </label>
      `;
    }

    if (tipo === "MULTIPLA") {
      opcoesRespostaHtml = alternativas.map(alt => `
        <label style="display:block;margin-bottom:8px;">
          <input type="radio" name="resposta_aluno" value="${escapeHtml(alt.letra)}">
          <strong>${escapeHtml(alt.letra)})</strong> ${escapeHtml(alt.texto)}
        </label>
      `).join("");
    }

    area.innerHTML = `
      ${montarFiltrosQuestoesPraticaHtml()}

      <div class="card">
        <h2>Questão ${dados.numero_questao}</h2>

        <div style="margin-top:12px;">
          ${questaoPraticaAtual.enunciado}
        </div>

        <div style="
          margin-top:18px;
          display:flex;
          justify-content:space-between;
          gap:16px;
          align-items:flex-start;
          flex-wrap:wrap;
        ">
          <div>
            ${tipo === "CERTO_ERRADO" ? `<div style="font-weight:bold;margin-bottom:8px;">Marque sua resposta:</div>` : ""}
            ${opcoesRespostaHtml}
          </div>

          <div style="margin-top:${tipo === "MULTIPLA" ? "118px" : "52px"};">
            <label>
              <input type="checkbox" id="rever_questao">
              Rever esta questão
            </label>
          </div>
        </div>

        <div style="margin-top:18px;">
          <div style="font-weight:bold;margin-bottom:8px;">
            Considero esta questão:
          </div>

          <div style="
            display:flex;
            gap:30px;
            align-items:center;
            flex-wrap:wrap;
          ">
            <label>
              <input type="radio" name="dificuldade_questao" value="FACIL">
              Fácil
            </label>

            <label>
              <input type="radio" name="dificuldade_questao" value="MEDIA">
              Média
            </label>

            <label>
              <input type="radio" name="dificuldade_questao" value="DIFICIL">
              Difícil
            </label>
          </div>
        </div>

        <div id="mensagem_questao" style="margin-top:12px;"></div>

        <div style="
          margin-top:18px;
          display:flex;
          gap:48px;
          flex-wrap:wrap;
          align-items:center;
        ">
          <button class="btn" onclick="responderQuestaoPratica()">
            Responder
          </button>

          <button class="btn" onclick="continuarDepoisQuestoesPratica()">
            Continuar depois
          </button>
        </div>
      </div>
    `;

  } catch (err) {
    area.innerHTML = `
      <div class="card">
        <h2>Erro</h2>
        <pre style="white-space:pre-wrap">${escapeHtml(err.message)}</pre>
      </div>
    `;
  }
}

async function responderQuestaoPratica() {
  if (!questaoPraticaAtual) return;

  const respostaSelecionada = document.querySelector("input[name='resposta_aluno']:checked");
  const dificuldadeSelecionada = document.querySelector("input[name='dificuldade_questao']:checked");
  const rever = document.getElementById("rever_questao")?.checked || false;
  const mensagem = document.getElementById("mensagem_questao");

  if (!respostaSelecionada) {
    mensagem.innerHTML = `<div style="color:#b45309;font-weight:bold;">Marque uma resposta antes de continuar.</div>`;
    return;
  }

  if (!dificuldadeSelecionada) {
    mensagem.innerHTML = `<div style="color:#b45309;font-weight:bold;">Classifique a questão antes de responder.</div>`;
    return;
  }

  const respostaAluno = respostaSelecionada.value;
  const dificuldade = dificuldadeSelecionada.value;
  const naoSoube = respostaAluno === "NAO_SEI";

  const gabarito = String(questaoPraticaAtual.gabarito || "").trim().toUpperCase();

  let acertou = null;
  if (!naoSoube) {
    acertou = respostaAluno === gabarito;
  }

  await apiPostAuth(`/questoes-pratica/${questaoPraticaAtual.id}/responder`, {
    dificuldade_marcada: dificuldade,
    acertou,
    rever,
    nao_soube: naoSoube,
    filtros: filtrosQuestoesPratica
  });

  const resultadoHtml = naoSoube
    ? `<div style="color:#b45309;font-weight:bold;">Registrado para revisar depois.</div>`
    : acertou
      ? `<div style="color:#16a34a;font-weight:bold;">${mensagemAcertoAleatoria()} ✓</div>`
      : `<div style="color:#dc2626;font-weight:bold;">Não desta vez</div>`;

  mensagem.innerHTML = `
    ${resultadoHtml}

    <div style="margin-top:12px;">
      <strong>Gabarito:</strong> ${escapeHtml(gabarito)}
    </div>

    ${
      questaoPraticaAtual.comentario
        ? `<div style="margin-top:10px;"><strong>Comentário:</strong><br>${questaoPraticaAtual.comentario}</div>`
        : ""
    }

    <div style="
      margin-top:18px;
      display:flex;
      gap:36px;
      flex-wrap:wrap;
      align-items:center;
    ">
      <button id="btn_proxima_questao" class="btn" onclick="carregarProximaQuestaoPratica()">Próxima</button>
      <button class="btn" onclick="continuarDepoisQuestoesPratica()">Continuar depois</button>
    </div>
  `;

  if (!naoSoube && acertou === false) {
    destacarAlternativasErro(respostaAluno, gabarito);
  }

  setTimeout(() => {
    document.getElementById("btn_proxima_questao")?.focus();
  }, 0);

  const btnResponder = document.querySelector("button[onclick='responderQuestaoPratica()']");
  if (btnResponder) btnResponder.style.display = "none";
}

function destacarAlternativasErro(respostaAluno, gabarito) {
  const opcoes = document.querySelectorAll("input[name='resposta_aluno']");

  opcoes.forEach(input => {
    const label = input.closest("label");
    if (!label) return;

    const valor = input.value;

    if (valor === gabarito) {
      label.style.color = "#16a34a";
      label.style.fontWeight = "bold";
    }

    if (valor === respostaAluno && valor !== gabarito) {
      label.style.color = "#dc2626";
      label.style.fontWeight = "bold";
    }
  });
}

function mensagemAcertoAleatoria() {
  const opcoes = ["Isso", "Boa", "Exato"];
  const indice = Math.floor(Math.random() * opcoes.length);
  return opcoes[indice];
}

function continuarDepoisQuestoesPratica() {
  const confirmar = confirm("Deseja realmente sair?");

  if (!confirmar) return;

  const cursoId = qs("curso_id");
  const cursoNome = qs("curso_nome") || "";
  const disciplinaId = qs("disciplina_id");
  const disciplinaNome = qs("disciplina_nome") || "";

  idsQuestoesSessaoPratica = null;

  window.location.href =
    `questoes-assuntos.html?curso_id=${encodeURIComponent(cursoId || "")}` +
    `&curso_nome=${encodeURIComponent(cursoNome)}` +
    `&disciplina_id=${encodeURIComponent(disciplinaId || "")}` +
    `&disciplina_nome=${encodeURIComponent(disciplinaNome)}`;
}

async function carregarFiltrosQuestoesPratica() {
  const assuntoId = qs("assunto_id");

  filtrosQuestoesDisponiveis = await apiGetAuth(
    `/curso-assuntos-proprios/${assuntoId}/questoes-pratica/filtros`
  );
}

function montarFiltrosQuestoesPraticaHtml() {
  const filtros = [
    { chave: "TODAS", label: "Todas" },
    { chave: "DIFICIL", label: "Difíceis" },
    { chave: "MEDIA", label: "Médias" },
    { chave: "FACIL", label: "Fáceis" },
    { chave: "ERREI", label: "As que errei" },
    { chave: "REVER", label: "Que marquei para rever" }
  ];

  return `
    <div class="card" style="
      margin-bottom:23px;
      padding-top:10px;
      padding-bottom:10px;
      display:flex;
      align-items:center;
    ">
      <h2 style="margin:0;">Questões</h2>
    </div>

    <div class="card" style="margin-bottom:25px;">

      <div style="
        margin-top:12px;
        display:flex;
        gap:14px;
        flex-wrap:wrap;
        align-items:center;
      ">
        ${filtros.map(f => {
          const info = filtrosQuestoesDisponiveis?.[f.chave];
          const habilitado = f.chave === "TODAS" || info?.habilitado;
          const marcado = filtrosQuestoesPratica.includes(f.chave);

          return `
            <label
              title="${habilitado ? "" : "Ainda não há questão neste filtro"}"
              style="
                opacity:${habilitado ? "1" : "0.45"};
                cursor:pointer;
                user-select:none;
              "
            >
              <input
                type="checkbox"
                ${marcado ? "checked" : ""}
                onclick="alternarFiltroQuestoesPratica('${f.chave}', ${habilitado})"
              >
              ${f.label}
            </label>
          `;
        }).join("")}
      </div>
    </div>
  `;
}

function alternarFiltroQuestoesPratica(filtro, habilitado) {
  if (!habilitado) return;

  if (filtro === "TODAS") {
    filtrosQuestoesPratica = ["TODAS"];
  } else {
    filtrosQuestoesPratica = filtrosQuestoesPratica.filter(f => f !== "TODAS");

    if (filtrosQuestoesPratica.includes(filtro)) {
      filtrosQuestoesPratica = filtrosQuestoesPratica.filter(f => f !== filtro);
    } else {
      filtrosQuestoesPratica.push(filtro);
    }

    if (filtrosQuestoesPratica.length === 0) {
      filtrosQuestoesPratica = ["TODAS"];
    }
  }

  idsQuestoesSessaoPratica = null;

  carregarProximaQuestaoPratica();
}

let questoesPraticaAdmin = [];
let filtroTipoQuestaoAdmin = "TODAS";
let posicaoScrollAntesEditarQuestaoAdmin = 0;
let editandoQuestaoPraticaAdmin = false;

async function pageAdminQuestoesPratica() {
  const assuntoId = qs("assunto_id");
  const lista = document.getElementById("lista_questoes");
  const resumo = document.getElementById("resumo_questoes");

  if (!assuntoId || !lista) {
    if (lista) lista.innerHTML = "<p>Assunto não identificado.</p>";
    return;
  }

  try {
    questoesPraticaAdmin = await apiGetAuth(
      `/admin/curso-assuntos-proprios/${assuntoId}/questoes-pratica`
    );

    const total = questoesPraticaAdmin.length;

    const multipla = questoesPraticaAdmin.filter(q =>
      String(q.tipo || "").toUpperCase() === "MULTIPLA"
    ).length;

    const certoErrado = questoesPraticaAdmin.filter(q =>
      String(q.tipo || "").toUpperCase() === "CERTO_ERRADO"
    ).length;

    if (resumo) {
      resumo.innerHTML = `
        Total: ${total} |
        Múltipla: ${multipla} |
        Certo/Errado: ${certoErrado}
      `;
    }

    renderizarListaQuestoesPraticaAdmin();

  } catch (err) {
    lista.innerHTML = `
      <div class="card">
        <h2>Erro</h2>
        <pre style="white-space:pre-wrap">${escapeHtml(err.message)}</pre>
      </div>
    `;
  }
}

function filtrarQuestoesPraticaAdmin(tipo) {
  filtroTipoQuestaoAdmin = tipo;
  renderizarListaQuestoesPraticaAdmin();
}

function obterQuestoesFiltradasPraticaAdmin() {
  if (filtroTipoQuestaoAdmin === "TODAS") {
    return questoesPraticaAdmin;
  }

  return questoesPraticaAdmin.filter(q => {
    const tipo = String(q.tipo || "").toUpperCase();
    const qtdAlternativas = q.alternativas ? q.alternativas.length : 0;

    if (filtroTipoQuestaoAdmin === "CERTO_ERRADO") {
      return tipo === "CERTO_ERRADO";
    }

    if (filtroTipoQuestaoAdmin === "MULTIPLA_4") {
      return tipo === "MULTIPLA" && qtdAlternativas === 4;
    }

    if (filtroTipoQuestaoAdmin === "MULTIPLA_5") {
      return tipo === "MULTIPLA" && qtdAlternativas === 5;
    }

    return true;
  });
}

function renderizarListaQuestoesPraticaAdmin() {
  const lista = document.getElementById("lista_questoes");
  if (!lista) return;

  const questoes = obterQuestoesFiltradasPraticaAdmin();

  const contador = document.getElementById("contador_questoes_admin");
  if (contador) {
    contador.textContent = questoes ? questoes.length : 0;
  }

  if (!questoes || questoes.length === 0) {
    const aindaNaoHaQuestoes =
      !questoesPraticaAdmin ||
      questoesPraticaAdmin.length === 0;

    lista.innerHTML = `
      <div class="card">
        <p>
          ${
            aindaNaoHaQuestoes
              ? "Ainda não há questões produzidas."
              : "Não há questões neste filtro."
          }
        </p>
      </div>
    `;

    return;
  }

  lista.innerHTML = questoes.map((q, index) => {
    const tipo = String(q.tipo || "").toUpperCase();

    const alternativasHtml = tipo === "MULTIPLA"
      ? `
        <div style="margin-top:10px;margin-bottom:14px;">
          ${(q.alternativas || []).map(alt => `
            <div style="margin-bottom:6px;">
              <strong>${escapeHtml(alt.letra)})</strong>
              ${escapeHtml(alt.texto)}
            </div>
          `).join("")}
        </div>
      `
      : "";

    const comentarioHtml = q.comentario
      ? `
        <div style="margin-top:12px;margin-bottom:14px;">
          <strong>Comentário:</strong>
          <div style="margin-top:6px; white-space:pre-wrap; text-indent:0; margin-left:0; padding-left:0;">${escapeHtml(q.comentario || "")}</div>
        </div>
      `
      : "";

    return `
      <div class="card">
        <h2 style="
            font-size:1.05rem;
            margin-bottom:12px;
        ">
            Questão ${index + 1}
        </h2>

        <div style="margin-bottom:12px; white-space:pre-wrap; text-indent:0; margin-left:0; padding-left:0;">${escapeHtml(q.enunciado || "")}</div>

        ${alternativasHtml}

        ${comentarioHtml}

        <div style="
          display:flex;
          gap:18px;
          flex-wrap:wrap;
        ">
          <button class="btn" onclick="editarQuestaoPraticaAdmin(${q.id})">
            Editar
          </button>

          <button class="btn" onclick="excluirQuestaoPraticaAdmin(${q.id})">
            Excluir
          </button>
        </div>
      </div>
    `;
  }).join("");
}

function novaQuestaoPraticaAdmin() {
  const box =
    document.getElementById("formulario_questao");

  const areaListagem =
    document.getElementById("areaListagemQuestoesAdmin");

  const btnListar =
    document.getElementById("btnListarQuestoesAdmin");

  if (!box) return;

  // Ao criar ou editar uma questão,
  // recolhe a lista para não deixar os conteúdos juntos.
  if (areaListagem) {
    areaListagem.style.display = "none";
  }

  if (btnListar) {
    btnListar.textContent = "Listar questões";
  }

  box.innerHTML = `
    <div class="card">

      <div style="margin-bottom:16px;">
        <strong>Escolha o tipo</strong>
      </div>

      <label style="display:block;margin-bottom:8px;">
        <input
          type="radio"
          name="tipo_questao_admin"
          value="MULTIPLA_5"
          onchange="montarFormularioQuestaoPraticaAdmin('MULTIPLA_5')"
        >
        Múltipla escolha 5
      </label>

      <label style="display:block;margin-bottom:8px;">
        <input
          type="radio"
          name="tipo_questao_admin"
          value="MULTIPLA_4"
          onchange="montarFormularioQuestaoPraticaAdmin('MULTIPLA_4')"
        >
        Múltipla escolha 4
      </label>

      <label style="display:block;margin-bottom:8px;">
        <input
          type="radio"
          name="tipo_questao_admin"
          value="CERTO_ERRADO"
          onchange="montarFormularioQuestaoPraticaAdmin('CERTO_ERRADO')"
        >
        Certo / Errado
      </label>

      <div
        id="campos_questao_admin"
        style="margin-top:18px;"
      ></div>

    </div>
  `;
}

function montarFormularioQuestaoPraticaAdmin(tipoEscolhido) {
  const tipo = String(tipoEscolhido || "").toUpperCase();

  if (tipo === "CERTO_ERRADO") {
    montarFormularioCertoErradoAdmin();
    return;
  }

  if (tipo === "MULTIPLA_5") {
    montarFormularioMultiplaAdmin("MULTIPLA_5", 5);
    return;
  }

  if (tipo === "MULTIPLA_4") {
    montarFormularioMultiplaAdmin("MULTIPLA_4", 4);
    return;
  }
}

function montarFormularioBaseAdmin(conteudoCampos, tipo) {
  const box = document.getElementById("campos_questao_admin");
  if (!box) return;

  box.innerHTML = `
    <div class="assunto">
      <label><b>Enunciado</b></label><br>
      <textarea id="questao_admin_enunciado" rows="5" style="width:100%;padding:12px;"></textarea>
    </div>

    ${conteudoCampos}

    <div class="assunto">
      <label><b>Comentário</b></label><br>
      <textarea id="questao_admin_comentario" rows="4" style="width:100%;padding:12px;"></textarea>
    </div>

    <div style="display:flex;gap:36px;flex-wrap:wrap;">
      <button class="btn" onclick="salvarQuestaoPraticaAdmin('${tipo}')">
        Salvar questão
      </button>

      <button class="btn" onclick="cancelarFormularioQuestaoPraticaAdmin()">
        Cancelar
      </button>
    </div>
  `;
}

function montarFormularioCertoErradoAdmin() {
  const campos = `
    <div class="assunto">
      <label><b>Gabarito</b></label><br>

      <label>
        <input type="radio" name="questao_admin_gabarito" value="C">
        CERTO
      </label>

      <label style="margin-left:24px;">
        <input type="radio" name="questao_admin_gabarito" value="E">
        ERRADO
      </label>
    </div>
  `;

  montarFormularioBaseAdmin(campos, "CERTO_ERRADO");
}

function montarFormularioMultiplaAdmin(tipo, qtd) {
  const letras = ["A", "B", "C", "D", "E"].slice(0, qtd);

  const campos = `
    <div class="assunto">
      <label><b>Alternativas</b></label><br>

      ${letras.map(letra => `
        <div
          class="linha_alternativa_admin"
          style="
            margin-top:10px;
            padding:8px;
            border-radius:6px;
            border:1px solid transparent;
          "
        >
          <label>
            <input
              type="radio"
              name="questao_admin_correta"
              value="${letra}"
              onchange="destacarAlternativaCorretaAdmin()"
            >
            <b>${letra})</b>
          </label>

          <input
            id="alternativa_${letra}"
            type="text"
            style="width:85%;padding:10px;margin-left:8px;"
            placeholder="Texto da alternativa ${letra}"
          >
        </div>
      `).join("")}
    </div>
  `;

  montarFormularioBaseAdmin(campos, tipo);
}

function destacarAlternativaCorretaAdmin() {
  const opcoes = document.querySelectorAll(".linha_alternativa_admin");

  opcoes.forEach(linha => {
    const radio = linha.querySelector("input[type='radio']");

    if (radio && radio.checked) {
      linha.style.background = "#dcfce7";
      linha.style.border = "1px solid #16a34a";
    } else {
      linha.style.background = "transparent";
      linha.style.border = "1px solid transparent";
    }
  });
}

function cancelarFormularioQuestaoPraticaAdmin() {
  const box = document.getElementById("formulario_questao");
  if (box) box.innerHTML = "";

  if (editandoQuestaoPraticaAdmin) {
    editandoQuestaoPraticaAdmin = false;

    setTimeout(() => {
      window.scrollTo({
        top: posicaoScrollAntesEditarQuestaoAdmin,
        behavior: "smooth"
      });
    }, 0);

    return;
  }

  novaQuestaoPraticaAdmin();
}

async function salvarQuestaoPraticaAdmin(tipoEscolhido) {
  const assuntoId = qs("assunto_id");

  const enunciado = document.getElementById("questao_admin_enunciado")?.value.trim();
  const comentario = document.getElementById("questao_admin_comentario")?.value.trim() || null;

  if (!assuntoId) {
    alert("Assunto não identificado.");
    return;
  }

  if (!enunciado) {
    alert("Informe o enunciado.");
    return;
  }

  const tipo = String(tipoEscolhido || "").toUpperCase();

  let payload = {
    curso_assunto_proprio_id: Number(assuntoId),
    tipo: tipo === "CERTO_ERRADO" ? "CERTO_ERRADO" : "MULTIPLA",
    enunciado,
    gabarito: "",
    comentario,
    ativo: true
  };

  if (tipo === "CERTO_ERRADO") {
    const gab = document.querySelector("input[name='questao_admin_gabarito']:checked")?.value;

    if (!gab) {
      alert("Marque o gabarito.");
      return;
    }

    payload.gabarito = gab;
  } else {
    const qtd = tipo === "MULTIPLA_5" ? 5 : 4;
    const letras = ["A", "B", "C", "D", "E"].slice(0, qtd);
    const correta = document.querySelector("input[name='questao_admin_correta']:checked")?.value;

    if (!correta) {
      alert("Marque a alternativa correta.");
      return;
    }

    payload.alternativas = letras.map(letra => {
      const texto = document.getElementById(`alternativa_${letra}`)?.value.trim();

      return {
        letra,
        texto,
        correta: letra === correta
      };
    });

    const algumaVazia = payload.alternativas.some(a => !a.texto);

    if (algumaVazia) {
      alert("Preencha todas as alternativas.");
      return;
    }
  }

  try {
    await apiPostAuth("/admin/questoes-pratica", payload);

    alert("Questão cadastrada com sucesso.");

    document.getElementById("formulario_questao").innerHTML = "";

    await pageAdminQuestoesPratica();

  } catch (err) {
    alert("Erro ao salvar questão: " + err.message);
  }
}

function editarQuestaoPraticaAdmin(questaoId) {
  const questao = questoesPraticaAdmin.find(q => Number(q.id) === Number(questaoId));

  if (!questao) {
    alert("Questão não encontrada.");
    return;
  }

  posicaoScrollAntesEditarQuestaoAdmin = window.scrollY;
  editandoQuestaoPraticaAdmin = true;

  const tipo = String(questao.tipo || "").toUpperCase();

  let tipoFormulario = "CERTO_ERRADO";

  if (tipo === "MULTIPLA") {
    const qtd = questao.alternativas ? questao.alternativas.length : 0;
    tipoFormulario = qtd === 5 ? "MULTIPLA_5" : "MULTIPLA_4";
  }

  novaQuestaoPraticaAdmin();

  const radioTipo = document.querySelector(
    `input[name='tipo_questao_admin'][value='${tipoFormulario}']`
  );

  if (radioTipo) {
    radioTipo.checked = true;
  }

  montarFormularioQuestaoPraticaAdmin(tipoFormulario);

  document.getElementById("questao_admin_enunciado").value = questao.enunciado || "";
  document.getElementById("questao_admin_comentario").value = questao.comentario || "";

  if (tipoFormulario === "CERTO_ERRADO") {
    const gab = String(questao.gabarito || "").toUpperCase();

    const radioGab = document.querySelector(
      `input[name='questao_admin_gabarito'][value='${gab}']`
    );

    if (radioGab) {
      radioGab.checked = true;
    }

  } else {
    (questao.alternativas || []).forEach(alt => {
      const input = document.getElementById(`alternativa_${alt.letra}`);
      if (input) {
        input.value = alt.texto || "";
      }

      if (alt.correta) {
        const radioCorreta = document.querySelector(
          `input[name='questao_admin_correta'][value='${alt.letra}']`
        );

        if (radioCorreta) {
          radioCorreta.checked = true;
        }
      }
    });

    destacarAlternativaCorretaAdmin();
  }

  const campos = document.getElementById("campos_questao_admin");

  if (campos) {
    const tipoSalvar = tipoFormulario;

    const btnSalvar = campos.querySelector("button");

    if (btnSalvar) {
      btnSalvar.textContent = "Salvar alterações";
      btnSalvar.onclick = () => salvarEdicaoQuestaoPraticaAdmin(questao.id, tipoSalvar);
    }
  }

  window.scrollTo({
    top: 0,
    behavior: "smooth"
  });
}

async function salvarEdicaoQuestaoPraticaAdmin(questaoId, tipoEscolhido) {
  const enunciado = document.getElementById("questao_admin_enunciado")?.value.trim();
  const comentario = document.getElementById("questao_admin_comentario")?.value.trim() || null;

  if (!enunciado) {
    alert("Informe o enunciado.");
    return;
  }

  const tipo = String(tipoEscolhido || "").toUpperCase();

  let payload = {
    tipo: tipo === "CERTO_ERRADO" ? "CERTO_ERRADO" : "MULTIPLA",
    enunciado,
    gabarito: "",
    comentario,
    ativo: true
  };

  if (tipo === "CERTO_ERRADO") {
    const gab = document.querySelector("input[name='questao_admin_gabarito']:checked")?.value;

    if (!gab) {
      alert("Marque o gabarito.");
      return;
    }

    payload.gabarito = gab;
  } else {
    const qtd = tipo === "MULTIPLA_5" ? 5 : 4;
    const letras = ["A", "B", "C", "D", "E"].slice(0, qtd);
    const correta = document.querySelector("input[name='questao_admin_correta']:checked")?.value;

    if (!correta) {
      alert("Marque a alternativa correta.");
      return;
    }

    payload.alternativas = letras.map(letra => {
      const texto = document.getElementById(`alternativa_${letra}`)?.value.trim();

      return {
        letra,
        texto,
        correta: letra === correta
      };
    });

    if (payload.alternativas.some(a => !a.texto)) {
      alert("Preencha todas as alternativas.");
      return;
    }
  }

  try {
    await apiPutAuth(`/admin/questoes-pratica/${questaoId}`, payload);

    alert("Questão atualizada com sucesso!");

    document.getElementById("formulario_questao").innerHTML = "";

    await pageAdminQuestoesPratica();

    editandoQuestaoPraticaAdmin = false;

    setTimeout(() => {
      window.scrollTo({
        top: posicaoScrollAntesEditarQuestaoAdmin,
        behavior: "smooth"
      });
    }, 0);

  } catch (err) {
    alert("Erro ao atualizar questão: " + err.message);
  }
}

async function excluirQuestaoPraticaAdmin(questaoId) {
  const confirmar = confirm("Deseja realmente excluir a questão?");

  if (!confirmar) return;

  try {
    await apiDeleteAuth(`/admin/questoes-pratica/${questaoId}`);

    alert("Questão excluída com sucesso!");

    await pageAdminQuestoesPratica();

  } catch (err) {
    alert("Erro ao excluir questão: " + err.message);
  }
}

function sairComConfirmacao() {
  if (confirm("Deseja realmente sair?")) {
    logout();
  }
}

/* ==========================================================
   Navegação para a página inicial
========================================================== */

function irParaInicio(urlInicio = "index.html") {

  localStorage.setItem(
    "pagina_antes_inicio",
    window.location.href
  );

  window.location.href = urlInicio;
}

function voltarDaPaginaInicial() {

  const urlAnterior =
    localStorage.getItem("pagina_antes_inicio");

  if (!urlAnterior) return;

  localStorage.removeItem("pagina_antes_inicio");

  window.location.href = urlAnterior;
}

function alternarListagemQuestoesAdmin() {
  const area =
    document.getElementById("areaListagemQuestoesAdmin");

  const botao =
    document.getElementById("btnListarQuestoesAdmin");

  if (!area || !botao) return;

  const estaFechada =
    getComputedStyle(area).display === "none";

  area.style.display =
    estaFechada ? "block" : "none";

  botao.textContent =
    estaFechada
      ? "Recolher questões"
      : "Listar questões";
}

async function restaurarEstadoCompraCursoInfo() {
  const estadoSalvo =
    localStorage.getItem(
      "estado_compra_curso"
    );

  if (!estadoSalvo) {
    return;
  }

  let estado;

  try {
    estado =
      JSON.parse(
        estadoSalvo
      );

  } catch {
    limparEstadoCompraCursoInfo();
    return;
  }

  if (
    !dadosCursoInfo ||
    Number(estado.curso_id) !==
      Number(dadosCursoInfo.id)
  ) {
    return;
  }

  const radioPlano =
    document.querySelector(
      `input[name="tipo_acesso"][data-tempo-id="${estado.tempo_acesso_id}"]`
    );

  if (!radioPlano) {
    limparEstadoCompraCursoInfo();
    return;
  }

  radioPlano.checked = true;

  controlarAvisoDemoCursoInfo();

  if (!estado.codigo_cupom) {
    return;
  }

  const campoCupom =
    document.getElementById(
      "codigo_cupom_desconto"
    );

  if (!campoCupom) {
    return;
  }

  campoCupom.value =
    estado.codigo_cupom;

  await aplicarCupomCursoInfo();
}

document.addEventListener(
  "DOMContentLoaded",
  () => {
    exibirNomeUsuarioLogado();
  }
);