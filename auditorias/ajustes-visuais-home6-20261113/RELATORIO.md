# Seis ajustes visuais pontuais da home

Base: origin/main `ce165073bf4a4f3d7223be8acede89257b412c30`.
Worktree isolada `/tmp/resumao-home-oliva`, branch `home-oliva-ajustes`.

## Ajustes realizados

1. Padding superior de 6 para 4 px no desktop/tablet, de 4 para 2 px no mobile. Separação inferior da identificação de 8 para 2 px. Assim, o estado autenticado sobe mais 8 px, conservando a linha de 15 px do nome, o min-height:0 e o nome ampliado fora do fluxo, sem reintroduzir a reserva indevida de 44 px. Visitantes já começavam a 4/6 px: redução limitada a 2 px, pois retirar 8 a 10 px nesses casos exigiria deslocamento negativo ou corte do logotipo. A separação marca/botão e os controles foram preservados.

2. O histórico anterior à primeira modernização identifica **#2E7D32** como a cor original da marca, em `.home-page header h1 {color:#2e7d32 !important}`. Usado esse valor original em Resumão, conforme a prioridade do pedido; é um verde mais fechado que a aproximação oliva #647D25. Trecho e referência em `cor-original.txt`. Não foi necessário escolher o fallback. Online permanece em **#D99C00**, slogan azul e livro principal com suas cores originais. Tipografia e tamanho do logo não mudaram.

3. Minha Área usa gradiente intermediário **#2278CE → #1E73C8**, borda #1E73C8, hover **#1E73C8 → #1968BA**, texto e ícone #FFFFFF. As cores foram ajustadas em relação ao exemplo #2684E8 para garantir legibilidade: contraste do gradiente normal entre **4,52:1 e 4,84:1** com branco, medido a partir dos valores renderizados e calculado por luminância relativa sRGB. Mantidos dimensões, formato, fonte e alinhamento ao nome.

4. Livros dos cartões reduzidos proporcionalmente em **12,5%**, com colunas ajustadas ao novo tamanho e gaps preservados. SVG, inclinação, check e cores não mudaram:

| Faixa | Antes | Depois |
| --- | --- | --- |
| Até 370 px | 36 × 36 px | 31,5 × 31,5 px |
| 371 a 600 px | 44 × 42 px | 38,5 × 36,75 px |
| Acima de 600 px | 64 × 58 px | 56 × 50,75 px |

O livro principal permanece **49 × 47,25 px** no mobile e **73,5 × 66,5 px** nas telas maiores.

5. Nome/cargo dos cursos e fallback passam para **#17365D**. Primeira linha dos metadados continua em #102D75, menor e semibold; segunda linha mantém tamanho maior e destaque, agora em azul-marinho profundo. Nenhuma mudança em dados, parsing, API ou regras de fallback.

6. Removidos SVG da seta, role button, tabindex, atributos de expansão, handlers de clique/teclado e função alternarCursosDisponiveis. O título mantém os livros empilhados e o alinhamento à esquerda. A lista permanece naturalmente visível e clicar no título não a recolhe. Preservados carregamento, busca, cartões, seleção, navegação e controles existentes de quantidade de cursos. Links antigos com ?cursos=aberto continuam rolando até a lista, sem precisar abri-la.

## Medidas no Chromium

Distância entre o topo amarelo e `.home-brand-title`, em CSS pixels, na mesma sessão de teste antes/depois:

| Largura | Estado | Antes (px) | Depois (px) | Redução (px) |
| --- | --- | --- | --- | --- |
| 320 | Visitante | 4.00 | 2.00 | 2.00 |
| 320 | Autenticado | 27.00 | 19.00 | 8.00 |
| 390 | Visitante | 4.00 | 2.00 | 2.00 |
| 390 | Autenticado | 27.00 | 19.00 | 8.00 |
| 768 | Visitante | 6.00 | 4.00 | 2.00 |
| 768 | Autenticado | 29.00 | 21.00 | 8.00 |
| 1366 | Visitante | 6.00 | 4.00 | 2.00 |
| 1366 | Autenticado | 29.00 | 21.00 | 8.00 |

Minha Área e slogan permanecem alinhados ao centro do texto Resumão Online, com diferença inferior a 0,5 px. Identificação e controles não se sobrepõem à marca ou ao botão. As oito capturas completas posteriores foram inspecionadas visualmente em 320, 390, 768 e 1366 px, visitante/autenticado: sem cortes, sobreposições ou transbordamento horizontal. Foram examinadas também capturas dos cartões com metadados, inclusive cargo extenso.

## Testes aprovados

- Suíte Chromium da home nas oito combinações, verificando medidas anteriores/posteriores, tamanhos dos dois tipos de livro, cores computadas, contraste do botão, hover da identificação sem deslocamento, título sem controles e lista permanentemente visível. Pesquisa, Mais/Menos cursos, navegação de curso, rotas de Minha Área por perfil, Atendimento, Voltar/Sair, nomes extensos, escape de HTML, metadados parciais/ausentes, estados vazio/erro e rodapés dinâmicos aprovados.
- **3 testes backend aprovados**, incluindo integração HTTP real da rota pública local com SQLAlchemy, SQLite descartável e Chromium nas mesmas quatro larguras e estados. Sem alteração de API ou banco de produção; os metadados dessas capturas são dados de teste locais. A identidade /me é simulada nos testes de navegador.
- **6 suítes frontend aprovadas**: compras, Meus Cursos, sessão, autenticação tardia, retorno de pagamento e perfis de acesso.
- `node --check` e `git diff --check` aprovados.

## Preservações e arquivos

Alterações limitadas a `site-html/css/home-publica.css`, `site-html/index.html`, `site-html/test-home-publica-browser.cjs` e esta pasta de evidências. Slogan, livro principal, campo de pesquisa e placeholder, título Localizar curso, Atendimento, carro, bandeira, rodapé, autenticação, acesso, checkout e pagamentos preservados. Sem alterações em backend, banco, migrações, app.js, SVG compartilhado, CSS global ou páginas administrativas e do aluno.

Workspace original, suas alterações pendentes e main local preservados. Reutilizados navegador e ferramentas existentes, sem instalações adicionais. Sem deploy no Render e sem operações no Supabase.

## Reprodução

```sh
PLAYWRIGHT_MODULE=/tmp/resumao-visual-tools/node_modules/playwright \
CHROMIUM_BIN=/home/codespace/.cache/ms-playwright/chromium-1254/chrome-linux64/chrome \
HOME_BEFORE_MEASUREMENTS=auditorias/ajustes-visuais-home6-20261113/measurements-antes.json \
HOME_TEST_ARTIFACTS=/tmp/home6-validacao \
node site-html/test-home-publica-browser.cjs

PYTHONPATH=/tmp/resumao-home4-python PUBLIC_HOME_BROWSER=1 \
PLAYWRIGHT_MODULE=/tmp/resumao-visual-tools/node_modules/playwright \
CHROMIUM_BIN=/home/codespace/.cache/ms-playwright/chromium-1254/chrome-linux64/chrome \
python -m pytest -q -s --disable-warnings backend/test_cursos_publicos.py
```
