BEGIN;

CREATE TABLE oportunidades_compra (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    curso_id INTEGER NOT NULL REFERENCES cursos(id),
    tipo_compra VARCHAR(20) NOT NULL,
    contratacao_id INTEGER REFERENCES contratacoes_curso(id),
    demonstracao_id INTEGER REFERENCES demonstracoes_curso(id),
    vencimento_original TIMESTAMP WITHOUT TIME ZONE,
    concluida_em TIMESTAMP WITHOUT TIME ZONE,
    criada_em TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_oportunidades_tipo
        CHECK (tipo_compra IN ('NOVA', 'RENOVACAO')),

    CONSTRAINT ck_oportunidades_renovacao
        CHECK (
            (tipo_compra = 'RENOVACAO'
             AND contratacao_id IS NOT NULL
             AND vencimento_original IS NOT NULL
             AND demonstracao_id IS NULL)
            OR
            (tipo_compra = 'NOVA'
             AND contratacao_id IS NULL
             AND vencimento_original IS NULL)
        )
);

CREATE UNIQUE INDEX ux_oportunidades_renovacao
    ON oportunidades_compra (contratacao_id, vencimento_original)
    WHERE tipo_compra = 'RENOVACAO';

CREATE UNIQUE INDEX ux_oportunidades_demonstracao
    ON oportunidades_compra (demonstracao_id)
    WHERE tipo_compra = 'NOVA' AND demonstracao_id IS NOT NULL;

CREATE UNIQUE INDEX ux_oportunidades_nova_aberta
    ON oportunidades_compra (usuario_id, curso_id)
    WHERE tipo_compra = 'NOVA'
      AND demonstracao_id IS NULL
      AND concluida_em IS NULL;

COMMIT;
