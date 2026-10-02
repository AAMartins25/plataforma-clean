BEGIN;
ALTER TABLE pagamentos ADD COLUMN oportunidade_id INTEGER REFERENCES oportunidades_compra(id);
CREATE INDEX ix_pagamentos_oportunidade ON pagamentos (oportunidade_id);
COMMIT;
