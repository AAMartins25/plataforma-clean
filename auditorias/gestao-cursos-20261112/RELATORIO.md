# Entrega — Gestão de Cursos

**Status atual:** o usuário confirmou a execução bem-sucedida da migração 027 no Supabase e autorizou integração por commit/push direto para origin/main. O agente não executou SQL em produção. Publicação no Render permanece manual, backend antes do frontend. As seções anteriores à integração registram o histórico da entrega.

Worktree isolada: `/tmp/gestao-cursos-20261112`.
Branch: `ajustes-gestao-cursos-20261112`.
Base: `origin/main` atualizada, commit `1fa9ad516b972746e196f6c2410a9ef15e3d09ae`.
Sem commit, push, PR, migração no Supabase ou deploy. A main local e os arquivos pendentes do workspace original foram preservados.

## Arquivos de aplicação

- `backend/app/models.py`: seis colunas nullable, produtor por FK para usuarios.id.
- `backend/app/schemas.py`: validação de criação/edição e resposta administrativa separada da pública.
- `backend/app/main.py`: gravação dos metadados/autoria, leitura administrativa autenticada, edição preservando campos omitidos, duplicação com autoria do duplicador.
- `site-html/admin/criar-curso-completo.html`: cinco novos campos, seis filtros, pesquisa e formulário de edição.
- `site-html/js/admin-criar-curso-completo.js`: integração dos novos formulários/lista sem recarregar a página.
- `site-html/js/gestao-cursos.js`: filtragem combinada, pesquisa parcial, ordenação, edição e erros.
- `site-html/css/gestao-cursos.css`: grade responsiva seguindo o padrão visual existente.
- `site-html/admin/cursos.html` e `site-html/js/admin.js`: compatibilidade do formulário simplificado de criação com os campos obrigatórios novos.

## SQL, documentação e testes

- `backend/migrations/027_metadados_cursos.sql`: SQL integral incremental, idempotente, transacional; sem backfill e sem mudança em permissões ou históricos.
- `backend/migrations/027_metadados_cursos.md`: esquema inspecionado, consultas de conferência, ordem de implantação e dependências.
- `backend/test_metadados_cursos.py`: validações, persistência, permissões, produtor, legados e falha de gravação por HTTP.
- `backend/test_migracao027_pg.py`: SQL real em contêiner local descartável.
- `backend/test_duplicar_curso.py`: metadados e autoria adicionados à regressão de cópia integral e preservação dos registros de alunos.
- `backend/test_admin_intermediario_seguro.py`, `backend/test_perfis_matriz.py`, `backend/test_homologacao_local_intermediario.py`: payloads positivos de criação atualizados para o novo contrato. A suíte de homologação PostgreSQL intermediária não foi executada; seu payload foi apenas ajustado.
- `backend/test_assuntos_proprios_admin.py`: fixture completada com tabelas de pagamentos e contestações já consultadas pelo código da base. Sem alteração na regra de acesso.
- `site-html/test-gestao-cursos-browser.py`: página/assets reais no Chromium local com API simulada; permissões verificadas separadamente pela suíte HTTP real em SQLite.
- Este diretório: relatório, logs, `browser.json` e oito capturas (criação/listagem e edição nas quatro larguras).

## Resultados

- **250 aprovados**: `test_metadados_cursos.py`, `test_duplicar_curso.py`, `test_admin_intermediario_seguro.py`, `test_perfis_matriz.py`, `test_aulas_admin.py`. Log: `backend.log`.
- **17 aprovados**: `test_assuntos_proprios_admin.py`. Log: `assuntos.log`.
- **1 aprovado**: migração 027 em PostgreSQL 15, duas aplicações, dados históricos intactos, rejeição de campos e produtor inválidos e rollback em esquema divergente.
- **2 verificações Node aprovadas**: `site-html/test-duplicar-curso.cjs` e `node --test site-html/js/tests/copias-admin.test.cjs`.
- **Chromium aprovado**: 320, 390, 768 e 1366 px, com edição aberta/fechada, sem transbordamento horizontal. Criação, edição, legado, seis filtros simultâneos, pesquisa parcial, ordenação sem distinção de caixa, limpar, seleção, duplicação, exclusão e recuperação de erros; valores de curso são inseridos como texto, sem executar HTML.
- `node --check` nos scripts novos/alterados e `git diff --check` aprovados.

As primeiras tentativas de teste identificaram dependências locais ausentes (`nh3` e `Pillow`) e bloqueio de comunicação local no sandbox. Somente essas dependências já declaradas foram baixadas para `/tmp/gestao-cursos-deps`; o navegador e a imagem PostgreSQL já existiam. A regressão ampliada inicialmente encontrou a fixture incompleta de assuntos, corrigida antes da execução final dos seus 17 testes. Os logs finais contêm avisos de depreciação do projeto.

## Pendências e ordem de publicação

O Supabase real não foi acessado; a conferência do esquema/grants/RLS e execução manual do SQL permanecem para o responsável. Sem pendência funcional conhecida nos fluxos testados. Ano adotado: inteiro de quatro dígitos, de 1000 a 9999. Legados podem manter metadados ausentes; duplicar um legado também preserva essas ausências.

Após aprovação: **conferência no Supabase → SQL 027 manual e verificações → backend Render → frontend da mesma revisão → smoke test autenticado**. Coordenar as gravações da gestão de cursos durante a troca de backend/frontend, pois o backend novo exige os dados que o formulário antigo não envia. Não há alteração em contratação, pagamentos, acessos, desempenho ou revisões.

## Revisão final da migração 027

A pedido do usuário, foram aperfeiçoados somente o SQL da migração, sua documentação e o teste PostgreSQL correspondente. A implementação da aplicação permaneceu inalterada nesta revisão.

- CHECKs homônimos: compatibilidade de expressão verificada pelo mecanismo nativo de mesclagem por herança em duas tabelas temporárias vazias, sem comparações textuais nem substituição de constraints permanentes. A migração requer TEMP no banco. As temporárias são removidas no COMMIT; nenhuma herança é criada sobre `public.cursos`.
- Produtor: preflight de chave referenciável em `usuarios.id`, incluindo PK/UNIQUE ou índice único independente imediato, válido e não parcial. O PostgreSQL continua fazendo a checagem definitiva na criação da FK.
- Validação atualizada: **25 testes aprovados no PostgreSQL 15** e **25 no PostgreSQL 17.6**, ambos locais descartáveis e sem rede. Logs: `migracao027-refino-pg15.log` e `migracao027-refino-pg17.log`. Esta suíte substitui o teste SQL inicial de um caso mencionado acima.
- Cobertura: execução inicial, reaplicação na mesma sessão e em sessões novas, CHECK alterado antes/depois da primeira aplicação, espaços/parênteses diferentes, NO INHERIT/tipo incompatível, coluna/FK incompatíveis, PK/UNIQUE/índice único/INCLUDE compatíveis, chaves ausentes/parciais/compostas/por expressão/adiáveis e índice inválido real, rollback integral, nulos legados e vínculos de alunos, preservação de grants/RLS/view/trigger e ausência de tabelas temporárias após COMMIT.
- Timeouts mantidos: lock 5s e comando 60s. Não há backfill, alteração de funcionalidades ou criação de índices permanentes.

Nenhuma execução no Supabase, integração, commit, push, PR ou publicação nesta revisão. Execução manual e deploy permanecem dependentes da aprovação do usuário.

## Validação final para integração autorizada

O responsável confirmou que executou a migração definitiva 027 no Supabase de produção e conferiu as seis colunas nullable, os cinco CHECKs e a FK, mantendo NOT VALID intencionalmente. A migração não foi reaplicada em produção pelo agente.

- `origin/main` conferida por fetch: continuava em `1fa9ad516b972746e196f6c2410a9ef15e3d09ae`, igual à base da worktree, sem commits posteriores a conciliar.
- **267 testes aprovados** na suíte final de backend: metadados, duplicação, permissões administrativas, matriz de perfis, assuntos e aulas (`integracao-backend.log`). Os avisos de depreciação permanecem no projeto.
- **25 + 25 testes aprovados** da migração em PostgreSQL 15 e 17.6 locais descartáveis, sem rede (`integracao-pg15.log`, `integracao-pg17.log`).
- **Chromium aprovado** novamente nas quatro larguras: 320, 390, 768 e 1366 px, sem transbordamento horizontal (`integracao-browser.log`, `browser.json` e capturas atualizadas). API simulada no navegador; permissões verificadas na suíte HTTP.
- Duplicação e cópia aprovadas nos testes Node existentes; sintaxe dos três scripts alterados e `git diff --check` aprovados.
- Migração definitiva incluída, SHA-256 `7b5361b4aa111d8877a7e419fe9513120568fd8fde42b384444a24487ced5285`.
- Nenhuma alteração funcional adicional nesta etapa. Documentação atualizada para registrar a migração já aplicada pelo usuário. Contêineres e Chromium locais de teste foram encerrados.

A integração por commit/push para `origin/main`, sem PR e sem force push, foi expressamente autorizada pelo usuário. A publicação continua exclusivamente manual pelo responsável, na ordem **backend Render → frontend Render → conferência autenticada dos fluxos**. Não executar novamente a migração como parte dessa publicação.
