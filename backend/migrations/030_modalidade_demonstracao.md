# Modalidade da demonstração

A migração exige a 028, define a modalidade tradicional por padrão e marca por ordem apenas cursos com registro direto em `importacoes_curso`. Não identifica cópias anteriores: a duplicação anterior não registrava a origem. Antes de executar em qualquer banco, inventariar essas cópias e obter evidência inequívoca para uma reconciliação específica; não inferir por nome, conteúdo ou preços. A migração não altera os marcadores das disciplinas nem histórico de alunos.

Executar o arquivo completo como uma única transação, após backup validado e conferência do esquema e permissões. Em caso de erro, confirmar o rollback antes de repetir. A reaplicação não reclassifica cursos. Após aplicação, conferir a coluna e os cursos identificados diretamente; não iniciar o novo backend antes da migração.
