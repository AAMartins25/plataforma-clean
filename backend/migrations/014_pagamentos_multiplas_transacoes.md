# Transações de uma mesma preferência

Não executar migrations anteriores automaticamente. A migration 014 é aditiva:
nenhum UPDATE/DELETE de pagamentos, nenhum preenchimento ou agrupamento histórico.
Registros existentes mantêm origem NULL. Cada nova transação legítima aponta
diretamente para a raiz; IDs MP já vinculados são imutáveis.
Exige PostgreSQL 14 ou superior (testada em PostgreSQL 15).

## Diagnósticos prévios (somente leitura)

Confirmar projeto/banco efetivamente usado pelo backend e proteção recuperável
antes de autorizar qualquer escrita. Não publicar credenciais.

```sql
SELECT current_database(), current_schema(), version();
SELECT table_name, column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('pagamentos', 'oportunidades_compra')
ORDER BY table_name, ordinal_position;

SELECT mp_payment_id, count(*) AS quantidade, array_agg(id ORDER BY id) AS ids
FROM public.pagamentos WHERE mp_payment_id IS NOT NULL
GROUP BY mp_payment_id HAVING count(*) > 1;

SELECT p.id, p.oportunidade_id
FROM public.pagamentos p LEFT JOIN public.oportunidades_compra o
  ON o.id = p.oportunidade_id
WHERE p.oportunidade_id IS NOT NULL
  AND (o.id IS NULL OR o.usuario_id <> p.usuario_id OR o.curso_id <> p.curso_id);

SELECT conname, pg_get_constraintdef(oid), convalidated
FROM pg_constraint WHERE conrelid = 'public.pagamentos'::regclass;
SELECT indexname, indexdef FROM pg_indexes
WHERE schemaname = 'public' AND tablename = 'pagamentos';
SELECT tgname, tgenabled, pg_get_triggerdef(oid)
FROM pg_trigger WHERE tgrelid = 'public.pagamentos'::regclass AND NOT tgisinternal;
```

Interromper diante de duplicidades de mp_payment_id, vínculo comercial inválido,
objetos homônimos incompatíveis, esquema diferente de public, falta de permissões
DDL ou impossibilidade de recuperação. Não mesclar registros por semelhança.

## Aplicação futura, somente após autorização

1. Confirmar proteção recuperável e diagnósticos. Reservar janela curta: o script
   usa ALTER TABLE e índice transacional, com locks; tamanho da tabela pode exigir
   janela maior. Não aumentar timeouts automaticamente.
2. Aplicar exclusivamente `014_pagamentos_multiplas_transacoes.sql` por uma conexão
   administrativa. O arquivo contém BEGIN/COMMIT, lock_timeout 5s e statement_timeout
   60s. Se ocorrer erro, executar ROLLBACK na mesma conexão e investigar. Tudo deve
   ser revertido; não prosseguir com deploy.
3. Validar estrutura com as consultas acima. Confirmar coluna integer nullable,
   sem default, FK sem cascade, índice de origem, índice único parcial e trigger.
   Confirmar que pagamentos antigos continuam sem origem e mantêm seus IDs.
4. Implantar o código apenas após a migration. O código novo consulta a coluna,
   portanto não é compatível com banco ainda não atualizado. O código antigo
   aceita a coluna aditiva; evitar coexistência prolongada durante o deploy, pois
   instâncias antigas continuam rejeitando novas tentativas com HTTP 409.
5. Validar retorno, webhook assinado e revalidação em ambiente de homologação,
   sem pagamento real. Não executar reembolsos automáticos.

Após disponibilizar transações filhas, rollback de código para versão antiga
perde a capacidade de reconhecer suas referências externas. Preferir correção
progressiva; não remover coluna/linhas/índice para tentar reverter.

## Vínculo confiável e históricos

A API GET /v1/payments/{id} fornece a identidade e os dados financeiros. Para
criar outra tentativa, GET /merchant_orders/{order.id} deve comprovar id da ordem,
preference_id da raiz, external_reference e presença do payment_id em payments.
Se faltar essa prova, responder erro sem criar linha. Documentação oficial:
https://www.mercadopago.com.br/developers/pt/reference/online-payments/checkout-pro-preferences/merchant-orders/get-merchant-order/get

Históricos sem oportunidade identificada continuam processáveis individualmente,
mas não ganham associações presumidas. Reembolsos e contestações continuam ligados
ao pagamento específico; uma cobrança duplicada não ganha período de acesso.
O recálculo ignora ocorrências conhecidas sem concessão (COBRANCA_DUPLICADA e
APROVACAO_FORA_PRAZO), preservando a exigência de conferência para compras antigas
realmente sem histórico. As listagens administrativas expõem origem, oportunidade
e ocorrência, sem esconder aprovações duplicadas. Nenhum estorno é disparado.
Consultas repetidas preservam os estados locais REFUND_REQUESTED,
REFUND_IN_PROCESS, REFUNDED, REFUND_DENIED e REFUND_ERROR. A reconciliação
registra separadamente o estado confiável do provedor em mp_status, sem conceder
novo acesso nem confirmar automaticamente uma devolução manual. Conflitos de
identidade ou vínculo financeiro continuam sendo rejeitados.
O histórico mantém a situação do acesso ao curso e passa a expor separadamente
a identidade e a ocorrência da transação, sem associar novo período à duplicidade.

## Testes locais

Usar exclusivamente PostgreSQL local descartável, banco `compras_test_*`.
`COMPRAS_TEST_DATABASE_URL` nunca deve receber uma URL de produção. A fixture
limpa o schema public desse banco isolado. API Mercado Pago sempre simulada.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q -p no:cacheprovider backend/test_transacoes_mp.py
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q -p no:cacheprovider backend/test_transacoes_concorrencia_pg.py backend/test_compras_concorrencia_pg.py
```

A segunda chamada exige COMPRAS_TEST_DATABASE_URL local de teste previamente
definida. Cobrir schema antigo, reaplicação idempotente, abortos sem escrita,
restrições diretas, concorrência com conexões independentes e rollback de negócio.

## Resultado da validação desta implementação

- Suíte principal: 161 testes de backend aprovados, incluindo 24 testes em
  PostgreSQL 15 descartável (21 de transações/migration e 3 de concorrência de compras).
- Frontend: 59 testes aprovados de compra, retorno, Meus Cursos e cupons.
- Rodada adicional de regressão: 36 aprovados e 7 falhas em
  `test_concessao_admin.py`, por comparação de timedelta com MagicMock. As mesmas
  7 falhas foram reproduzidas executando a função admin_criar_acesso extraída de
  HEAD. Sua AST é idêntica à implementação atual; nenhum ajuste nessa função
  ou nesses testes antigos foi incluído. A concessão administrativa também foi
  validada pelos testes com banco isolado da suíte principal.
- Sintaxe Python e git diff --check aprovados. Há avisos de depreciação já
  existentes nas dependências; não foram alteradas dependências nesta etapa.
- Nenhuma chamada ao Mercado Pago real, envio de e-mail, alteração de produção,
  commit, push ou deploy. PostgreSQL de teste encerrado e removido.

Antes da publicação, revisar a pendência dos testes antigos de concessão. A
migration e o código continuam sujeitos à autorização explícita de implantação.
