# Intermediário seguro — construção local isolada — 23/10/2026

## Identidade e limites

Worktree: `/workspaces/resumao-intermediario-seguro`, destacado exatamente em `cdba603e9a8d3a3a04a77fc03863ad41c93c1a93` (HEAD continua sendo o commit-base, não um novo commit do patch). Nenhum commit, push, deploy, alteração no Render/Supabase, credencial ou banco persistente foi realizado. A migração 022 foi executada somente em bancos efêmeros de testes.

O worktree e os logs da primeira execução em `/tmp` desapareceram entre sessões. A implementação foi reconstruída no caminho acima e os resultados deste relatório correspondem às execuções repetidas, cujos logs estão em `evidencias/`. O registro antigo de worktree em /tmp não foi limpo globalmente.

O workspace principal não foi substituído: a verificação por SHA-256 dos 6.979 arquivos rastreados/não ignorados do manifesto desta retomada confirmou zero arquivos alterados, removidos ou adicionados. As únicas mudanças de metadados Git foram as necessárias à criação do worktree autorizado.

## Patch de aplicação: seis arquivos

| Arquivo | Mudança restrita e justificativa |
| --- | --- |
| `backend/app/main.py` | Dependência Geral nas quatro gravações; tipo em `/me`; criação administrativa compatível com 022, auditoria e revalidação transacional. Recusa atribuição de tipo por payload e booleanos inválidos. |
| `backend/app/models.py` | Apenas `Usuario` recebe tipo, booleano não nulo e CHECK definitivo; acrescenta `AuditoriaPerfilAdmin`. Todos os demais modelos publicados são preservados. |
| `backend/app/schemas.py` | Apenas `UsuarioResponse` recebe tipo e validação da combinação. Sem schemas de atribuição. |
| `backend/app/admin_intermediario.py` (novo) | Validação da combinação, exigência exclusiva de Geral e releitura do autor sob advisory lock transacional/row lock. Não consulta flags para liberar restritos. |
| `backend/migrations/022_tipos_administrador.sql` (novo) | Coluna, backfill dos gerais, CHECK e tabela de auditoria, em transação com limites de espera. Preserva restritos false/tipo em reaplicação e recusa estados inválidos. |
| `site-html/js/admin.js` | Somente dois consumidores: criação de curso e associação curso/disciplina passam de `apiPost` para `apiPostAuth`. Disciplina e assunto já enviavam autenticação. |

A normalização de datas foi excluída do patch da aplicação por não pertencer ao escopo. O tratamento publicado permanece intacto; a fixture SQLite emula o cast de DATE que PostgreSQL aceita.

Representação: true/admin_geral; false/admin_prod; false/admin_adm; false/NULL. Nenhum fallback promove restritos. Os restritos permanecem sem competência administrativa, mesmo com ADMIN_RESTRITOS_HABILITADOS=1. Seus direitos próprios de aluno/vendedor continuam independentes.

As quatro operações protegidas são POST /cursos, POST /disciplinas, POST /cursos/{curso_id}/disciplinas/{disciplina_id} e POST /assuntos. Leitura pública de metadados e os fluxos acadêmicos compartilhados não foram reformulados.

Não foram transportados `permissoes.py`, `perfis_admin.py`, endpoints de atribuição, seleção de tipos, guarda/navegação diferenciada ou mudanças do painel. A versão não fornece caminho de ativação: não é uma remoção da barreira com liberação por flag. A substituição da barreira da implementação completa continua pendente.

## Preservação do publicado e revisão por trechos

O teste estrutural verifica que apenas seis funções existentes de main mudaram: criar_curso, criar_disciplina, associar_disciplina_ao_curso, criar_assunto, me e admin_criar_aluno. Há uma nova dependência e um import. O conjunto de decorators/rotas permanece igual ao publicado, sem endpoints administrativos novos.

Todos os outros modelos/schemas permanecem iguais em AST. auth.py, database.py, checkout_seguro.py, transacoes_mp.py, direitos_acesso.py, contestacoes.py, pausa_financeira.py, emails_pagamentos.py, cupons_admin.py, desempenho.py, revisoes.py e juridico.py permanecem idênticos à base. Também foram preservados manutenção, app.js, login.js, perfis.js e o criador de curso completo.

Assim permanecem presentes reformulação de mensagens, campos/índice de identidade de checkout, validações de direitos acadêmicos, e-mails e isolamento de notificações que divergiam no workspace principal. Nenhuma correção desses domínios foi incorporada.

## Arquivos de teste

- `backend/test_auth_jwt.py` e `backend/test_compras_fluxo.py`: somente fixtures, acrescentando explicitamente tipo_admin=admin_geral aos administradores antigos. Não foi alterada a expectativa funcional.
- Novos: `backend/test_admin_intermediario_seguro.py`, `backend/test_admin_intermediario_diff.py`, `backend/test_admin_intermediario_pg.py` e `site-html/test-admin-intermediario.cjs`.
- Documentação e evidências: este relatório e diretório `evidencias/`, incluindo logs, runner SQLite, manifesto e patch para revisão. Não fazem parte do comportamento da aplicação.

## Resultados repetidos nesta retomada

| Execução | Resultado | Evidência |
| --- | --- | --- |
| Matriz HTTP e integridade + comparação estrutural | 39 passaram (35 funcionais, quatro estruturais) | seguranca-diff.log |
| Regressão publicada de 15 arquivos | 467 passaram | regressao-publicada.log |
| PostgreSQL 17.6 | Seis passaram | postgresql.log |
| Frontend de sete arquivos | 84 passaram | frontend.log |
| Cupons/concessão, intermediário e base intacta | Ambos: 30 passaram, nove falharam, mesmos testes | cupons-concessao.log e base-cupons-concessao.log |
| Frontend compras, intermediário e base intacta | Ambos: nove passaram, dois falharam, mesmos testes | compras-frontend.log e base-compras-frontend.log |

Não somar execuções repetidas da base às contagens do intermediário. Há avisos de depreciação que não foram corrigidos.

Os 467 cobrem autenticação/JWT, aulas, assuntos, checkout seguro, compras, transações, contestações, pausa/isolation financeiro, mensagens/reformulação, e-mails, duplicação, revalidação e reembolso manual. Cupons e vendedores foram exercitados na execução complementar.

A matriz específica verifica visitante, aluno, vendedor, Geral, Produção e Administrativo; payloads válidos nas quatro gravações; todas as leituras /admin; tentativas de escrita nas quatro seções; JWT com claims administrativos antigos; login real; cadastro público sem elevação; indisponibilidade dos endpoints de atribuição; combinações inválidas no banco e na resposta; criação auditada; rollback da criação se a auditoria falha. Todas as tentativas dos restritos são feitas com flags ligadas, sem conceder poderes.

## PostgreSQL e concorrência

Contêiner exclusivo `resumao-intermediario-seguro-test`, PostgreSQL 17.6, sem rede, armazenamento tmpfs e socket Unix exclusivo. Cada teste cria e remove seu próprio banco; nunca usa DATABASE_URL ou dados de produção. Não há mudança de credencial persistente.

Processos Python independentes, com engines, pools e conexões próprios, exercitam a criação administrativa real. Um processo lê o autor como Geral; outro revoga seu tipo ou o inativa; a criação é então recusada com 403 após a releitura, sem novo usuário/auditoria. Duas criações simultâneas persistem corretamente os dois usuários e os dois registros de auditoria.

A migração é testada em backfill, reaplicação, estados inválidos, rollback em erro e massa fictícia de 60 usuários, com cinco administradores que permanecem Gerais, sem alteração de hashes, perfis, acessos, pagamentos e vínculos de vendedores.

O teste de pool verifica liberação de advisory locks transacionais em commit, rollback e devolução da conexão. Parâmetros Psycopg 3/SQLAlchemy seguem o padrão publicado (prepare_threshold=None, pre_ping), em READ COMMITTED. Isso NÃO equivale a ensaio do Supavisor. Session Pooler real de homologação, reconexão e implantação parcial permanecem pendentes.

Não há gestão nova de remoção/rebaixamento de administradores neste intermediário. Testes de revalidação não autorizam escritores SQL externos nem substituem a futura proteção do último Geral na versão completa.

## Pendências legadas: não corrigidas

As nove falhas de test_concessao_admin.py são exatamente as mesmas na base intacta: concessão sem acesso, preservação de prazo, reativação expirada/inativa, acesso sem vencimento, fuso, usuário inexistente, curso inexistente e conflito de banco. O diagnóstico inclui mocks incompatíveis com a consulta atual e operações entre timedelta e MagicMock. Não demonstram regressão deste patch.

As duas falhas de test-compras.cjs são `payload preserva demonstração e cupom` e `renovação mantém contrato e não oferece demo`; reproduzidas na base intacta. Os arquivos de negócio envolvidos não foram alterados.

A fixture SQLite de cupons carece de BTRIM, usado pelo schema já publicado. O runner temporário preservado em evidencias/runner_sqlite.py emula apenas essa função PostgreSQL nas duas bases, sem alterar arquivos de negócio ou expectativas. Os 28 testes de cupons passam com esse suporte. A conversão DATE da fixture específica tem finalidade semelhante e foi confirmada também em PostgreSQL real.

Esses resultados não constituem aprovação de todas as funcionalidades históricas; as falhas foram preservadas e não consideradas bloqueios automáticos desta mudança.

## Compatibilidade frontend/backend

| Frontend | Backend | Resultado/limite |
| --- | --- | --- |
| Novo | Publicado | Bearer e mesmo payload aceitos pelos quatro handlers originais, extraídos do Git e executados em SQLite efêmero. Não torna o backend antigo seguro. |
| Novo | Intermediário | Geral autenticado aceito; demais perfis recusados. |
| Antigo | Intermediário | Consumidores que não enviam token recebem 401; falha segura, mas interrupção funcional até atualizar o script. Outros consumidores já autenticados permanecem compatíveis. |
| Antigo | Publicado | Vulnerabilidade conhecida continua até substituir o backend. Não é recuperação aceitável após ativar restritos. |

Por isso, homologar e publicar primeiro somente o frontend compatível, verificar caches e o script efetivamente carregado; depois coordenar migração/backend em manutenção. O deploy automático do frontend após futuro push precisa ser considerado antes de autorizar esse push.

## Homologação, recuperação e próximos passos

O intermediário é candidato a BASE de recuperação compatível com 022, com restritos bloqueados. Ainda não é versão de recuperação publicada/certificada: faltam revisão humana do patch, identificação de artefato imutável por SHA após autorização de commit e ensaio operacional de recuperação.

Sequência futura, não executada: revisar patch isolado; homologar frontend antigo/novo e cache; testar em cópia sanitizada e Session Pooler de homologação; construir/identificar artefato recuperável; aprovar backup restaurável e manutenção; publicar frontend compatível; interromper/drenar TODOS os escritores antigos; aplicar 022; iniciar manualmente todos os processos intermediários no Render; verificar cinco Gerais, vínculos, auditoria, negativas HTTP e saúde; manter restritos bloqueados.

Não iniciar este modelo contra banco sem 022: create_all não acrescenta a coluna na tabela existente. Durante a migração, o código antigo também não deve continuar criando administradores sem tipo. Em falha parcial, permanecer em manutenção até recuperar artefato compatível; não remover CHECK, apagar tipos ou promover restritos. cdba603 não é o alvo de recuperação recomendado.

Para futuramente substituir a barreira antiga sem desativar postgres: comprovar inventário/retirada de versões inseguras, ausência de escritores externos, drenagem, limitação operacional efetiva de rollback/deploy e disponibilidade do piso seguro, incluindo processos sobrepostos e falhas. Uma instância configurada ou uma flag não comprovam essas garantias. Nenhuma delas foi presumida ou alterada nesta construção.

Aguardar autorização para qualquer etapa seguinte. Sem commit, push, deploy ou alteração em produção.
