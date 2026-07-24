(async function () {

  const nomeVendedor =
    document.getElementById(
      "nomeVendedor"
    );

  const percentualComissao =
    document.getElementById(
      "percentualComissao"
    );

  const btnCalcularComissao =
    document.getElementById(
      "btnCalcularComissao"
    );

  const listaCupons =
    document.getElementById(
      "listaCupons"
    );

  const totalVendas =
    document.getElementById(
      "totalVendas"
    );

  const detalhesTotalVendas =
    document.getElementById(
      "detalhesTotalVendas"
    );

  const totalVendasEfetivas =
    document.getElementById(
      "totalVendasEfetivas"
    );

  const detalhesVendasEfetivas =
    document.getElementById(
      "detalhesVendasEfetivas"
    );

  const totalVendasAConfirmar =
    document.getElementById(
      "totalVendasAConfirmar"
    );

  const detalhesVendasAConfirmar =
    document.getElementById(
      "detalhesVendasAConfirmar"
    );

  const comissaoEfetivada =
    document.getElementById(
      "comissaoEfetivada"
    );

  const detalhesComissaoEfetivada =
    document.getElementById(
      "detalhesComissaoEfetivada"
    );

  const comissaoAConfirmar =
    document.getElementById(
      "comissaoAConfirmar"
    );

  const detalhesComissaoAConfirmar =
    document.getElementById(
      "detalhesComissaoAConfirmar"
    );


  let dadosVendedor = null;
  let dadosVendas = null;


  function escapeHtml(valor) {
    return String(
      valor ?? ""
    )
      .replace(
        /&/g,
        "&amp;"
      )
      .replace(
        /</g,
        "&lt;"
      )
      .replace(
        />/g,
        "&gt;"
      )
      .replace(
        /"/g,
        "&quot;"
      )
      .replace(
        /'/g,
        "&#039;"
      );
  }


  function formatarMoeda(valor) {
    const numero =
      Number(valor || 0);

    return numero.toLocaleString(
      "pt-BR",
      {
        style: "currency",
        currency: "BRL"
      }
    );
  }


  function formatarValorVenda(
    valorCents
  ) {
    const numero =
      Number(
        valorCents || 0
      ) / 100;

    return numero.toLocaleString(
      "pt-BR",
      {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
      }
    );
  }


  function obterNomeExibicao(
    nomeCompleto
  ) {
    const partes =
      String(
        nomeCompleto || ""
      )
        .trim()
        .split(/\s+/)
        .filter(Boolean);

    if (partes.length === 0) {
      return "-";
    }

    if (partes.length === 1) {
      return partes[0];
    }

    return (
      partes[0] +
      " " +
      partes[
        partes.length - 1
      ]
    );
  }


  function normalizarListaCupons() {
    if (
      !dadosVendas ||
      !Array.isArray(
        dadosVendas.cupons
      )
    ) {
      return [];
    }

    return dadosVendas.cupons;
  }


  function montarCursosDoCupom(
    cursos
  ) {
    if (
      !Array.isArray(cursos) ||
      cursos.length === 0
    ) {
      return `
        <div
          style="
            margin-top:6px;
            margin-left:18px;
            font-size:.86rem;
            opacity:.75;
          "
        >
          Nenhuma venda neste cupom.
        </div>
      `;
    }

    return cursos
      .map(
        curso => `
          <div
            style="
              margin-top:6px;
              margin-left:18px;
              padding-left:4px;
              font-size:.86rem;
              line-height:1.3;
            "
          >
            ${escapeHtml(
              curso.nome_curso ||
              "Curso não identificado"
            )}
            (R$ ${escapeHtml(
              formatarValorVenda(
                curso.valor_cents
              )
            )} cada):
            ${escapeHtml(
              curso.quantidade ?? 0
            )}
          </div>
        `
      )
      .join("");
  }


  function montarLinhasPorCupom(
    dados,
    campoValor,
    campoCursos,
    grupo,
    formatador = null
  ) {
    if (
      !Array.isArray(dados) ||
      dados.length === 0
    ) {
      return "";
    }

    return dados
      .map(
        (
          item,
          indice
        ) => {

          const codigo =
            item.codigo_cupom ||
            item.codigo ||
            "-";

          const valor =
            item[
              campoValor
            ] ?? 0;

          const valorExibido =
            formatador
              ? formatador(valor)
              : valor;

          const cursos =
            Array.isArray(
              item[
                campoCursos
              ]
            )
              ? item[
                  campoCursos
                ]
              : [];

          const idConteudo =
            `cupom_${grupo}_${indice}`;


          return `
            <div
              class="assunto"
              style="
                cursor:pointer;
              "
            >

              <div
                class="cupom-vendas-trigger"
                data-grupo="${escapeHtml(
                  grupo
                )}"
                data-alvo="${escapeHtml(
                  idConteudo
                )}"
              >
                <b>
                  ${escapeHtml(
                    codigo
                  )}
                </b>

                (${escapeHtml(
                  valorExibido
                )})
              </div>


              <div
                id="${escapeHtml(
                  idConteudo
                )}"
                class="cupom-vendas-conteudo"
                data-grupo="${escapeHtml(
                  grupo
                )}"
                style="
                  display:none;
                "
              >
                ${montarCursosDoCupom(
                  cursos
                )}
              </div>

            </div>
          `;
        }
      )
      .join("");
  }


  function configurarSanfonaCupons(
    container
  ) {
    if (!container) {
      return;
    }

    const gatilhos =
      container.querySelectorAll(
        ".cupom-vendas-trigger"
      );


    gatilhos.forEach(
      gatilho => {

        gatilho.addEventListener(
          "click",
          function () {

            const grupo =
              gatilho.dataset.grupo;

            const alvoId =
              gatilho.dataset.alvo;

            const alvo =
              document.getElementById(
                alvoId
              );

            if (!alvo) {
              return;
            }


            const estaAberto =
              alvo.style.display
              !== "none";


            // Fecha todos os cupons
            // abertos do mesmo grupo.
            const outros =
              document.querySelectorAll(
                `.cupom-vendas-conteudo[data-grupo="${grupo}"]`
              );

            outros.forEach(
              item => {
                item.style.display =
                  "none";
              }
            );


            // Se o item clicado já
            // estava aberto, permanece
            // fechado.
            if (estaAberto) {
              return;
            }


            alvo.style.display =
              "block";

          }
        );

      }
    );
  }


  function renderizarDadosGerais() {
    const cupons =
      normalizarListaCupons();


    if (nomeVendedor) {
      nomeVendedor.textContent =
        obterNomeExibicao(
          dadosVendedor?.nome
        );
    }


    if (listaCupons) {

      if (cupons.length === 0) {

        listaCupons.textContent =
          "Nenhum cupom vinculado.";

      } else {

        listaCupons.textContent =
          cupons
            .map(
              item =>
                item.codigo_cupom ||
                item.codigo
            )
            .filter(Boolean)
            .join(", ");

      }

    }


    if (totalVendas) {
      totalVendas.textContent =
        String(
          dadosVendas
            ?.total_vendas ??
          0
        );
    }


    if (detalhesTotalVendas) {

      detalhesTotalVendas.innerHTML =
        montarLinhasPorCupom(
          cupons,
          "total_vendas",
          "cursos_total",
          "total"
        );

      configurarSanfonaCupons(
        detalhesTotalVendas
      );

    }


    if (totalVendasEfetivas) {
      totalVendasEfetivas.textContent =
        String(
          dadosVendas
            ?.total_vendas_efetivas ??
          0
        );
    }


    if (detalhesVendasEfetivas) {

      detalhesVendasEfetivas.innerHTML =
        montarLinhasPorCupom(
          cupons,
          "vendas_efetivas",
          "cursos_efetivos",
          "efetivas"
        );

      configurarSanfonaCupons(
        detalhesVendasEfetivas
      );

    }


    if (totalVendasAConfirmar) {
      totalVendasAConfirmar.textContent =
        String(
          dadosVendas
            ?.total_vendas_a_confirmar ??
          0
        );
    }


    if (detalhesVendasAConfirmar) {

      detalhesVendasAConfirmar.innerHTML =
        montarLinhasPorCupom(
          cupons,
          "vendas_a_confirmar",
          "cursos_a_confirmar",
          "a_confirmar"
        );

      configurarSanfonaCupons(
        detalhesVendasAConfirmar
      );

    }


    calcularComissoes();
  }


  function calcularComissoes() {
    const percentual =
      Number(
        percentualComissao?.value ||
        0
      );

    const taxa =
      percentual / 100;


    const valorEfetivadoCents =
      Number(
        dadosVendas
          ?.valor_vendas_efetivas_cents ??
        0
      );


    const valorAConfirmarCents =
      Number(
        dadosVendas
          ?.valor_vendas_a_confirmar_cents ??
        0
      );


    const totalComissaoEfetivadaCents =
      Math.round(
        valorEfetivadoCents *
        taxa
      );


    const totalComissaoAConfirmarCents =
      Math.round(
        valorAConfirmarCents *
        taxa
      );


    if (comissaoEfetivada) {

      comissaoEfetivada.textContent =
        formatarMoeda(
          totalComissaoEfetivadaCents /
          100
        );

    }


    if (comissaoAConfirmar) {

      comissaoAConfirmar.textContent =
        formatarMoeda(
          totalComissaoAConfirmarCents /
          100
        );

    }


    const cupons =
      normalizarListaCupons();


    if (detalhesComissaoEfetivada) {

      detalhesComissaoEfetivada.innerHTML =
        cupons
          .map(
            (
              item,
              indice
            ) => {

              const codigo =
                item.codigo_cupom ||
                item.codigo ||
                "-";


              const valorBaseCents =
                Number(
                  item
                    .valor_vendas_efetivas_cents ??
                  0
                );


              const comissaoCents =
                Math.round(
                  valorBaseCents *
                  taxa
                );


              const idConteudo =
                `cupom_comissao_efetiva_${indice}`;


              return `
                <div
                  class="assunto"
                  style="
                    cursor:pointer;
                  "
                >

                  <div
                    class="cupom-vendas-trigger"
                    data-grupo="comissao_efetiva"
                    data-alvo="${idConteudo}"
                  >
                    <b>
                      ${escapeHtml(
                        codigo
                      )}
                    </b>

                    (${escapeHtml(
                      formatarMoeda(
                        comissaoCents /
                        100
                      )
                    )})
                  </div>


                  <div
                    id="${idConteudo}"
                    class="cupom-vendas-conteudo"
                    data-grupo="comissao_efetiva"
                    style="
                      display:none;
                    "
                  >
                    ${montarCursosDoCupom(
                      item.cursos_efetivos
                    )}
                  </div>

                </div>
              `;

            }
          )
          .join("");


      configurarSanfonaCupons(
        detalhesComissaoEfetivada
      );

    }


    if (detalhesComissaoAConfirmar) {

      detalhesComissaoAConfirmar.innerHTML =
        cupons
          .map(
            (
              item,
              indice
            ) => {

              const codigo =
                item.codigo_cupom ||
                item.codigo ||
                "-";


              const valorBaseCents =
                Number(
                  item
                    .valor_vendas_a_confirmar_cents ??
                  0
                );


              const comissaoCents =
                Math.round(
                  valorBaseCents *
                  taxa
                );


              const idConteudo =
                `cupom_comissao_confirmar_${indice}`;


              return `
                <div
                  class="assunto"
                  style="
                    cursor:pointer;
                  "
                >

                  <div
                    class="cupom-vendas-trigger"
                    data-grupo="comissao_confirmar"
                    data-alvo="${idConteudo}"
                  >
                    <b>
                      ${escapeHtml(
                        codigo
                      )}
                    </b>

                    (${escapeHtml(
                      formatarMoeda(
                        comissaoCents /
                        100
                      )
                    )})
                  </div>


                  <div
                    id="${idConteudo}"
                    class="cupom-vendas-conteudo"
                    data-grupo="comissao_confirmar"
                    style="
                      display:none;
                    "
                  >
                    ${montarCursosDoCupom(
                      item.cursos_a_confirmar
                    )}
                  </div>

                </div>
              `;

            }
          )
          .join("");


      configurarSanfonaCupons(
        detalhesComissaoAConfirmar
      );

    }

  }


  async function carregarPagina() {

    try {

      dadosVendedor =
        await apiGetAuth(
          "/me/vendedor"
        );


      dadosVendas =
        await apiGetAuth(
          "/me/vendedor/vendas"
        );


      renderizarDadosGerais();


    } catch (err) {

      console.error(
        "Erro ao carregar área do vendedor:",
        err
      );


      alert(
        "Não foi possível carregar " +
        "os dados de suas vendas."
      );

    }

  }


  if (btnCalcularComissao) {

    btnCalcularComissao.addEventListener(
      "click",
      calcularComissoes
    );

  }


  if (percentualComissao) {

    percentualComissao.addEventListener(
      "input",
      calcularComissoes
    );

  }


  await carregarPagina();

})();