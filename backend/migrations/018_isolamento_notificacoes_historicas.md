# 018 — isolamento auditável dos testes históricos

Somente criar a tabela notificacoes_mp_isolamentos; nenhuma escrita em pagamentos,
notificações, controle financeiro ou acessos. Não altera migrations anteriores.
Dependências: migration 016 e usuarios(id integer); backend definitivo continua
exigindo 014/015/017. PostgreSQL 17.6 é usado nos testes. SQL transacional,
lock_timeout 5s, statement_timeout 60s, assinatura estrutural validada na reaplicação.
A tabela tem RLS sem políticas públicas, sem sequence, sem acesso PUBLIC/anon/authenticated.
O papel do backend precisa SELECT/INSERT/UPDATE, e BYPASSRLS ou política própria
previamente autorizada; o postgres confirmado tem acesso como proprietário.

## Publicação (ações de produção dependem de autorização separada)

1. Confirmar backup recuperável e RECUPERACAO/geração vigente; Auto-Deploy Off.
2. Conferir homônimos, dependências, privilégios e ausência de locks longos.
3. Executar somente o SQL 018 integral no SQL Editor. Falha: rollback; não adaptar.
4. Validar tabela, oito colunas, oito constraints, PK válida, RLS e privilégios;
   confirmar tabela vazia e modo/geração inalterados. SQL não isola nenhum evento.
5. Publicar o backend revisado manualmente, ainda em RECUPERACAO.
6. Após autorização: POST /admin/financeiro/notificacoes/isolamento com token
   administrativo e {"geracao":2,"motivo":"Decisão do proprietário: eventos de testes históricos"}.
   Endpoint fixa IDs 1,2,3,4,7,8,9,10; campos extras (incluindo IDs ou administrador) são rejeitados; tudo em uma transação, mesma barreira e ordem
   de locks do consumo. Faltas, eventos concluídos, geração obsoleta ou modo diferente
   impedem a operação. Identidade do administrador vem da sessão. Repetição não
   substitui auditoria. Não modifica estado, tentativas, erros ou resultado da inbox.
7. GET /admin/financeiro/notificacoes mostra auditoria e flag isolada. Confirmar
   somente oito isolamentos e igualdade dos pagamentos/acessos e registros originais.
8. Autorizar separadamente NORMAL, com geração atual e conferencia_provedor=true.
   Qualquer outra pendência/erro continua impedindo a retomada. Nunca reabrir no deploy.
9. Compra real controlada: Pix/cartão, webhook, consulta de aprovação e acesso único.

Para retomar um evento isolado: em RECUPERACAO, POST
/admin/financeiro/notificacoes/{id}/isolamento/revogar com geração e motivo;
revogação registra administrador/data/motivo e preserva auditoria inicial. Depois
usar recuperação por ID existente. Reaplicação de isolamento revogado é bloqueada.

Novos eventos, inclusive sobre o mesmo pagamento antigo, não herdam isolamento.
Repetição do mesmo evento de webhook continua apontando para o mesmo registro
isolado, duravelmente armazenado. Nenhum estorno/bloqueio/concessão ocorre no isolamento.

Checkout legado pendente não é reutilizado nem substituído por cobrança automática.
Pode bloquear aquela intenção específica até decisão posterior. Checkout seguro
continua reutilizável. Nenhuma regra comercial foi alterada.

## Contingência

Migration falha: transação revertida. Código falha após 018: conservar tabela e
RECUPERACAO; backend anterior ignora auditoria e continua recusando NORMAL por fila
não concluída. Se voltar ao código anterior após isolamento, ele pode consumir os
históricos em RECUPERACAO; não executar recuperação/webhooks com vendas reabertas
nesse rollback. Não remover auditoria nem reverter dados. Antes de qualquer rollback para código sem suporte a 018, ativar e confirmar
PAUSADO e a drenagem das operações; conservar a pausa durante e depois do rollback.
Não voltar a NORMAL nesse código enquanto houver isolamentos ativos. Não assumir que rollback de código
reverte isolamento ou processamento financeiro.

## Validação local desta implementação

Base c72bd9974919678d07ff6fcd2f5fbdf0a72c222c, worktree persistente
/workspaces/resumao-isolamento-historico. Rodada principal: 134 testes backend
aprovados; rodada complementar: 87 aprovados (há sobreposição dos testes de
isolamento). Rodada PostgreSQL 17.6 ampliada: 64 aprovados, incluindo 14 de
isolamento/migration/RLS/concorrência; excluído somente o teste preexistente de
exportação intermediária, incompatível com uma base já definitiva.
Mercado Pago simulado, PostgreSQL restrito a localhost e banco compras_test_*.
Nenhuma consulta financeira externa, migration de produção, commit ou deploy.

A CHECK dos IDs foi comparada com a saída real de pg_get_constraintdef no
PostgreSQL 17.6. A reaplicação preserva auditoria, inbox e modo/geração.
Isolamento aguarda processamento transacional em andamento; se um evento for
concluído nesse intervalo, todo o isolamento é recusado. NORMAL aguarda o commit
do isolamento e não é ativado automaticamente pelo endpoint de auditoria.
