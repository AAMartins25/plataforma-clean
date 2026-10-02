-- Vinculação dos pagamentos às contratações.
-- Aplicar inicialmente apenas no PostgreSQL local de testes.
BEGIN;

ALTER TABLE pagamentos
    ADD COLUMN contratacao_id INTEGER REFERENCES contratacoes_curso(id);

CREATE INDEX ix_pagamentos_contratacao
    ON pagamentos (contratacao_id);

ALTER TABLE periodos_acesso_pagamento
    ADD COLUMN contratacao_id INTEGER REFERENCES contratacoes_curso(id);

CREATE INDEX ix_periodos_acesso_pagamento_contratacao
    ON periodos_acesso_pagamento (contratacao_id);

COMMIT;
