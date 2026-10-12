# Migration 015 — auditoria do reembolso manual

Preparada para revisão; não aplicada em produção. Aplicar antes do novo backend.
A migration 014 continua necessária para o backend de múltiplas transações;
este script não executa as migrations 013/014 nem depende da coluna revisao_id.

Acrescenta pagamentos.mp_status (varchar(30), NULL, sem default) e
reembolsos_financeiros.confirmado_por (integer, NULL, FK usuarios.id, sem cascade).
Não atualiza históricos: NULL significa estado/administrador ainda não registrado,
sem inferir quem confirmou devoluções antigas ou o estado financeiro do provedor.
Não faz transferências, não confirma reembolsos e não altera acessos.

Antes de aplicar, confirmar banco correto, backup recuperável, existência das
três tabelas e usuarios.id integer NOT NULL com chave primária/única, privilégios
administrativos e ausência de estruturas homônimas incompatíveis. Conferir:

```sql
SELECT current_database(), current_schema();
SELECT table_name, column_name, data_type, character_maximum_length,
       is_nullable, column_default
FROM information_schema.columns
WHERE table_schema='public' AND table_name IN
 ('pagamentos','reembolsos_financeiros','usuarios')
AND column_name IN ('id','mp_status','confirmado_por');
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid IN ('public.reembolsos_financeiros'::regclass,
                  'public.usuarios'::regclass);
```

Executar o arquivo SQL integral em uma conexão administrativa. A transação usa
lock_timeout=5s e statement_timeout=60s. Falha de compatibilidade/lock/validação
impede commit; executar ROLLBACK se a sessão permanecer em transação abortada.
A FK valida referências já existentes, caso confirmado_por já esteja presente.
Não alterar a estrutura para contornar um erro sem diagnóstico.

Depois, repetir consultas acima e confirmar a FK fk_reembolso_confirmado_por,
colunas anuláveis/sem default e preservação dos registros. Testar com dados de
teste a interface; não fazer transferências reais para validar implantação.

Rollback operacional: manter as colunas aditivas. O retorno ao backend anterior
exige verificar que não existem transações filhas ou operações que dependam dos
novos campos e fluxos. Após esse uso, não retornar indiscriminadamente à versão
antiga: manter a pausa financeira e priorizar correção progressiva. Não remover
colunas nem apagar dados de auditoria para tentar reverter a implantação.
