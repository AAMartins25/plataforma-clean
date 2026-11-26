# UF NACIONAL em cursos (032)

A migração amplia `public.cursos.uf` de `varchar(2)` para `varchar(8)` e acrescenta `NACIONAL` ao CHECK existente. Nenhuma linha é atualizada; UFs e vínculos históricos permanecem iguais. A coluna continua nullable e o estado de validação anterior do CHECK é preservado. A migração é transacional, reaplicável no esquema esperado e aborta se tipo ou constraints forem incompatíveis.

**Não executada em produção.** Após aprovação da implantação, fazer backup e executar manualmente `032_uf_nacional_cursos.sql` no banco correto. O comando adquire bloqueio exclusivo de `cursos` com timeout de cinco segundos; se não puder obtê-lo ou encontrar esquema diferente, investigar antes de tentar novamente. Confirmar tipo, CHECK e dados após a migração. Publicar o backend somente depois da migração e, em seguida, o frontend. Nenhuma alteração de cursos existentes é necessária. Não reaplicar a migração 027 após esta migração: ela verifica o tipo anterior de duas posições.

Depois que um curso usar `NACIONAL`, uma versão antiga do backend não aceitará gravar esse valor. Não reduzir a coluna nem restaurar a constraint anterior sem antes tratar tais cursos expressamente.
