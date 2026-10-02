-- Identificação de renovações e preservação do vencimento original.
-- Executar em produção somente após os testes locais.

BEGIN;

ALTER TABLE pagamentos
    ADD COLUMN IF NOT EXISTS tipo_compra VARCHAR(20)
        NOT NULL DEFAULT 'NOVA',
    ADD COLUMN IF NOT EXISTS vencimento_original
        TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE pagamentos
    ADD CONSTRAINT ck_pagamentos_tipo_compra
    CHECK (
        (tipo_compra = 'NOVA' AND vencimento_original IS NULL)
        OR
        (tipo_compra = 'RENOVACAO' AND vencimento_original IS NOT NULL)
    );

COMMIT;
