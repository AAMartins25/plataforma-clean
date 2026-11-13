# Seis ajustes pontuais da home

Base: origin/main `474fbb6f724c5033d9cec8b5afae82d770630ddc`.
Worktree: `/tmp/resumao-home-ajustes`, branch `ajustes-home-pontuais`.

## Resultado por solicitação

1. Padding superior reduzido de 16 para 10 px no mobile e de 22 para 14 px acima de 600 px. Padding inferior, detalhes do fundo e linhas de navegação preservados. Redução de posição da marca confirmada em relação à versão anterior, inclusive autenticado.
2. Centro do botão coincide com o centro do texto Resumão Online. O deslocamento corresponde à metade da soma da largura do livro e do espaçamento livro/nome. As medidas responsivas são compartilhadas via variáveis CSS exclusivas da home, mantendo intactos o símbolo, suas proporções, seu espaçamento e a centralização do slogan.
3. Fonte de Minha Área aumentada em 1 px: 17 px no mobile e 18 px nas demais telas. Dimensões, ícone, peso, cores, gradiente e handlers mantidos.
4. SVG próprio com três livros empilhados horizontalmente substitui somente o ícone de Cursos disponíveis. Texto, alinhamento e expansão/recolhimento preservados.
5. Verificado o renderizador existente: já exibe órgão/UF e ano antes do cargo, com hierarquia e cores solicitadas, quando recebe metadados. Mantido sem alterações em app.js. Testes ampliados para múltiplos cartões, cargos extensos e metadados parciais ou ausentes; nenhum dado inferido a partir do nome.
6. Refinado apenas o SVG do carro: silhueta mais baixa, rodas pretas circulares, cockpit aberto, proteção atrás do piloto, aerofólios traseiro e dianteiro e velocidade atrás do carro. Orientação, viewBox, dimensões externas, posição, bandeira e distância entre elementos preservados.

## API e limites

Consulta HTTP GET somente leitura a `https://plataforma-quality-backend.onrender.com/cursos-publicos` retornou HTTP 200, com os campos `id`, `nome`, `ativo`, `publicado`. A resposta pública está registrada em `api-publica-confirmada.json`.

Faltam `orgao` (ou localização), `uf`, `ano`, `cargo`. O endpoint em `backend/app/main.py` confirma a projeção limitada a esses quatro campos públicos; o modelo Curso contém os campos opcionais cargo, orgao, ano e uf, mas não são expostos pelo endpoint público. Nenhuma alteração de backend, banco ou nomes oficiais foi realizada. Assim, o curso atual continua exibindo o nome oficial como fallback. A apresentação resumida depende de a API futuramente fornecer os metadados confirmados, mediante autorização separada para qualquer alteração de backend.

A versão em origin/main não contém animação do conjunto carro/bandeira: não há CSS animation, SVG animate ou lógica JavaScript associada. Nenhuma animação foi removida ou acrescentada. A bandeira permaneceu idêntica.

Nenhuma captura externa veio anexada nesta mensagem. A referência verificável utilizada foi a versão atual de origin/main e os seis ajustes textuais solicitados.

## Validação renderizada

Chromium/Chrome for Testing 158.0.8127.18. Quatro larguras × visitante/autenticado. As oito capturas completas e quatro capturas com metadados explícitos foram inspecionadas visualmente: sem sobreposições, cortes ou transbordamento horizontal. Testes de geometria com tolerância menor que 0,5 px, preservação do gap livro/nome, slogan e ausência de colisão dos controles. Comparação automática com as medidas anteriores:

| Largura | Estado | Centro nome (px) | Centro botão (px) | Diferença (px) | Redução superior (px) |
| --- | --- | --- | --- | --- | --- |
| 320 | Visitante | 192.000 | 192.000 | 0.000 | 6 |
| 320 | Autenticado | 192.000 | 192.000 | 0.000 | 6 |
| 390 | Visitante | 227.000 | 227.000 | 0.000 | 6 |
| 390 | Autenticado | 227.000 | 227.000 | 0.000 | 6 |
| 768 | Visitante | 433.000 | 433.000 | 0.000 | 8 |
| 768 | Autenticado | 433.000 | 433.000 | 0.000 | 8 |
| 1366 | Visitante | 732.000 | 732.000 | 0.000 | 8 |
| 1366 | Autenticado | 732.000 | 732.000 | 0.000 | 8 |

Capturas `referencia-*` usam metadados explícitos simulados exclusivamente nos testes, incluindo dois cartões e cargo extenso. Não representam metadados recebidos atualmente de produção. Os testes funcionais do navegador utilizam APIs e sessões simuladas, sem login em conta real ou transações financeiras.

Teste Chromium aprovado: pesquisa, visibilidade e limite de cursos, Mais/Menos, expansão pelo teclado, nomes oficiais e escape de HTML, navegação para curso-info, atendimento, Minha Área como visitante/aluno/admin/múltiplos perfis, retorno, saída com confirmação, estados vazio/erro e rodapés dinâmicos. As cinco combinações adicionais de metadados parciais/ausentes não inventam informações.

Seis suítes de regressão aprovadas: compras, Meus Cursos, sessão, autenticação tardia, retorno de pagamento e perfis de acesso. `node --check` e `git diff --check` aprovados.

Conferência de preservação por comparação de código: marca e slogan, handlers do cabeçalho, Localizar, Atendimento, bandeira, rodapé e scripts inline idênticos. Sem alterações em CSS global, app.js, backend, administração ou área do aluno. O workspace original e a main local foram preservados. Nenhuma instalação adicional foi necessária. Sem deploy no Render.

## Arquivos

- `site-html/css/home-publica.css`: apenas geometria do cabeçalho, deslocamento e fonte do botão, com variáveis responsivas locais.
- `site-html/index.html`: SVG dos livros empilhados, SVG do carro e versão de cache do CSS.
- `site-html/test-home-publica-browser.cjs`: novas medidas e cenários de metadados.
- Esta pasta: relatório, resposta pública, medições anteriores/posteriores e 12 capturas completas.

## Reprodução

```sh
PLAYWRIGHT_MODULE=/tmp/resumao-visual-tools/node_modules/playwright \
CHROMIUM_BIN=/home/codespace/.cache/ms-playwright/chromium-1254/chrome-linux64/chrome \
HOME_BEFORE_MEASUREMENTS=auditorias/ajustes-home-20261113/measurements-antes.json \
HOME_TEST_ARTIFACTS=/tmp/resumao-home-ajustes-validacao \
node site-html/test-home-publica-browser.cjs

node --test site-html/test-compras.cjs site-html/test-meus-cursos.cjs \
  site-html/test-sessao.cjs site-html/test-auth-tardio.cjs \
  site-html/test-retorno-pagamento.cjs site-html/test-perfis-acesso.cjs
```
