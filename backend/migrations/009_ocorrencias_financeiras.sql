ALTER TABLE pagamentos
    ADD COLUMN ocorrencia_financeira VARCHAR(30),
    ADD COLUMN ocorrencia_registrada_em TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE pagamentos
    ADD CONSTRAINT ck_pagamentos_ocorrencia_financeira
    CHECK (
        ocorrencia_financeira IS NULL
        OR ocorrencia_financeira IN (
            'COBRANCA_DUPLICADA',
            'APROVACAO_FORA_PRAZO'
        )
    );
