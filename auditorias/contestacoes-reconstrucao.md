# Contestações de Cartão — reconstrução

Worktree: `/tmp/resumao-contestacoes-reconstruido-20261019`.
Branch: `reconstruir-contestacoes-20261019`, base `df7cd16` (`origin/main` na criação).
O workspace principal não foi copiado nem alterado. Reutilizados modelos, constraints e schemas da base, originados da implementação histórica `3e3ea20`; os antigos handlers não foram restaurados em bloco.

## Invariantes

- Registro do MP e estado CHARGED_BACK não confirmam devolução nem bloqueiam acesso.
- Confirmação e bloqueio exigem administrador e ações separadas, auditadas e idempotentes.
- Nenhuma chamada de estorno, transferência, envio de documentação ou outra operação financeira externa é feita.
- Bloqueio grava apenas os campos de auditoria da contestação. Não modifica pagamentos, contratações, períodos, cache AcessoCurso ou concessões.
- Direitos são avaliados sobre períodos originais. Outras compras, períodos de renovação (inclusive futuros), ADMIN e demonstrações permanecem independentes.
- Sem cronologia contínua, vínculos completos ou cobertura conhecida do cache agregado: CONFERENCIA_NECESSARIA, sem bloqueio.
- A autorização não tolera falha de consulta ao banco como autorização de acesso.

## Pontos de autorização

`validar_contexto_estudo` aplica `contrato_vigente`; cobre disciplinas, aulas, baterias, questões, Sprints, Revisões, anotações, mensagens e rotas de desempenho/revisões que recebem o validador. Dashboard `/me/cursos`, `/me.tem_cursos`, aquisição/renovação e acesso direto à pasta de teoria usam a mesma lógica. QuizIA, CartoesIA e QuestoesIA legados passaram a exigir autenticação e direito efetivo ao curso; escritas exigem administrador, e seus consumidores enviam o token access_token existente. Histórico de atividades não é apagado.

## Endpoints

- GET `/admin/contestacoes?pagina=1` — 50 itens, dados de aluno/curso/pagamento/transação/caso, auditoria financeira e disponibilidade de bloqueio.
- POST `/admin/contestacoes/{id}/confirmar-devolucao` — `referencia_devolucao` (1–255 caracteres após trim) e `confirmacao_devolucao=true`. Referência repetida retorna sucesso; referência conflitante não substitui auditoria.
- POST `/admin/contestacoes/{id}/bloquear-acesso?confirmacao_bloqueio=true` — exige confirmação anterior completa e histórico comprovado. Repetição preserva a primeira decisão.

Locks na ordem usuário → raiz → transação → contestação, compatíveis com resolver_transacao. Ambos os POSTs usam a barreira financeira existente. A listagem não reserva uma autorização: o POST refaz a conferência sob locks.

## Recebimento Mercado Pago

- Notificações payment continuam usando inbox, pausa, recuperação e transação atômica existentes.
- `resolver_transacao` registra idempotentemente CHARGED_BACK antes do commit; cobre webhook, confirmação e revalidação. Estados manuais de reembolso continuam protegidos pela conciliação existente.
- O mesmo receptor assinado aceita `topic_chargebacks_wh` e `chargebacks`. Valida data.id assinado e igualdade com o corpo. Consulta GET `/v1/chargebacks/{id}`, depois GET `/v1/payments/{id}`; reutiliza validações de recebedor, identidade, moeda, valor e locks do pagamento.
- Apenas um pagamento canônico por caso e valor integral BRL são associados. Corpo do webhook não decide aluno, pagamento ou valor. Casos parciais/múltiplos, identidades divergentes e falhas de consulta permanecem como pendências duráveis, sem inferir vínculos nem autorizar bloqueio.
- Eventos específicos usam a inbox existente antes de qualquer consulta externa, com namespace `c:` separado dos pagamentos `w:`. Para esses eventos, a coluna legada `payment_id` contém o ID do recurso caso; o dispatcher nunca o envia à API de pagamentos. Metadados selecionados em `resultado` identificam tipo, envelope, escopo, pagamentos canônicos, valor/moeda e histórico de tentativas, sem payload, assinatura ou token. O ACK ocorre somente após persistência. Falha ao armazenar retorna 503. A recuperação administrativa existente reconhece o novo namespace.
- Uma linha por pagamento e mp_dispute_id único, conforme constraints existentes. Atualizações/repetições não sobrescrevem referência, datas ou administradores das decisões. Segundo caso diferente na mesma compra exige conferência.
- Status ABERTA significa caso registrado na plataforma. mp_status exibe o estado canônico do pagamento. Não é inferido desfecho financeiro do caso ou confirmação de devolução a partir de flags do provedor.

Referências de contrato do provedor:
- https://www.mercadopago.com.br/developers/en/docs/checkout-pro-preferences/chargebacks/notifications
- https://www.mercadopago.com.br/developers/en/docs/checkout-pro-preferences/chargebacks/manage

## Produção

Nenhuma migration nova é necessária ao código: usa `contestacoes_pagamento`, `periodos_acesso_pagamento`, `contratacoes_curso`, `concessoes_acesso_admin` e demais estruturas já modeladas. Conferir disponibilidade das constraints/índices e permissões existentes antes da integração. Não houve acesso ao Supabase nem execução de migrations.

Habilitar o evento de chargebacks na integração MP e manter o segredo de assinatura configurado, após aprovação de publicação. Validar o formato de notificações contratado na conta (Payments/Preferences API); Orders API não é implementada aqui. Casos parciais ou que agrupem pagamentos permanecem para conferência externa, sem bloqueio presumido. Pendência de DEFAULT PRIVILEGES de supabase_admin continua fora deste patch.

## Validação

Testes específicos e regressão com SQLite em memória e provedor simulado; testes de concorrência com PostgreSQL 17 local descartável e schema exclusivo por execução, criado por fixtures ORM, sem executar scripts de migração. Testes UI em Node verificam autorização, escaping, ações separadas, bloqueio indisponível em históricos ambíguos, cliques duplicados e falhas sem repetição automática de POST.

Resultado final: 287 testes de backend/regressão aprovados; 3 testes concorrentes PostgreSQL aprovados (incluindo renovação concorrente ao bloqueio); 22 testes UI aprovados (8 de contestações e 14 de reembolsos). `git diff --check`, compilação Python e sintaxe JavaScript aprovados. Avisos de depreciação existentes não impedem execução. Nenhuma chamada real a banco de produção ou operações financeiras reais.

## Correção da auditoria final — escopo e pendências

- CHARGED_BACK genérico e mp_dispute_id isolado não comprovam valor integral. `conferir_escopo` exige evento específico concluído com comprovação canônica integral, pagamento único e valor/moeda iguais aos da compra. Registros antigos sem essa evidência permanecem para conferência; não há backfill presumido.
- Qualquer evento pendente/ERRO do mesmo caso, ou pendente associado canonicamente ao mesmo pagamento, impede nova ação de bloqueio, mesmo que exista prova integral anterior. Não desfaz automaticamente decisões históricas já executadas.
- Confirmação financeira continua independente; a interface solicita conferência da devolução integral no extrato. A confirmação jamais cria uma comprovação de escopo nem executa bloqueio.
- O efeito do caso e a prova de escopo têm commit único. Reprocessamentos não substituem datas/administradores da decisão e mantêm as tentativas anteriores no JSON de auditoria.
- Pendências sem compra identificada aparecem no Admin separadamente, sem formulário financeiro ou botão de bloqueio. Não é necessário associar um aluno por presunção para preservar o evento.
- PostgreSQL usa advisory lock transacional por caso tanto na recepção quanto na decisão manual. Nova pendência recebida antes da decisão impede que ela utilize uma prova antiga.
- Nenhuma estrutura nova ou migration é necessária: são usados os campos existentes de `notificacoes_mp`, inclusive `resultado` JSON, e os estados/fonte já permitidos pela migration 016. Não foi executada migration.
- Publicar todos os consumidores de inbox com esta versão antes de habilitar o evento específico no MP; uma versão antiga não reconhece o namespace de caso.
- Casos parciais/múltiplos e envelopes sem identidade comprovável exigem conferência administrativa. Falhas transitórias podem ser recuperadas pelo controle financeiro existente, consultando novamente o provedor; não há override de escopo para habilitar bloqueio inseguro.

Validação da correção: 43 testes direcionados de backend aprovados (42 no conjunto de escopo/pendências/fluxos afetados e 1 novo de recuperação administrativa); 1 teste novo de concorrência PostgreSQL aprovado; 9 testes da interface de contestações aprovados. Não foi repetida a regressão geral. Os testes existentes de contestações foram adequados para fixtures com comprovação canônica explícita; um teste da inbox de pagamentos foi repetido porque o dispatcher compartilhado mudou. Conferências de sintaxe e `git diff --check` aprovadas. Nenhum acesso ao Supabase, migration ou operação financeira real.
