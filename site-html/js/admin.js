function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

async function apiGet(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`);
  return res.json();
}

async function apiPost(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const dataText = await res.text();
  let data = null;
  try { data = dataText ? JSON.parse(dataText) : null; } catch { data = dataText; }

  if (!res.ok) {
    const detail = typeof data === "string" ? data : JSON.stringify(data, null, 2);
    throw new Error(`POST ${path} -> ${res.status}\n${detail}`);
  }
  return data;
}

async function apiGetAuth(path) {
  const token = localStorage.getItem("access_token");
  if (!token) throw new Error("Sem token. Faça login novamente.");

  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Authorization": `Bearer ${token}` }
  });

  const txt = await res.text();
  let data = null;
  try { data = txt ? JSON.parse(txt) : null; } catch { data = txt; }

  if (!res.ok) {
    const detail = typeof data === "string" ? data : JSON.stringify(data, null, 2);
    throw new Error(`GET ${path} -> ${res.status}\n${detail}`);
  }
  return data;
}

async function apiPostAuth(path, body) {
  const token = localStorage.getItem("access_token");
  if (!token) throw new Error("Sem token. Faça login novamente.");

  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`
    },
    body: JSON.stringify(body || {})
  });

  const txt = await res.text();
  let data = null;
  try { data = txt ? JSON.parse(txt) : null; } catch { data = txt; }

  if (!res.ok) {
    const detail = typeof data === "string" ? data : JSON.stringify(data, null, 2);
    throw new Error(`POST ${path} -> ${res.status}\n${detail}`);
  }
  return data;
}


async function apiGetAuth(path) {
  const token = localStorage.getItem("access_token");
  if (!token) throw new Error("Sem token. Faça login novamente.");

  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Authorization": `Bearer ${token}` }
  });

  const txt = await res.text();
  let data = null;
  try { data = txt ? JSON.parse(txt) : null; } catch { data = txt; }

  if (!res.ok) {
    const detail = typeof data === "string" ? data : JSON.stringify(data, null, 2);
    throw new Error(`GET ${path} -> ${res.status}\n${detail}`);
  }
  return data;
}

async function apiPostAuth(path, body) {
  const token = localStorage.getItem("access_token");
  if (!token) throw new Error("Sem token. Faça login novamente.");

  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`
    },
    body: JSON.stringify(body || {})
  });

  const txt = await res.text();
  let data = null;
  try { data = txt ? JSON.parse(txt) : null; } catch { data = txt; }

  if (!res.ok) {
    const detail = typeof data === "string" ? data : JSON.stringify(data, null, 2);
    throw new Error(`POST ${path} -> ${res.status}\n${detail}`);
  }
  return data;
}


// ======= GUARDA DO ADMIN =======
async function requireAdmin() {
  try {
    const token = localStorage.getItem("access_token");
    if (!token) {
      alert("Você precisa estar logado para acessar o Admin.");
      window.location.href = "../login.html";
      return false;
    }

    // Reaproveita API_BASE do app.js
    const res = await fetch(`${API_BASE}/me`, {
      headers: { Authorization: `Bearer ${token}` }
    });

    if (!res.ok) {
      localStorage.removeItem("access_token");
      alert("Sessão expirada. Faça login novamente.");
      window.location.href = "../login.html";
      return false;
    }

    const me = await res.json();

    if (!me.is_admin) {
      alert("Acesso negado: área restrita ao administrador.");
      window.location.href = "../cursos.html";
      return false;
    }

    return true;
  } catch (err) {
    alert("Erro ao validar permissões do Admin: " + err.message);
    window.location.href = "../cursos.html";
    return false;
  }
}

const AdminCursos = {
  async init() {
    if (!(await requireAdmin())) return;
    await this.carregarLista();
    this.bindCriar();
  },

  bindCriar() {
    const form = document.getElementById("formCriarCurso");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const nome = document.getElementById("cursoNome").value.trim();
      const ativo = document.getElementById("cursoAtivo").value === "true";
      const msg = document.getElementById("msgCriar");

      msg.innerHTML = "Salvando...";
      try {
        // Ajuste se sua rota for diferente (ex.: "/curso" ao invés de "/cursos")
        await apiPost("/cursos", { nome, ativo });

        msg.innerHTML = "✅ Curso criado. Recarregando...";
        // Recarregamento (padrão desejado)
        window.location.reload();

      } catch (err) {
        msg.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
      }
    });
  },

  async carregarLista() {
    const el = document.getElementById("listaCursos");
    try {
      // Ajuste se sua rota for diferente (ex.: "/curso" ao invés de "/cursos")
      const cursos = await apiGet("/cursos");

      if (!cursos || cursos.length === 0) {
        el.innerHTML = "<p>Nenhum curso cadastrado.</p>";
        return;
      }

      el.innerHTML = `
        <div class="list">
          ${cursos.map(c => `
            <div class="disciplina">
              <b>${esc(c.nome)}</b><br/>
              <span style="opacity:.8">id=${esc(c.id)} • ativo=${esc(c.ativo)}</span>
            </div>
          `).join("")}
        </div>
      `;

    } catch (err) {
      el.innerHTML = `
        <div class="assunto" style="border-left:4px solid #6B4F3F; padding-left:10px;">
          <b>Erro</b>
          <pre style="white-space:pre-wrap">${esc(err.message)}</pre>
          <p style="opacity:.85; margin-top:8px;">
            Verifique se o backend está rodando e se CORS está liberado.
          </p>
        </div>
      `;
    }
  }
};

async function apiGetSafe(path) {
  const res = await fetch(`${API_BASE}${path}`);
  const txt = await res.text();
  let data = null;
  try { data = txt ? JSON.parse(txt) : null; } catch { data = txt; }
  if (!res.ok) {
    const detail = typeof data === "string" ? data : JSON.stringify(data, null, 2);
    throw new Error(`GET ${path} -> ${res.status}\n${detail}`);
  }
  return data;
}

const AdminCursoDisciplinas = {
  async init() {
    if (!(await requireAdmin())) return;
    await this.carregarCursosNoSelect();
    await this.carregarDisciplinasDisponiveis();
    this.bindAcoes();
  },

  bindAcoes() {
    document.getElementById("btnCarregar").addEventListener("click", async () => {
      await this.carregarVinculadas();
    });
  },

  async carregarCursosNoSelect() {
    const select = document.getElementById("cursoSelect");
    const msg = document.getElementById("msgCurso");
    msg.innerHTML = "Carregando cursos...";

    try {
      const cursos = await apiGetSafe("/cursos");
      if (!cursos || cursos.length === 0) {
        select.innerHTML = "";
        msg.innerHTML = "Nenhum curso cadastrado.";
        return;
      }
      select.innerHTML = cursos.map(c => `<option value="${c.id}">${esc(c.nome)} (id=${c.id})</option>`).join("");
      msg.innerHTML = "✅ Cursos carregados.";
    } catch (err) {
      msg.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
    }
  },

  async carregarDisciplinasDisponiveis() {
    const el = document.getElementById("listaDisciplinas");
    el.innerHTML = "Carregando...";

    try {
      // sua API já tem GET /disciplinas (você usou antes no Swagger)
      const disciplinas = await apiGetSafe("/disciplinas");

      if (!disciplinas || disciplinas.length === 0) {
        el.innerHTML = "<p>Nenhuma disciplina cadastrada.</p>";
        return;
      }

      el.innerHTML = `
        <div class="list">
          ${disciplinas.map(d => `
            <div class="disciplina">
              <b>${esc(d.nome)}</b><br/>
              <span style="opacity:.8">id=${esc(d.id)} • ativo=${esc(d.ativo)}</span><br/>
              <button class="btn" style="margin-top:10px" onclick="AdminCursoDisciplinas.vincular(${d.id})">
                Vincular ao curso selecionado
              </button>
            </div>
          `).join("")}
        </div>
      `;
    } catch (err) {
      el.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
    }
  },

  async carregarVinculadas() {
    const cursoId = document.getElementById("cursoSelect").value;
    const el = document.getElementById("listaVinculadas");
    const msg = document.getElementById("msgVinculo");

    el.innerHTML = "Carregando...";
    msg.innerHTML = "";

    try {
      const vinculadas = await apiGetSafe(`/cursos/${cursoId}/disciplinas`);

      if (!vinculadas || vinculadas.length === 0) {
        el.innerHTML = "<p>Nenhuma disciplina vinculada a este curso ainda.</p>";
        return;
      }

      el.innerHTML = `
        <div class="list">
          ${vinculadas.map(d => `
            <div class="disciplina">
              <b>${esc(d.nome)}</b><br/>
              <span style="opacity:.8">id=${esc(d.id)} • ativo=${esc(d.ativo)}</span>
            </div>
          `).join("")}
        </div>
      `;
    } catch (err) {
      el.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
    }
  },

  async vincular(disciplinaId) {
    const cursoId = document.getElementById("cursoSelect").value;
    const msg = document.getElementById("msgVinculo");
    msg.innerHTML = "Vinculando...";

    try {
      // Você já tem essa rota no backend (foi usada antes): POST /cursos/{curso_id}/disciplinas/{disciplina_id}
      await apiPost(`/cursos/${cursoId}/disciplinas/${disciplinaId}`, {});

      msg.innerHTML = "✅ Vinculado! Recarregando lista do curso...";
      await this.carregarVinculadas();

    } catch (err) {
      msg.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
    }
  }
};

const AdminAssuntos = {
  async init() {
    if (!(await requireAdmin())) return; 
    await this.carregarDisciplinasNoSelect();
    this.bindAcoes();
  },

  bindAcoes() {
    document.getElementById("btnCarregarAssuntos").addEventListener("click", async () => {
      await this.carregarAssuntosDaDisciplina();
    });

    document.getElementById("formCriarAssunto").addEventListener("submit", async (e) => {
      e.preventDefault();
      await this.criarAssunto();
    });
  },

  async carregarDisciplinasNoSelect() {
    const select = document.getElementById("disciplinaSelect");
    const msg = document.getElementById("msgDisciplina");
    msg.innerHTML = "Carregando disciplinas...";

    try {
      // ✅ com token (admin)
      const disciplinas = await apiGetAuth("/disciplinas");

      if (!disciplinas || disciplinas.length === 0) {
        select.innerHTML = "";
        msg.innerHTML = "Nenhuma disciplina cadastrada.";
        return;
      }
      select.innerHTML = disciplinas
        .map(d => `<option value="${d.id}">${esc(d.nome)} (id=${d.id})</option>`)
        .join("");
      msg.innerHTML = "✅ Disciplinas carregadas.";
    } catch (err) {
      msg.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
    }
  },

  async carregarAssuntosDaDisciplina() {
    const disciplinaId = document.getElementById("disciplinaSelect").value;
    const el = document.getElementById("listaAssuntos");
    el.innerHTML = "Carregando...";

    try {
      // ✅ endpoint correto + com token
      const assuntos = await apiGetAuth(`/disciplinas/${disciplinaId}/assuntos`);

      if (!assuntos || assuntos.length === 0) {
        el.innerHTML = "<p>Nenhum assunto cadastrado para esta disciplina.</p>";
        return;
      }

      el.innerHTML = `
        <div class="list">
          ${assuntos.map(a => `
            <div class="disciplina">
              <b>${esc(a.nome)}</b><br/>
              <span style="opacity:.8">id=${esc(a.id)} • ativo=${esc(a.ativo)}</span>
              ${a.descricao ? `<div style="margin-top:8px; opacity:.85">${esc(a.descricao)}</div>` : ""}
            </div>
          `).join("")}
        </div>
      `;
    } catch (err) {
      el.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
    }
  },

  async criarAssunto() {
    const disciplinaId = Number(document.getElementById("disciplinaSelect").value);
    const nome = document.getElementById("assuntoNome").value.trim();
    const descricao = document.getElementById("assuntoDescricao").value.trim() || null;
    const ativo = document.getElementById("assuntoAtivo").value === "true";
    const msg = document.getElementById("msgCriarAssunto");

    if (!disciplinaId) {
      msg.innerHTML = "⚠️ Selecione uma disciplina.";
      return;
    }
    if (!nome) {
      msg.innerHTML = "⚠️ Informe o nome do assunto.";
      return;
    }

    msg.innerHTML = "Salvando...";

    try {
      // ✅ com token
      await apiPostAuth("/assuntos", {
        disciplina_id: disciplinaId,
        nome,
        descricao,
        ativo
      });

      msg.innerHTML = "✅ Assunto criado. Atualizando lista...";
      await this.carregarAssuntosDaDisciplina();

      // limpa campos
      document.getElementById("assuntoNome").value = "";
      document.getElementById("assuntoDescricao").value = "";

    } catch (err) {
      msg.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
    }
  }
};

const AdminAulaConteudo = {
  pastaTeoriaId: null,
  aulaId: null,
  bateriaId: null,

  async init() {
    if (!(await requireAdmin())) return;
    this.bindUI();
    await this.carregarDisciplinas();
  },

  bindUI() {
    document.getElementById("disciplinaSelect")?.addEventListener("change", async () => {
      await this.carregarAssuntos();
    });

    document.getElementById("assuntoSelect")?.addEventListener("change", async () => {
      await this.carregarAulasDaTeoria();
    });

    document.getElementById("btnCarregarTudo")?.addEventListener("click", async () => {
      await this.carregarTudo();
    });

    document.getElementById("materialTipo")?.addEventListener("change", () => {
      const t = document.getElementById("materialTipo")?.value;
      const boxTexto = document.getElementById("materialBoxTexto");
      const boxPdf = document.getElementById("materialBoxPdf");
      if (boxTexto) boxTexto.style.display = (t === "TEXTO") ? "block" : "none";
      if (boxPdf) boxPdf.style.display = (t === "PDF") ? "block" : "none";
    });

    document.getElementById("formVideo")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      await this.salvarVideoPadrao();
    });

    document.getElementById("formMaterial")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      await this.salvarMaterialPadrao();
    });

    document.getElementById("formBateria")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      await this.salvarBateriaPadrao();
    });

    document.getElementById("btnGerar10Questoes")?.addEventListener("click", async () => {
      await this.gerar10Questoes();
    });

    document.getElementById("btnVerQuestoes")?.addEventListener("click", async () => {
      await this.verQuestoes();
    });
  },

  async carregarDisciplinas() {
    const msg = document.getElementById("msgSelecao");
    if (msg) msg.innerHTML = "Carregando disciplinas...";

    try {
      const disciplinas = await apiGetSafe("/disciplinas");

      const sel = document.getElementById("disciplinaSelect");
      if (!disciplinas || disciplinas.length === 0) {
        if (sel) sel.innerHTML = "";
        if (msg) msg.innerHTML = "Nenhuma disciplina cadastrada.";
        return;
      }

      if (sel) {
        sel.innerHTML = disciplinas
          .map(d => `<option value="${d.id}">${esc(d.nome)} (id=${d.id})</option>`)
          .join("");
      }

      if (msg) msg.innerHTML = "✅ Disciplinas carregadas.";
      await this.carregarAssuntos();
    } catch (err) {
      if (msg) msg.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
    }
  },

  async carregarAssuntos() {
    this.pastaTeoriaId = null;
    this.aulaId = null;
    this.bateriaId = null;

    // limpa selects/boxes
    document.getElementById("aulaSelect") && (document.getElementById("aulaSelect").innerHTML = "");
    document.getElementById("videosBox") && (document.getElementById("videosBox").innerHTML = "Clique em “Carregar conteúdo”.");
    document.getElementById("materiaisBox") && (document.getElementById("materiaisBox").innerHTML = "Clique em “Carregar conteúdo”.");
    document.getElementById("bateriasBox") && (document.getElementById("bateriasBox").innerHTML = "Clique em “Carregar conteúdo”.");
    document.getElementById("questoesBox") && (document.getElementById("questoesBox").innerHTML = "");

    const disciplinaId = document.getElementById("disciplinaSelect")?.value;
    const msg = document.getElementById("msgSelecao");
    if (msg) msg.innerHTML = "Carregando assuntos...";

    try {
      const assuntos = await apiGetSafe(`/disciplinas/${disciplinaId}/assuntos`);

      const selAss = document.getElementById("assuntoSelect");
      if (!assuntos || assuntos.length === 0) {
        if (selAss) selAss.innerHTML = "";
        if (msg) msg.innerHTML = "Nenhum assunto cadastrado para esta disciplina.";
        return;
      }

      if (selAss) {
        selAss.innerHTML = assuntos
          .map(a => `<option value="${a.id}">${esc(a.nome)} (id=${a.id})</option>`)
          .join("");
      }

      if (msg) msg.innerHTML = "✅ Assuntos carregados.";
      await this.carregarAulasDaTeoria();
    } catch (err) {
      if (msg) msg.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
    }
  },

  // ✅ AGORA: robusto para achar TEORIA
  async carregarAulasDaTeoria() {
    const msg = document.getElementById("msgSelecao");
    const assuntoId = document.getElementById("assuntoSelect")?.value;

    this.pastaTeoriaId = null;
    this.aulaId = null;
    this.bateriaId = null;

    if (msg) msg.innerHTML = "Buscando pasta TEORIA e aulas...";

    try {
      const pastas = await apiGetSafe(`/assuntos/${assuntoId}/pastas`);

      const teoria = (pastas || []).find(p =>
        String(p?.tipo || "").toUpperCase() === "TEORIA" ||
        String(p?.nome || p?.titulo || "").toLowerCase().includes("teoria")
      );

      const selAula = document.getElementById("aulaSelect");

      if (!teoria) {
        if (msg) msg.innerHTML = "❌ Não encontrei a pasta TEORIA (ex.: 'Teoria e Questões') para este assunto.";
        if (selAula) selAula.innerHTML = "";
        return;
      }

      this.pastaTeoriaId = teoria.id;

      const aulas = await apiGetSafe(`/pastas/${this.pastaTeoriaId}/aulas`);

      if (selAula) {
        selAula.innerHTML = (aulas && aulas.length > 0)
          ? aulas.map(a => `<option value="${a.id}">${esc(a.titulo || a.nome || "Sem título")} (aula_id=${a.id})</option>`).join("")
          : "";
      }

      if (msg) msg.innerHTML = `✅ TEORIA encontrada (pasta_id=${esc(this.pastaTeoriaId)}). Aulas carregadas.`;

    } catch (err) {
      if (msg) msg.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
    }
  },

  async carregarTudo() {
    const msg = document.getElementById("msgSelecao");
    this.aulaId = Number(document.getElementById("aulaSelect")?.value || 0);

    if (!this.aulaId) {
      if (msg) msg.innerHTML = "Selecione uma aula primeiro.";
      return;
    }

    if (msg) msg.innerHTML = `Carregando conteúdo da aula_id=${esc(this.aulaId)}...`;
    await this.carregarVideos();
    await this.carregarMateriais();
    await this.carregarBaterias();
    if (msg) msg.innerHTML = `✅ Conteúdo carregado para aula_id=${esc(this.aulaId)}.`;
  },

  async carregarVideos() {
    const box = document.getElementById("videosBox");
    if (box) box.innerHTML = "Carregando...";

    try {
      const videos = await apiGetSafe(`/aulas/${this.aulaId}/videos`);
      if (!videos || videos.length === 0) {
        if (box) box.innerHTML = "<p>Nenhum vídeo cadastrado.</p>";
        return;
      }

      const v = videos[0];
      if (box) {
        box.innerHTML = `
          <div class="disciplina">
            <b>${esc(v.titulo || "Vídeo")}</b><br/>
            <span style="opacity:.8">video_id=${esc(v.id)} • ordem=${esc(v.ordem)} • ativo=${esc(v.ativo)}</span>
            <div style="margin-top:8px;"><a href="${esc(v.url)}" target="_blank">${esc(v.url)}</a></div>
          </div>
        `;
      }
    } catch (err) {
      if (box) box.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
    }
  },

  async salvarVideoPadrao() {
    const msg = document.getElementById("msgVideo");
    if (!this.aulaId) {
      if (msg) msg.innerHTML = "Selecione uma aula e clique em Carregar conteúdo.";
      return;
    }

    const url = (document.getElementById("videoUrl")?.value || "").trim();
    if (!url) {
      if (msg) msg.innerHTML = "Informe a URL do vídeo.";
      return;
    }

    if (msg) msg.innerHTML = "Salvando...";

    try {
      // ✅ não depende de videoTitulo (não existe no seu HTML)
      const titulo = "Vídeo da aula";
      await apiPost("/videos", { aula_id: this.aulaId, titulo, url, ordem: 1, ativo: true });

      if (msg) msg.innerHTML = "✅ Vídeo salvo (ordem 1).";
      await this.carregarVideos();
    } catch (err) {
      if (msg) msg.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
    }
  },

  async carregarMateriais() {
    const box = document.getElementById("materiaisBox");
    if (box) box.innerHTML = "Carregando...";

    try {
      const mats = await apiGetSafe(`/aulas/${this.aulaId}/materiais`);
      if (!mats || mats.length === 0) {
        if (box) box.innerHTML = "<p>Nenhum material cadastrado.</p>";
        return;
      }

      const m = mats[0];
      if (box) {
        box.innerHTML = `
          <div class="disciplina">
            <b>${esc(m.titulo || "Material")} • ${esc(m.tipo)}</b><br/>
            <span style="opacity:.8">material_id=${esc(m.id)} • ativo=${esc(m.ativo)}</span>
            ${m.url ? `<div style="margin-top:8px;"><a href="${esc(m.url)}" target="_blank">${esc(m.url)}</a></div>` : ""}
          </div>
        `;
      }
    } catch (err) {
      if (box) box.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
    }
  },

  async salvarMaterialPadrao() {
    const msg = document.getElementById("msgMaterial");
    if (!this.aulaId) {
      if (msg) msg.innerHTML = "Selecione uma aula e clique em Carregar conteúdo.";
      return;
    }

    const tipo = document.getElementById("materialTipo")?.value;
    const titulo = (document.getElementById("materialTitulo")?.value || "").trim() || "Material da aula";
    const conteudo = (document.getElementById("materialConteudo")?.value || "").trim();
    const url = (document.getElementById("materialUrl")?.value || "").trim();

    if (msg) msg.innerHTML = "Salvando...";

    try {
      if (tipo === "TEXTO") {
        if (!conteudo) throw new Error("Para material TEXTO, informe o conteúdo.");
        await apiPost("/materiais", { aula_id: this.aulaId, tipo: "TEXTO", titulo, conteudo, ativo: true });
      } else {
        if (!url) throw new Error("Para material PDF, informe a URL do PDF.");
        await apiPost("/materiais", { aula_id: this.aulaId, tipo: "PDF", titulo, url, ativo: true });
      }

      if (msg) msg.innerHTML = "✅ Material salvo.";
      await this.carregarMateriais();
    } catch (err) {
      if (msg) msg.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
    }
  },

  async carregarBaterias() {
    const box = document.getElementById("bateriasBox");
    if (box) box.innerHTML = "Carregando...";
    this.bateriaId = null;

    try {
      const bats = await apiGetSafe(`/aulas/${this.aulaId}/baterias`);
      if (!bats || bats.length === 0) {
        if (box) box.innerHTML = "<p>Nenhuma sprint (bateria) cadastrada.</p>";
        return;
      }

      const b = bats[0];
      this.bateriaId = b.id;

      if (box) {
        box.innerHTML = `
          <div class="disciplina">
            <b>${esc(b.titulo)}</b><br/>
            <span style="opacity:.8">bateria_id=${esc(b.id)} • ordem=${esc(b.ordem)} • ativo=${esc(b.ativo)}</span>
          </div>
        `;
      }
    } catch (err) {
      if (box) box.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
    }
  },

  async salvarBateriaPadrao() {
    const msg = document.getElementById("msgBateria");
    if (!this.aulaId) {
      if (msg) msg.innerHTML = "Selecione uma aula e clique em Carregar conteúdo.";
      return;
    }

    const titulo = (document.getElementById("bateriaNome")?.value || "").trim() || "Sprint 1 — Fixação";
    if (msg) msg.innerHTML = "Salvando...";

    try {
      const r = await apiPost("/baterias", { aula_id: this.aulaId, titulo, ordem: 1, ativo: true });
      if (r && r.id) this.bateriaId = r.id;
      await this.carregarBaterias();
      if (msg) msg.innerHTML = "✅ Sprint salva (ordem 1).";
    } catch (err) {
      if (msg) msg.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
    }
  },

  async gerar10Questoes() {
    const msg = document.getElementById("msgGerar10");
    if (!this.bateriaId) {
      if (msg) msg.innerHTML = "Crie/Carregue uma sprint primeiro.";
      return;
    }

    if (msg) msg.innerHTML = "Gerando...";
    try {
      await apiPost(`/baterias/${this.bateriaId}/gerar-10-questoes`, { tipo: "MULTIPLA" });
      if (msg) msg.innerHTML = "✅ 10 questões geradas.";
    } catch (err) {
      if (msg) msg.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
    }
  },

  async verQuestoes() {
    const box = document.getElementById("questoesBox");
    if (!this.bateriaId) {
      if (box) box.innerHTML = "Crie/Carregue uma sprint primeiro.";
      return;
    }

    if (box) box.innerHTML = "Carregando...";
    try {
      const qs = await apiGetSafe(`/baterias/${this.bateriaId}/questoes`);
      if (!qs || qs.length === 0) {
        if (box) box.innerHTML = "<p>Nenhuma questão cadastrada para esta sprint.</p>";
        return;
      }

      if (box) {
        box.innerHTML = `
          <div class="list">
            ${qs.map((q, i) => `
              <div class="disciplina">
                <b>Q${i + 1}</b> — ${esc(q.enunciado || q.pergunta || "Questão")}<br/>
                <span style="opacity:.8">questao_id=${esc(q.id)} • tipo=${esc(q.tipo)}</span>
              </div>
            `).join("")}
          </div>
        `;
      }
    } catch (err) {
      if (box) box.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
    }
  }
};

// ===============================
// ADMIN • PAGAMENTOS
// ===============================
const AdminPagamentos = {
  async init() {
    if (!(await requireAdmin())) return;

    const btnBuscar = document.getElementById("btnBuscar");
    const btnRevalidar = document.getElementById("btnRevalidar");

    if (btnBuscar) btnBuscar.addEventListener("click", () => this.buscar());
    if (btnRevalidar) btnRevalidar.addEventListener("click", () => this.revalidar());

    const msg = document.getElementById("msgBusca");
    if (msg) msg.innerHTML = "✅ Admin validado. Use a busca.";
  },

  async buscar() {
    const q = (document.getElementById("q")?.value || "").trim();
    const msg = document.getElementById("msgBusca");
    const box = document.getElementById("listaPagamentos");

    msg.innerHTML = "Buscando...";
    box.innerHTML = "";

    try {
      const data = await apiGetAuth(`/admin/pagamentos?q=${encodeURIComponent(q)}`);

      if (!data || data.length === 0) {
        msg.innerHTML = "Nenhuma compra encontrada.";
        box.innerHTML = "<p>Nenhum resultado.</p>";
        return;
      }

      msg.innerHTML = `✅ ${data.length} compra(s) encontrada(s).`;

      box.innerHTML = `
        <div class="list">
          ${data.map(p => `
            <div class="disciplina">
              <b>${esc(p.usuario_email)}</b><br/>
              <span style="opacity:.85">
                status=${esc(p.status)} • curso=${esc(p.curso_nome)}<br/>
                mp_payment_id=${esc(p.mp_payment_id || "-")}
              </span>
              <div style="margin-top:8px;">
                <button class="btn"
                  onclick="document.getElementById('mp_payment_id').value='${esc(p.mp_payment_id || "")}'">
                  Revalidar
                </button>
              </div>
            </div>
          `).join("")}
        </div>
      `;

    } catch (err) {
      msg.innerHTML = `<pre style="white-space:pre-wrap">${esc(err.message)}</pre>`;
    }
  },

  async revalidar() {
    const mp_payment_id = document.getElementById("mp_payment_id").value.trim();
    const msg = document.getElementById("msgRevalidar");

    msg.innerHTML = "Revalidando...";

    try {
      const r = await apiPostAuth("/admin/pagamentos/revalidar", { mp_payment_id });

      msg.innerHTML = `
        <div class="disciplina">
          Status: <b>${esc(r.status)}</b><br/>
          Liberou acesso: <b>${esc(r.liberou_acesso)}</b>
        </div>
      `;
    } catch (err) {
      msg.innerHTML = `<pre style="white-space:pre-wrap">${esc(err.message)}</pre>`;
    }
  }
};

console.log("[admin.js] carregou OK");

window.requireAdmin = requireAdmin;
window.AdminPagamentos = AdminPagamentos;

// ===============================
// ADMIN • ALUNOS
// ===============================

const AdminAlunos = {
  async init() {
    if (!(await requireAdmin())) return;

    const form = document.getElementById("formCriarAluno");
    const btnBuscar = document.getElementById("btnBuscarAlunos");

    if (form) {
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        await this.criar();
      });
    }

    if (btnBuscar) {
      btnBuscar.addEventListener("click", async () => {
        await this.buscar();
      });
    }
  },

  async criar() {
    const nome = (document.getElementById("alunoNome")?.value || "").trim();
    const email = (document.getElementById("alunoEmail")?.value || "").trim();
    const senha = (document.getElementById("alunoSenha")?.value || "").trim();
    const is_admin = !!document.getElementById("alunoIsAdmin")?.checked;

    const msg = document.getElementById("msgCriarAluno");
    if (msg) msg.innerHTML = "Criando usuário...";

    try {
      // ✅ aqui estava o erro: você não estava mandando is_admin
      const r = await apiPostAuth("/admin/alunos", { nome, email, senha, is_admin });

      if (msg) {
        msg.innerHTML = `
          <div class="disciplina">
            ✅ Usuário criado!<br/>
            id=<b>${esc(r.id)}</b> • ${esc(r.nome)} • ${esc(r.email)} • is_admin=${esc(r.is_admin)}
          </div>
        `;
      }

      // limpa
      const elNome = document.getElementById("alunoNome");
      const elEmail = document.getElementById("alunoEmail");
      const elSenha = document.getElementById("alunoSenha");
      const elIsAdmin = document.getElementById("alunoIsAdmin");

      if (elNome) elNome.value = "";
      if (elEmail) elEmail.value = "";
      if (elSenha) elSenha.value = "";
      if (elIsAdmin) elIsAdmin.checked = false;

    } catch (err) {
      if (msg) msg.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
    }
  },

  async buscar() {
    const q = (document.getElementById("qAluno")?.value || "").trim();
    const msg = document.getElementById("msgBuscarAlunos");
    const box = document.getElementById("listaAlunos");

    if (msg) msg.innerHTML = "Buscando...";
    if (box) box.innerHTML = "";

    try {
      const data = await apiGetAuth(`/admin/alunos${q ? `?q=${encodeURIComponent(q)}` : ""}`);

      if (!data || data.length === 0) {
        if (msg) msg.innerHTML = "Nenhum usuário encontrado.";
        if (box) box.innerHTML = "<p>Nenhum resultado.</p>";
        return;
      }

      if (msg) msg.innerHTML = `✅ ${data.length} usuário(s) encontrado(s).`;

      if (box) {
        box.innerHTML = `
          <div class="list">
            ${data.map(u => `
              <div class="disciplina">
                <b>#${esc(u.id)}</b> • ${esc(u.nome)}<br/>
                <span style="opacity:.9">${esc(u.email)} • ativo=${esc(u.ativo)} • is_admin=${esc(u.is_admin)}</span>
              </div>
            `).join("")}
          </div>
        `;
      }
    } catch (err) {
      if (msg) msg.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
      if (box) box.innerHTML = "";
    }
  }
};

// ===============================
// ADMIN • DISCIPLINAS
// ===============================
const AdminDisciplinas = {
  async init() {
    if (!(await requireAdmin())) return;

    const form = document.getElementById("formCriarDisciplina");
    const btnBuscar = document.getElementById("btnBuscarDisciplinas");
    const btnListarTudo = document.getElementById("btnListarTudo");

    if (form) {
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        await this.criar();
      });
    }

    if (btnBuscar) {
      btnBuscar.addEventListener("click", async (e) => {
        e.preventDefault();
        await this.buscar();
      });
    }

    if (btnListarTudo) {
      btnListarTudo.addEventListener("click", async (e) => {
        e.preventDefault();
        document.getElementById("qDisciplina").value = "";
        await this.buscar();
      });
    }

    // opcional: listar ao abrir
    await this.buscar();
  },

  async criar() {
    const nome = (document.getElementById("disciplinaNome").value || "").trim();
    const ativo = !!document.getElementById("disciplinaAtivo").checked;
    const msg = document.getElementById("msgCriarDisciplina");

    msg.innerHTML = "Salvando disciplina...";

    try {
      if (!nome) throw new Error("Informe o nome da disciplina.");

      // ✅ Rotas SEM /admin, conforme seu Swagger
      const r = await apiPostAuth("/disciplinas", { nome, ativo });

      msg.innerHTML = `
        <div class="disciplina">
          ✅ Disciplina criada!<br/>
          id=<b>${esc(r.id)}</b> • ${esc(r.nome)} • ativo=${esc(r.ativo)}
        </div>
      `;

      document.getElementById("disciplinaNome").value = "";
      document.getElementById("disciplinaAtivo").checked = true;

      // Atualiza lista
      await this.buscar();

    } catch (err) {
      msg.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
    }
  },

  async buscar() {
    const q = (document.getElementById("qDisciplina").value || "").trim().toLowerCase();
    const msg = document.getElementById("msgBuscarDisciplinas");
    const box = document.getElementById("listaDisciplinas");

    msg.innerHTML = "Buscando...";
    box.innerHTML = "";

    try {
      // Swagger: GET /disciplinas (sem filtro)
      // Se quiser filtro, filtramos no front mesmo
      const data = await apiGetAuth("/disciplinas");

      const lista = (data || []).filter(d => {
        if (!q) return true;
        return String(d.nome || "").toLowerCase().includes(q);
      });

      if (lista.length === 0) {
        msg.innerHTML = "Nenhuma disciplina encontrada.";
        box.innerHTML = "<p>Nenhum resultado.</p>";
        return;
      }

      msg.innerHTML = `✅ ${lista.length} disciplina(s) encontrada(s).`;

      box.innerHTML = `
        <div class="list">
          ${lista.map(d => `
            <div class="disciplina">
              <b>#${esc(d.id)}</b> • ${esc(d.nome)}<br/>
              <span style="opacity:.9">ativo=${esc(d.ativo)}</span>
            </div>
          `).join("")}
        </div>
      `;

    } catch (err) {
      msg.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
      box.innerHTML = "";
    }
  }
};

// ===============================
// ADMIN • AULAS
// ===============================
const AdminAulas = {
  disciplinaId: null,
  assuntoId: null,
  pastaTeoriaId: null,

  async init() {
    if (!(await requireAdmin())) return;

    await this.carregarDisciplinas();
    this.bind();
  },

  bind() {
    const selDisc = document.getElementById("disciplinaSelect");
    const selAss = document.getElementById("assuntoSelect");

    if (selDisc) {
      selDisc.addEventListener("change", async () => {
        this.disciplinaId = Number(selDisc.value || 0) || null;
        this.assuntoId = null;
        this.pastaTeoriaId = null;

        // limpa UI
        if (selAss) selAss.innerHTML = "";
        const pastaBox = document.getElementById("pastaTeoriaBox");
        if (pastaBox) pastaBox.innerHTML = "Selecione um assunto e clique em “Carregar pastas”.";
        const lista = document.getElementById("listaAulas");
        if (lista) lista.innerHTML = "Carregue as pastas do assunto para listar as aulas.";

        await this.carregarAssuntos();
      });
    }

    const btnPastas = document.getElementById("btnCarregarPastas");
    if (btnPastas) {
      btnPastas.addEventListener("click", async () => {
        await this.carregarPastasEIdentificarTeoria();
      });
    }

    const form = document.getElementById("formCriarAula");
    if (form) {
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        await this.criarAula();
      });
    }
  },

  async carregarDisciplinas() {
    const msg = document.getElementById("msgSelecao");
    const sel = document.getElementById("disciplinaSelect");

    if (msg) msg.innerHTML = "Carregando disciplinas...";
    try {
      const disciplinas = await apiGetSafe("/disciplinas");

      if (!disciplinas || disciplinas.length === 0) {
        if (sel) sel.innerHTML = "";
        if (msg) msg.innerHTML = "Nenhuma disciplina cadastrada.";
        return;
      }

      if (sel) {
        sel.innerHTML = disciplinas
          .map(d => `<option value="${d.id}">${esc(d.nome)} (id=${d.id})</option>`)
          .join("");
      }

      this.disciplinaId = Number(sel?.value || 0) || null;
      if (msg) msg.innerHTML = "✅ Disciplinas carregadas.";

      await this.carregarAssuntos();

    } catch (err) {
      if (msg) msg.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
    }
  },

  async carregarAssuntos() {
    const msg = document.getElementById("msgSelecao");
    const selAss = document.getElementById("assuntoSelect");

    if (!this.disciplinaId) {
      if (msg) msg.innerHTML = "Selecione uma disciplina.";
      return;
    }

    if (msg) msg.innerHTML = "Carregando assuntos...";
    try {
      // usa a rota que você já confirmou que funciona
      const assuntos = await apiGetSafe(`/disciplinas/${this.disciplinaId}/assuntos`);

      if (!assuntos || assuntos.length === 0) {
        if (selAss) selAss.innerHTML = "";
        if (msg) msg.innerHTML = "Nenhum assunto cadastrado para esta disciplina.";
        return;
      }

      if (selAss) {
        selAss.innerHTML = assuntos
          .map(a => `<option value="${a.id}">${esc(a.nome)} (id=${a.id})</option>`)
          .join("");
      }

      this.assuntoId = Number(selAss?.value || 0) || null;
      this.pastaTeoriaId = null;

      const pastaBox = document.getElementById("pastaTeoriaBox");
      if (pastaBox) pastaBox.innerHTML = "Selecione um assunto e clique em “Carregar pastas”.";

      const lista = document.getElementById("listaAulas");
      if (lista) lista.innerHTML = "Carregue as pastas do assunto para listar as aulas.";

      if (msg) msg.innerHTML = "✅ Assuntos carregados.";

    } catch (err) {
      if (msg) msg.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
    }
  },

  async carregarPastasEIdentificarTeoria() {
    const msg = document.getElementById("msgSelecao");
    const selAss = document.getElementById("assuntoSelect");
    const pastaBox = document.getElementById("pastaTeoriaBox");
    const lista = document.getElementById("listaAulas");

    this.assuntoId = Number(selAss?.value || 0) || null;
    this.pastaTeoriaId = null;

    if (!this.assuntoId) {
      if (msg) msg.innerHTML = "Selecione um assunto.";
      return;
    }

    if (msg) msg.innerHTML = "Carregando pastas do assunto...";
    if (pastaBox) pastaBox.innerHTML = "Carregando...";

    try {
      const pastas = await apiGetSafe(`/assuntos/${this.assuntoId}/pastas`);

      if (!pastas || pastas.length === 0) {
        if (pastaBox) pastaBox.innerHTML = "Nenhuma pasta encontrada para este assunto.";
        if (msg) msg.innerHTML = "Nenhuma pasta encontrada.";
        return;
      }

      // acha TEORIA (robusto: aceita "teoria" dentro do nome/título)
      const teoria = pastas.find(p => String(p.nome || p.titulo || "").toLowerCase().includes("teoria"));

      if (!teoria) {
        if (pastaBox) pastaBox.innerHTML = "⚠️ Não encontrei a pasta TEORIA para este assunto.";
        if (msg) msg.innerHTML = "⚠️ Pastas carregadas, mas não existe TEORIA.";
        return;
      }

      this.pastaTeoriaId = Number(teoria.id);

      if (pastaBox) {
        const nome = teoria.nome || teoria.titulo || "TEORIA";
        pastaBox.innerHTML = `
          <div class="disciplina">
            ✅ Pasta TEORIA encontrada:<br/>
            <b>${esc(nome)}</b> • pasta_id=<b>${esc(teoria.id)}</b>
          </div>
        `;
      }

      if (msg) msg.innerHTML = "✅ Pastas carregadas.";
      if (lista) lista.innerHTML = "Carregando aulas da TEORIA...";

      await this.listarAulasTeoria();

    } catch (err) {
      if (pastaBox) pastaBox.innerHTML = "";
      if (lista) lista.innerHTML = "";
      if (msg) msg.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
    }
  },

  async listarAulasTeoria() {
    const el = document.getElementById("listaAulas");

    if (!this.pastaTeoriaId) {
      if (el) el.innerHTML = "Carregue as pastas e encontre a TEORIA primeiro.";
      return;
    }

    if (el) el.innerHTML = "Carregando...";

    try {
      const aulas = await apiGetSafe(`/pastas/${this.pastaTeoriaId}/aulas`);

      if (!aulas || aulas.length === 0) {
        if (el) el.innerHTML = "<p>Nenhuma aula cadastrada na TEORIA.</p>";
        return;
      }

      if (el) {
        el.innerHTML = `
          <div class="list">
            ${aulas.map(a => `
              <div class="disciplina">
                <b>${esc(a.titulo || a.nome || "Sem título")}</b><br/>
                <span style="opacity:.85">
                  id=${esc(a.id)} • ordem=${esc(a.ordem)} • ativo=${esc(a.ativo)}
                </span>
                ${a.descricao ? `<div style="margin-top:8px; opacity:.85">${esc(a.descricao)}</div>` : ""}
              </div>
            `).join("")}
          </div>
        `;
      }

    } catch (err) {
      if (el) el.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
    }
  },

  async criarAula() {
    const msg = document.getElementById("msgCriarAula");

    if (!this.pastaTeoriaId) {
      if (msg) msg.innerHTML = "⚠️ Primeiro carregue as pastas do assunto (precisamos da TEORIA).";
      return;
    }

    const titulo = (document.getElementById("aulaTitulo").value || "").trim();
    const descricao = (document.getElementById("aulaDescricao").value || "").trim() || null;
    const ordem = Number(document.getElementById("aulaOrdem").value || 1) || 1;
    const ativo = document.getElementById("aulaAtivo").value === "true";

    if (!titulo) {
      if (msg) msg.innerHTML = "Informe o título da aula.";
      return;
    }

    if (msg) msg.innerHTML = "Salvando aula...";

    try {
      await apiPost("/aulas", {
        pasta_id: Number(this.pastaTeoriaId),
        titulo,
        descricao,
        ordem,
        ativo
      });

      if (msg) msg.innerHTML = "✅ Aula criada. Atualizando lista...";
      await this.listarAulasTeoria();

      // limpa
      document.getElementById("aulaTitulo").value = "";
      document.getElementById("aulaDescricao").value = "";
      document.getElementById("aulaOrdem").value = "1";
      document.getElementById("aulaAtivo").value = "true";

    } catch (err) {
      if (msg) msg.innerHTML = `<pre style="white-space:pre-wrap; color:#6B4F3F">${esc(err.message)}</pre>`;
    }
  }
};
