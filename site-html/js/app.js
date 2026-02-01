// js/app.js
const API_BASE = "http://127.0.0.1:8002";

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
    <div class="disciplina">
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


// ✅ função global: usar no botão da HOME (onclick="entrarEEstudar()")
window.entrarEEstudar = async function entrarEEstudar() {
  // ✅ mata qualquer estado de compra (isso é MUITO importante)
  localStorage.removeItem("ultimo_curso_id_compra");
  localStorage.removeItem("ultimo_checkout_curso_id");

  const token = getToken();

  // 1) Não logado → login
  if (!token) {
    // ✅ ao logar, decide com base no /me (admin vai pro painel)
    localStorage.setItem("pos_login_redirect", "index.html"); // voltar pra HOME (opcional)
    window.location.href = "login.html";
    return;
  }

  // 2) Logado → decide admin x aluno pelo /me
  try {
    const me = await apiGetAuth("/me");

    if (me && me.is_admin) {
      window.location.href = "admin/index.html";
    } else {
      window.location.href = "cursos.html";
    }
  } catch (err) {
    // token inválido/expirado → força login de novo
    console.warn("Falha ao obter /me:", err);
    clearToken();
    localStorage.setItem("pos_login_redirect", "index.html");
    window.location.href = "login.html";
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

// 1) Cursos (ÁREA LOGADA: mostra SOMENTE cursos adquiridos)
async function pageCursos() {
  const el = document.getElementById("lista");
  if (!el) throw new Error("Não achei o elemento #lista no cursos.html");

  try {
    // garante que está logado
    const token = getToken();
    if (!token) {
      // se não tiver token, manda para login
      localStorage.setItem("pos_login_redirect", "cursos.html");
      window.location.href = "login.html";
      return;
    }

    if (typeof tentarConfirmarPagamentoAoVoltar === "function") {
      await tentarConfirmarPagamentoAoVoltar();
    }

    const acessos = await apiGetAuth("/me/cursos"); // só cursos liberados pro usuário

    el.innerHTML = "";

    if (!acessos || acessos.length === 0) {
      el.innerHTML = `
        <div class="disciplina">
          <div><strong>Você ainda não possui preparatório ativo no momento.</strong></div>
          <div style="margin-top:8px; opacity:.85;">
            Vá para a página inicial para ver os cursos disponíveis para compra.
          </div>
        </div>
      `;
      return;
    }

    // Renderiza só "Abrir"
    acessos.forEach(a => {
      const div = document.createElement("div");
      div.className = "disciplina";

      div.innerHTML = `
        <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap;">
          <div>
            <div style="font-size:1.05rem;font-weight:bold;">${a.nome_curso}</div>
            <div style="opacity:.85;">curso_id=${a.curso_id} • ativo=${a.ativo}</div>
          </div>

          <div style="display:flex;gap:10px;flex-wrap:wrap;">
            <a class="btn" href="disciplinas.html?curso_id=${a.curso_id}&curso_nome=${encodeURIComponent(a.nome_curso)}">Abrir</a>
          </div>
        </div>
      `;

      el.appendChild(div);
    });

  } catch (err) {
    showError("conteudo", err);
  }
}

// 2) Disciplinas do Curso
async function pageDisciplinas() {
  const cursoId = qs("curso_id");
  const cursoNome = qs("curso_nome") || "";
  setHTML("subtitulo", cursoNome ? `Curso: <b>${escapeHtml(cursoNome)}</b> (id=${cursoId})` : `Curso id=${cursoId}`);

  if (!cursoId) {
    showError("conteudo", new Error("Faltou curso_id na URL. Volte e clique no curso novamente."));
    return;
  }

  try {
    const disciplinas = await apiGet(`/cursos/${cursoId}/disciplinas`);
    renderList("lista", disciplinas.map(d => ({
      title: d.nome,
      subtitle: `id=${d.id} • ativo=${d.ativo}`,
      href: `assuntos.html?disciplina_id=${d.id}&disciplina_nome=${encodeURIComponent(d.nome)}`
    })));
  } catch (err) {
    showError("conteudo", err);
  }
}

// 3) Assuntos da Disciplina
async function pageAssuntos() {
  const disciplinaId = qs("disciplina_id");
  const disciplinaNome = qs("disciplina_nome") || "";
  setHTML("subtitulo", disciplinaNome ? `Disciplina: <b>${escapeHtml(disciplinaNome)}</b> (id=${disciplinaId})` : `Disciplina id=${disciplinaId}`);

  if (!disciplinaId) {
    showError("conteudo", new Error("Faltou disciplina_id na URL. Volte e clique na disciplina novamente."));
    return;
  }

  try {
    let assuntos;
    try {
      assuntos = await apiGet(`/disciplinas/${disciplinaId}/assuntos`);
    } catch (e1) {
      assuntos = await apiGet(`/disciplinas/${disciplinaId}/assunto`);
    }

    renderList("lista", assuntos.map(a => ({
      title: a.nome,
      subtitle: `id=${a.id} • ativo=${a.ativo ?? true}`,
      href: `pastas.html?assunto_id=${a.id}&assunto_nome=${encodeURIComponent(a.nome)}`
    })));
  } catch (err) {
    showError("conteudo", err);
  }
}

// 4) Pastas do Assunto (Teoria e Questões / Interatividade)
async function pagePastas() {
  const assuntoId = qs("assunto_id");
  const assuntoNome = qs("assunto_nome") || "";
  setHTML("subtitulo", assuntoNome ? `Assunto: <b>${escapeHtml(assuntoNome)}</b> (id=${assuntoId})` : `Assunto id=${assuntoId}`);

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
        <div class="disciplina">
          <div style="font-weight:bold">📘 ${escapeHtml(teoria.nome || "Teoria e Questões")}</div>
          <div style="opacity:.85">pasta_id=${teoria.id} • tipo=${teoria.tipo}</div>
          <a class="btn" href="teoria.html?pasta_id=${teoria.id}&assunto_id=${assuntoId}">Abrir</a>
        </div>
      `;
    } else {
      html += `<p>Não achei a pasta TEORIA.</p>`;
    }

    if (inter) {
      html += `
        <div class="disciplina">
          <div style="font-weight:bold">🎯 ${escapeHtml(inter.nome || "Interatividade")}</div>
          <div style="opacity:.85">pasta_id=${inter.id} • tipo=${inter.tipo}</div>
          <a class="btn" href="interatividade.html?pasta_id=${inter.id}&assunto_id=${assuntoId}">Abrir</a>
        </div>
      `;
    } else {
      html += `<p>Não achei a pasta INTERATIVIDADE.</p>`;
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
async function pageHomeCursosPublico() {
  const containerId = "lista-cursos-publicos";

  try {
    const cursos = await apiGet("/cursos"); // público

    const html = (cursos || [])
      .filter(c => c.ativo)
      .map(c => `
        <div class="curso-linha">
          <span class="curso-nome">${c.nome}</span>
          <button class="btn" onclick="comprarCursoFromHome(${Number(c.id)})">Comprar</button>
        </div>
      `)
      .join("");

    const el = document.getElementById(containerId);
    if (!el) throw new Error(`Não achei o elemento #${containerId} no index.html`);

    el.innerHTML = html || "<p>Nenhum curso disponível no momento.</p>";
  } catch (err) {
    showError(containerId, err);
  }
}

async function comprarCursoFromHome(cursoId) {
  localStorage.setItem("ultimo_curso_id_compra", String(cursoId));
  localStorage.setItem("pos_login_redirect", "index.html");

  const token = getToken();

  // 1) Se não estiver logado → vai para login
  if (!token) {
    window.location.href = "login.html";
    return;
  }

  // 2) Se estiver logado → checa se já possui o curso
  try {
    const meus = await apiGetAuth("/me/cursos");
    const meusIds = new Set((meus || []).map(m => Number(m.curso_id)));

    if (meusIds.has(Number(cursoId))) {
      const ok = confirm("Você já possui este preparatório! Deseja continuar mesmo assim?\n\n[OK] Sim • [Cancelar] Não");
      if (!ok) return;
    }

    // 3) Continua para checkout normalmente
    await comprarCurso(Number(cursoId));

  } catch (err) {
    alert("Erro ao validar seu acesso/checkout: " + err.message);
    console.error(err);
  }
}

