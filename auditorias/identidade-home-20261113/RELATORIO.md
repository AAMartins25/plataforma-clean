# Identidade visual da home pública — 13/11/2026

Base: origin/main `70a6adb2dcb0c1c880836897d3bed694467fd927`.
Worktree isolada: `/tmp/resumao-visual-home`, branch `visual-home-quality`.
Workspace original e branch main local preservados. Nenhuma alteração de backend, banco ou pagamento. Sem deploy no Render.

## Implementação e fidelidade

Cabeçalho amarelo-claro em gradiente com ondas discretas, marca azul e dourada, livro/check em SVG próprio compartilhado entre marca e cursos, slogan centralizado e botão azul Minha Área. Identificação, Voltar e Sair preservados em espaços próprios. Cartões brancos com borda superior dourada, alinhamento comum, lupa e link em SVG. Carro de corrida vermelho com velocidade atrás e bandeira quadriculada à direita, sem elementos entre ambos. O gráfico anterior não tinha animação ou eventos associados.

A implementação segue a especificação textual fornecida. A imagem aprovada não foi anexada à conversa nem localizada no repositório; não é possível confirmar equivalência visual exata com essa imagem. As capturas anexas representam a página efetivamente renderizada no Chromium.

Cursos com metadados explícitos exibem localização/UF e ano primeiro, cargo em azul abaixo. Sem esses dados, usam o nome oficial completo, sem inferir dados. Nomes oficiais permanecem na API, no destino da navegação e no título do link; busca, filtros, ordenação e limite de cursos mantidos. A API atual fornece o nome oficial sem os metadados opcionais. As capturas `referencia-*` usam dados simulados explícitos do exemplo solicitado apenas no teste, nunca no catálogo da aplicação.

58 rodapés públicos, administrativos e do aluno substituem somente RO por Quality. Anos fixos dos scripts de rodapé passam a `new Date().getFullYear()`, preservando IDs e mecanismos existentes; `rodape.js` também cobre páginas legadas sem atualização própria. Nenhuma sigla em outro contexto é substituída.

## Validação

- Chromium/Chrome for Testing 158.0.8127.18, sem downloads de navegador.
- Home: 320, 390, 768 e 1366 px, visitante e usuário autenticado com nome longo, Voltar e Sair. Oito capturas completas inspecionadas visualmente: sem sobreposição ou transbordamento horizontal, marca e Minha Área centralizados, texto legível e seções na ordem solicitada.
- Quatro capturas adicionais do exemplo com metadados explícitos, uma em cada largura, também inspecionadas.
- Teste Chromium aprovado: catálogo, curso inativo oculto, Mais/Menos cursos, pesquisa, resultados vazios e erro de API, nomes longos sem espaços, escape de HTML, ordem dos metadados, links de curso com nome oficial, teclado na expansão, atendimento, parâmetro de abertura e sua remoção, destinos de Minha Área para visitante/aluno/admin/múltiplos perfis, limpeza de contexto de compra, Voltar e logout com confirmação.
- 58 rodapés reais extraídos de suas páginas e renderizados com relógio simulado em 2032: todos exibem © 2032 Quality. Caminhos do script conferidos; verificação de ausência de atribuições de ano fixo.
- Seis suítes de regressão aprovadas: `test-compras.cjs`, `test-meus-cursos.cjs`, `test-sessao.cjs`, `test-auth-tardio.cjs`, `test-retorno-pagamento.cjs`, `test-perfis-acesso.cjs`.
- `node --check` dos scripts alterados e `git diff --check`: aprovados.

Testes de navegador usam servidor local e APIs simuladas, incluindo os estados autenticados. Não houve login em conta real, transação de pagamento ou validação ponta a ponta em produção. As regras e handlers de autenticação, acesso, checkout, pagamento e administração não foram modificados.

## Reprodução

```sh
PLAYWRIGHT_MODULE=/tmp/resumao-visual-tools/node_modules/playwright \
CHROMIUM_BIN=/home/codespace/.cache/ms-playwright/chromium-1254/chrome-linux64/chrome \
HOME_TEST_ARTIFACTS=/tmp/resumao-visual-evidencias \
node site-html/test-home-publica-browser.cjs

node --test site-html/test-compras.cjs site-html/test-meus-cursos.cjs \
  site-html/test-sessao.cjs site-html/test-auth-tardio.cjs \
  site-html/test-retorno-pagamento.cjs site-html/test-perfis-acesso.cjs
```

## Arquivos

A lista completa dos arquivos da aplicação e do teste está em [arquivos-aplicacao.txt](arquivos-aplicacao.txt). Esta pasta adiciona o relatório, medições e 12 capturas completas como evidência. Nenhuma dependência ou instalação temporária foi incluída no repositório.
