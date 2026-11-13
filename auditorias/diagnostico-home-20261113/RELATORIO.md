# Diagnóstico da home e correção do cabeçalho

Base: origin/main `df07c349baf6a5c6dd816653a656c74c601db0f7`.
Worktree `/tmp/resumao-home-diagnostico`, branch `diagnostico-header-publico`.
Consulta final da API: **2026-11-13 22:31:46 UTC**, HTTP 200.

## Causa comprovada antes da alteração

O Chromium carregou a página pública implantada em `https://plataforma-quality.onrender.com/index.html`. Os corpos de style.css, home-publica.css?v=4, app.js e cabecalho.js eram byte a byte idênticos aos arquivos de origin/main antes desta execução. Os hashes estão em `antes/diagnostico.json`. Não é falta de deploy nem cache desatualizado nesses arquivos.

O cabeçalho real usa grid, sem altura fixa e com min-height calculado em 0. Padding superior efetivo de 4 px no mobile e 6 px nas demais telas, padding inferior de 26/32 px, margens do logo/contêineres em 0. As regras exclusivas da home prevalecem sobre as media queries e as regras compartilhadas.

A diferença surge quando cabecalho.js organiza a identificação autenticada: a identidade ocupa a primeira linha da grade inteira, e a marca fica na segunda. `.ro-identity` herda de style.css **min-height:44px**, embora home-publica.css já defina height:auto. Portanto, a redução de height não remove a altura mínima. Além disso, `::after` do nome ampliado fica com display:block e visibility:hidden, ainda no fluxo (15,59 px + 2 px de margem), e a grade acrescenta 16/18 px entre linhas. O mínimo de 44 px é a parcela dominante.

Assim, a posição inicial da marca autenticada era **4 + 44 + 16 = 64 px** no mobile e **6 + 44 + 18 = 68 px** no desktop/tablet. Visitantes não têm essa linha e já começam a 4/6 px. Os diagnósticos registram retângulos, display, alturas, min-height, paddings, margens, grid-template-rows, posição, alinhamento e pseudo-elemento dos contêineres efetivamente renderizados.

## Correção aplicada

Somente na home, a identificação textual perde o mínimo interativo de 44 px e o padding interno herdado; sua linha passa a 15 px de texto + 8 px de separação inferior = 23 px. O nome ampliado continua disponível no hover, sobre a mesma linha, fora do fluxo, sem acrescentar uma reserva invisível. O hover foi testado e não altera a posição da marca.

O gap vertical global da grade passa a 0. O intervalo original entre marca e Minha Área é mantido especificamente na margem inferior do contêiner da marca (18 px nas telas maiores, 16 px no mobile). A linha separada de navegação em 320 px mantém 16 px acima de seus controles. Padding superior/inferior não foi reduzido novamente. O problema foi corrigido na linha que realmente consumia o espaço.

A marca autenticada passa para 27 px no mobile e 29 px no desktop/tablet: redução real de **37 e 39 px**. Visitantes permanecem a 4/6 px. Minha Área e slogan continuam centralizados no nome, com diferença horizontal inferior a 0,5 px nos testes. Controles, identificação e marca não se sobrepõem.

## Livro do cabeçalho

Redução proporcional de **12,5% em largura e altura**, preservando o SVG existente e a inclinação:

| Tela | Tamanho anterior | Tamanho novo |
| --- | --- | --- |
| Até 600 px | 56 × 54 px | **49 × 47,25 px** |
| Acima de 600 px | 84 × 76 px | **73,5 × 66,5 px** |

O arquivo SVG compartilhado e o tamanho dos livros dos cartões não foram alterados. O cálculo de alinhamento do botão acompanha a variável de largura do símbolo.

## Medidas antes e depois

Distâncias relativas ao topo da faixa amarela, em CSS pixels. “Marca” é a caixa de `.home-brand-title`; “Texto” é `.home-brand-name`. O tamanho menor do livro também muda discretamente o alinhamento vertical interno do texto. Os retângulos do livro estão nos JSONs completos.

| Largura | Estado | Marca antes | Marca depois | Texto antes | Texto depois | Altura faixa antes | Altura faixa depois |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 320 | Visitante | 4.00 | 4.00 | 6.38 | 4.00 | 151.00 | 146.25 |
| 320 | Identificado | 64.00 | 27.00 | 66.38 | 27.00 | 271.00 | 229.25 |
| 390 | Visitante | 4.00 | 4.00 | 6.38 | 4.00 | 151.00 | 146.25 |
| 390 | Identificado | 64.00 | 27.00 | 66.38 | 27.00 | 257.00 | 215.25 |
| 768 | Visitante | 6.00 | 6.00 | 12.16 | 7.41 | 185.00 | 175.50 |
| 768 | Identificado | 68.00 | 29.00 | 74.16 | 30.41 | 247.00 | 198.50 |
| 1366 | Visitante | 6.00 | 6.00 | 6.73 | 6.00 | 185.00 | 183.53 |
| 1366 | Identificado | 68.00 | 29.00 | 68.73 | 29.00 | 247.00 | 206.53 |

Os oito estados antes/depois foram capturados no Chromium. As oito capturas posteriores foram inspecionadas visualmente em 320, 390, 768 e 1366 px: sem sobreposição ou overflow. A identidade de usuário é fictícia e controlada para a medição; não se autenticou em contas reais. Os arquivos públicos implantados foram carregados pelo navegador, e a resposta pública consultada foi reproduzida para isolar a geometria, sem enviar tokens fictícios ao backend ou fazer escritas.

## API de produção e curso ainda com nome completo

A consulta pública real `GET https://plataforma-quality-backend.onrender.com/cursos-publicos` retornou:

```json
{
  "id": 39,
  "nome": "RESUMÃO PROF EDUC INFANTIL ALVORADA-RS 26",
  "ativo": true,
  "publicado": true,
  "cargo": null,
  "orgao": null,
  "uf": null,
  "ano": null
}
```

A versão implantada já disponibiliza as quatro propriedades corretas, mas **cargo, orgao, uf e ano estão todos null no ID 39**. A implementação da rota retorna diretamente esses quatro atributos do modelo Curso. O frontend lê exatamente essas mesmas propriedades; não há incompatibilidade de nomes ou estrutura. Quando todos estão vazios, renderizarCursosPublicos usa corretamente `c.nome` como fallback. A seta permanece ausente e o link aponta para curso_id=39, mantendo o nome oficial.

**O problema dos cursos não está resolvido em produção**: depende de preencher metadados confirmados no registro correto. Não foi feita alteração de dados, tentativa de inferência pelo nome nem escrita em produção.

A Gestão lê `/admin/cursos`, edita pelo ID selecionado com `PUT /cursos/{id}`, e a listagem pública consulta a mesma entidade Curso. Um novo teste HTTP real em SQLite descartável verificou a sequência para o ID 39: campos vazios em Gestão e público; edição pela rota usada pela Gestão; leitura pública dos mesmos valores no mesmo ID, sem mudar o nome oficial. Isso confirma a integração por ID. Não há sessão administrativa de produção nesta execução, portanto **não foi possível confirmar qual registro o usuário editou anteriormente**. Pode-se afirmar que o registro público a conferir é o ID 39, não que uma edição anterior tenha sido feita nele.

## Providência pendente pela Gestão de Cursos

1. Entrar com um administrador autorizado na Gestão de Cursos, página `admin/criar-curso-completo.html`.
2. Selecionar **ID 39 — RESUMÃO PROF EDUC INFANTIL ALVORADA-RS 26**. Se houver nomes iguais, confirmar o ID do item na resposta autenticada de `/admin/cursos` e no valor da seleção; não editar uma cópia ou outro curso.
3. Clicar **Editar curso**, conferir **Cargo**, **Órgão/Entidade**, **Ano** e **UF**, preencher apenas os dados oficialmente confirmados e manter o nome oficial. Não é necessário renomear ou duplicar o curso.
4. Clicar **Salvar curso** e conferir a confirmação. Esse fluxo salva em `/cursos/39`; o botão “Salvar descrição e valores” pertence a outro formulário e não preenche esses metadados.
5. Reconsultar `/cursos-publicos`, localizar `id:39` e confirmar que os quatro campos retornam os valores salvos. Então recarregar a home. A apresentação em duas linhas ocorrerá automaticamente, respeitando o conteúdo efetivamente cadastrado; dados parciais continuam com fallback seguro.

Não se prescrevem valores a partir do nome abreviado nem se executa esse procedimento automaticamente.

## Testes aprovados e preservações

- Suíte Chromium da home: quatro larguras × visitante/autenticado, geometria antes/depois, tamanho do livro, livro dos cartões preservado, alinhamento de botão e slogan, hover sem deslocamento, controle de expansão, pesquisa, navegação, perfis de acesso, Atendimento, Voltar/Sair, metadados completos/parciais/ausentes, escaping, nomes extensos e rodapés dinâmicos.
- **3 testes backend aprovados**: contrato HTTP público real, consistência Gestão/público por ID e integração HTTP real FastAPI + SQLAlchemy + SQLite descartável + Chromium. Sem JSON simulado na rota pública local. O estado /me dos testes de navegador é simulado, sem contas reais.
- **6 suítes de regressão frontend aprovadas**: compras, Meus Cursos, sessão, autenticação tardia, retorno de pagamento e perfis de acesso.
- `node --check` e `git diff --check` aprovados.
- Sem alteração em app.js, cabecalho.js, backend de produção, banco, migrações, SVG compartilhado, cartões, Localizar, Atendimento, carro, bandeira ou rodapé. Apenas CSS local da home, versão do CSS no index e testes alterados, além destas evidências.
- Workspace original, alterações pendentes e main local preservados. Sem deploy no Render, operação no Supabase ou chamada real de pagamentos.

## Reprodução

```sh
DIAG_ORIGIN=https://plataforma-quality.onrender.com \
DIAG_OUT=/tmp/header-producao-antes \
node auditorias/diagnostico-home-20261113/diagnosticar-header.cjs

DIAG_OUT=/tmp/header-local-depois \
node auditorias/diagnostico-home-20261113/diagnosticar-header.cjs

PLAYWRIGHT_MODULE=/tmp/resumao-visual-tools/node_modules/playwright \
CHROMIUM_BIN=/home/codespace/.cache/ms-playwright/chromium-1254/chrome-linux64/chrome \
HOME_BEFORE_MEASUREMENTS=auditorias/home-api-metadados-20261113/medidas-regressao.json \
node site-html/test-home-publica-browser.cjs

PYTHONPATH=/tmp/resumao-home4-python PUBLIC_HOME_BROWSER=1 \
PLAYWRIGHT_MODULE=/tmp/resumao-visual-tools/node_modules/playwright \
CHROMIUM_BIN=/home/codespace/.cache/ms-playwright/chromium-1254/chrome-linux64/chrome \
python -m pytest -q -s --disable-warnings backend/test_cursos_publicos.py
```
