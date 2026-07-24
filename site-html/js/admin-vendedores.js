(async function () {

  if (!(await requireAdmin())) return;

  const formVendedor =
    document.getElementById("formVendedor");

  const listaVendedores =
    document.getElementById("listaVendedores");

  const msgVendedor =
    document.getElementById("msgVendedor");

  const campoNome =
    document.getElementById("vendedorNome");

  const campoEmail =
    document.getElementById("vendedorEmail");

  const campoTelefone =
    document.getElementById("vendedorTelefone");

  const campoSenha =
    document.getElementById(
      "vendedorSenha"
    );

  const campoConfirmarSenha =
    document.getElementById(
      "vendedorConfirmarSenha"
    );

  const campoCpfCnpj =
    document.getElementById("vendedorCpfCnpj");

  const campoDataNascimento =
    document.getElementById(
      "vendedorDataNascimento"
    );

  const campoEstadoUf =
    document.getElementById("vendedorEstadoUf");

  const campoCidade =
    document.getElementById("vendedorCidade");

  const tituloVendedoresCadastrados =
    document.getElementById(
      "tituloVendedoresCadastrados"
    );

  const areaVendedoresCadastrados =
    document.getElementById(
      "areaVendedoresCadastrados"
    );

  const btnLocalizarVendedor =
    document.getElementById(
      "btnLocalizarVendedor"
    );

  const boxBuscaVendedor =
    document.getElementById(
      "boxBuscaVendedor"
    );

  const buscaVendedor =
    document.getElementById(
      "buscaVendedor"
    );

  let vendedoresCarregados = [];

  // =========================================================
  // FUNÇÕES AUXILIARES
  // =========================================================

  function somenteDigitos(valor) {
    return String(valor || "").replace(/\D/g, "");
  }


  function cpfValido(cpf) {
    const numeros = somenteDigitos(cpf);

    if (numeros.length !== 11) {
        return false;
    }

    if (/^(\d)\1{10}$/.test(numeros)) {
        return false;
    }

    let soma = 0;

    for (let i = 0; i < 9; i++) {
        soma += Number(numeros[i]) * (10 - i);
    }

    let resto = (soma * 10) % 11;

    if (resto === 10) {
        resto = 0;
    }

    if (resto !== Number(numeros[9])) {
        return false;
    }

    soma = 0;

    for (let i = 0; i < 10; i++) {
        soma += Number(numeros[i]) * (11 - i);
    }

    resto = (soma * 10) % 11;

    if (resto === 10) {
        resto = 0;
    }

    return resto === Number(numeros[10]);
    }


function cnpjValido(cnpj) {
  const numeros = somenteDigitos(cnpj);

  if (numeros.length !== 14) {
    return false;
  }

  if (/^(\d)\1{13}$/.test(numeros)) {
    return false;
  }

  function calcularDigito(base, pesos) {
    let soma = 0;

    for (let i = 0; i < pesos.length; i++) {
      soma += Number(base[i]) * pesos[i];
    }

    const resto = soma % 11;

    return resto < 2
      ? 0
      : 11 - resto;
  }

  const primeiroDigito =
    calcularDigito(
      numeros.slice(0, 12),
      [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    );

  if (
    primeiroDigito !==
    Number(numeros[12])
  ) {
    return false;
  }

  const segundoDigito =
    calcularDigito(
      numeros.slice(0, 13),
      [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    );

  return (
    segundoDigito ===
    Number(numeros[13])
  );
}


  function formatarTelefone(valor) {
    let v = somenteDigitos(valor).slice(0, 11);

    if (v.length <= 10) {
      v = v.replace(/^(\d{2})(\d)/, "($1) $2");
      v = v.replace(/(\d{4})(\d)/, "$1-$2");
    } else {
      v = v.replace(/^(\d{2})(\d)/, "($1) $2");
      v = v.replace(/(\d{5})(\d)/, "$1-$2");
    }

    return v;
  }

  function formatarDataBr(valor) {
    if (!valor) {
      return "-";
    }

    const partes =
      String(valor)
        .split("-");

    if (partes.length !== 3) {
      return valor;
    }

    const [ano, mes, dia] =
      partes;

    return `${dia}/${mes}/${ano}`;
  }

  function formatarCpfCnpj(valor) {
    const numeros =
      somenteDigitos(valor).slice(0, 14);

    // CPF
    if (numeros.length <= 11) {
      let v = numeros;

      v = v.replace(
        /^(\d{3})(\d)/,
        "$1.$2"
      );

      v = v.replace(
        /^(\d{3})\.(\d{3})(\d)/,
        "$1.$2.$3"
      );

      v = v.replace(
        /\.(\d{3})(\d)/,
        ".$1-$2"
      );

      return v;
    }

    // CNPJ
    let v = numeros;

    v = v.replace(
      /^(\d{2})(\d)/,
      "$1.$2"
    );

    v = v.replace(
      /^(\d{2})\.(\d{3})(\d)/,
      "$1.$2.$3"
    );

    v = v.replace(
      /\.(\d{3})(\d)/,
      ".$1/$2"
    );

    v = v.replace(
      /(\d{4})(\d)/,
      "$1-$2"
    );

    return v;
  }


  function emailValido(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(
      email
    );
  }


  function cidadeValida(cidade) {
    return /^[A-Za-zÀ-ÖØ-öø-ÿ\s.'-]+$/.test(
      cidade
    );
  }


  function validarDadosVendedor(dados) {

    if (
      !dados.nome ||
      !dados.cpf_cnpj ||
      !dados.data_nascimento ||
      !dados.email ||
      !dados.telefone ||
      !dados.senha ||
      !dados.confirmar_senha ||
      !dados.estado_uf ||
      !dados.cidade
    ) {
      return (
        "Preencha todas as informações " +
        "para realizar o cadastro."
      );
    }

    if (
      dados.senha !==
      dados.confirmar_senha
    ) {
      return (
        "A senha e a confirmação " +
        "da senha não coincidem."
      );
    }

    if (dados.senha.length < 8) {
      return (
        "A senha deve conter " +
        "pelo menos 8 caracteres."
      );
    }

    if (!emailValido(dados.email)) {
      return "Informe um e-mail válido.";
    }

    const telefoneNumeros =
      somenteDigitos(dados.telefone);

    if (
      telefoneNumeros.length !== 10 &&
      telefoneNumeros.length !== 11
    ) {
      return "Informe um telefone válido.";
    }

    const cpfCnpjNumeros =
      somenteDigitos(dados.cpf_cnpj);

    const cpfCnpjValido =
      (
        cpfCnpjNumeros.length === 11 &&
        cpfValido(cpfCnpjNumeros)
      ) ||
      (
        cpfCnpjNumeros.length === 14 &&
        cnpjValido(cpfCnpjNumeros)
      );

    if (!cpfCnpjValido) {
      return "Informe um CPF / CNPJ válido.";
    }

    if (
      dados.estado_uf.length !== 2 ||
      !/^[A-Za-z]{2}$/.test(dados.estado_uf)
    ) {
      return "Informe uma UF válida com 2 letras.";
    }

    if (!cidadeValida(dados.cidade)) {
      return "Informe uma cidade válida.";
    }

    return null;
  }


  // =========================================================
  // FORMATAÇÃO DOS CAMPOS
  // =========================================================

  campoTelefone.addEventListener(
    "input",
    () => {
      campoTelefone.value =
        formatarTelefone(
          campoTelefone.value
        );
    }
  );


  campoCpfCnpj.addEventListener(
    "input",
    () => {
      campoCpfCnpj.value =
        formatarCpfCnpj(
          campoCpfCnpj.value
        );
    }
  );


  campoEstadoUf.addEventListener(
    "input",
    () => {
      campoEstadoUf.value =
        campoEstadoUf.value
          .replace(
            /[^A-Za-z]/g,
            ""
          )
          .slice(0, 2)
          .toUpperCase();
    }
  );

  campoCidade.addEventListener(
    "input",
    () => {
      campoCidade.value =
        campoCidade.value.replace(
          /[^A-Za-zÀ-ÖØ-öø-ÿ\s.'-]/g,
          ""
        );
    }
  );


  // =========================================================
  // CARREGAR PARCEIROS/VENDEDORES
  // =========================================================

  async function carregarVendedores() {
    try {
      const vendedores =
        await apiGetAuth(
          "/admin/vendedores"
        );

      vendedoresCarregados =
        [...(vendedores || [])]
          .sort(
            (a, b) =>
              String(a.nome || "")
                .localeCompare(
                  String(b.nome || ""),
                  "pt-BR",
                  {
                    sensitivity: "base"
                  }
                )
          );

      if (
        vendedoresCarregados.length === 0
      ) {
        listaVendedores.innerHTML =
          "<p>Nenhum parceiro/vendedor cadastrado.</p>";

        return;
      }

      renderizarVendedores(
        vendedoresCarregados
      );

    } catch (err) {
      console.error(err);

      listaVendedores.innerHTML = `
        <div class="assunto">
          Erro ao carregar parceiros/vendedores.
        </div>
      `;
    }
  }


  // =========================================================
  // CADASTRAR PARCEIRO/VENDEDOR
  // =========================================================

  formVendedor.addEventListener(
    "submit",
    async (e) => {
      e.preventDefault();

      const dados = {
        nome:
          campoNome.value.trim(),

        cpf_cnpj:
          campoCpfCnpj.value.trim(),

        data_nascimento:
          campoDataNascimento.value,

        email:
          campoEmail.value.trim(),

        telefone:
          campoTelefone.value.trim(),

        senha:
          campoSenha.value,

        confirmar_senha:
          campoConfirmarSenha.value,

        estado_uf:
          campoEstadoUf.value
            .trim()
            .toUpperCase(),

        cidade:
          campoCidade.value.trim()
      };


      const erroValidacao =
        validarDadosVendedor(dados);


      if (erroValidacao) {
        msgVendedor.textContent =
          erroValidacao;

        msgVendedor.style.color =
          "#8a1f1f";

        return;
      }

      const payload = {
        nome:
          dados.nome,

        cpf_cnpj:
          dados.cpf_cnpj,

        data_nascimento:
          dados.data_nascimento,

        email:
          dados.email,

        telefone:
          dados.telefone,

        senha:
          dados.senha,

        estado_uf:
          dados.estado_uf,

        cidade:
          dados.cidade
      };


      try {
        msgVendedor.textContent =
          "Cadastrando parceiro/vendedor...";

        msgVendedor.style.color = "";


        await apiPostAuth(
          "/admin/vendedores",
          payload
        );


        msgVendedor.textContent =
          "Parceiro/vendedor cadastrado com sucesso!";

        msgVendedor.style.color =
          "#2f5e46";


        formVendedor.reset();


        await carregarVendedores();

      } catch (err) {
        console.error(err);

        msgVendedor.textContent =
          "Erro ao fazer o cadastro. " +
          "Por favor, verifique os dados.";

        msgVendedor.style.color =
          "#8a1f1f";
      }
    }
  );


  // =========================================================
  // EDITAR PARCEIRO/VENDEDOR
  // =========================================================

  window.editarVendedor =
    async function (vendedorId) {

      try {
        const vendedores =
          await apiGetAuth(
            "/admin/vendedores"
          );


        const vendedor =
          vendedores.find(
            v => v.id === vendedorId
          );


        if (!vendedor) {
          alert(
            "Parceiro/vendedor não encontrado."
          );

          return;
        }


        const nome =
          prompt(
            "Nome:",
            vendedor.nome || ""
          );

        if (nome === null) {
          return;
        }


        const email =
          prompt(
            "Email:",
            vendedor.email || ""
          );

        if (email === null) {
          return;
        }


        const telefone =
          prompt(
            "Telefone:",
            vendedor.telefone || ""
          );

        if (telefone === null) {
          return;
        }


        const cpfCnpj =
          prompt(
            "CPF/CNPJ:",
            vendedor.cpf_cnpj || ""
          );

        if (cpfCnpj === null) {
          return;
        }

        const dataNascimento =
          prompt(
            "Data de nascimento (AAAA-MM-DD):",
            vendedor.data_nascimento || ""
          );

        if (dataNascimento === null) {
          return;
        }

        const estadoUf =
          prompt(
            "Estado/UF:",
            vendedor.estado_uf || ""
          );

        if (estadoUf === null) {
          return;
        }


        const cidade =
          prompt(
            "Cidade:",
            vendedor.cidade || ""
          );

        if (cidade === null) {
          return;
        }


        const dadosAtualizados = {
          nome:
            nome.trim(),

          cpf_cnpj:
            formatarCpfCnpj(
              cpfCnpj
            ),

          data_nascimento:
            dataNascimento.trim(),

          email:
            email.trim(),

          telefone:
            formatarTelefone(
              telefone
            ),

          estado_uf:
            estadoUf
              .replace(
                /[^A-Za-z]/g,
                ""
              )
              .slice(0, 2)
              .toUpperCase(),

          cidade:
            cidade
              .replace(
                /[^A-Za-zÀ-ÖØ-öø-ÿ\s.'-]/g,
                ""
              )
              .trim()
        };


        const erroValidacao =
          validarDadosVendedor(
            dadosAtualizados
          );


        if (erroValidacao) {
          alert(erroValidacao);

          return;
        }


        await apiPutAuth(
          `/admin/vendedores/${vendedorId}`,
          dadosAtualizados
        );


        await carregarVendedores();


        alert(
          "Dados do parceiro/vendedor " +
          "atualizados com sucesso!"
        );

      } catch (err) {
        console.error(err);

        alert(
          "Erro ao editar parceiro/vendedor."
        );
      }
    };

  // =========================================================
  // DESATIVAR / REATIVAR
  // =========================================================

  window.alterarStatusVendedor =
    async function (
      vendedorId,
      novoStatus
    ) {

      const texto =
        novoStatus
          ? "reativar"
          : "desativar";


      const ok =
        confirm(
          `Deseja realmente ${texto} ` +
          "este parceiro/vendedor?"
        );


      if (!ok) {
        return;
      }


      try {
        await apiPutAuth(
          `/admin/vendedores/${vendedorId}`,
          {
            ativo: novoStatus
          }
        );


        await carregarVendedores();

      } catch (err) {
        console.error(err);

        alert(
          "Erro ao alterar " +
          "o parceiro/vendedor."
        );
      }
    };

    tituloVendedoresCadastrados.addEventListener(
      "click",
      () => {
        const estaAberto =
          areaVendedoresCadastrados.style.display
          !== "none";

        if (estaAberto) {
          areaVendedoresCadastrados.style.display =
            "none";

          boxBuscaVendedor.style.display =
            "none";

          buscaVendedor.value = "";

          renderizarVendedores(
            vendedoresCarregados
          );

          return;
        }

        areaVendedoresCadastrados.style.display =
          "block";
      }
    );

    btnLocalizarVendedor.addEventListener(
      "click",
      () => {
        areaVendedoresCadastrados.style.display =
          "block";

        const buscaAberta =
          boxBuscaVendedor.style.display
          !== "none";

        if (buscaAberta) {
          boxBuscaVendedor.style.display =
            "none";

          buscaVendedor.value = "";

          renderizarVendedores(
            vendedoresCarregados
          );

          return;
        }

        boxBuscaVendedor.style.display =
          "block";

        buscaVendedor.focus();
      }
    );

    buscaVendedor.addEventListener(
      "input",
      () => {
        const termo =
          buscaVendedor.value
            .trim()
            .toLocaleLowerCase("pt-BR");

        if (!termo) {
          renderizarVendedores(
            vendedoresCarregados
          );

          return;
        }

        const filtrados =
          vendedoresCarregados.filter(
            vendedor =>
              String(vendedor.nome || "")
                .toLocaleLowerCase("pt-BR")
                .includes(termo)
          );

        renderizarVendedores(
          filtrados
        );
      }
    );

    function renderizarVendedores(lista) {

      if (!lista || lista.length === 0) {
        listaVendedores.innerHTML =
          "<p>Nenhum parceiro/vendedor encontrado.</p>";

        return;
      }

      listaVendedores.innerHTML =
        lista
          .map(v => `
            <div
              class="assunto"
              style="${!v.ativo ? "opacity:.60;" : ""}"
            >

              <div
                style="
                  display:flex;
                  justify-content:space-between;
                  align-items:center;
                  gap:12px;
                  flex-wrap:wrap;
                "
              >

                <div>
                  <b>${escapeHtml(v.nome)}</b><br/>

                  <span style="opacity:.85;">
                    ${escapeHtml(v.email || "-")}
                    <br/>

                    ${escapeHtml(v.telefone || "-")}
                    <br/>

                    ${escapeHtml(v.cpf_cnpj || "-")}
                    <br/>

                    ${escapeHtml(
                      formatarDataBr(
                        v.data_nascimento
                      )
                    )}

                    <br/>

                    ${escapeHtml(v.cidade || "-")}
                    ${
                      v.estado_uf
                        ? " / " +
                          escapeHtml(v.estado_uf)
                        : ""
                    }

                    <br/>

                  </span>
                </div>

                <div
                  style="
                    display:flex;
                    gap:8px;
                    flex-wrap:wrap;
                  "
                >

              
                <button
                    class="btn"
                    type="button"
                    onclick="editarVendedor(${v.id})"
                  >
                    Editar
                  </button>

                  <button
                    class="btn"
                    type="button"
                    onclick="
                      alterarStatusVendedor(
                        ${v.id},
                        ${v.ativo ? "false" : "true"}
                      )
                    "
                  >
                    ${
                      v.ativo
                        ? "Desativar"
                        : "Reativar"
                    }
                  </button>

                </div>

              </div>

            </div>
          `)
          .join("");
    }


  // =========================================================
  // INICIALIZAÇÃO
  // =========================================================

  await carregarVendedores();

})();