(async function () {

  if (!(await requireAdmin())) return;

  const quantidadeCupons =
    document.getElementById(
      "quantidadeCupons"
    );

  const btnGerarCupons =
    document.getElementById(
      "btnGerarCupons"
    );

  const msgGerarCupons =
    document.getElementById(
      "msgGerarCupons"
    );

  const tituloCuponsDisponiveis =
    document.getElementById(
        "tituloCuponsDisponiveis"
    );

  const listaResultadoBuscaCupom =
    document.getElementById(
        "listaResultadoBuscaCupom"
    );

  const areaCuponsDisponiveis =
    document.getElementById(
        "areaCuponsDisponiveis"
    );

  const btnLocalizarCupom =
    document.getElementById(
      "btnLocalizarCupom"
    );

  const boxBuscaCupom =
    document.getElementById(
      "boxBuscaCupom"
    );

  const buscaCupom =
    document.getElementById(
      "buscaCupom"
    );

  const listaCuponsDisponiveis =
    document.getElementById(
        "listaCuponsDisponiveis"
    );

  const tituloCuponsAtribuidos =
    document.getElementById(
      "tituloCuponsAtribuidos"
    );

  const areaCuponsAtribuidos =
    document.getElementById(
      "areaCuponsAtribuidos"
    );

  const listaCuponsAtribuidos =
    document.getElementById(
      "listaCuponsAtribuidos"
    );

  let cuponsCarregados = [];
  let vendedoresCarregados = [];


  async function carregarDados() {
    try {
      const [
        cupons,
        vendedores
      ] = await Promise.all([
        apiGetAuth(
          "/admin/cupons-desconto"
        ),
        apiGetAuth(
          "/admin/vendedores"
        )
      ]);

      cuponsCarregados =
        [...(cupons || [])];

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

      renderizarCupons(
        cuponsCarregados
      );

    } catch (err) {
      console.error(err);

      listaCupons.innerHTML =
        `
          <div class="assunto">
            Erro ao carregar cupons.
          </div>
        `;
    }
  }


  function obterNomeVendedor(
    vendedorId
  ) {
    if (!vendedorId) {
      return "Sem vínculo";
    }

    const vendedor =
      vendedoresCarregados.find(
        v => v.id === vendedorId
      );

    return vendedor
      ? vendedor.nome
      : "Vendedor não encontrado";
  }


  function montarHtmlCupom(cupom) {
    const vinculado =
        cupom.vendedor_id !== null;

    const nomeVendedor =
        obterNomeVendedor(
        cupom.vendedor_id
        );

    return `
        <div
        class="assunto"
        style="
            ${vinculado ? "opacity:.60;" : ""}
            ${!cupom.ativo ? "filter:grayscale(1);" : ""}
        "
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
            <b>
                ${escapeHtml(cupom.codigo)}
            </b>

            <br/>

            <span style="opacity:.85;">
                Desconto:
                ${cupom.percentual_desconto}%
                <br/>

                Parceiro/vendedor:
                ${escapeHtml(nomeVendedor)}
                <br/>

                Status:
                ${
                cupom.ativo
                    ? "Ativo"
                    : "Inativo"
                }
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
                onclick="
                gerenciarVinculoCupom(
                    ${cupom.id}
                )
                "
            >
                ${
                vinculado
                    ? "Trocar / remover vínculo"
                    : "Vincular vendedor"
                }
            </button>

            <button
                class="btn"
                type="button"
                onclick="
                alterarStatusCupom(
                    ${cupom.id},
                    ${cupom.ativo ? "false" : "true"}
                )
                "
            >
                ${
                cupom.ativo
                    ? "Desativar"
                    : "Reativar"
                }
            </button>

            </div>

        </div>

        </div>
    `;
  }


  function renderizarCupons(lista) {
    const cupons =
        lista || [];

    const disponiveis =
        cupons.filter(
        cupom =>
            cupom.vendedor_id === null
        );

    const atribuidos =
        cupons.filter(
        cupom =>
            cupom.vendedor_id !== null
        );

    if (disponiveis.length === 0) {
        listaCuponsDisponiveis.innerHTML =
        "<p>Nenhum cupom disponível.</p>";
    } else {
        listaCuponsDisponiveis.innerHTML =
        disponiveis
            .map(montarHtmlCupom)
            .join("");
    }

    if (atribuidos.length === 0) {
        listaCuponsAtribuidos.innerHTML =
        "<p>Nenhum cupom atribuído.</p>";
    } else {
        listaCuponsAtribuidos.innerHTML =
        atribuidos
            .map(montarHtmlCupom)
            .join("");
    }
  }

  tituloCuponsAtribuidos.addEventListener(
    "click",
    () => {
        const estaAberto =
        areaCuponsAtribuidos.style.display
        !== "none";

        areaCuponsAtribuidos.style.display =
        estaAberto
            ? "none"
            : "block";
    }
    );


  btnGerarCupons.addEventListener(
    "click",
    async () => {

      const quantidade =
        Number(
          quantidadeCupons.value
        );

      if (
        !Number.isInteger(quantidade) ||
        quantidade < 1 ||
        quantidade > 100
      ) {
        msgGerarCupons.textContent =
          "Informe uma quantidade entre 1 e 100.";

        msgGerarCupons.style.color =
          "#8a1f1f";

        return;
      }

      const ok = confirm(
        `Deseja gerar ${quantidade} ` +
        `${
          quantidade === 1
            ? "cupom"
            : "cupons"
        }?`
      );

      if (!ok) return;

      try {
        msgGerarCupons.textContent =
          "Gerando cupons...";

        msgGerarCupons.style.color =
          "";

        await apiPostAuth(
          "/admin/cupons-desconto/gerar",
          {
            quantidade
          }
        );

        msgGerarCupons.textContent =
          "Cupons gerados com sucesso!";

        msgGerarCupons.style.color =
          "#2f5e46";

        await carregarDados();

      } catch (err) {
        console.error(err);

        msgGerarCupons.textContent =
          "Erro ao gerar cupons.";

        msgGerarCupons.style.color =
          "#8a1f1f";
      }
    }
  );


  window.gerenciarVinculoCupom =
    async function (cupomId) {

      const cupom =
        cuponsCarregados.find(
          c => c.id === cupomId
        );

      if (!cupom) {
        alert(
          "Cupom não encontrado."
        );

        return;
      }

      const vendedoresAtivos =
        vendedoresCarregados.filter(
          v => v.ativo
        );

      if (
        vendedoresAtivos.length === 0
      ) {
        alert(
          "Não há parceiros/vendedores ativos cadastrados."
        );

        return;
      }

      const opcoes =
        vendedoresAtivos
          .map(
            v =>
              `${v.id} - ${v.nome}`
          )
          .join("\n");

      const mensagem =
        (
          cupom.vendedor_id
            ? (
                "Informe o ID do novo parceiro/vendedor.\n\n" +
                "Digite 0 para remover o vínculo.\n\n"
              )
            : (
                "Informe o ID do parceiro/vendedor.\n\n"
              )
        ) +
        opcoes;

      const resposta =
        prompt(
          mensagem,
          cupom.vendedor_id || ""
        );

      if (resposta === null) {
        return;
      }

      const valor =
        resposta.trim();

      if (
        cupom.vendedor_id &&
        valor === "0"
      ) {
        const ok = confirm(
          "Deseja remover o vínculo deste cupom?"
        );

        if (!ok) return;

        try {
          await apiPutAuth(
            `/admin/cupons-desconto/${cupomId}/vendedor`,
            {
              vendedor_id: null
            }
          );

          await carregarDados();

        } catch (err) {
          console.error(err);

          alert(
            "Erro ao remover vínculo."
          );
        }

        return;
      }

      const vendedorId =
        Number(valor);

      if (
        !Number.isInteger(vendedorId) ||
        vendedorId <= 0
      ) {
        alert(
          "Informe um parceiro/vendedor válido."
        );

        return;
      }

      const vendedorExiste =
        vendedoresAtivos.some(
          v => v.id === vendedorId
        );

      if (!vendedorExiste) {
        alert(
          "Parceiro/vendedor não encontrado."
        );

        return;
      }

      try {
        await apiPutAuth(
            `/admin/cupons-desconto/${cupomId}/vendedor`,
            {
            vendedor_id: vendedorId
            }
        );

        const vendedorSelecionado =
            vendedoresAtivos.find(
            v => v.id === vendedorId
            );

        await carregarDados();

        alert(
            "Atribuição efetuada com sucesso para o parceiro/vendedor " +
            `${vendedorSelecionado?.nome || ""}!`
        );

        } catch (err) {
        console.error(err);

        alert(
          "Erro ao alterar vínculo do cupom."
        );
      }
    };


  window.alterarStatusCupom =
    async function (
      cupomId,
      novoStatus
    ) {

      const texto =
        novoStatus
          ? "reativar"
          : "desativar";

      const ok =
        confirm(
          `Deseja realmente ${texto} este cupom?`
        );

      if (!ok) return;

      try {
        await apiPutAuth(
          `/admin/cupons-desconto/${cupomId}/status?ativo=${novoStatus}`,
          {}
        );

        await carregarDados();

      } catch (err) {
        console.error(err);

        alert(
          "Erro ao alterar status do cupom."
        );
      }
    };


  tituloCuponsDisponiveis.addEventListener(
    "click",
    () => {
        const estaAberto =
        areaCuponsDisponiveis.style.display
        !== "none";

        areaCuponsDisponiveis.style.display =
        estaAberto
            ? "none"
            : "block";
    }
    );


  btnLocalizarCupom.addEventListener(
    "click",
    () => {
        const buscaAberta =
        boxBuscaCupom.style.display
        !== "none";

        if (buscaAberta) {
        boxBuscaCupom.style.display =
            "none";

        buscaCupom.value = "";

        listaResultadoBuscaCupom.innerHTML =
            "";

        return;
        }

        boxBuscaCupom.style.display =
        "block";

        buscaCupom.focus();
    }
    );


  buscaCupom.addEventListener(
    "input",
    () => {
        buscaCupom.value =
        buscaCupom.value
            .toUpperCase()
            .replace(
            /[^A-Z0-9]/g,
            ""
            )
            .slice(0, 5);

        const termo =
        buscaCupom.value.trim();

        if (!termo) {
        listaResultadoBuscaCupom.innerHTML =
            "";

        return;
        }

        const filtrados =
        cuponsCarregados.filter(
            cupom =>
            String(cupom.codigo || "")
                .toUpperCase()
                .includes(termo)
        );

        if (filtrados.length === 0) {
        listaResultadoBuscaCupom.innerHTML =
            "<p>Nenhum cupom encontrado.</p>";

        return;
        }

        listaResultadoBuscaCupom.innerHTML =
        filtrados
            .map(montarHtmlCupom)
            .join("");
    }
    );


  await carregarDados();

})();