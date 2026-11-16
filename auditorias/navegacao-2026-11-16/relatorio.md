# Navegação e identificação — 16/11/2026

Base retomada: `0da3e5a` (padronização prévia da Home, preservada).
Trabalho realizado na worktree isolada `/tmp/resumao-navegacao-20261116`.
O checkout original e suas alterações locais não foram usados como base nem modificados.

## Implementação

- Estilos compartilhados em `site-html/css/style.css`, limitados ao cabeçalho organizado e aos três controles existentes.
- Compensação das escalas locais de fonte, mantendo as dimensões efetivas de Meus Cursos em cada largura.
- O organizador conserva os elementos de link/botão, destinos, eventos, rótulos acessíveis e regras de ocultamento. Não cria controles de navegação.
- Os textos originais ficam preservados para medir o layout anterior. O estilo exibe os símbolos equivalentes da referência.
- O espaço vazio do cabeçalho absorve as diferenças de tamanho, com nova medição em resize, mudança de identificação e carregamento de fontes. A altura continua automática.
- O espaço originalmente reservado ao nome é mantido para evitar deslocar outros elementos; nomes extensos usam o tratamento de truncamento da referência.
- Teoria calcula os títulos com a apresentação original antes de reaplicar a navegação, preservando fontes, posição e altura também com títulos extensos.

## Validação

A matriz usa os cabeçalhos extraídos dos HTML reais, com suas folhas de estilo locais e o organizador real. Compara com os arquivos do commit original, sem consultar APIs de produção. Inclui estado anônimo, identificação tardia com nome curto e nome longo em 1366, 768, 390 e 320 px. Não é uma homologação de todas as funções de backend.

- 60 páginas, 720 combinações, 2.340 verificações de aparência: aprovadas.
- Dimensões, fontes, cores, espaçamentos internos e estilo do nome/botões comparados com Meus Cursos.
- Altura dos cabeçalhos comparada com a base; tolerância de arredondamento de 0,035 px.
- Quantidade de controles, destinos, handlers e visibilidade preservados; ausência de rolagem horizontal e controles dentro do cabeçalho.
- Cliques após organização e resize; foco visível por teclado: aprovados.
- Repetição final nas oito páginas com escala própria: 96 combinações e 340 verificações de aparência aprovadas.
- Teoria em página completa, com APIs simuladas: 24 cenários nas quatro larguras, seis tipos de título, três modos de estudo, paginação, foco e oito redimensionamentos aprovados. Altura, fontes e posição dos títulos idênticas à referência original.
- Sete suítes existentes de sessão, autenticação tardia, carregamento, permissões, Meus Cursos e título de Revisões: aprovadas.
- Inspeção visual de capturas nas quatro larguras. As quatro imagens incluídas mostram os cabeçalhos isolados.

O teste existente de Teoria foi atualizado para comparar com o layout vigente completo. A referência antiga removia o módulo de títulos, usava fontes anteriores à densidade atual e exigia uma alternância de bloco externo que já não existe. A nova regressão compara altura, posição e fontes com a base completa e mantém as verificações de paginação, modos, acessibilidade, cortes e sobreposições.

O teste de contexto administrativo de cursos não foi usado como evidência: requer fixtures locais do CKEditor que não estão disponíveis neste ambiente. Não houve alterações no editor, nas APIs nem no fluxo administrativo de cursos.

## Reprodução

Com Playwright instalado e um executável Chromium disponível:

```bash
NAV_BASE_REF=0da3e5a CHROMIUM_EXECUTABLE=/caminho/chromium node site-html/test-navegacao-browser.cjs
HEADER_BASE_REF=0da3e5a CHROMIUM_BIN=/caminho/chromium node site-html/test-teoria-cabecalho.cjs
node --test site-html/test-meus-cursos.cjs site-html/test-meus-cursos-carregamento.cjs site-html/test-carregamento-sessao.cjs site-html/test-sessao.cjs site-html/test-auth-tardio.cjs site-html/test-revisoes-cabecalho.cjs site-html/test-perfis-acesso.cjs
```

A matriz aceita `NAV_PAGES` para repetir páginas específicas, `NAV_REPORT` para resultados JSON e `NAV_SCREENSHOTS` para capturas. Os módulos Playwright podem ser localizados via `NODE_PATH` ou `PLAYWRIGHT_MODULE`.

## Páginas abrangidas

- `assuntos.html`
- `aula.html`
- `cartoes.html`
- `checkout.html`
- `curso-expirado.html`
- `curso-info.html`
- `curso.html`
- `cursos.html`
- `dashboard.html`
- `desempenho-expirado.html`
- `disciplinas-expirado.html`
- `disciplinas.html`
- `fale-com-a-clean.html`
- `index.html`
- `interatividade-assuntos.html`
- `interatividade-disciplinas.html`
- `interatividade.html`
- `login.html`
- `mensagens-prof-expirado.html`
- `mensagens-prof.html`
- `meus-dados.html`
- `minha-area.html`
- `minhas-anotacoes-expirado.html`
- `minhas-anotacoes.html`
- `minhas-vendas.html`
- `pagamento_erro.html`
- `pagamento_pendente.html`
- `pagamento_sucesso.html`
- `pastas.html`
- `questoes-assuntos.html`
- `questoes-criticas.html`
- `questoes-disciplinas.html`
- `questoes-ia.html`
- `questoes-pratica.html`
- `quiz.html`
- `redefinir-senha.html`
- `reembolso.html`
- `register.html`
- `revisoes-programadas.html`
- `sprint.html`
- `teoria.html`
- `admin/admin-mensagens-questoes.html`
- `admin/admin-questoes-aluno.html`
- `admin/admin-questoes-pratica.html`
- `admin/alunos.html`
- `admin/assuntos.html`
- `admin/atendimento.html`
- `admin/aula-conteudo.html`
- `admin/aulas.html`
- `admin/contestacoes.html`
- `admin/criar-curso-completo.html`
- `admin/cupons.html`
- `admin/curso-disciplinas.html`
- `admin/cursos.html`
- `admin/disciplinas.html`
- `admin/index.html`
- `admin/pagamentos.html`
- `admin/perfis.html`
- `admin/reembolsos.html`
- `admin/vendedores.html`
