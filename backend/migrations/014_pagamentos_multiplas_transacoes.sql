-- Incremental, sem alteração de registros históricos. Executar antes do código.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
SET LOCAL search_path = public, pg_catalog;

DO $$
DECLARE coluna text;
BEGIN
    IF current_setting('server_version_num')::integer < 140000 THEN
        RAISE EXCEPTION 'Este script exige PostgreSQL 14 ou superior';
    END IF;
    IF to_regclass('public.pagamentos') IS NULL
       OR to_regclass('public.oportunidades_compra') IS NULL THEN
        RAISE EXCEPTION 'Tabelas de pagamentos/oportunidades ausentes';
    END IF;
    IF to_regprocedure('public.validar_origem_transacao_pagamento()') IS NOT NULL
        AND obj_description(to_regprocedure('public.validar_origem_transacao_pagamento()'), 'pg_proc')
            IS DISTINCT FROM 'resumao:migration014:origem_transacao' THEN
        RAISE EXCEPTION 'Função homônima não pertence à migration 014';
    END IF;
    IF EXISTS (SELECT FROM pg_trigger WHERE tgrelid='public.pagamentos'::regclass
        AND tgname='validar_origem_transacao_pagamento'
        AND (tgfoid IS DISTINCT FROM to_regprocedure('public.validar_origem_transacao_pagamento()')
            OR tgtype <> 23 OR tgenabled <> 'O' OR tgisinternal)) THEN
        RAISE EXCEPTION 'Trigger homônimo incompatível';
    END IF;
    FOREACH coluna IN ARRAY ARRAY['id', 'usuario_id', 'curso_id', 'oportunidade_id',
        'tempo_acesso_id', 'valor_cents', 'mp_payment_id', 'mp_preference_id',
        'tipo_compra', 'vencimento_original', 'contratacao_id', 'codigo_cupom',
        'vendedor_id', 'qr_code_id', 'provedor', 'moeda'] LOOP
        IF NOT EXISTS (SELECT FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'pagamentos' AND column_name = coluna) THEN
            RAISE EXCEPTION 'Coluna obrigatória ausente: pagamentos.%', coluna;
        END IF;
    END LOOP;
    FOREACH coluna IN ARRAY ARRAY['tipo_compra', 'contratacao_id', 'demonstracao_id',
        'vencimento_original', 'concluida_em', 'criada_em'] LOOP
        IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_schema='public'
            AND table_name='oportunidades_compra' AND column_name=coluna) THEN
            RAISE EXCEPTION 'Coluna obrigatória de oportunidade ausente: %', coluna;
        END IF;
    END LOOP;
    FOREACH coluna IN ARRAY ARRAY['id', 'usuario_id', 'curso_id'] LOOP
        IF NOT EXISTS (SELECT FROM information_schema.columns
            WHERE table_schema='public' AND table_name='oportunidades_compra'
            AND column_name=coluna AND data_type='integer') THEN
            RAISE EXCEPTION 'Coluna de oportunidade incompatível: %', coluna;
        END IF;
    END LOOP;
    IF EXISTS (SELECT FROM pagamentos p LEFT JOIN oportunidades_compra o ON o.id=p.oportunidade_id
        WHERE p.oportunidade_id IS NOT NULL AND (o.id IS NULL
        OR o.usuario_id IS DISTINCT FROM p.usuario_id OR o.curso_id IS DISTINCT FROM p.curso_id)) THEN
        RAISE EXCEPTION 'Oportunidade comercial incompatível';
    END IF;
    IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_schema='public'
        AND table_name='pagamentos' AND column_name='id' AND data_type='integer') THEN
        RAISE EXCEPTION 'pagamentos.id deve ser integer';
    END IF;
    IF EXISTS (SELECT mp_payment_id FROM pagamentos WHERE mp_payment_id IS NOT NULL
        GROUP BY mp_payment_id HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'mp_payment_id duplicado: interromper e analisar históricos, sem mesclar';
    END IF;
END $$;

ALTER TABLE pagamentos ADD COLUMN IF NOT EXISTS pagamento_origem_id integer;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_schema='public'
        AND table_name='pagamentos' AND column_name='pagamento_origem_id'
        AND data_type='integer' AND is_nullable='YES' AND column_default IS NULL) THEN
        RAISE EXCEPTION 'pagamento_origem_id incompatível';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_constraint WHERE conrelid='pagamentos'::regclass
        AND conname='fk_pagamentos_origem') THEN
        ALTER TABLE pagamentos ADD CONSTRAINT fk_pagamentos_origem
            FOREIGN KEY (pagamento_origem_id) REFERENCES pagamentos(id);
    ELSIF NOT EXISTS (SELECT FROM pg_constraint WHERE conrelid='pagamentos'::regclass
        AND conname='fk_pagamentos_origem' AND contype='f' AND convalidated
        AND confrelid='pagamentos'::regclass AND confdeltype='a'
        AND pg_get_constraintdef(oid)='FOREIGN KEY (pagamento_origem_id) REFERENCES pagamentos(id)') THEN
        RAISE EXCEPTION 'fk_pagamentos_origem incompatível';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_constraint WHERE conrelid='pagamentos'::regclass
        AND conname='ck_pagamentos_origem_distinta') THEN
        ALTER TABLE pagamentos ADD CONSTRAINT ck_pagamentos_origem_distinta
            CHECK (pagamento_origem_id IS NULL OR pagamento_origem_id <> id);
    ELSIF NOT EXISTS (SELECT FROM pg_constraint WHERE conrelid='pagamentos'::regclass
        AND conname='ck_pagamentos_origem_distinta' AND contype='c'
        AND pg_get_constraintdef(oid)='CHECK (((pagamento_origem_id IS NULL) OR (pagamento_origem_id <> id)))') THEN
        RAISE EXCEPTION 'ck_pagamentos_origem_distinta incompatível';
    END IF;
    IF EXISTS (SELECT FROM pagamentos p LEFT JOIN pagamentos r ON r.id=p.pagamento_origem_id
        WHERE p.pagamento_origem_id IS NOT NULL AND (r.id IS NULL
        OR r.pagamento_origem_id IS NOT NULL OR p.id=r.id
        OR p.oportunidade_id IS NULL OR p.mp_preference_id IS NULL
        OR ROW(p.usuario_id,p.curso_id,p.tempo_acesso_id,p.oportunidade_id,p.mp_preference_id,
            p.valor_cents,p.tipo_compra,p.codigo_cupom,p.vendedor_id,p.qr_code_id,p.vencimento_original,p.moeda,p.provedor)
        IS DISTINCT FROM ROW(r.usuario_id,r.curso_id,r.tempo_acesso_id,r.oportunidade_id,r.mp_preference_id,
            r.valor_cents,r.tipo_compra,r.codigo_cupom,r.vendedor_id,r.qr_code_id,r.vencimento_original,r.moeda,r.provedor)
        OR (p.tipo_compra='RENOVACAO' AND p.contratacao_id IS DISTINCT FROM r.contratacao_id))) THEN
        RAISE EXCEPTION 'Vínculos de tentativas incompatíveis';
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_pagamentos_pagamento_origem_id ON pagamentos(pagamento_origem_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_pagamentos_mp_payment_id ON pagamentos(mp_payment_id)
    WHERE mp_payment_id IS NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_index WHERE indexrelid='uq_pagamentos_mp_payment_id'::regclass
        AND indrelid='pagamentos'::regclass AND indisunique AND indisvalid
        AND pg_get_indexdef(indexrelid)='CREATE UNIQUE INDEX uq_pagamentos_mp_payment_id ON public.pagamentos USING btree (mp_payment_id) WHERE (mp_payment_id IS NOT NULL)')
    OR NOT EXISTS (SELECT FROM pg_index WHERE indexrelid='ix_pagamentos_pagamento_origem_id'::regclass
        AND indrelid='pagamentos'::regclass AND indisvalid
        AND pg_get_indexdef(indexrelid)='CREATE INDEX ix_pagamentos_pagamento_origem_id ON public.pagamentos USING btree (pagamento_origem_id)') THEN
        RAISE EXCEPTION 'Índices de pagamentos incompatíveis';
    END IF;
END $$;

CREATE OR REPLACE FUNCTION public.validar_origem_transacao_pagamento()
RETURNS trigger LANGUAGE plpgsql SET search_path = public, pg_catalog AS $$
DECLARE raiz pagamentos%ROWTYPE;
BEGIN
    IF TG_OP='UPDATE' THEN
        IF NEW.pagamento_origem_id IS DISTINCT FROM OLD.pagamento_origem_id THEN
            RAISE EXCEPTION 'Origem financeira imutável';
        END IF;
        IF OLD.mp_payment_id IS NOT NULL AND NEW.mp_payment_id IS DISTINCT FROM OLD.mp_payment_id THEN
            RAISE EXCEPTION 'Identificador de transação imutável';
        END IF;
        IF EXISTS (SELECT FROM pagamentos WHERE pagamento_origem_id=OLD.id)
            AND ROW(NEW.usuario_id,NEW.curso_id,NEW.tempo_acesso_id,NEW.oportunidade_id,NEW.mp_preference_id,
                NEW.valor_cents,NEW.tipo_compra,NEW.codigo_cupom,NEW.vendedor_id,NEW.qr_code_id,NEW.vencimento_original,NEW.moeda,NEW.provedor)
            IS DISTINCT FROM ROW(OLD.usuario_id,OLD.curso_id,OLD.tempo_acesso_id,OLD.oportunidade_id,OLD.mp_preference_id,
                OLD.valor_cents,OLD.tipo_compra,OLD.codigo_cupom,OLD.vendedor_id,OLD.qr_code_id,OLD.vencimento_original,OLD.moeda,OLD.provedor) THEN
            RAISE EXCEPTION 'Dados comerciais da origem com tentativas são imutáveis';
        END IF;
    END IF;
    IF NEW.pagamento_origem_id IS NOT NULL THEN
        SELECT * INTO raiz FROM pagamentos WHERE id=NEW.pagamento_origem_id FOR UPDATE;
        IF raiz.id IS NULL OR raiz.pagamento_origem_id IS NOT NULL OR raiz.id=NEW.id
            OR NEW.oportunidade_id IS NULL OR NEW.mp_preference_id IS NULL
            OR ROW(NEW.usuario_id,NEW.curso_id,NEW.tempo_acesso_id,NEW.oportunidade_id,NEW.mp_preference_id,
                NEW.valor_cents,NEW.tipo_compra,NEW.codigo_cupom,NEW.vendedor_id,NEW.qr_code_id,NEW.vencimento_original,NEW.moeda,NEW.provedor)
            IS DISTINCT FROM ROW(raiz.usuario_id,raiz.curso_id,raiz.tempo_acesso_id,raiz.oportunidade_id,raiz.mp_preference_id,
                raiz.valor_cents,raiz.tipo_compra,raiz.codigo_cupom,raiz.vendedor_id,raiz.qr_code_id,raiz.vencimento_original,raiz.moeda,raiz.provedor)
            OR (NEW.tipo_compra='RENOVACAO' AND NEW.contratacao_id IS DISTINCT FROM raiz.contratacao_id) THEN
            RAISE EXCEPTION 'Tentativa deve apontar diretamente para uma origem comercial compatível';
        END IF;
    END IF;
    RETURN NEW;
END $$;

COMMENT ON FUNCTION public.validar_origem_transacao_pagamento()
    IS 'resumao:migration014:origem_transacao';

CREATE OR REPLACE TRIGGER validar_origem_transacao_pagamento
    BEFORE INSERT OR UPDATE ON pagamentos FOR EACH ROW
    EXECUTE FUNCTION public.validar_origem_transacao_pagamento();
COMMIT;
