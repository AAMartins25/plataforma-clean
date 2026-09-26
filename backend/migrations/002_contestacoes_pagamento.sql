-- Gestão de contestações de compras com cartão de crédito.
-- Não executar em produção antes da validação dos testes.

BEGIN;

CREATE TABLE IF NOT EXISTS contestacoes_pagamento (
    id SERIAL PRIMARY KEY,

    pagamento_id INTEGER NOT NULL UNIQUE
        REFERENCES pagamentos(id),

    mp_dispute_id VARCHAR(100) UNIQUE,

    status VARCHAR(40) NOT NULL DEFAULT 'ABERTA',

    motivo TEXT,

    valor_cents INTEGER NOT NULL
        CHECK (valor_cents > 0),

    criada_em TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    devolucao_confirmada_em TIMESTAMP WITHOUT TIME ZONE,

    devolucao_confirmada_por INTEGER
        REFERENCES usuarios(id),

    referencia_devolucao VARCHAR(255),

    CONSTRAINT ck_contestacoes_confirmacao_completa CHECK (
        devolucao_confirmada_em IS NULL
        OR (
            devolucao_confirmada_por IS NOT NULL
            AND NULLIF(BTRIM(referencia_devolucao), '') IS NOT NULL
        )
    ),

    bloqueio_executado_em TIMESTAMP WITHOUT TIME ZONE,

    bloqueio_executado_por INTEGER
        REFERENCES usuarios(id),

    CHECK (
        bloqueio_executado_em IS NULL
        OR (
            devolucao_confirmada_em IS NOT NULL
            AND bloqueio_executado_por IS NOT NULL
        )
    )
);

CREATE INDEX IF NOT EXISTS
    ix_contestacoes_pagamento_pagamento_id
ON contestacoes_pagamento(pagamento_id);

ALTER TABLE contestacoes_pagamento
ENABLE ROW LEVEL SECURITY;

COMMIT;
