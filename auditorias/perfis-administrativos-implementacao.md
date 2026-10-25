# Implementação local dos perfis administrativos

Data: 25/10/2026. Alterações locais, sem commit, push ou publicação.

## Comportamento implementado

| Área administrativa | Geral | Produção | Administrativo |
|---|---|---|---|
| Cursos, conteúdo, questões, cópias, publicação e configuração de curso | Sim | Sim | Não |
| Pagamentos, revalidação, atendimento e mensagens de questões | Sim | Não | Sim |
| Alunos / Usuários e concessão de acesso | Sim | Não | Não |
| Vendedores, cupons, reembolsos e contestações | Sim | Não | Não |
| Gerenciar perfis | Sim | Não | Não |
| Ferramentas operacionais de manutenção financeira e emails | Sim | Não | Não |

Alunos / Usuários foi movido visualmente para Comercial. QR Codes e Comissões continuam com os botões de recurso em desenvolvimento já existentes, exclusivos do Geral.

A autorização usa a identidade atual do banco. Apenas Geral possui `is_admin=true`; Produção e Administrativo mantêm `is_admin=false`. As leituras administrativas de conteúdo reconhecem Produção, preservando a validação de matrícula/contexto para alunos e para acessos pessoais de vendedores.

Os corpos das operações financeiras existentes foram preservados; os testes estruturais normalizam apenas as guardas para verificar essa preservação.

## Gestão de perfis

`GET /admin/usuarios/perfis?q=...` pesquisa usuários existentes. `PUT /admin/usuarios/{id}/tipo-admin` atribui `admin_geral`, `admin_prod`, `admin_adm` ou revoga com `null`. Somente Geral pode executar essas operações.

O usuário é criado sem administração na tela Alunos / Usuários. A atribuição administrativa ocorre em Gerenciar perfis. A API de criação de aluno rejeita tentativas de atribuir administração por esse caminho.

A alteração usa a tabela existente `auditoria_perfis_admin`, na mesma transação da atualização. Revalida o autor após adquirir o bloqueio transacional compartilhado do PostgreSQL, bloqueia o alvo e impede remover o último Geral ativo. Falhas desfazem a transação. Reenvio do mesmo perfil não gera auditoria duplicada.

Foram completados os contratos já chamados pela interface e ausentes no backend local: pesquisa/gestão de perfis, seleção de disciplinas/assuntos de questões e criação/edição/ativação/descredenciamento de vendedores. Esses handlers não alteram comissões, cupons ou regras de pagamento. O prazo existente de acesso do vendedor após descredenciamento continua sendo aplicado por `/me`.

## Frontend

Todas as 19 páginas de `site-html/admin/` carregam a guarda no cabeçalho. A página fica oculta até a validação de `/me`; páginas indevidas redirecionam. Os auxiliares de requisições administrativas aguardam a guarda, inclusive os próprios da tela de mensagens. O dispatcher de questões também aguarda autorização.

Menus são filtrados por área; login, Minha Área e Entrar e estudar reconhecem os dois perfis restritos. Retorno pelo histórico e troca de sessão revalidam a guarda. Scripts afetados nas páginas administrativas usam uma nova chave de cache. O asset histórico 022 foi preservado e deixou de ser a referência das páginas atuais.

As páginas são arquivos estáticos: a guarda controla navegação/renderização no navegador. A proteção dos dados e das operações é feita no backend, independentemente de JavaScript ou menus.

## Validação local

- Backend, conteúdo, autenticação, mensagens e perfis: 331 testes aprovados no lote consolidado.
- Verificação final de perfis, criação/login de vendedor, concessão e duplicação: 86 testes aprovados após os últimos ajustes.
- PostgreSQL descartável, sem rede: 3 testes aprovados de concorrência e revalidação do autor.
- Aceites jurídicos e concessão administrativa em SQLite: 17 testes aprovados.
- Frontend: 144 testes aprovados em 10 arquivos Node, incluindo sessão, login, conteúdo, cupons, reembolsos e contestações.
- Chromium real: 76 combinações de páginas/perfis aprovadas e formulário de atribuição/troca/revogação aprovado. API inteiramente interceptada, sem chamadas ao Render.
- Regressão financeira com provedores simulados: 225 testes aprovados (117,93 s).
- `git diff --check` e verificação sintática Python/JavaScript aprovados.

Os lotes têm testes em comum; seus números não representam uma soma de testes únicos. Suítes históricas que exigem migrações ou bancos previamente populados não foram executadas.

As fixtures usam SQLite em memória. A fixture PostgreSQL exige explicitamente `/tmp/resumao-perfis-matriz-pg` e cria/remove apenas bancos `perfis_matriz_*` novos. Nenhum script de migração é executado. A adaptação BTRIM no conftest apenas reproduz no SQLite a função usada pelas constraints existentes, como o runner SQLite histórico já fazia.

Reprodução principal:

```sh
python -m pytest backend/test_perfis_matriz.py backend/test_admin_intermediario_seguro.py backend/test_admin_intermediario_diff.py backend/test_concessao_admin.py backend/test_duplicar_curso.py -q
RESUMAO_PERFIS_PG_SOCKET=/tmp/resumao-perfis-matriz-pg python -m pytest backend/test_perfis_concorrencia_pg.py -q
node site-html/test-perfis-acesso.cjs
node site-html/test-auth-tardio.cjs
node site-html/test-perfis-browser.cjs
```

O teste de navegador usa o Chromium local indicado por `RESUMAO_TEST_CHROMIUM`, ou o caminho padrão documentado no próprio teste.

## Preparação da publicação definitiva

O usuário confirmou posteriormente as sete consultas de diagnóstico executadas no Supabase, com estrutura pós-022 e cinco Gerais. A confirmação está registrada em `evidencias/diagnostico-pos022-confirmado.json`, sem repetição das consultas.

O empacotamento definitivo é descrito em `preparacao/PUBLICACAO-PERFIS-DEFINITIVOS.md`. O manifesto e os pacotes intermediários foram preservados como histórico. Nenhuma nova migração é necessária. Publicação, cache do ambiente servido e quaisquer alterações em produção continuam sujeitos à autorização posterior.

## Inventário exato de arquivos desta implementação

### Backend e suporte

- `backend/app/admin_intermediario.py`
- `backend/app/contestacoes.py`
- `backend/app/cupons_admin.py`
- `backend/app/main.py`
- `backend/app/pausa_financeira.py`
- `backend/app/perfis_admin.py`
- `backend/app/vendedores_admin.py`
- `backend/conftest.py`
- `backend/test_aceites_juridicos.py`
- `backend/test_admin_intermediario_diff.py`
- `backend/test_admin_intermediario_seguro.py`
- `backend/test_admin_reembolsos.py`
- `backend/test_assuntos_proprios_admin.py`
- `backend/test_aulas_admin.py`
- `backend/test_compras_fluxo.py`
- `backend/test_concessao_admin.py`
- `backend/test_contestacoes_concorrencia_pg.py`
- `backend/test_contestacoes_reconstruido.py`
- `backend/test_copias_concorrencia_pg.py`
- `backend/test_cupons_admin.py`
- `backend/test_cupons_concorrencia_pg.py`
- `backend/test_duplicar_curso.py`
- `backend/test_mensagens_prof.py`
- `backend/test_pausa_financeira.py`
- `backend/test_perfis_concorrencia_pg.py`
- `backend/test_perfis_matriz.py`
- `backend/test_questoes_pratica_patch.py`
- `backend/test_reembolso_integrado.py`
- `backend/test_reembolso_manual_fluxo.py`
- `backend/test_reembolso_manual_pg.py`
- `backend/test_reformular_conversa_postgres.py`
- `backend/test_revalidacao.py`
- `backend/test_transacoes_concorrencia_pg.py`
- `backend/test_transacoes_mp.py`

### Frontend e seus testes

- `site-html/admin/admin-mensagens-questoes.html`
- `site-html/admin/admin-questoes-aluno.html`
- `site-html/admin/admin-questoes-pratica.html`
- `site-html/admin/alunos.html`
- `site-html/admin/assuntos.html`
- `site-html/admin/atendimento.html`
- `site-html/admin/aula-conteudo.html`
- `site-html/admin/aulas.html`
- `site-html/admin/contestacoes.html`
- `site-html/admin/criar-curso-completo.html`
- `site-html/admin/cupons.html`
- `site-html/admin/curso-disciplinas.html`
- `site-html/admin/cursos.html`
- `site-html/admin/disciplinas.html`
- `site-html/admin/index.html`
- `site-html/admin/pagamentos.html`
- `site-html/admin/perfis.html`
- `site-html/admin/reembolsos.html`
- `site-html/admin/vendedores.html`
- `site-html/js/admin-acesso.js`
- `site-html/js/admin.js`
- `site-html/js/app.js`
- `site-html/js/login.js`
- `site-html/js/perfis.js`
- `site-html/login.html`
- `site-html/minha-area.html`
- `site-html/test-admin-intermediario.cjs`
- `site-html/test-auth-tardio.cjs`
- `site-html/test-perfis-acesso.cjs`
- `site-html/test-perfis-browser.cjs`

### Documentação

- `auditorias/perfis-administrativos-implementacao.md`

As entradas não rastreadas `artefatos/` e `preparacao/diagnostico022_leitura.sql` já existiam e não foram alteradas por esta implementação.
