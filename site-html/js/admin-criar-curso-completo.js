(function () {
  let cursoAtual = null;
  let disciplinasDoCurso = [];

  const formCurso = document.getElementById("formCurso");
  const cursoNome = document.getElementById("cursoNome");
  const msgCurso = document.getElementById("msgCurso");

  const boxDisciplinas = document.getElementById("boxDisciplinas");
  const disciplinaNome = document.getElementById("disciplinaNome");
  const btnAdicionarDisciplina = document.getElementById("btnAdicionarDisciplina");
  const listaDisciplinasCurso = document.getElementById("listaDisciplinasCurso");

  const boxConteudo = document.getElementById("boxConteudo");
  let disciplinaAtualId = null;
  const cursoExistenteSelect = document.getElementById("cursoExistenteSelect");
  const btnUsarCursoExistente = document.getElementById("btnUsarCursoExistente");
  const btnEditarCurso = document.getElementById("btnEditarCurso");
  const btnDuplicarCurso = document.getElementById("btnDuplicarCurso");
  const btnExcluirCurso = document.getElementById("btnExcluirCurso");
  let assuntosDaDisciplina = [];
  
  const areaAssuntos = document.getElementById("areaAssuntos");
  const assuntoNome = document.getElementById("assuntoNome");
  const tituloDisciplinaSelecionada = document.getElementById("tituloDisciplinaSelecionada");
  const btnAdicionarAssunto = document.getElementById("btnAdicionarAssunto");
  const listaAssuntos = document.getElementById("listaAssuntos");
  const btnPublicarCurso =
    document.getElementById("btnPublicarCurso");
  const btnRetirarCursoVenda =
    document.getElementById("btnRetirarCursoVenda");
  let aulasDoAssunto = [];
  let pastaTeoriaAtual = null;
  let bateriaAtualId = null;
  let questoesDaBateria = [];
  let questaoEditandoId = null;
  let tipoQuestaoAtual = "MULTIPLA_5";

  const areaAulas = document.getElementById("areaAulas");
  const aulaTitulo = document.getElementById("aulaTitulo");
  const btnAdicionarAula = document.getElementById("btnAdicionarAula");
  const listaAulas = document.getElementById("listaAulas");

  const boxConfigPublicaCurso = document.getElementById("boxConfigPublicaCurso");
  const cursoDescricaoPublica = document.getElementById("cursoDescricaoPublica");
  const valor4Meses = document.getElementById("valor4Meses");
  const valor8Meses = document.getElementById("valor8Meses");
  const valor12Meses = document.getElementById("valor12Meses");
  const btnSalvarConfigPublicaCurso = document.getElementById("btnSalvarConfigPublicaCurso");
  const msgConfigPublicaCurso = document.getElementById("msgConfigPublicaCurso");
  const btnEditarConfigPublicaCurso = document.getElementById("btnEditarConfigPublicaCurso");

  const boxCopiarAssunto =
    document.getElementById("boxCopiarAssunto");
  const cursoDestinoAssuntoSelect =
    document.getElementById("cursoDestinoAssuntoSelect");
  const disciplinaDestinoAssuntoSelect =
    document.getElementById("disciplinaDestinoAssuntoSelect");
  const btnConfirmarCopiaAssunto =
    document.getElementById("btnConfirmarCopiaAssunto");
  const btnCancelarCopiaAssunto =
    document.getElementById("btnCancelarCopiaAssunto");
  const msgCopiarAssunto =
    document.getElementById("msgCopiarAssunto");
  let assuntoCopiandoId = null;
  let assuntoCopiandoNome = "";

  formCurso.addEventListener("submit", async (e) => {
    e.preventDefault();

    const nome = cursoNome.value.trim();

    if (!nome) {
      msgCurso.textContent = "Informe o nome do curso.";
      msgCurso.style.color = "#8a1f1f";
      return;
    }

    try {
      const curso = await apiPostAuth("/cursos", {
        nome,
        ativo: true
      });

      cursoAtual = curso;
      cursoAtual.publicado = false;
      atualizarBotoesPublicacaoCurso();

      boxConfigPublicaCurso.style.display = "block";
      cursoDescricaoPublica.value = "";
      valor4Meses.value = "";
      valor8Meses.value = "";
      valor12Meses.value = "";

      msgCurso.textContent = "Curso criado com sucesso!";
      msgCurso.style.color = "#2f5e46";

      boxDisciplinas.style.display = "block";
      boxConteudo.style.display = "block";

      cursoNome.disabled = false;
      cursoNome.value = "";

      await carregarCursosExistentes();
      cursoExistenteSelect.value = curso.id;

    } catch (err) {
        const msg = String(err.message || "");

        if (msg.includes("Já existe um curso com esse nome")) {
          msgCurso.textContent = "Já existe um curso com esse nome.";
        } else {
          msgCurso.textContent = "Não foi possível criar o curso.";
        }

        msgCurso.style.color = "#8a1f1f";
        console.error(err);
      }
  });

  btnAdicionarDisciplina.addEventListener("click", async (e) => {
    e.preventDefault();

    if (!cursoAtual) {
      alert("Crie o curso primeiro.");
      return;
    }

    const nome = disciplinaNome.value.trim();

    if (!nome) {
      alert("Informe o nome da disciplina.");
      return;
    }

    try {

        const proximaOrdem = disciplinasDoCurso.length + 1;

        const disciplina = await apiPostAuth(
            `/cursos/${cursoAtual.id}/disciplinas-proprias`,
            {
                curso_id: cursoAtual.id,
                nome,
                ativo: true,
                ordem: proximaOrdem
            }
        );

        disciplinasDoCurso.push(disciplina);

        disciplinaNome.value = "";

        renderizarDisciplinas();

    } catch (err) {

        alert("Erro ao adicionar disciplina: " + err.message);

        console.error("Erro completo:", err);
    }
  });

  function renderizarDisciplinas() {
    if (disciplinasDoCurso.length === 0) {
      listaDisciplinasCurso.innerHTML = "Nenhuma disciplina adicionada ainda.";
      return;
    }

    listaDisciplinasCurso.innerHTML = disciplinasDoCurso.map(d => `
      <div class="assunto">
        <div style="
          display:flex;
          justify-content:space-between;
          align-items:center;
          gap:10px;
          flex-wrap:wrap;
        ">
          <b>${d.nome}</b>

          <div style="display:flex; gap:10px; flex-wrap:wrap;">
            <button
            class="btn"
            type="button"
            onclick="trabalharNestaDisciplina(${d.id})"
          >
            Trabalhar nesta disciplina
          </button>

          <button
            class="btn"
            type="button"
            onclick="editarDisciplinaPropria(${d.id}, '${d.nome.replace(/'/g, "\\'")}')"
          >
            Editar nome
          </button>

          <button
            class="btn"
            type="button"
            onclick="copiarDisciplinaParaOutroCurso(${d.id}, '${d.nome.replace(/'/g, "\\'")}')"
          >
            Copiar disciplina
          </button>

          <button
            class="btn"
            type="button"
            onclick="excluirDisciplinaPropria(${d.id})"
          >
            Excluir
          </button>

          <button
            class="btn"
            type="button"
            onclick="moverDisciplina(${d.id}, -1)"
          >
            ↑
          </button>

          <button
            class="btn"
            type="button"
            onclick="moverDisciplina(${d.id}, 1)"
          >
            ↓
          </button>
          </div>
        </div>
      </div>
    `).join("");
  }

  async function carregarCursosExistentes() {
    try {
        const todosCursos = await apiGetAuth("/cursos");

        const cursos = (todosCursos || []).filter(
          curso => curso.ativo === true
        );

        if (!cursos || cursos.length === 0) {
        cursoExistenteSelect.innerHTML = `<option value="">Nenhum curso cadastrado</option>`;
        return;
        }

        cursoExistenteSelect.innerHTML = `
        <option value="">Selecione um curso existente</option>
        ${cursos.map(c => `
            <option value="${c.id}">${c.nome}</option>
        `).join("")}
        `;

    } catch (err) {
        cursoExistenteSelect.innerHTML = `<option value="">Erro ao carregar cursos</option>`;
        console.error(err);
    }
    }

    btnUsarCursoExistente.addEventListener("click", async () => {
    const cursoId = cursoExistenteSelect.value;

    if (!cursoId) {
        alert("Selecione um curso existente.");
        return;
    }

    const nomeCurso = cursoExistenteSelect.options[cursoExistenteSelect.selectedIndex].text;

    cursoAtual = {
        id: Number(cursoId),
        nome: nomeCurso,
        ativo: true
    };

    // Limpa o estado visual e interno do curso anteriormente selecionado
    disciplinaAtualId = null;
    assuntosDaDisciplina = [];
    aulasDoAssunto = [];
    pastaTeoriaAtual = null;
    aulaAtual = null;
    bateriaAtualId = null;
    questoesDaBateria = [];
    questaoEditandoId = null;

    limparAreaCopiaAssunto();

    // Recolhe a área de assuntos até que uma disciplina seja escolhida
    areaAssuntos.style.display = "none";

    tituloDisciplinaSelecionada.textContent =
      "Disciplina selecionada";

    listaAssuntos.innerHTML =
      "Selecione uma disciplina para visualizar seus assuntos.";

    // Fecha áreas internas que possam ter ficado abertas
    areaAulas.style.display = "none";
    areaConteudoAula.style.display = "none";

    listaAulas.innerHTML = "";
    boxConteudoAula.innerHTML = "";

    msgCurso.textContent = `Curso selecionado: ${nomeCurso}`;
    msgCurso.style.color = "#2f5e46";

    cursoNome.disabled = false;
    cursoNome.value = "";
    boxDisciplinas.style.display = "block";
    boxConteudo.style.display = "block";

    await carregarDisciplinasDoCurso();
    
    await carregarConfigPublicaCurso();

    setTimeout(() => {
      boxDisciplinas.scrollIntoView({
        behavior: "smooth",
        block: "start"
      });
    }, 100);

    });

    async function carregarDisciplinasDoCurso() {
    if (!cursoAtual) return;

    try {
        const disciplinas = await apiGetAuth(`/cursos/${cursoAtual.id}/disciplinas-proprias`);

        disciplinasDoCurso = disciplinas || [];

        renderizarDisciplinas();

    } catch (err) {
        console.error(err);
        alert("Erro ao carregar disciplinas do curso.");
    }
    }

    window.editarDisciplinaPropria = async function (disciplinaId, nomeAtual) {
      const novoNome = prompt("Editar nome da disciplina:", nomeAtual);

      if (!novoNome || !novoNome.trim()) return;

      try {
        const atualizada = await apiPutAuth(`/disciplinas-proprias/${disciplinaId}`, {
          nome: novoNome.trim(),
          ativo: true
        });

        disciplinasDoCurso = disciplinasDoCurso.map(d =>
          d.id === disciplinaId ? atualizada : d
        );

        renderizarDisciplinas();

      } catch (err) {
        console.error(err);
        alert("Erro ao editar disciplina.");
      }
    };

    window.copiarDisciplinaParaOutroCurso = async function (
      disciplinaId,
      nomeDisciplina
    ) {
      const todosCursos = await apiGetAuth("/cursos");

      const cursosDestino = (todosCursos || []).filter(
        curso =>
          curso.ativo === true &&
          curso.id !== Number(cursoAtual?.id)
      );

      if (cursosDestino.length === 0) {
        alert("Não há outro curso disponível para receber esta disciplina.");
        return;
      }

      const opcoes = cursosDestino
        .map(
          curso =>
            `${curso.id} - ${curso.nome}`
        )
        .join("\n");

      const cursoDestinoId = prompt(
        "Informe o ID do curso de destino:\n\n" +
        opcoes
      );

      if (!cursoDestinoId) {
        return;
      }

      const cursoDestino = cursosDestino.find(
        curso =>
          curso.id === Number(cursoDestinoId)
      );

      if (!cursoDestino) {
        alert("Curso de destino inválido.");
        return;
      }

      const ok = confirm(
        "Deseja copiar esta disciplina?\n\n" +
        `Disciplina: ${nomeDisciplina}\n` +
        `Curso de destino: ${cursoDestino.nome}\n\n` +
        "Todo o conteúdo da disciplina será duplicado."
      );

      if (!ok) return;

      try {
        const resultado = await apiPostAuth(
          `/admin/disciplinas/${disciplinaId}/copiar`,
          {
            curso_destino_id: cursoDestino.id
          }
        );

        alert(
          "Disciplina copiada com sucesso!\n\n" +
          `Disciplina: ${resultado.nova_disciplina_nome}\n` +
          `Curso de destino: ${resultado.curso_destino_nome}`
        );

      } catch (err) {
        console.error(err);

        alert(
          "Erro ao copiar disciplina: " +
          err.message
        );
      }
    };

    window.excluirDisciplinaPropria = async function (disciplinaId) {
      const ok = confirm("Excluir esta disciplina deste curso?");

      if (!ok) return;

      try {
        await apiDeleteAuth(`/disciplinas-proprias/${disciplinaId}`);

        disciplinasDoCurso = disciplinasDoCurso.filter(d => d.id !== disciplinaId);

        renderizarDisciplinas();

      } catch (err) {
        console.error(err);
        alert("Erro ao excluir disciplina.");
      }
    };

    function renderizarAssuntos() {

      if (assuntosDaDisciplina.length === 0) {
        listaAssuntos.innerHTML = "Nenhum assunto criado ainda.";
        return;
      }

      listaAssuntos.innerHTML = assuntosDaDisciplina.map(a => `
        <div class="assunto">

          <div style="
            display:flex;
            justify-content:space-between;
            align-items:center;
            gap:10px;
            flex-wrap:wrap;
          ">

            <div>
              <b>${a.nome}</b>
              ${
                a.descricao
                  ? `<div style="opacity:.8; margin-top:4px;">${a.descricao}</div>`
                  : ""
              }
            </div>

            <div style="display:flex; gap:10px; flex-wrap:wrap;">

              <button
                class="btn"
                type="button"
                onclick="abrirAulasDoAssunto(${a.id})"
              >
                Aulas
              </button>

              <button
                class="btn"
                type="button"
                onclick="editarAssuntoProprio(${a.id}, '${a.nome.replace(/'/g, "\\'")}', \`${(a.descricao || "").replace(/`/g, "\\`")}\`)"
              >
                Editar nome do assunto
              </button>

              <button
                class="btn"
                type="button"
                onclick="abrirCopiaAssunto(
                  ${a.id},
                  '${a.nome.replace(/'/g, "\\'")}'
                )"
              >
                Copiar assunto
              </button>

              <button
                class="btn"
                type="button"
                onclick="excluirAssuntoProprio(${a.id})"
              >
                Excluir
              </button>

              <button
                class="btn"
                type="button"
                onclick="moverAssunto(${a.id}, -1)"
              >
                ↑
              </button>

              <button
                class="btn"
                type="button"
                onclick="moverAssunto(${a.id}, 1)"
              >
                ↓
              </button>

            </div>

          </div>

        </div>
      `).join("");
    }

    async function carregarAssuntosDaDisciplina(disciplinaId) {

      try {

        const assuntos = await apiGetAuth(
          `/disciplinas-proprias/${disciplinaId}/assuntos-proprios`
        );

        assuntosDaDisciplina = assuntos || [];

        renderizarAssuntos();

      } catch (err) {
        console.error(err);
        alert("Erro ao carregar assuntos.");
      }
    }

    btnAdicionarAssunto.addEventListener("click", async () => {

      const disciplinaId = disciplinaAtualId;

      if (!disciplinaId) {
        alert("Selecione uma disciplina.");
        return;
      }

      const nome = assuntoNome.value.trim();

      if (!nome) {
        alert("Informe o nome do assunto.");
        return;
      }

      try {

        const proximaOrdem = assuntosDaDisciplina.length + 1;

        const assunto = await apiPostAuth(
          `/disciplinas-proprias/${disciplinaId}/assuntos-proprios`,
          {
            curso_disciplina_propria_id: Number(disciplinaId),
            nome,
            descricao: null,
            ativo: true,
            ordem: proximaOrdem
          }
        );

        assuntosDaDisciplina.push(assunto);

        assuntoNome.value = "";

        renderizarAssuntos();

      } catch (err) {
        console.error(err);
        alert("Erro ao adicionar assunto.");
      }
    });

    window.editarAssuntoProprio = async function (
      assuntoId,
      nomeAtual,
      descricaoAtual
    ) {

      const novoNome = prompt(
        "Editar nome do assunto:",
        nomeAtual
      );

      if (!novoNome || !novoNome.trim()) return;

      try {

        const atualizado = await apiPutAuth(
          `/assuntos-proprios/${assuntoId}`,
          {
            nome: novoNome.trim(),
            descricao: descricaoAtual,
            ativo: true
          }
        );

        assuntosDaDisciplina = assuntosDaDisciplina.map(a =>
          a.id === assuntoId ? atualizado : a
        );

        renderizarAssuntos();

      } catch (err) {
        console.error(err);
        alert("Erro ao editar assunto.");
      }
    };

    function limparAreaCopiaAssunto() {
      assuntoCopiandoId = null;
      assuntoCopiandoNome = "";

      if (cursoDestinoAssuntoSelect) {
        cursoDestinoAssuntoSelect.value = "";
      }

      if (disciplinaDestinoAssuntoSelect) {
        disciplinaDestinoAssuntoSelect.innerHTML =
          `<option value="">Selecione primeiro o curso</option>`;

        disciplinaDestinoAssuntoSelect.disabled = true;
      }

      if (msgCopiarAssunto) {
        msgCopiarAssunto.textContent = "";
      }

      if (boxCopiarAssunto) {
        boxCopiarAssunto.style.display = "none";
      }
    }

    window.abrirCopiaAssunto = async function (
      assuntoId,
      nomeAssunto
    ) {
      assuntoCopiandoId = assuntoId;
      assuntoCopiandoNome = nomeAssunto;

      boxCopiarAssunto.style.display = "block";

      msgCopiarAssunto.textContent =
        `Assunto selecionado: ${nomeAssunto}`;

      msgCopiarAssunto.style.color = "#2f5e46";

      cursoDestinoAssuntoSelect.innerHTML =
        `<option value="">Carregando cursos...</option>`;

      disciplinaDestinoAssuntoSelect.innerHTML =
        `<option value="">Selecione primeiro o curso</option>`;

      disciplinaDestinoAssuntoSelect.disabled = true;

      try {
        const cursos = await apiGetAuth("/cursos");

        const cursosAtivos = (cursos || []).filter(
          curso => curso.ativo === true
        );

        cursoDestinoAssuntoSelect.innerHTML =
          `<option value="">Selecione o curso de destino</option>`;

        cursosAtivos.forEach(curso => {
          const option = document.createElement("option");

          option.value = curso.id;
          option.textContent = curso.nome;

          cursoDestinoAssuntoSelect.appendChild(option);
        });

        boxCopiarAssunto.scrollIntoView({
          behavior: "smooth",
          block: "start"
        });

      } catch (err) {
        console.error(err);

        msgCopiarAssunto.textContent =
          "Erro ao carregar os cursos.";

        msgCopiarAssunto.style.color = "#8a1f1f";
      }
    };

    cursoDestinoAssuntoSelect.addEventListener(
      "change",
      async () => {
        const cursoDestinoId =
          cursoDestinoAssuntoSelect.value;

        disciplinaDestinoAssuntoSelect.innerHTML = "";

        if (!cursoDestinoId) {
          disciplinaDestinoAssuntoSelect.disabled = true;

          disciplinaDestinoAssuntoSelect.innerHTML =
            `<option value="">Selecione primeiro o curso</option>`;

          return;
        }

        disciplinaDestinoAssuntoSelect.disabled = true;

        disciplinaDestinoAssuntoSelect.innerHTML =
          `<option value="">Carregando disciplinas...</option>`;

        try {
          const disciplinas = await apiGetAuth(
            `/cursos/${cursoDestinoId}/disciplinas-proprias`
          );

          disciplinaDestinoAssuntoSelect.innerHTML =
            `<option value="">Selecione a disciplina de destino</option>`;

          const disciplinasDisponiveis =
            (disciplinas || []).filter(
              disciplina =>
                disciplina.id !== Number(disciplinaAtualId)
            );

          disciplinasDisponiveis.forEach(disciplina => {
            const option =
              document.createElement("option");

            option.value = disciplina.id;
            option.textContent = disciplina.nome;

            disciplinaDestinoAssuntoSelect.appendChild(
              option
            );
          });

          disciplinaDestinoAssuntoSelect.disabled = false;

        } catch (err) {
          console.error(err);

          disciplinaDestinoAssuntoSelect.innerHTML =
            `<option value="">Erro ao carregar disciplinas</option>`;
        }
      }
    );

    window.excluirAssuntoProprio = async function (assuntoId) {

      const ok = confirm("Excluir este assunto?");

      if (!ok) return;

      try {

        await apiDeleteAuth(`/assuntos-proprios/${assuntoId}`);

        assuntosDaDisciplina = assuntosDaDisciplina.filter(
          a => a.id !== assuntoId
        );

        renderizarAssuntos();

      } catch (err) {
        console.error(err);
        alert("Erro ao excluir assunto.");
      }
    };

    function renderizarAulas() {
      if (aulasDoAssunto.length === 0) {
        listaAulas.innerHTML = "Nenhuma aula criada ainda.";
        return;
      }

      listaAulas.innerHTML = aulasDoAssunto.map(a => `
        <div class="assunto">
          <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap;">
            <b>${a.titulo}</b>

            <div style="display:flex; gap:10px; flex-wrap:wrap;">

              <button
                class="btn"
                type="button"
                onclick="abrirTeoriaAula(${a.id}, '${a.titulo.replace(/'/g, "\\'")}')"
              >
                📄 Teoria em Texto
              </button>

              <button
                class="btn"
                type="button"
                onclick="abrirVideoAula(${a.id}, '${a.titulo.replace(/'/g, "\\'")}')"
              >
                🎥 Resumo em Vídeo
              </button>

              <button
                class="btn"
                type="button"
                onclick="abrirQuestoesAula(${a.id}, '${a.titulo.replace(/'/g, "\\'")}')"
              >
                🏁 Questões
              </button>

              <button class="btn" type="button" onclick="editarAula(${a.id}, '${a.titulo.replace(/'/g, "\\'")}')">
                Editar
              </button>

              <button class="btn" type="button" onclick="excluirAula(${a.id})">
                Excluir
              </button>
            </div>
          </div>
        </div>
      `).join("");
    }

    window.abrirAulasDoAssunto = async function (assuntoId) {
      try {
        pastaTeoriaAtual = await apiGetAuth(`/assuntos-proprios/${assuntoId}/pasta-teoria`);

        const assunto = assuntosDaDisciplina.find(a => a.id === assuntoId);

        if (assunto) {
          document.getElementById("tituloAreaAulas").textContent = assunto.nome;
        }

        let aulas = await apiGetAuth(`/pastas/${pastaTeoriaAtual.id}/aulas`);

        if (!aulas || aulas.length === 0) {
          const aulaCriada = await apiPostAuth(`/pastas/${pastaTeoriaAtual.id}/aulas`, {
            pasta_id: pastaTeoriaAtual.id,
            titulo: "Aula principal",
            descricao: null,
            ordem: 1,
            ativo: true
          });

          aulas = [aulaCriada];
        }

        aulasDoAssunto = aulas;

        const aula = aulasDoAssunto[0];

        aulaAtual = {
          id: aula.id,
          titulo: aula.titulo
        };

        areaAulas.style.display = "block";

        setTimeout(() => {
          areaAulas.scrollIntoView({
            behavior: "smooth",
            block: "start"
          });
        }, 100);

        document.getElementById("boxCriacaoAula").style.display = "none";

        listaAulas.innerHTML = `
          <div class="assunto">
            <div style="display:flex; gap:10px; flex-wrap:wrap;">

              <button
                class="btn"
                type="button"
                onclick="abrirTeoriaAula(${aula.id}, '${aula.titulo.replace(/'/g, "\\'")}')"
              >
                📄 Teoria em Texto
              </button>

              <button
                class="btn"
                type="button"
                onclick="abrirVideoAula(${aula.id}, '${aula.titulo.replace(/'/g, "\\'")}')"
              >
                🎥 Resumo em Vídeo
              </button>

              <button
                class="btn"
                type="button"
                onclick="abrirQuestoesAula(${aula.id}, '${aula.titulo.replace(/'/g, "\\'")}')"
              >
                🏁 Questões
              </button>

            </div>
          </div>
        `;

      } catch (err) {
        console.error(err);
        alert("Erro ao carregar área de aulas do assunto.");
      }
    };

    btnAdicionarAula.addEventListener("click", async () => {
      if (!pastaTeoriaAtual) {
        alert("Selecione um assunto e clique em Aulas.");
        return;
      }

      const titulo = aulaTitulo.value.trim();

      if (!titulo) {
        alert("Informe o título da aula.");
        return;
      }

      try {
        const proximaOrdem = aulasDoAssunto.length + 1;

        const aula = await apiPostAuth(`/pastas/${pastaTeoriaAtual.id}/aulas`, {
          pasta_id: pastaTeoriaAtual.id,
          titulo,
          descricao: null,
          ordem: proximaOrdem,
          ativo: true
        });

        aulasDoAssunto.push(aula);
        aulaTitulo.value = "";
        renderizarAulas();

      } catch (err) {
        console.error(err);
        alert("Erro ao adicionar aula.");
      }
    });

    window.editarAula = async function (aulaId, tituloAtual) {
      const novoTitulo = prompt("Editar título da aula:", tituloAtual);

      if (!novoTitulo || !novoTitulo.trim()) return;

      try {
        const atualizada = await apiPutAuth(`/aulas/${aulaId}`, {
          titulo: novoTitulo.trim(),
          ativo: true
        });

        aulasDoAssunto = aulasDoAssunto.map(a =>
          a.id === aulaId ? atualizada : a
        );

        renderizarAulas();

      } catch (err) {
        console.error(err);
        alert("Erro ao editar aula.");
      }
    };

    window.excluirAula = async function (aulaId) {
      const ok = confirm("Excluir esta aula?");

      if (!ok) return;

      try {
        await apiDeleteAuth(`/aulas/${aulaId}`);

        aulasDoAssunto = aulasDoAssunto.filter(a => a.id !== aulaId);

        renderizarAulas();

      } catch (err) {
        console.error(err);
        alert("Erro ao excluir aula.");
      }
    };

    let aulaAtual = null;

    const areaConteudoAula = document.getElementById("areaConteudoAula");
    const tituloAulaSelecionada = document.getElementById("tituloAulaSelecionada");
    const boxConteudoAula = document.getElementById("boxConteudoAula");

    window.abrirConteudoAula = function (aulaId, titulo) {

      aulaAtual = {
        id: aulaId,
        titulo
      };

      areaConteudoAula.style.display = "block";

      setTimeout(() => {
        areaConteudoAula.scrollIntoView({
          behavior: "smooth",
          block: "start"
        });
      }, 100);

      boxConteudoAula.innerHTML = `
        Selecione uma opção da aula.
      `;
    };

    window.salvarTeoriaTexto = async function () {
      if (!aulaAtual) {
        alert("Selecione uma aula.");
        return;
      }

      const texto = document.getElementById("textoTeoriaAula").value.trim();

      if (!texto) {
        alert("Digite a teoria da aula.");
        return;
      }

      try {
        await apiPostAuth("/materiais", {
          aula_id: aulaAtual.id,
          tipo: "TEXTO",
          titulo: "Teoria em Texto",
          conteudo: texto,
          url: null,
          ordem: 1,
          ativo: true
        });

        alert("Teoria salva com sucesso.");

      } catch (err) {
        console.error(err);
        alert("Erro ao salvar teoria: " + err.message);
      }
    };

    window.salvarResumoVideo = async function () {

      if (!aulaAtual) {
        alert("Selecione uma aula.");
        return;
      }

      const url = document.getElementById("urlVideoAula").value.trim();

      if (!url) {
        alert("Informe a URL do vídeo.");
        return;
      }

      try {

        await apiPostAuth("/videos", {
          aula_id: aulaAtual.id,
          titulo: "Resumo em Vídeo",
          url: url,
          duracao_segundos: 0,
          transcricao: null,
          ordem: 1,
          ativo: true
        });

        alert("Vídeo salvo com sucesso.");

      } catch (err) {
        console.error(err);
        alert("Erro ao salvar vídeo: " + err.message);
      }
    };

    let bateriasDaAula = [];

    window.criarBateriaQuestoes = async function () {
      if (!aulaAtual) {
        alert("Selecione uma aula.");
        return;
      }

      const titulo = prompt("Informe o título da bateria de questões:");

      if (!titulo || !titulo.trim()) {
        alert("Informe o título da bateria.");
        return;
      }

      try {
        const ordem = bateriasDaAula.length + 1;

        const bateria = await apiPostAuth("/baterias", {
          aula_id: aulaAtual.id,
          titulo: titulo.trim(),
          ordem,
          ativo: true
        });

        if (bateria.erro) {
          alert(bateria.erro);
          await carregarBateriasDaAula();
          return;
        }

        bateriasDaAula.push(bateria);
        renderizarBaterias();

      } catch (err) {
        console.error(err);
        alert("Erro ao criar bateria.");
      }
    };

    async function carregarBateriasDaAula() {
      if (!aulaAtual) return;

      try {
        bateriasDaAula = await apiGetAuth(`/aulas/${aulaAtual.id}/baterias`);
        renderizarBaterias();
      } catch (err) {
        console.error(err);
        alert("Erro ao carregar baterias.");
      }
    }

    function renderizarBaterias() {
      const lista = document.getElementById("listaBateriasAula");

      console.log("Baterias renderizadas:", bateriasDaAula);

      if (!lista) return;

      if (!bateriasDaAula || bateriasDaAula.length === 0) {
        lista.innerHTML = "Nenhuma bateria criada ainda.";
        return;
      }

      lista.innerHTML = bateriasDaAula.map(b => {
        const qtd = b.questoes_count ?? b.total_questoes ?? b.questoes?.length ?? 0;

        let status = "";

        if (b.status === "CONCLUIDA") {
          status = `
            <span
              style="
                padding:4px 10px;
                border:1px solid #2f5e46;
                border-radius:999px;
              "
            >
              Concluída
            </span>
          `;
        }
        else if (qtd > 0) {
          status = `
            <span
              style="
                padding:4px 10px;
                border:1px solid #8a5a00;
                border-radius:999px;
              "
            >
              Em andamento
            </span>
          `;
        }

        return `
          <div class="assunto">
            <div style="display:flex; justify-content:space-between; gap:10px; align-items:center; flex-wrap:wrap;">
              <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
                <b>${b.titulo || `Bateria ${b.id}`}</b>
                ${status}
              </div>

              <div style="display:flex; gap:10px; flex-wrap:wrap;">
                <button class="btn" type="button" onclick="abrirQuestoesDaBateria(${b.id})">
                  Abrir / editar questões
                </button>

                <button
                  class="btn"
                  type="button"
                  onclick="editarTituloBateria(${b.id}, '${(b.titulo || "").replace(/'/g, "\\'")}', ${b.ordem})"
                >
                  Editar título
                </button>

                <button
                  class="btn"
                  type="button"
                  onclick="excluirBateria(${b.id})"
                >
                  Excluir
                </button>
              </div>
            </div>
          </div>
        `;
      }).join("");
      }

    window.abrirQuestoesDaBateria = async function (bateriaId) {
      bateriaAtualId = bateriaId;

      const bateria = bateriasDaAula.find(b => b.id === bateriaId);
      const tituloBateria = bateria ? bateria.titulo : "Questões";

      document.querySelector("#areaConteudoAula h3").textContent = tituloBateria;

      boxConteudoAula.innerHTML = `
        <div class="assunto">

          <div style="display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin-bottom:15px;">
            <button class="btn" type="button" onclick="voltarParaBaterias()">
              Voltar
            </button>

            <strong id="contadorQuestoesTopo">0/10 questões</strong>
          </div>

          <div id="boxFormularioQuestao">

            <label><b>Tipo da questão</b></label><br/>
            <select
              id="questaoTipoQuestao"
              onchange="renderizarCamposQuestaoCompleta()"
              style="width:100%; padding:12px; border:1px solid #ddd; border-radius:6px;"
            >
              <option value="MULTIPLA_5">Múltipla-escolha com 5 alternativas</option>
              <option value="MULTIPLA_4">Múltipla-escolha com 4 alternativas</option>
              <option value="CERTO_ERRADO">CERTO ou ERRADO</option>
            </select>

            <div id="camposQuestaoCompleta" style="margin-top:15px;"></div>

            <div style="margin-top:12px; display:flex; gap:10px; flex-wrap:wrap;">

              <button class="btn" type="button" onclick="criarQuestaoManual()">
                <span id="textoBotaoSalvarQuestao">Salvar questão</span>
              </button>

              <button
                id="btnConcluirBateria"
                class="btn"
                type="button"
                onclick="concluirBateriaQuestoes()"
                style="display:none;"
              >
                Concluir bateria de questões
              </button>

            </div>

          </div>

          <div id="listaQuestoesBateria" style="margin-top:15px;">
            Carregando questões...
          </div>
        </div>
      `;

      await carregarQuestoesDaBateria();
      renderizarCamposQuestaoCompleta();
    };

    async function carregarQuestoesDaBateria() {
      if (!bateriaAtualId) return;

      try {
        questoesDaBateria = await apiGetAuth(`/baterias/${bateriaAtualId}/questoes`);
        renderizarQuestoes();
      } catch (err) {
        console.error(err);
        alert("Erro ao carregar questões.");
      }
    }

    window.excluirBateria = async function (bateriaId) {
      const ok = confirm(
        "Deseja realmente excluir esta bateria?\n\n" +
        "Todas as questões vinculadas a ela também serão removidas."
      );

      if (!ok) return;

      try {
        await apiDeleteAuth(`/baterias/${bateriaId}`);

        alert("Bateria excluída com sucesso!");

        await carregarBateriasDaAula();

      } catch (err) {
        console.error(err);
        alert("Erro ao excluir bateria.");
      }
    };

    function valorMonetarioParaCents(valor) {
      const limpo = String(valor || "")
        .replace(/\./g, "")
        .replace(",", ".")
        .trim();

      const numero = Number(limpo);

      if (!numero || numero <= 0) {
        return 0;
      }

      return Math.round(numero * 100);
    }

    function centsParaValorMonetario(cents) {
      return (Number(cents || 0) / 100)
        .toFixed(2)
        .replace(".", ",");
    }

    function atualizarBotoesPublicacaoCurso() {
      if (!btnPublicarCurso || !btnRetirarCursoVenda) {
        console.error("Botões de publicação não encontrados no HTML.");
        return;
      }

      if (!cursoAtual || !cursoAtual.id) {
        btnPublicarCurso.style.display = "none";
        btnRetirarCursoVenda.style.display = "none";
        return;
      }

      if (cursoAtual.publicado === true) {
        btnPublicarCurso.style.display = "none";
        btnRetirarCursoVenda.style.display = "inline-block";
      } else {
        btnPublicarCurso.style.display = "inline-block";
        btnRetirarCursoVenda.style.display = "none";
      }
    }

    async function carregarConfigPublicaCurso() {
      if (!cursoAtual || !cursoAtual.id) return;

      boxConfigPublicaCurso.style.display = "block";
      msgConfigPublicaCurso.textContent =
        "Carregando descrição e valores...";
      msgConfigPublicaCurso.style.color = "";

      try {
        const dados = await apiGetAuth(
          `/admin/cursos/${cursoAtual.id}/config-publica`
        );

        cursoAtual.publicado = dados.publicado === true;

        cursoDescricaoPublica.value =
          dados.descricao_publica || "";

        const tempos = dados.tempos_acesso || [];

        const t4 = tempos.find(t => t.meses === 4);
        const t8 = tempos.find(t => t.meses === 8);
        const t12 = tempos.find(t => t.meses === 12);

        valor4Meses.value = t4
          ? centsParaValorMonetario(t4.valor_cents)
          : "";

        valor8Meses.value = t8
          ? centsParaValorMonetario(t8.valor_cents)
          : "";

        valor12Meses.value = t12
          ? centsParaValorMonetario(t12.valor_cents)
          : "";

        msgConfigPublicaCurso.textContent = "";

        bloquearConfigPublicaCurso();
        atualizarBotoesPublicacaoCurso();

      } catch (err) {
        console.error("Erro em carregarConfigPublicaCurso:", err);

        msgConfigPublicaCurso.textContent =
          "Erro ao carregar descrição e valores.";

        msgConfigPublicaCurso.style.color = "#8a1f1f";
      }
      
    }

    btnEditarConfigPublicaCurso.addEventListener("click", () => {
      liberarEdicaoConfigPublicaCurso();
      msgConfigPublicaCurso.textContent = "";
    });

    btnSalvarConfigPublicaCurso.addEventListener("click", async () => {
      if (!cursoAtual || !cursoAtual.id) {
        alert("Selecione ou crie um curso primeiro.");
        return;
      }

      const v4 = valorMonetarioParaCents(valor4Meses.value);
      const v8 = valorMonetarioParaCents(valor8Meses.value);
      const v12 = valorMonetarioParaCents(valor12Meses.value);

      if (!v4 || !v8 || !v12) {
        alert("Informe valores válidos para 4, 8 e 12 meses.");
        return;
      }

      try {
        msgConfigPublicaCurso.textContent = "Salvando...";
        msgConfigPublicaCurso.style.color = "";

        await apiPutAuth(
          `/admin/cursos/${cursoAtual.id}/config-publica`,
          {
            descricao_publica:
              cursoDescricaoPublica.value.trim(),

            tempos_acesso: [
              {
                meses: 4,
                valor_cents: v4
              },
              {
                meses: 8,
                valor_cents: v8
              },
              {
                meses: 12,
                valor_cents: v12
              }
            ]
          }
        );

        msgConfigPublicaCurso.textContent =
          "Descrição e valores salvos com sucesso.";

        msgConfigPublicaCurso.style.color = "#2f5e46";

        bloquearConfigPublicaCurso();

      } catch (err) {
        console.error(err);

        msgConfigPublicaCurso.textContent =
          "Erro ao salvar descrição e valores.";

        msgConfigPublicaCurso.style.color = "#8a1f1f";
      }
    });
    btnEditarConfigPublicaCurso.addEventListener("click", () => {
      liberarEdicaoConfigPublicaCurso();
      msgConfigPublicaCurso.textContent = "";
    });

    btnSalvarConfigPublicaCurso.addEventListener("click", async () => {
      if (!cursoAtual || !cursoAtual.id) {
        alert("Selecione ou crie um curso primeiro.");
        return;
      }

      const v4 = valorMonetarioParaCents(valor4Meses.value);
      const v8 = valorMonetarioParaCents(valor8Meses.value);
      const v12 = valorMonetarioParaCents(valor12Meses.value);

      if (!v4 || !v8 || !v12) {
        alert("Informe valores válidos para 4, 8 e 12 meses.");
        return;
      }

      try {
        msgConfigPublicaCurso.textContent = "Salvando...";
        msgConfigPublicaCurso.style.color = "";

        await apiPutAuth(`/admin/cursos/${cursoAtual.id}/config-publica`, {
          descricao_publica: cursoDescricaoPublica.value.trim(),
          tempos_acesso: [
            { meses: 4, valor_cents: v4 },
            { meses: 8, valor_cents: v8 },
            { meses: 12, valor_cents: v12 }
          ]
        });

        msgConfigPublicaCurso.textContent =
          "Descrição e valores salvos com sucesso.";

        msgConfigPublicaCurso.style.color = "#2f5e46";

        bloquearConfigPublicaCurso();

      } catch (err) {
        console.error(err);
        msgConfigPublicaCurso.textContent = "Erro ao salvar descrição e valores.";
        msgConfigPublicaCurso.style.color = "#8a1f1f";
      }
    });

    btnPublicarCurso.addEventListener("click", async () => {
      if (!cursoAtual || !cursoAtual.id) {
        alert("Selecione um curso primeiro.");
        return;
      }

      const ok = confirm(
        "Deseja publicar este curso?\n\n" +
        "Ele passará a aparecer na área de cursos disponíveis."
      );

      if (!ok) return;

      try {
        await apiPutAuth(
          `/admin/cursos/${cursoAtual.id}/publicar`,
          {}
        );

        cursoAtual.publicado = true;
        atualizarBotoesPublicacaoCurso();

        alert("Curso publicado com sucesso.");

      } catch (err) {
        console.error(err);

        alert(
          "Erro ao publicar curso: " +
          err.message
        );
      }
    });

    btnRetirarCursoVenda.addEventListener("click", async () => {
      if (!cursoAtual || !cursoAtual.id) {
        alert("Selecione um curso primeiro.");
        return;
      }

      const ok = confirm(
        "Deseja retirar este curso da venda?\n\n" +
        "Ele deixará de aparecer para novos alunos, " +
        "mas continuará disponível para edição no painel."
      );

      if (!ok) return;

      try {
        await apiPutAuth(
          `/admin/cursos/${cursoAtual.id}/retirar-venda`,
          {}
        );

        cursoAtual.publicado = false;
        atualizarBotoesPublicacaoCurso();

        alert("Curso retirado da venda com sucesso.");

      } catch (err) {
        console.error(err);

        alert(
          "Erro ao retirar curso da venda: " +
          err.message
        );
      }
    });

    btnConfirmarCopiaAssunto.addEventListener(
      "click",
      async () => {
        if (!assuntoCopiandoId) {
          alert("Nenhum assunto foi selecionado.");
          return;
        }

        const cursoDestinoId =
          cursoDestinoAssuntoSelect.value;

        const disciplinaDestinoId =
          disciplinaDestinoAssuntoSelect.value;

        if (!cursoDestinoId) {
          alert("Selecione o curso de destino.");
          return;
        }

        if (!disciplinaDestinoId) {
          alert("Selecione a disciplina de destino.");
          return;
        }

        const nomeCursoDestino =
          cursoDestinoAssuntoSelect.options[
            cursoDestinoAssuntoSelect.selectedIndex
          ].text;

        const nomeDisciplinaDestino =
          disciplinaDestinoAssuntoSelect.options[
            disciplinaDestinoAssuntoSelect.selectedIndex
          ].text;

        const ok = confirm(
          "Deseja copiar este assunto?\n\n" +
          `Assunto: ${assuntoCopiandoNome}\n` +
          `Curso de destino: ${nomeCursoDestino}\n` +
          `Disciplina de destino: ${nomeDisciplinaDestino}\n\n` +
          "Todo o conteúdo do assunto será duplicado."
        );

        if (!ok) return;

        try {
          msgCopiarAssunto.textContent =
            "Copiando assunto. Aguarde...";

          msgCopiarAssunto.style.color = "";

          const resultado = await apiPostAuth(
            `/admin/assuntos/${assuntoCopiandoId}/copiar`,
            {
              disciplina_destino_id:
                Number(disciplinaDestinoId)
            }
          );

          msgCopiarAssunto.textContent =
            `Assunto "${resultado.novo_assunto_nome}" copiado com sucesso.`;

          msgCopiarAssunto.style.color = "#2f5e46";

          alert(
            "Assunto copiado com sucesso!\n\n" +
            `Assunto: ${resultado.novo_assunto_nome}\n` +
            `Disciplina de destino: ${resultado.disciplina_destino_nome}`
          );

        } catch (err) {
          console.error(err);

          msgCopiarAssunto.textContent =
            "Erro ao copiar assunto.";

          msgCopiarAssunto.style.color = "#8a1f1f";
        }
      }
    );

    btnCancelarCopiaAssunto.addEventListener(
      "click",
      () => {
        assuntoCopiandoId = null;
        assuntoCopiandoNome = "";

        cursoDestinoAssuntoSelect.value = "";

        disciplinaDestinoAssuntoSelect.innerHTML =
          `<option value="">Selecione primeiro o curso</option>`;

        disciplinaDestinoAssuntoSelect.disabled = true;

        msgCopiarAssunto.textContent = "";

        boxCopiarAssunto.style.display = "none";
      }
    );

    function renderizarQuestoes() {
      const lista = document.getElementById("listaQuestoesBateria");
      if (!lista) return;

      const total = questoesDaBateria ? questoesDaBateria.length : 0;
      const contadorTopo = document.getElementById("contadorQuestoesTopo");

      if (contadorTopo) {
        contadorTopo.textContent = `${total}/10 questões`;
      }

      let html = "";

      if (!questoesDaBateria || questoesDaBateria.length === 0) {
        html += "Nenhuma questão criada ainda.";
        lista.innerHTML = html;
        return;
      }

      html += questoesDaBateria.map(q => {
        const tipoFormatado =
          q.tipo_questao === "MULTIPLA_5"
            ? "Múltipla escolha - 5 alternativas"
            : q.tipo_questao === "MULTIPLA_4"
              ? "Múltipla escolha - 4 alternativas"
              : q.tipo_questao === "CERTO_ERRADO"
                ? "Certo/Errado"
                : q.tipo;

        const alternativasHtml = (q.alternativas || []).length > 0
          ? `
            <div style="margin-top:10px;">
              ${(q.alternativas || []).map(a => `
                <div style="margin-top:6px;">
                  <b>${a.letra})</b> ${a.texto}
                </div>
              `).join("")}
            </div>
          `
          : "";

        const comentarioCompleto = q.comentario || "Nenhum comentário cadastrado.";

        const comentarioResumo =
          comentarioCompleto.length > 250
            ? comentarioCompleto.substring(0, 250) + "..."
            : comentarioCompleto;

        return `
          <div class="assunto" id="cardQuestao_${q.id}">

            <b>Questão ${q.ordem}</b>

            <div style="white-space:pre-wrap; margin-top:10px;">
              ${q.enunciado}
            </div>

            ${alternativasHtml}

            <div style="margin-top:10px;">
              <b>Gabarito:</b> ${q.gabarito || "-"}
            </div>

            <div style="margin-top:10px;">
              <b>Comentário:</b>

              <div
                id="comentarioQuestao_${q.id}"
                data-resumo="${comentarioResumo.replace(/"/g, "&quot;")}"
                data-completo="${comentarioCompleto.replace(/"/g, "&quot;")}"
                data-aberto="false"
                style="white-space:pre-wrap; opacity:.9; margin-top:4px;"
              >
                ${comentarioResumo}
              </div>

              ${
                comentarioCompleto.length > 250
                  ? `
                    <button
                      class="btn"
                      type="button"
                      style="margin-top:8px;"
                      onclick="alternarComentarioQuestao(${q.id})"
                      id="btnComentarioQuestao_${q.id}"
                    >
                      Visualizar comentário
                    </button>
                  `
                  : ""
              }
            </div>

            <div style="margin-top:10px; display:flex; gap:10px; flex-wrap:wrap;">
              <button
                class="btn"
                type="button"
                onclick="editarQuestao(${q.id})"
              >
                Editar
              </button>

              <button
                class="btn"
                type="button"
                onclick="excluirQuestao(${q.id})"
              >
                Excluir
              </button>
            </div>

          </div>
        `;
      }).join("");

      const btnConcluir = document.getElementById("btnConcluirBateria");

      if (btnConcluir) {
        btnConcluir.style.display = total >= 10 ? "inline-block" : "none";
      }

      lista.innerHTML = html;
    }

    window.renderizarCamposQuestaoCompleta = function () {
      const tipo = document.getElementById("questaoTipoQuestao").value;
      tipoQuestaoAtual = tipo;
      const box = document.getElementById("camposQuestaoCompleta");

      let letras = ["A", "B", "C", "D", "E"];

      if (tipo === "MULTIPLA_4") {
        letras = ["A", "B", "C", "D"];
      }

      if (tipo === "CERTO_ERRADO") {
        letras = ["C", "E"];
      }

      const questaoOriginal = questaoEditandoId
        ? questoesDaBateria.find(q => q.id === questaoEditandoId)
        : null;

      const numeroQuestao = questaoOriginal
        ? questaoOriginal.ordem
        : (questoesDaBateria?.length || 0) + 1;

      if (!questaoEditandoId && (questoesDaBateria?.length || 0) >= 10) {
        const boxFormulario = document.getElementById("boxFormularioQuestao");

        if (boxFormulario) {
          boxFormulario.innerHTML = `
            <div class="assunto">
              <div class="assunto" id="boxConcluirBateriaAdmin">
              </div>
            </div>
          `;
        }

        return;
      }

      box.innerHTML = `
        <label><b>Questão ${numeroQuestao}</b></label><br/>
        <textarea
          id="questaoEnunciado"
          placeholder="Enunciado..."
          style="width:100%; min-height:120px; padding:12px; border:1px solid #ddd; border-radius:6px;"
        ></textarea>

        ${
          tipo === "CERTO_ERRADO"
            ? `
              <div style="margin-top:15px;">
                <label style="display:block; margin-top:10px; cursor:pointer;">
                  <input
                    type="radio"
                    name="gabarito_certo_errado"
                    value="C"
                    onchange="document.getElementById('questaoGabarito').value = 'C'"
                    style="margin-right:10px;"
                  />
                  <b>CERTO</b>
                </label>

                <label style="display:block; margin-top:12px; cursor:pointer;">
                  <input
                    type="radio"
                    name="gabarito_certo_errado"
                    value="E"
                    onchange="document.getElementById('questaoGabarito').value = 'E'"
                    style="margin-right:10px;"
                  />
                  <b>ERRADO</b>
                </label>

                <input
                  id="questaoGabarito"
                  type="hidden"
                  value="C"
                />
              </div>
            `
            : `
              <div style="margin-top:15px;">
                <label><b>Alternativas</b></label>

                ${letras.map(letra => `
                  <div style="margin-top:10px;">
                    <label><b>${letra})</b></label>

                    <input
                      id="alternativa_${letra}"
                      type="text"
                      value=""
                      style="width:100%; padding:12px; border:1px solid #ddd; border-radius:6px;"
                    />
                  </div>
                `).join("")}
              </div>

              <div style="margin-top:15px;">
                <label><b>Gabarito</b></label><br/>
                <select
                  id="questaoGabarito"
                  style="width:100%; padding:12px; border:1px solid #ddd; border-radius:6px;"
                >
                  ${letras.map(letra => `
                    <option value="${letra}">${letra}</option>
                  `).join("")}
                </select>
              </div>
            `
        }

        <div style="margin-top:15px;">
          <label><b>Comentário</b></label><br/>
          <textarea
            id="questaoComentario"
            placeholder="Digite ou cole o comentário da questão..."
            style="width:100%; min-height:140px; padding:12px; border:1px solid #ddd; border-radius:6px;"
          ></textarea>
        </div>
      `;
    };

    window.criarQuestaoManual = async function () {
      if (!bateriaAtualId) {
        alert("Selecione uma bateria.");
        return;
      }

      if (!questaoEditandoId && questoesDaBateria.length >= 10) {
        alert("Esta bateria já possui 10 questões.");
        return;
      }

      const tipoQuestao = document.getElementById("questaoTipoQuestao").value;
      const enunciado = document.getElementById("questaoEnunciado").value.trim();
      const gabarito = document.getElementById("questaoGabarito").value;
      const comentario = document.getElementById("questaoComentario").value.trim();

      if (!enunciado) {
        alert("Digite o enunciado da questão.");
        return;
      }

      if (!comentario) {
        alert("Digite o comentário da questão.");
        return;
      }

      let letras = ["A", "B", "C", "D", "E"];

      if (tipoQuestao === "MULTIPLA_4") {
        letras = ["A", "B", "C", "D"];
      }

      if (tipoQuestao === "CERTO_ERRADO") {
        letras = ["C", "E"];
      }

      if (tipoQuestao !== "CERTO_ERRADO") {
        for (const letra of letras) {
          const textoAlt = document.getElementById(`alternativa_${letra}`).value.trim();

          if (!textoAlt) {
            alert(`Preencha a alternativa ${letra}.`);
            return;
          }
        }
      }

      try {
        const questaoOriginal = questaoEditandoId
          ? questoesDaBateria.find(q => q.id === questaoEditandoId)
          : null;

        const ordem = questaoOriginal
          ? questaoOriginal.ordem
          : questoesDaBateria.length + 1;

        const payloadQuestao = {
          bateria_id: bateriaAtualId,
          enunciado,
          tipo: tipoQuestao === "CERTO_ERRADO" ? "CERTO_ERRADO" : "MULTIPLA",
          tipo_questao: tipoQuestao,
          quantidade_alternativas: letras.length,
          gabarito,
          comentario,
          ordem,
          ativo: true
        };

        const questao = questaoEditandoId
          ? await apiPutAuth(`/questoes/${questaoEditandoId}`, payloadQuestao)
          : await apiPostAuth("/questoes", payloadQuestao);

        if (questao.erro) {
          alert(questao.erro);
          return;
        }

        if (!questaoEditandoId && tipoQuestao !== "CERTO_ERRADO") {
          for (const letra of letras) {
            const textoAlt = document.getElementById(`alternativa_${letra}`).value.trim();

            const alternativa = await apiPostAuth(`/questoes/${questao.id}/alternativas`, {
              letra,
              texto: textoAlt,
              comentario: null
            });

            if (alternativa.erro) {
              alert(alternativa.erro);
              return;
            }
          }
        }

        const estavaEditando = !!questaoEditandoId;
        const questaoEditadaId = questaoEditandoId;

        await carregarQuestoesDaBateria();

        alert(
          estavaEditando
            ? `Questão ${ordem} atualizada com sucesso!`
            : `Questão ${ordem} salva com sucesso.`
        );

        questaoEditandoId = null;

        if (estavaEditando) {
          const boxFormulario = document.getElementById("boxFormularioQuestao");

          if (questoesDaBateria.length >= 10) {
            if (boxFormulario) {
              boxFormulario.innerHTML = `
                <div class="assunto">
                  Bateria concluída.
                </div>
              `;
            }

            const destino = document.getElementById(`cardQuestao_${questaoEditadaId}`);

            if (destino) {
              destino.scrollIntoView({
                behavior: "smooth",
                block: "start"
              });
            }

          } else {
            if (boxFormulario) {
              boxFormulario.innerHTML = `
                <label><b>Tipo da questão</b></label><br/>
                <select
                  id="questaoTipoQuestao"
                  onchange="renderizarCamposQuestaoCompleta()"
                  style="width:100%; padding:12px; border:1px solid #ddd; border-radius:6px;"
                >
                  <option value="MULTIPLA_5">Múltipla-escolha com 5 alternativas</option>
                  <option value="MULTIPLA_4">Múltipla-escolha com 4 alternativas</option>
                  <option value="CERTO_ERRADO">CERTO ou ERRADO</option>
                </select>

                <div id="camposQuestaoCompleta" style="margin-top:15px;"></div>

                <div style="margin-top:12px; display:flex; gap:10px; flex-wrap:wrap;">
                  <button class="btn" type="button" onclick="criarQuestaoManual()">
                    <span id="textoBotaoSalvarQuestao">Salvar questão</span>
                  </button>

                  <button
                    id="btnConcluirBateria"
                    class="btn"
                    type="button"
                    onclick="concluirBateriaQuestoes()"
                    style="display:none;"
                  >
                    Concluir bateria de questões
                  </button>
                </div>
              `;

              document.getElementById("questaoTipoQuestao").value = tipoQuestao;
              renderizarCamposQuestaoCompleta();

              const campoTipo = document.getElementById("questaoTipoQuestao");

              if (campoTipo) {
                campoTipo.scrollIntoView({
                  behavior: "smooth",
                  block: "start"
                });
              }
            }
          }

          return;
        }

        if (questoesDaBateria.length >= 10) {

          await apiPutAuth(`/baterias/${bateriaAtualId}/concluir`, {});
          await carregarBateriasDaAula();

          const lista = document.getElementById("listaQuestoesBateria");

          if (lista) {
            lista.insertAdjacentHTML("beforeend", `
              <div
                class="assunto"
                id="boxBateriaConcluida"
                style="margin-top:20px;"
              >
                <h3 style="margin-bottom:15px;">
                  Bateria concluída!
                </h3>

                <button
                  class="btn"
                  type="button"
                  onclick="voltarParaBaterias()"
                >
                  Fechar
                </button>
              </div>
            `);
          }

          setTimeout(() => {
            const boxFinal = document.getElementById("boxBateriaConcluida");

            if (boxFinal) {
              boxFinal.scrollIntoView({
                behavior: "smooth",
                block: "end"
              });
            }
          }, 100);

        } else {
          renderizarCamposQuestaoCompleta();

          document.getElementById("questaoTipoQuestao").scrollIntoView({
            behavior: "smooth",
            block: "start"
          });
        }

      } catch (err) {
        console.error(err);
        alert("Erro ao salvar questão.");
      }
    };
    
    window.concluirBateriaQuestoes = async function () {
      if (!bateriaAtualId) {
        alert("Selecione uma bateria.");
        return;
      }

      try {
        const resposta = await apiPutAuth(`/baterias/${bateriaAtualId}/concluir`, {});

        if (resposta.erro) {
          alert(resposta.erro);
          return;
        }

        alert("Bateria concluída com sucesso!");

        await carregarBateriasDaAula();

        boxConteudoAula.innerHTML = `
          <div class="assunto">
            Bateria concluída.

            <div style="margin-top:15px;">
              <button class="btn" type="button" onclick="voltarParaBaterias()">
                Voltar
              </button>
            </div>
          </div>
        `;

      } catch (err) {
        console.error(err);
        alert("Erro ao concluir bateria.");
      }
    };
    
    window.novaBateriaQuestoes = function () {
      btnQuestoes.click();
    };

    window.voltarParaBaterias = async function () {
      boxConteudoAula.innerHTML = `
        <div class="assunto">

          <div style="margin-top:12px;">
            <button class="btn" type="button" onclick="criarBateriaQuestoes()">
              Criar bateria de questões
            </button>
          </div>

          <div id="listaBateriasAula" style="margin-top:15px;">
            Carregando baterias...
          </div>
        </div>
      `;

      await carregarBateriasDaAula();
    };

    window.abrirTeoriaAula = async function (aulaId, titulo) {

      abrirConteudoAula(aulaId, titulo);
      document.querySelector("#areaConteudoAula h3").textContent = "Teoria em Texto";

      if (!aulaAtual) return;

      try {

        const materiais = await apiGetAuth(`/aulas/${aulaId}/materiais`);

        const textos = (materiais || []).filter(
          m => m.tipo === "TEXTO"
        );

        boxConteudoAula.innerHTML = `
          <div class="assunto">

            <div style="margin-top:12px;">
              <button
                class="btn"
                type="button"
                onclick="novoTextoTeoria()"
              >
                Novo texto
              </button>

              <button
                class="btn"
                type="button"
                onclick="voltarAreaAssunto()"
                style="margin-left:10px;"
              >
                Voltar
              </button>
            </div>

            <div id="listaTextosTeoria" style="margin-top:20px;">
              ${
                textos.length === 0
                  ? "Nenhum texto criado ainda."
                  : textos.map(t => `
                      <div class="assunto">

                        <div style="
                          display:flex;
                          justify-content:space-between;
                          align-items:center;
                          gap:10px;
                          flex-wrap:wrap;
                        ">

                          <div>
                            <b>${t.titulo || "Texto sem título"}</b>
                          </div>

                          <button
                            class="btn"
                            type="button"
                            onclick="abrirEditarTexto(${t.id})"
                          >
                            Abrir / editar
                          </button>

                        </div>

                      </div>
                    `).join("")
              }
            </div>

          </div>
        `;

        setTimeout(() => {
          areaConteudoAula.scrollIntoView({
            behavior: "smooth",
            block: "start"
          });
        }, 100);

      } catch (err) {
        console.error(err);
        alert("Erro ao carregar textos.");
      }
    };

    window.abrirVideoAula = async function (aulaId, titulo) {

      abrirConteudoAula(aulaId, titulo);
      document.querySelector("#areaConteudoAula h3").textContent = "Resumo em Vídeo";

      if (!aulaAtual) return;

      try {
        const videos = await apiGetAuth(`/aulas/${aulaId}/videos`);

        boxConteudoAula.innerHTML = `
          <div class="assunto">

            <div style="margin-top:12px;">
              <button class="btn" type="button" onclick="novoResumoVideo()">
                Novo vídeo
              </button>

              <button class="btn" type="button" onclick="voltarAreaAssunto()" style="margin-left:10px;">
                Voltar
              </button>
            </div>

            <div id="listaVideosAula" style="margin-top:20px;">
              ${
                !videos || videos.length === 0
                  ? "Nenhum vídeo criado ainda."
                  : videos.map(v => `
                      <div class="assunto">
                        <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap;">
                          <div>
                            <b>${v.titulo || "Vídeo sem título"}</b><br/>
                            <span style="opacity:.8;">${v.url || ""}</span>
                          </div>

                          <button class="btn" type="button" onclick="abrirEditarVideo(${v.id})">
                            Abrir / editar
                          </button>
                        </div>
                      </div>
                    `).join("")
              }
            </div>

          </div>
        `;

        setTimeout(() => {
          areaConteudoAula.scrollIntoView({
            behavior: "smooth",
            block: "start"
          });
        }, 100);

      } catch (err) {
        console.error(err);
        alert("Erro ao carregar vídeos.");
      }
    };

    window.abrirQuestoesAula = async function (aulaId, titulo) {
      abrirConteudoAula(aulaId, titulo);
      document.querySelector("#areaConteudoAula h3").textContent = "Questões";

      if (!aulaAtual) return;

      boxConteudoAula.innerHTML = `
        <div class="assunto">

          <div style="margin-top:12px; display:flex; gap:10px; flex-wrap:wrap;">
            <button class="btn" type="button" onclick="criarBateriaQuestoes()">
              Criar bateria de questões
            </button>

            <button class="btn" type="button" onclick="voltarAreaAssunto()">
              Voltar
            </button>
          </div>

          <div id="listaBateriasAula" style="margin-top:15px;">
            Nenhuma bateria carregada.
          </div>
        </div>
      `;

      await carregarBateriasDaAula();

      setTimeout(() => {
        areaConteudoAula.scrollIntoView({
          behavior: "smooth",
          block: "start"
        });
      }, 100);
    };

    window.novoTextoTeoria = function () {

      boxConteudoAula.innerHTML = `
        <div class="assunto">

          <input
            id="tituloTextoTeoria"
            type="text"
            placeholder="Título do texto"
            style="
              width:100%;
              padding:12px;
              border:1px solid #ddd;
              border-radius:6px;
              margin-bottom:12px;
            "
          />

          <textarea
            id="textoTeoriaAula"
            placeholder="Digite a teoria..."
            style="
              width:100%;
              min-height:260px;
              padding:12px;
              border:1px solid #ddd;
              border-radius:6px;
            "
          ></textarea>

          <div style="
            margin-top:15px;
            display:flex;
            gap:10px;
            flex-wrap:wrap;
          ">

            <button
              class="btn"
              type="button"
              onclick="salvarNovoTextoTeoria()"
            >
              Concluir texto
            </button>

            <button
              class="btn"
              type="button"
              onclick="voltarParaListaTextos()"
            >
              Descartar e voltar
            </button>

          </div>

        </div>
      `;
    };

    window.salvarNovoTextoTeoria = async function () {

      const titulo = document.getElementById("tituloTextoTeoria").value.trim();

      const texto = document.getElementById("textoTeoriaAula").value.trim();

      if (!titulo) {
        alert("Informe o título do texto.");
        return;
      }

      if (!texto) {
        alert("Digite o conteúdo do texto.");
        return;
      }

      try {

        const materiais = await apiGetAuth(`/aulas/${aulaAtual.id}/materiais`);

        const textos = (materiais || []).filter(
          m => m.tipo === "TEXTO"
        );

        const ordem = textos.length + 1;

        const resposta = await apiPostAuth("/materiais", {
          aula_id: aulaAtual.id,
          tipo: "TEXTO",
          titulo: titulo || `Texto ${ordem}`,
          conteudo: texto,
          url: null,
          ordem,
          ativo: true
        });

        if (resposta.erro) {
          alert(resposta.erro);
          return;
        }

        alert("Texto salvo com sucesso.");

        abrirTeoriaAula(aulaAtual.id, aulaAtual.titulo);

      } catch (err) {
        console.error(err);
        alert("Erro ao salvar texto.");
      }
    };

    window.abrirEditarTexto = async function (materialId) {

      try {

        const materiais = await apiGetAuth(`/aulas/${aulaAtual.id}/materiais`);

        const material = materiais.find(m => m.id === materialId);

        if (!material) {
          alert("Texto não encontrado.");
          return;
        }

        boxConteudoAula.innerHTML = `
          <div class="assunto">

            <h4>📄 Editar Texto</h4>

            <input
              id="tituloTextoTeoria"
              type="text"
              value="${(material.titulo || "").replace(/"/g, "&quot;")}"
              style="
                width:100%;
                padding:12px;
                border:1px solid #ddd;
                border-radius:6px;
                margin-bottom:12px;
              "
            />

            <textarea
              id="textoTeoriaAula"
              style="
                width:100%;
                min-height:260px;
                padding:12px;
                border:1px solid #ddd;
                border-radius:6px;
              "
            >${material.conteudo || ""}</textarea>

            <div style="
              margin-top:15px;
              display:flex;
              gap:10px;
              flex-wrap:wrap;
            ">

              <button
                class="btn"
                type="button"
                onclick="salvarEdicaoTexto(${material.id}, ${material.ordem})"
              >
                Concluir edição de texto
              </button>

              <button
                class="btn"
                type="button"
                onclick="voltarParaListaTextos()"
              >
                Descartar alterações e voltar
              </button>

            </div>

          </div>
        `;
        
      } catch (err) {
        console.error(err);
        alert("Erro ao abrir texto.");
      }
    };

    window.salvarEdicaoTexto = async function (materialId, ordem) {

      const titulo = document.getElementById("tituloTextoTeoria").value.trim();

      const texto = document.getElementById("textoTeoriaAula").value.trim();

      if (!titulo) {
        alert("Informe o título do texto.");
        return;
      }

      if (!texto) {
        alert("Digite o conteúdo.");
        return;
      }

      try {

        await apiPutAuth(`/materiais/${materialId}`, {
          aula_id: aulaAtual.id,
          tipo: "TEXTO",
          titulo,
          conteudo: texto,
          url: null,
          ordem,
          ativo: true
        });

        alert("Texto atualizado com sucesso.");

        abrirTeoriaAula(aulaAtual.id, aulaAtual.titulo);

      } catch (err) {
        console.error(err);
        alert("Erro ao atualizar texto.");
      }
    };

    window.voltarAreaAssunto = function () {
      areaConteudoAula.style.display = "none";
    };

    window.voltarParaListaTextos = function () {

      if (!aulaAtual) return;

      abrirTeoriaAula(aulaAtual.id, aulaAtual.titulo);
    };

    window.novoResumoVideo = function () {
      boxConteudoAula.innerHTML = `
        <div class="assunto">

          <input
            id="tituloVideoAula"
            type="text"
            placeholder="Título do vídeo"
            style="width:100%; padding:12px; border:1px solid #ddd; border-radius:6px; margin-bottom:12px;"
          />

          <input
            id="urlVideoAula"
            type="text"
            placeholder="URL do vídeo"
            style="width:100%; padding:12px; border:1px solid #ddd; border-radius:6px;"
          />

          <div style="margin-top:15px; display:flex; gap:10px; flex-wrap:wrap;">
            <button class="btn" type="button" onclick="salvarNovoResumoVideo()">
              Concluir vídeo
            </button>

            <button class="btn" type="button" onclick="voltarParaListaVideos()">
              Descartar e voltar
            </button>
          </div>
        </div>
      `;
    };

    window.salvarNovoResumoVideo = async function () {
      const titulo = document.getElementById("tituloVideoAula").value.trim();
      const url = document.getElementById("urlVideoAula").value.trim();

      if (!titulo) {
        alert("Informe o título do vídeo.");
        return;
      }

      if (!url) {
        alert("Informe a URL do vídeo.");
        return;
      }

      try {
        const videos = await apiGetAuth(`/aulas/${aulaAtual.id}/videos`);
        const ordem = (videos || []).length + 1;

        const resposta = await apiPostAuth("/videos", {
          aula_id: aulaAtual.id,
          titulo,
          url,
          duracao_segundos: 0,
          transcricao: null,
          ordem,
          ativo: true
        });

        if (resposta.erro) {
          alert(resposta.erro);
          return;
        }

        alert("Vídeo salvo com sucesso.");
        abrirVideoAula(aulaAtual.id, aulaAtual.titulo);

      } catch (err) {
        console.error(err);
        alert("Erro ao salvar vídeo.");
      }
    };

    window.abrirEditarVideo = async function (videoId) {
      try {
        const videos = await apiGetAuth(`/aulas/${aulaAtual.id}/videos`);
        const video = videos.find(v => v.id === videoId);

        if (!video) {
          alert("Vídeo não encontrado.");
          return;
        }

        boxConteudoAula.innerHTML = `
          <div class="assunto">
            <h4>🎥 Editar Vídeo</h4>

            <input
              id="tituloVideoAula"
              type="text"
              value="${(video.titulo || "").replace(/"/g, "&quot;")}"
              style="width:100%; padding:12px; border:1px solid #ddd; border-radius:6px; margin-bottom:12px;"
            />

            <input
              id="urlVideoAula"
              type="text"
              value="${(video.url || "").replace(/"/g, "&quot;")}"
              style="width:100%; padding:12px; border:1px solid #ddd; border-radius:6px;"
            />

            <div style="margin-top:15px; display:flex; gap:10px; flex-wrap:wrap;">
              <button class="btn" type="button" onclick="salvarEdicaoVideo(${video.id}, ${video.ordem})">
                Concluir edição de vídeo
              </button>

              <button class="btn" type="button" onclick="voltarParaListaVideos()">
                Descartar alterações e voltar
              </button>
            </div>
          </div>
        `;

      } catch (err) {
        console.error(err);
        alert("Erro ao abrir vídeo.");
      }
    };

    window.salvarEdicaoVideo = async function (videoId, ordem) {
      const titulo = document.getElementById("tituloVideoAula").value.trim();
      const url = document.getElementById("urlVideoAula").value.trim();

      if (!titulo) {
        alert("Informe o título do vídeo.");
        return;
      }

      if (!url) {
        alert("Informe a URL do vídeo.");
        return;
      }

      try {
        const resposta = await apiPutAuth(`/videos/${videoId}`, {
          aula_id: aulaAtual.id,
          titulo,
          url,
          duracao_segundos: 0,
          transcricao: null,
          ordem,
          ativo: true
        });

        if (resposta.erro) {
          alert(resposta.erro);
          return;
        }

        alert("Vídeo atualizado com sucesso.");
        abrirVideoAula(aulaAtual.id, aulaAtual.titulo);

      } catch (err) {
        console.error(err);
        alert("Erro ao atualizar vídeo.");
      }
    };

    window.voltarParaListaVideos = function () {
      if (!aulaAtual) return;
      abrirVideoAula(aulaAtual.id, aulaAtual.titulo);
    };

    btnEditarCurso.addEventListener("click", async () => {
      const cursoId = cursoExistenteSelect.value;

      if (!cursoId) {
        alert("Selecione um curso para editar.");
        return;
      }

      const nomeAtual = cursoExistenteSelect.options[cursoExistenteSelect.selectedIndex].text;
      const novoNome = prompt("Editar nome do curso:", nomeAtual);

      if (!novoNome || !novoNome.trim()) return;

      const ok = confirm(`Confirmar alteração do nome do curso para:\n\n${novoNome.trim()}?`);
      if (!ok) return;

      try {
        const curso = await apiPutAuth(`/cursos/${cursoId}`, {
          nome: novoNome.trim(),
          ativo: true
        });

        msgCurso.textContent = `Curso atualizado: ${curso.nome}!`;
        msgCurso.style.color = "#2f5e46";

        await carregarCursosExistentes();
        cursoExistenteSelect.value = cursoId;
        cursoNome.disabled = false;
        cursoNome.value = "";

      } catch (err) {
        console.error(err);
        alert("Erro ao editar curso: " + err.message);
      }
    });

    btnDuplicarCurso.addEventListener("click", async () => {
      const cursoId = cursoExistenteSelect.value;

      if (!cursoId) {
        alert("Selecione um curso para duplicar.");
        return;
      }

      const nomeCurso =
        cursoExistenteSelect.options[
          cursoExistenteSelect.selectedIndex
        ].text;

      const novoNome = prompt(
        "Informe o nome do novo curso:",
        `Cópia de ${nomeCurso}`
      );

      if (!novoNome || !novoNome.trim()) {
        return;
      }

      const ok = confirm(
        "Deseja duplicar este curso?\n\n" +
        `Curso de origem: ${nomeCurso}\n` +
        `Novo curso: ${novoNome.trim()}\n\n` +
        "Todo o conteúdo será copiado para um novo curso independente."
      );

      if (!ok) return;

      try {
        msgCurso.textContent =
          "Duplicando curso. Aguarde...";

        msgCurso.style.color = "";

        const resultado = await apiPostAuth(
          `/admin/cursos/${cursoId}/duplicar`,
          {
            novo_nome: novoNome.trim()
          }
        );

        await carregarCursosExistentes();

        cursoExistenteSelect.value =
          String(resultado.novo_curso_id);

        msgCurso.textContent =
          `Curso duplicado com sucesso: ${resultado.novo_curso_nome}`;

        msgCurso.style.color = "#2f5e46";

      } catch (err) {
        console.error(err);

        const mensagem =
          String(err?.message || "");

        if (
          mensagem.includes(
            "Já existe um curso com este nome"
          )
        ) {
          msgCurso.textContent =
            "Já existe um curso com este nome.";
        } else {
          msgCurso.textContent =
            "Erro ao duplicar curso.";
        }

        msgCurso.style.color = "#8a1f1f";
      }
    });

    btnExcluirCurso.addEventListener("click", async () => {
      const cursoId = cursoExistenteSelect.value;

      if (!cursoId) {
        alert("Selecione um curso para excluir.");
        return;
      }

      const nomeCurso =
        cursoExistenteSelect.options[
          cursoExistenteSelect.selectedIndex
        ].text;

      const ok = confirm(
        `Tem certeza que deseja excluir o curso?\n\n` +
        `${nomeCurso}\n\n` +
        `Esta ação não poderá ser desfeita.`
      );

      if (!ok) return;

      try {
        await apiDeleteAuth(`/cursos/${cursoId}`);

        msgCurso.textContent = "Curso excluído com sucesso!";
        msgCurso.style.color = "#2f5e46";

        cursoAtual = null;
        disciplinasDoCurso = [];

        renderizarDisciplinas();

        boxDisciplinas.style.display = "none";
        boxConteudo.style.display = "none";
        boxConfigPublicaCurso.style.display = "none";

        btnPublicarCurso.style.display = "none";
        btnRetirarCursoVenda.style.display = "none";

        cursoDescricaoPublica.value = "";
        valor4Meses.value = "";
        valor8Meses.value = "";
        valor12Meses.value = "";
        msgConfigPublicaCurso.textContent = "";

        cursoNome.disabled = false;
        cursoNome.value = "";

        cursoExistenteSelect.value = "";

        await carregarCursosExistentes();

      } catch (err) {
        console.error(err);

        alert(
          "Erro ao excluir curso: " +
          err.message
        );
      }
    });

    window.trabalharNestaDisciplina = async function (disciplinaId) {

      limparAreaCopiaAssunto();

      disciplinaAtualId = disciplinaId;

      const disciplina = disciplinasDoCurso.find(
        d => d.id === disciplinaId
      );

      if (disciplina) {
        tituloDisciplinaSelecionada.textContent = disciplina.nome;
      }

      areaAssuntos.style.display = "block";

      areaAulas.style.display = "none";
      areaConteudoAula.style.display = "none";
      listaAulas.innerHTML = "";
      boxConteudoAula.innerHTML = "";

      await carregarAssuntosDaDisciplina(disciplinaId);
      
      areaAssuntos.scrollIntoView({
        behavior: "smooth",
        block: "start"
      });

    };

    window.moverDisciplina = async function (disciplinaId, direcao) {
      const index = disciplinasDoCurso.findIndex(d => d.id === disciplinaId);

      if (index === -1) return;

      const novoIndex = index + direcao;

      if (novoIndex < 0 || novoIndex >= disciplinasDoCurso.length) return;

      const novaLista = [...disciplinasDoCurso];

      const [itemMovido] = novaLista.splice(index, 1);
      novaLista.splice(novoIndex, 0, itemMovido);

      try {
        for (let i = 0; i < novaLista.length; i++) {
          const d = novaLista[i];

          await apiPutAuth(`/disciplinas-proprias/${d.id}`, {
            nome: d.nome,
            ativo: d.ativo,
            ordem: i + 1
          });
        }

        disciplinasDoCurso = novaLista.map((d, i) => ({
          ...d,
          ordem: i + 1
        }));

        renderizarDisciplinas();

      } catch (err) {
        console.error(err);
        alert("Erro ao alterar a ordem da disciplina.");
      }
    };

    window.moverAssunto = async function (assuntoId, direcao) {
      const index = assuntosDaDisciplina.findIndex(a => a.id === assuntoId);

      if (index === -1) return;

      const novoIndex = index + direcao;

      if (novoIndex < 0 || novoIndex >= assuntosDaDisciplina.length) return;

      const novaLista = [...assuntosDaDisciplina];

      const [itemMovido] = novaLista.splice(index, 1);
      novaLista.splice(novoIndex, 0, itemMovido);

      try {
        for (let i = 0; i < novaLista.length; i++) {
          const a = novaLista[i];

          await apiPutAuth(`/assuntos-proprios/${a.id}`, {
            nome: a.nome,
            descricao: a.descricao || null,
            ativo: a.ativo,
            ordem: i + 1
          });
        }

        assuntosDaDisciplina = novaLista.map((a, i) => ({
          ...a,
          ordem: i + 1
        }));

        renderizarAssuntos();

      } catch (err) {
        console.error(err);
        alert("Erro ao alterar a ordem do assunto.");
      }
    };

    window.editarTituloBateria = async function (bateriaId, tituloAtual, ordem) {
      const novoTitulo = prompt("Editar título da bateria:", tituloAtual);

      if (!novoTitulo || !novoTitulo.trim()) return;

      try {
        const atualizada = await apiPutAuth(`/baterias/${bateriaId}`, {
          aula_id: aulaAtual.id,
          titulo: novoTitulo.trim(),
          ordem,
          ativo: true
        });

        bateriasDaAula = bateriasDaAula.map(b =>
          b.id === bateriaId ? { ...b, titulo: atualizada.titulo } : b
        );

        renderizarBaterias();

      } catch (err) {
        console.error(err);
        alert("Erro ao editar título da bateria.");
      }
    };

    window.editarQuestao = function (questaoId) {
      const questao = questoesDaBateria.find(q => q.id === questaoId);

      if (!questao) {
        alert("Questão não encontrada.");
        return;
      }

      questaoEditandoId = questao.id;

      const boxFormulario = document.getElementById("boxFormularioQuestao");

      boxFormulario.innerHTML = `
        <label><b>Tipo da questão</b></label><br/>
        <select
          id="questaoTipoQuestao"
          onchange="renderizarCamposQuestaoCompleta()"
          style="width:100%; padding:12px; border:1px solid #ddd; border-radius:6px;"
        >
          <option value="MULTIPLA_5">Múltipla-escolha com 5 alternativas</option>
          <option value="MULTIPLA_4">Múltipla-escolha com 4 alternativas</option>
          <option value="CERTO_ERRADO">CERTO ou ERRADO</option>
        </select>

        <div id="camposQuestaoCompleta" style="margin-top:15px;"></div>

        <div style="margin-top:12px; display:flex; gap:10px; flex-wrap:wrap;">
          <button class="btn" type="button" onclick="criarQuestaoManual()">
            <span id="textoBotaoSalvarQuestao">Salvar edição</span>
          </button>

          <button
            class="btn"
            type="button"
            onclick="descartarEdicaoQuestao(${questao.id})"
          >
            Descartar e fechar edição
          </button>

        </div>
      `;

      document.getElementById("questaoTipoQuestao").value = questao.tipo_questao || "MULTIPLA_5";

      renderizarCamposQuestaoCompleta();

      document.getElementById("questaoEnunciado").value = questao.enunciado || "";
      document.getElementById("questaoGabarito").value = questao.gabarito || "A";
      document.getElementById("questaoComentario").value = questao.comentario || "";

      if (questao.alternativas && questao.alternativas.length > 0) {
        questao.alternativas.forEach(alt => {
          const campo = document.getElementById(`alternativa_${alt.letra}`);
          if (campo) campo.value = alt.texto || "";
        });
      }

      document.getElementById("questaoTipoQuestao").scrollIntoView({
        behavior: "smooth",
        block: "start"
      });
    };

    window.excluirQuestao = async function (questaoId) {
      const ok = confirm("Deseja realmente excluir esta questão?");

      if (!ok) return;

      try {
        await apiDeleteAuth(`/questoes/${questaoId}`);

        alert("Questão excluída com sucesso!");

        questaoEditandoId = null;

        await carregarQuestoesDaBateria();

        const boxFormulario = document.getElementById("boxFormularioQuestao");

        if (boxFormulario && questoesDaBateria.length < 10) {
          boxFormulario.innerHTML = `
            <label><b>Tipo da questão</b></label><br/>
            <select
              id="questaoTipoQuestao"
              onchange="renderizarCamposQuestaoCompleta()"
              style="width:100%; padding:12px; border:1px solid #ddd; border-radius:6px;"
            >
              <option value="MULTIPLA_5">Múltipla-escolha com 5 alternativas</option>
              <option value="MULTIPLA_4">Múltipla-escolha com 4 alternativas</option>
              <option value="CERTO_ERRADO">CERTO ou ERRADO</option>
            </select>

            <div id="camposQuestaoCompleta" style="margin-top:15px;"></div>

            <div style="margin-top:12px; display:flex; gap:10px; flex-wrap:wrap;">
              <button class="btn" type="button" onclick="criarQuestaoManual()">
                <span id="textoBotaoSalvarQuestao">Salvar questão</span>
              </button>
            </div>
          `;

          document.getElementById("questaoTipoQuestao").value =
            tipoQuestaoAtual || "MULTIPLA_5";

          renderizarCamposQuestaoCompleta();

          document.getElementById("questaoTipoQuestao").scrollIntoView({
            behavior: "smooth",
            block: "start"
          });
        }

      } catch (err) {
        console.error(err);
        alert("Erro ao excluir questão.");
      }
    };

    window.alternarComentarioQuestao = function (questaoId) {
      const box = document.getElementById(`comentarioQuestao_${questaoId}`);
      const btn = document.getElementById(`btnComentarioQuestao_${questaoId}`);

      if (!box || !btn) return;

      const aberto = box.dataset.aberto === "true";

      if (aberto) {
        box.textContent = box.dataset.resumo;
        box.dataset.aberto = "false";
        btn.textContent = "Visualizar comentário";
      } else {
        box.textContent = box.dataset.completo;
        box.dataset.aberto = "true";
        btn.textContent = "Ocultar comentário";
      }
    };

    window.descartarEdicaoQuestao = function (questaoId) {
      questaoEditandoId = null;

      const boxFormulario = document.getElementById("boxFormularioQuestao");

      if (!boxFormulario) return;

      if (questoesDaBateria.length >= 10) {
        boxFormulario.innerHTML = `
          <div class="assunto">
            Bateria concluída.
          </div>
        `;
      
        const card = document.getElementById(`cardQuestao_${questaoId}`);

        if (card) {
          card.scrollIntoView({
            behavior: "smooth",
            block: "start"
          });
        }

        return;
      }

      boxFormulario.innerHTML = `
        <label><b>Tipo da questão</b></label><br/>
        <select
          id="questaoTipoQuestao"
          onchange="renderizarCamposQuestaoCompleta()"
          style="width:100%; padding:12px; border:1px solid #ddd; border-radius:6px;"
        >
          <option value="MULTIPLA_5">Múltipla-escolha com 5 alternativas</option>
          <option value="MULTIPLA_4">Múltipla-escolha com 4 alternativas</option>
          <option value="CERTO_ERRADO">CERTO ou ERRADO</option>
        </select>

        <div id="camposQuestaoCompleta" style="margin-top:15px;"></div>

        <div style="margin-top:12px; display:flex; gap:10px; flex-wrap:wrap;">
          <button class="btn" type="button" onclick="criarQuestaoManual()">
            <span id="textoBotaoSalvarQuestao">Salvar questão</span>
          </button>
        </div>
      `;

      document.getElementById("questaoTipoQuestao").value =
        tipoQuestaoAtual || "MULTIPLA_5";

      renderizarCamposQuestaoCompleta();
      const campoTipo = document.getElementById("questaoTipoQuestao");

      if (campoTipo) {
        campoTipo.scrollIntoView({
          behavior: "smooth",
          block: "start"
        });
      }
    };
    
    carregarCursosExistentes();

})();

function bloquearConfigPublicaCurso() {
  cursoDescricaoPublica.disabled = true;
  valor4Meses.disabled = true;
  valor8Meses.disabled = true;
  valor12Meses.disabled = true;

  btnEditarConfigPublicaCurso.disabled = false;
  btnEditarConfigPublicaCurso.style.opacity = "1";

  btnSalvarConfigPublicaCurso.disabled = true;
  btnSalvarConfigPublicaCurso.style.opacity = ".45";
}

function liberarEdicaoConfigPublicaCurso() {
  cursoDescricaoPublica.disabled = false;
  valor4Meses.disabled = false;
  valor8Meses.disabled = false;
  valor12Meses.disabled = false;

  btnEditarConfigPublicaCurso.disabled = true;
  btnEditarConfigPublicaCurso.style.opacity = ".45";

  btnSalvarConfigPublicaCurso.disabled = false;
  btnSalvarConfigPublicaCurso.style.opacity = "1";
}

function atualizarBotoesPublicacaoCurso() {
  if (!cursoAtual || !cursoAtual.id) {
    btnPublicarCurso.style.display = "none";
    btnRetirarCursoVenda.style.display = "none";
    return;
  }

  if (cursoAtual.publicado === true) {
    btnPublicarCurso.style.display = "none";
    btnRetirarCursoVenda.style.display = "inline-block";
  } else {
    btnPublicarCurso.style.display = "inline-block";
    btnRetirarCursoVenda.style.display = "none";
  }
}