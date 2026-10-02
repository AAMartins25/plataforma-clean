-- Histórico independente de contratações.
-- Executar inicialmente apenas no PostgreSQL local de testes.

BEGIN;

CREATE TABLE contratacoes_curso (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    curso_id INTEGER NOT NULL REFERENCES cursos(id),
    data_inicio TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    data_fim TIMESTAMP WITHOUT TIME ZONE,
    origem VARCHAR(20) NOT NULL,
    criada_em TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_contratacoes_origem
        CHECK (origem IN ('PAGAMENTO', 'ADMIN', 'DEMONSTRACAO')),
    CONSTRAINT ck_contratacoes_periodo
        CHECK (data_fim IS NULL OR data_fim > data_inicio)
);

CREATE INDEX ix_contratacoes_usuario_curso
    ON contratacoes_curso (usuario_id, curso_id);

COMMIT;
