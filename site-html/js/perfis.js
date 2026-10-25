(async function () {
  if (!(await requireAdmin())) return;

  const campoBusca =
    document.getElementById(
      "buscaPerfilUsuario"
    );

  const btnBuscar =
    document.getElementById(
      "btnBuscarPerfilUsuario"
    );

  const msgBusca =
    document.getElementById(
      "msgBuscaPerfilUsuario"
    );

  const areaPerfisUsuario =
    document.getElementById(
      "areaPerfisUsuario"
    );

  const dadosUsuarioPerfil =
    document.getElementById(
      "dadosUsuarioPerfil"
    );

  const acoesPerfilUsuario =
    document.getElementById(
      "acoesPerfilUsuario"
    );


  function escaparHtml(valor) {
    return String(
      valor ?? ""
    )
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }


  function textoSimNao(valor) {
    return valor
      ? "Sim"
      : "Não";
  }


  function mostrarUsuario(
    usuario
    ) {
    if (!usuario) {
        return;
    }

    if (areaPerfisUsuario) {
        areaPerfisUsuario.style.display =
        "block";
    }


    if (dadosUsuarioPerfil) {
        dadosUsuarioPerfil.innerHTML = `
        <div class="assunto">

            <b>Nome:</b>
            ${escaparHtml(usuario.nome)}
            <br>

            <b>CPF:</b>
            ${escaparHtml(usuario.cpf)}
            <br><br>

            <b>Admin:</b>
            ${escaparHtml(({admin_geral: "Administrador Geral", admin_prod: "Administrador de Produção", admin_adm: "Administrador Administrativo"})[usuario.tipo_admin] || "Sem perfil administrativo")}
            <br>

            <b>Vendedor:</b>
            ${textoSimNao(
            usuario.is_vendedor
            )}
            <br>

            <b>Aluno:</b>
            ${textoSimNao(
              usuario.is_aluno
            )}

        </div>
        `;
    }


    if (acoesPerfilUsuario) {

        const textoBotaoVendedor =
        usuario.vendedor_ativo
            ? "Descredenciar vendedor"
            : usuario.vendedor_id
            ? "Reativar vendedor"
            : "Ativar como vendedor";


        acoesPerfilUsuario.innerHTML = `
        <label>Perfil administrativo
          <select id="tipoAdminUsuario">
            ${[["", "Sem perfil administrativo"], ["admin_geral", "Administrador Geral"],
               ["admin_prod", "Administrador de Produção"], ["admin_adm", "Administrador Administrativo"]]
              .map(([valor, nome]) => `<option value="${valor}" ${valor === (usuario.tipo_admin || "") ? "selected" : ""}>${nome}</option>`).join("")}
          </select>
        </label>
        <button id="btnAlterarPerfilAdmin" class="btn" type="button">Salvar perfil administrativo</button>

        <button
            id="btnAlterarPerfilVendedor"
            class="btn"
            type="button"
        >
            ${textoBotaoVendedor}
        </button>
        `;


        const btnAlterarPerfilAdmin =
        document.getElementById(
            "btnAlterarPerfilAdmin"
        );

        const btnAlterarPerfilVendedor =
        document.getElementById(
            "btnAlterarPerfilVendedor"
        );


        // O retorno da API é a fonte do estado exibido; não alternar flags localmente.
        if (btnAlterarPerfilAdmin) {
          btnAlterarPerfilAdmin.addEventListener("click", async () => {
            const tipo = document.getElementById("tipoAdminUsuario").value || null;
            if (tipo === usuario.tipo_admin) return;
            if (!confirm("Confirma a alteração do perfil administrativo deste usuário?")) return;
            btnAlterarPerfilAdmin.disabled = true;
            try {
              const atualizado = await apiPutAuth(`/admin/usuarios/${usuario.id}/tipo-admin`, {tipo_admin: tipo});
              Object.assign(usuario, atualizado);
              mostrarUsuario(usuario);
              alert("Perfil administrativo atualizado com sucesso.");
              // Uma alteração do próprio perfil deve revalidar a página imediatamente.
              const me = await apiGetAuth("/me");
              if (me.tipo_admin !== "admin_geral") location.replace("../minha-area.html");
            } catch (err) {
              alert("Não foi possível alterar o perfil: " + err.message);
              btnAlterarPerfilAdmin.disabled = false;
            }
          });
        }

        // ALTERAR PERFIL VENDEDOR
        if (btnAlterarPerfilVendedor) {

        btnAlterarPerfilVendedor.addEventListener(
            "click",
            async () => {

            let mensagemConfirmacao = "";


            if (!usuario.vendedor_id) {

                mensagemConfirmacao =
                "Deseja realmente ativar " +
                "este usuário como vendedor?";


            } else if (
                usuario.vendedor_ativo
            ) {

                mensagemConfirmacao =
                "Deseja realmente descredenciar " +
                "este vendedor?";


            } else {

                mensagemConfirmacao =
                "Deseja realmente reativar " +
                "este vendedor?";

            }


            const confirmou =
                confirm(
                mensagemConfirmacao
                );


            if (!confirmou) {
                return;
            }


            try {

                btnAlterarPerfilVendedor.disabled =
                true;


                // USUÁRIO AINDA NÃO É VENDEDOR
                if (!usuario.vendedor_id) {

                const vendedorCriado =
                    await apiPostAuth(
                    `/admin/usuarios/${usuario.id}/tornar-vendedor`,
                    {}
                    );


                usuario.vendedor_id =
                    vendedorCriado.id;

                usuario.vendedor_ativo =
                    true;

                usuario.is_vendedor =
                    true;


                // VENDEDOR ATIVO
                } else if (
                usuario.vendedor_ativo
                ) {

                await apiPutAuth(
                    `/admin/vendedores/${usuario.vendedor_id}/descredenciar`,
                    {}
                );


                usuario.vendedor_ativo =
                    false;

                // Durante os 30 dias,
                // ainda mantém acesso à área.
                usuario.is_vendedor =
                    true;


                // VENDEDOR INATIVO
                } else {

                await apiPutAuth(
                    `/admin/vendedores/${usuario.vendedor_id}/reativar`,
                    {}
                );


                usuario.vendedor_ativo =
                    true;

                usuario.is_vendedor =
                    true;

                }


                mostrarUsuario(
                usuario
                );


                alert(
                "Perfil de vendedor " +
                "atualizado com sucesso."
                );


            } catch (err) {

                console.error(
                "Erro ao alterar perfil de vendedor:",
                err
                );


                alert(
                "Não foi possível alterar " +
                "o perfil de vendedor."
                );


                btnAlterarPerfilVendedor.disabled =
                false;

            }

            }
        );

        }

    }


    areaPerfisUsuario?.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });
    }


  function renderizarResultados(
    usuarios
  ) {
    if (!msgBusca) {
      return;
    }

    if (
      !Array.isArray(usuarios) ||
      usuarios.length === 0
    ) {
      msgBusca.innerHTML =
        "Nenhum usuário encontrado.";

      if (areaPerfisUsuario) {
        areaPerfisUsuario.style.display =
          "none";
      }

      return;
    }

    msgBusca.innerHTML = `
      <div class="list">
        ${usuarios
          .map(
            usuario => `
              <div class="disciplina">

                <div>
                  <b>
                    ${escaparHtml(
                      usuario.nome
                    )}
                  </b>

                  <br>

                  <span
                    style="
                      opacity:.85;
                    "
                  >
                    ${escaparHtml(
                      usuario.email
                    )}
                  </span>
                </div>

                <div
                  style="
                    margin-top:10px;
                  "
                >
                  <button
                    class="btn"
                    type="button"
                    data-usuario-id="${usuario.id}"
                  >
                    Gerenciar
                  </button>
                </div>

              </div>
            `
          )
          .join("")}
      </div>
    `;


    const botoes =
      msgBusca.querySelectorAll(
        "[data-usuario-id]"
      );

    botoes.forEach(
      botao => {

        botao.addEventListener(
          "click",
          () => {

            const usuarioId =
              Number(
                botao.dataset.usuarioId
              );

            const usuario =
              usuarios.find(
                item =>
                  item.id === usuarioId
              );

            mostrarUsuario(
              usuario
            );

          }
        );

      }
    );
  }


  async function buscarUsuarios() {
    const termo =
      (
        campoBusca?.value ||
        ""
      ).trim();

    if (!termo) {
      if (msgBusca) {
        msgBusca.textContent =
          "Digite nome, e-mail ou CPF.";
      }

      return;
    }

    if (msgBusca) {
      msgBusca.textContent =
        "Buscando...";
    }

    if (areaPerfisUsuario) {
      areaPerfisUsuario.style.display =
        "none";
    }

    try {

      const usuarios =
        await apiGetAuth(
          "/admin/usuarios/perfis" +
          "?q=" +
          encodeURIComponent(
            termo
          )
        );

      renderizarResultados(
        usuarios
      );

    } catch (err) {

      console.error(
        "Erro ao buscar usuários:",
        err
      );

      if (msgBusca) {
        msgBusca.textContent =
          "Não foi possível realizar a busca.";
      }

    }
  }


  if (btnBuscar) {
    btnBuscar.addEventListener(
      "click",
      buscarUsuarios
    );
  }


  if (campoBusca) {
    campoBusca.addEventListener(
      "keydown",
      event => {

        if (
          event.key === "Enter"
        ) {
          event.preventDefault();

          buscarUsuarios();
        }

      }
    );
  }


})();