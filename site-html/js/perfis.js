(async function () {

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
            ${textoSimNao(
            usuario.is_admin
            )}
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

        const textoBotaoAdmin =
        usuario.is_admin
            ? "Retirar Admin"
            : "Conceder Admin";


        const textoBotaoVendedor =
        usuario.vendedor_ativo
            ? "Descredenciar vendedor"
            : usuario.vendedor_id
            ? "Reativar vendedor"
            : "Ativar como vendedor";


        acoesPerfilUsuario.innerHTML = `
        <button
            id="btnAlterarPerfilAdmin"
            class="btn"
            type="button"
        >
            ${textoBotaoAdmin}
        </button>

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


        // ALTERAR PERFIL ADMIN
        if (btnAlterarPerfilAdmin) {

        btnAlterarPerfilAdmin.addEventListener(
            "click",
            async () => {

            const acao =
                usuario.is_admin
                ? "retirar-admin"
                : "conceder-admin";


            const mensagemConfirmacao =
                usuario.is_admin
                ? (
                    "Deseja realmente retirar " +
                    "o perfil Admin deste usuário?"
                    )
                : (
                    "Deseja realmente conceder " +
                    "o perfil Admin a este usuário?"
                    );


            const confirmou =
                confirm(
                mensagemConfirmacao
                );


            if (!confirmou) {
                return;
            }


            try {

                btnAlterarPerfilAdmin.disabled =
                true;


                await apiPutAuth(
                `/admin/usuarios/${usuario.id}/${acao}`,
                {}
                );


                usuario.is_admin =
                !usuario.is_admin;


                mostrarUsuario(
                usuario
                );


                alert(
                "Perfil Admin atualizado com sucesso."
                );


            } catch (err) {

                console.error(
                "Erro ao alterar perfil Admin:",
                err
                );


                alert(
                "Não foi possível alterar " +
                "o perfil Admin."
                );


                btnAlterarPerfilAdmin.disabled =
                false;

            }

            }
        );

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