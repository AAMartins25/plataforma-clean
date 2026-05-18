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


// ✅ função global: usar no botão da HOME (onclick="entrarEEstudar()")
window.entrarEEstudar = async function entrarEEstudar() {
  // ✅ mata qualquer estado de compra (isso é MUITO importante)
  localStorage.removeItem("ultimo_curso_id_compra");
  localStorage.removeItem("ultimo_checkout_curso_id");

  const token = getToken();

  // 1) Não logado → login
  if (!token) {
    // ✅ ao logar, decide com base no /me (admin vai pro painel)
    localStorage.setItem("pos_login_redirect", "cursos.html");
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
    localStorage.setItem("pos_login_redirect", "cursos.html");
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
    const historico = await apiGetAuth("/me/cursos/historico");

    const tituloCursos = document.getElementById("titulo_cursos");
    if (tituloCursos) {
      tituloCursos.style.display = acessos && acessos.length > 0 ? "block" : "none";
    }

    el.innerHTML = "";

    if (!acessos || acessos.length === 0) {
      el.innerHTML = `
        <div class="disciplina">
          <div><strong>Você não possui curso ativo no momento.</strong></div>

          ${
            historico && historico.length > 0
              ? `
                <div style="margin-top:12px;">
                  <strong>Histórico:</strong>
                </div>

                <div class="list" style="margin-top:12px;">
                  ${historico.map(c => `
                    <div class="assunto">
                      <div style="font-weight:bold;">${escapeHtml(c.nome_curso)}</div>
                      <div style="opacity:.85;">
                        Liberação: ${escapeHtml(c.data_inicio || "-")}<br/>
                        Cessação da liberação: ${escapeHtml(c.data_fim || "-")}
                      </div>
                    </div>
                  `).join("")}
                </div>
              `
              : ""
          }
        </div>
      `;
      return;
    }

    // Renderiza só "Abrir"
    for (const a of acessos) {
      const prog = await calcularProgressoCurso(a.curso_id);
      const div = document.createElement("div");
      div.className = "disciplina";
      div.style.padding = "15px 14px";

      div.innerHTML = `
        <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;">
          
          <div style="flex:1; min-width:0;">
            <div style="font-size:1.05rem;font-weight:bold;">${a.nome_curso}</div>

            ${renderProgressoLinha(prog.percentual, prog.aulasConcluidas)}
          </div>

          <div style="margin-left:12px;">
            <a class="btn" href="curso.html?curso_id=${a.curso_id}&curso_nome=${encodeURIComponent(a.nome_curso)}">Abrir</a>
          </div>

        </div>
      `;

      el.appendChild(div);
    };

    if (historico && historico.length > 0) {
      const histDiv = document.createElement("div");
      histDiv.className = "disciplina";

      histDiv.innerHTML = `
        <div style="font-weight:bold;">Histórico:</div>

        <div class="list" style="margin-top:12px;">
          ${historico.map(c => `
            <div class="assunto">
              <div style="font-weight:bold;">${escapeHtml(c.nome_curso)}</div>
              <div style="opacity:.85;">
                Liberação: ${escapeHtml(c.data_inicio || "-")}<br/>
                Cessação da liberação: ${escapeHtml(c.data_fim || "-")}
              </div>
            </div>
          `).join("")}
        </div>
      `;

      el.appendChild(histDiv);
    }

  } catch (err) {
    showError("conteudo", err);
  }
}

async function calcularProgressoDisciplina(disciplinaId) {
  try {

    // assuntos da disciplina
    const assuntos = await apiGet(`/disciplinas/${disciplinaId}/assuntos`);

    let totalAulas = 0;
    let aulasConcluidas = 0;

    for (const assunto of assuntos) {

      // pastas do assunto
      const pastas = await apiGet(`/assuntos/${assunto.id}/pastas`);

      // pega apenas TEORIA
      const pastaTeoria = pastas.find(p => p.tipo === "TEORIA");

      if (!pastaTeoria) continue;

      // aulas da pasta teoria
      const aulas = await apiGet(`/pastas/${pastaTeoria.id}/aulas`);

      totalAulas += aulas.length;

      // progresso do aluno
      const progresso = await apiGetAuth(`/me/progresso?pasta_id=${pastaTeoria.id}`);

      aulasConcluidas += progresso.length;
    }

    const percentual = totalAulas > 0
      ? Math.round((aulasConcluidas / totalAulas) * 100)
      : 0;

    return {
      percentual,
      aulasConcluidas,
      totalAulas
    };

  } catch (err) {
    console.error("Erro ao calcular progresso:", err);

    return {
      percentual: 0,
      aulasConcluidas: 0,
      totalAulas: 0
    };
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
    const disciplinas = await apiGet(`/cursos/${cursoId}/disciplinas`);
    const lista = document.getElementById("lista");

    lista.innerHTML = "";

    for (const d of disciplinas) {

      const prog = await calcularProgressoDisciplina(d.id);

      const div = document.createElement("div");
      div.className = "disciplina";
      div.style.padding = "3px 14px";

      div.innerHTML = `
        <div style="
          display:flex;
          justify-content:space-between;
          align-items:flex-start;
          gap:12px;
          flex-wrap:wrap;
        ">

          <div style="flex:1; min-width:240px;">

            <div style="
              font-weight:bold;
              margin-top:-6px;
            ">
              ${escapeHtml(d.nome)}
            </div>

          </div>

          <div>
            <a class="btn"
              href="assuntos.html?disciplina_id=${d.id}&disciplina_nome=${encodeURIComponent(d.nome)}&curso_nome=${encodeURIComponent(cursoNome)}">
              Abrir
            </a>
          </div>

        </div>

        <div style="
          margin-top:18px;
          display:flex;
          align-items:center;
          gap:2px;
        ">

          <div style="
            font-size:0.95rem;
            color:${prog.aulasConcluidas > 0 ? '#16a34a' : '#c2cad9'};
            font-weight:bold;
            min-width:34px;
          ">
            ${prog.percentual}%
          </div>

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
              background:${prog.aulasConcluidas > 0 ? '#16a34a' : '#c2cad9'};
            "></div>
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
    const pastas = await apiGet(`/assuntos/${assuntoId}/pastas`);
    const pastaTeoria = pastas.find(p => p.tipo === "TEORIA");

    if (!pastaTeoria) {
      return { percentual: 0, aulasConcluidas: 0, totalAulas: 0 };
    }

    const aulas = await apiGet(`/pastas/${pastaTeoria.id}/aulas`);
    const progresso = await apiGetAuth(`/me/progresso?pasta_id=${pastaTeoria.id}`);

    const concluidasSet = new Set(progresso.map(p => p.aula_id));

    const totalAulas = aulas.length;
    const aulasConcluidas = aulas.filter(a => concluidasSet.has(a.id)).length;

    const percentual = totalAulas > 0
      ? Math.round((aulasConcluidas / totalAulas) * 100)
      : 0;

    return { percentual, aulasConcluidas, totalAulas };

  } catch {
    return { percentual: 0, aulasConcluidas: 0, totalAulas: 0 };
  }
}

async function abrirAssuntoDireto(assuntoId, assuntoNomeEncoded, disciplinaNomeEncoded) {
  const pastas = await apiGet(`/assuntos/${assuntoId}/pastas`);
  const pastaTeoria = pastas.find(p => p.tipo === "TEORIA");

  if (!pastaTeoria) {
    alert("Não encontrei a pasta de Teoria deste assunto.");
    return;
  }

  window.location.href =
    `teoria.html?pasta_id=${pastaTeoria.id}&assunto_id=${assuntoId}&assunto_nome=${assuntoNomeEncoded}&disciplina_nome=${disciplinaNomeEncoded}`;
}

// 3) Assuntos da Disciplina
async function pageAssuntos() {
  const disciplinaId = qs("disciplina_id");
  const disciplinaNome = qs("disciplina_nome") || "";
  const cursoNome = qs("curso_nome") || "";

  const tituloCurso = document.getElementById("titulo_curso");
  const titulo = document.getElementById("titulo_pagina");

  if (tituloCurso) {
    tituloCurso.innerText = cursoNome
      ? `📘 ${cursoNome}`
      : "📘 Curso";
  }

  if (titulo) {
    titulo.innerText = disciplinaNome
      ? disciplinaNome
      : "🧩 Assuntos";
  }

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

    const lista = document.getElementById("lista");
    lista.innerHTML = "";

    for (const a of assuntos) {
      const prog = await calcularProgressoAssunto(a.id);

      const div = document.createElement("div");
      div.className = "disciplina";
      div.style.padding = "10px 14px";

      div.innerHTML = `
        <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;">
          <div style="flex:1; min-width:240px;">
            <div style="font-weight:bold;">
              ${escapeHtml(a.nome)}
            </div>

            ${renderProgressoLinha(prog.percentual, prog.aulasConcluidas)}
          </div>

          <a class="btn"
            href="javascript:void(0)"
            onclick="abrirAssuntoDireto(${a.id}, '${encodeURIComponent(a.nome)}', '${encodeURIComponent(disciplinaNome)}')">
            Abrir
          </a>
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
    <div class="disciplina" style="padding:10px 14px;">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;">
        <div style="font-weight:bold;">📚 Disciplinas do curso</div>
        <a class="btn" href="disciplinas.html?curso_id=${encodeURIComponent(cursoId)}&curso_nome=${encodeURIComponent(cursoNome)}">Abrir</a>
      </div>
    </div>

    <div class="disciplina" style="padding:10px 14px;">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;">
        <div style="font-weight:bold;">📊 Meu Progresso e Revisão</div>
        <a class="btn" href="dashboard.html?curso_id=${encodeURIComponent(cursoId)}&curso_nome=${encodeURIComponent(cursoNome)}">Abrir</a>
      </div>
    </div>

    <div class="disciplina" style="padding:10px 14px;">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;">
        <div style="font-weight:bold;">🎯 Interatividade</div>
        <a class="btn" href="interatividade-disciplinas.html?curso_id=${encodeURIComponent(cursoId)}&curso_nome=${encodeURIComponent(cursoNome)}">Abrir</a>
      </div>
    </div>
  `;
}

async function pageCursoInfo() {
  const cursoId = qs("curso_id");
  const cursoNome = qs("curso_nome") || "";

  const tituloCurso = document.getElementById("titulo_curso");
  const estrutura = document.getElementById("estrutura_curso");
  const btnQueroCurso = document.getElementById("btnQueroCurso");

  if (tituloCurso) {
    tituloCurso.innerText = cursoNome || "Curso";
  }

  if (!cursoId || !estrutura) {
    if (estrutura) estrutura.innerHTML = "<p>Curso não identificado.</p>";
    return;
  }

  if (btnQueroCurso) {
    btnQueroCurso.onclick = () => comprarCursoFromHome(Number(cursoId));
  }

  try {
    const disciplinas = await apiGet(`/cursos/${cursoId}/disciplinas`);

    if (!disciplinas || disciplinas.length === 0) {
      estrutura.innerHTML = "<p>Nenhuma disciplina cadastrada para este curso.</p>";
      return;
    }

    let html = "";

    for (const d of disciplinas) {
      let assuntos = [];

      try {
        assuntos = await apiGet(`/disciplinas/${d.id}/assuntos`);
      } catch {
        assuntos = await apiGet(`/disciplinas/${d.id}/assunto`);
      }

      html += `
        <div class="disciplina" style="padding:10px 14px;">
          <div style="font-weight:bold;">
            📚 ${escapeHtml(d.nome)}
          </div>

          ${
            assuntos && assuntos.length > 0
              ? `
                <div class="list" style="margin-top:10px;">
                  ${assuntos.map(a => `
                    <div class="assunto" style="padding:8px 12px;">
                      ${escapeHtml(a.nome)}
                    </div>
                  `).join("")}
                </div>
              `
              : `<p style="opacity:.75;">Nenhum assunto cadastrado.</p>`
          }
        </div>
      `;
    }

    estrutura.innerHTML = html;

  } catch (err) {
    estrutura.innerHTML = `
      <div class="card">
        <h2>Erro ao carregar estrutura do curso</h2>
        <pre style="white-space:pre-wrap">${escapeHtml(err.message)}</pre>
      </div>
    `;
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
  if (page === "interatividade-disciplinas") {
    pageInteratividadeDisciplinas();
  }
  if (page === "interatividade-assuntos") pageInteratividadeAssuntos();
  if (page === "curso") pageCurso();
  if (page === "curso-info") pageCursoInfo();

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
    cursosPublicosCache = await apiGet("/cursos");
    renderizarCursosPublicos();
  } catch (err) {
    showError("lista-cursos-publicos", err);
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