-- Executar antes do backend que persiste o administrador da confirmação.
-- Não executa devoluções e não modifica registros históricos.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
SET LOCAL search_path = public, pg_catalog;

DO $$
BEGIN
    IF to_regclass('public.reembolsos_financeiros') IS NULL
       OR to_regclass('public.usuarios') IS NULL
       OR to_regclass('public.pagamentos') IS NULL THEN
        RAISE EXCEPTION 'Tabelas de reembolsos/usuarios ausentes';
    END IF;
    IF NOT EXISTS (SELECT FROM information_schema.columns
        WHERE table_schema='public' AND table_name='usuarios'
        AND column_name='id' AND data_type='integer' AND is_nullable='NO') THEN
        RAISE EXCEPTION 'usuarios.id incompatível';
    END IF;
    IF EXISTS (SELECT FROM information_schema.columns
        WHERE table_schema='public' AND table_name='reembolsos_financeiros'
        AND column_name='confirmado_por'
        AND (data_type <> 'integer' OR is_nullable <> 'YES' OR column_default IS NOT NULL)) THEN
        RAISE EXCEPTION 'confirmado_por existente incompatível';
    END IF;
    IF EXISTS (SELECT FROM information_schema.columns
        WHERE table_schema='public' AND table_name='pagamentos'
        AND column_name='mp_status'
        AND (data_type <> 'character varying' OR character_maximum_length IS DISTINCT FROM 30
             OR is_nullable <> 'YES' OR column_default IS NOT NULL)) THEN
        RAISE EXCEPTION 'pagamentos.mp_status existente incompatível';
    END IF;
END $$;

ALTER TABLE public.pagamentos ADD COLUMN IF NOT EXISTS mp_status varchar(30) NULL;

ALTER TABLE public.reembolsos_financeiros
    ADD COLUMN IF NOT EXISTS confirmado_por integer NULL;

DO $$
DECLARE existente pg_constraint%ROWTYPE;
BEGIN
    SELECT * INTO existente FROM pg_constraint
        WHERE conrelid='public.reembolsos_financeiros'::regclass
        AND conname='fk_reembolso_confirmado_por';
    IF FOUND THEN
        IF existente.contype <> 'f'
           OR existente.confrelid <> 'public.usuarios'::regclass
           OR existente.conkey <> ARRAY[(SELECT attnum FROM pg_attribute
                WHERE attrelid='public.reembolsos_financeiros'::regclass
                AND attname='confirmado_por' AND NOT attisdropped)]::smallint[]
           OR existente.confkey <> ARRAY[(SELECT attnum FROM pg_attribute
                WHERE attrelid='public.usuarios'::regclass
                AND attname='id' AND NOT attisdropped)]::smallint[]
           OR existente.confdeltype <> 'a' OR existente.confupdtype <> 'a'
           OR existente.condeferrable OR NOT existente.convalidated THEN
            RAISE EXCEPTION 'Constraint fk_reembolso_confirmado_por incompatível';
        END IF;
    ELSE
        ALTER TABLE public.reembolsos_financeiros
            ADD CONSTRAINT fk_reembolso_confirmado_por
            FOREIGN KEY (confirmado_por) REFERENCES public.usuarios(id);
    END IF;
END $$;
COMMIT;
