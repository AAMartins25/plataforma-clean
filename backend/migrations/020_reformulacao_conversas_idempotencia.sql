BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '30s';
SET LOCAL search_path = public, pg_catalog;

CREATE TABLE public.reformulacoes_conversa_operacoes (
    operacao_id varchar(36) NOT NULL,
    curso_id integer NOT NULL,
    contratacao_id integer NULL,
    demonstracao_id integer NULL,
    conversa_nova_id integer NOT NULL,
    fingerprint varchar(64) NOT NULL,
    criado_em timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT reformulacoes_conversa_operacoes_pkey PRIMARY KEY (operacao_id),
    CONSTRAINT ck_reformulacao_curso_positivo CHECK (curso_id > 0),
    CONSTRAINT ck_reformulacao_contexto_exclusivo
        CHECK ((contratacao_id IS NULL) <> (demonstracao_id IS NULL)),
    CONSTRAINT ck_reformulacao_fingerprint CHECK (length(fingerprint) = 64),
    CONSTRAINT uq_reformulacao_conversa_nova UNIQUE (conversa_nova_id)
);

COMMENT ON TABLE public.reformulacoes_conversa_operacoes IS
    'Idempotency metadata for teacher-message reformulation; stores no message text.';
ALTER TABLE public.reformulacoes_conversa_operacoes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.reformulacoes_conversa_operacoes FROM PUBLIC;
DO $$
DECLARE papel text;
BEGIN
    FOREACH papel IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT FROM pg_roles WHERE rolname = papel) THEN
            EXECUTE format('REVOKE ALL ON public.reformulacoes_conversa_operacoes FROM %I', papel);
        END IF;
    END LOOP;
END $$;
COMMIT;
