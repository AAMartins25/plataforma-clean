# Idempotência das operações administrativas de acesso

Aplicar antes do backend correspondente, após conferir as tabelas e chaves de usuários, acessos e contratações e validar um backup. A migração é aditiva e não altera dados históricos. Executar o arquivo completo em transação; se a tabela já existir, a execução falha e exige conferência do esquema antes de prosseguir. A existência da tabela não prova que a migração está correta.

A interface deve ser atualizada para enviar uma chave estável em cada tentativa da mesma operação. Clientes antigos sem chave recebem erro 428 quando há contratação administrativa vigente; novas concessões sem contratação vigente mantêm compatibilidade. A migração não deve ser aplicada ao banco de homologação existente ou à produção sem autorização específica.
