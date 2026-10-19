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
- Apenas um pagamento canônico por caso e valor integral BRL são associados. Corpo do webhook não decide aluno, pagamento ou valor. Casos parciais/múltiplos, identidades divergentes e falhas de consulta retornam não-2xx para conferência/reentrega, sem inferir vínculos.
- Eventos de caso não são inseridos como IDs de pagamento na inbox. Esse ramo é síncrono e depende da reentrega MP em caso de falha; não cria uma fila nova. Falhas persistentes exigem acompanhamento operacional no MP e nos logs HTTP.
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
