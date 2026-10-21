BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
SET LOCAL search_path = public, pg_catalog;
DO $$
BEGIN
    IF to_regclass('public.pagamentos') IS NULL OR NOT EXISTS (
        SELECT FROM pg_attribute WHERE attrelid='public.pagamentos'::regclass
        AND attname='id' AND atttypid='integer'::regtype AND attnotnull AND NOT attisdropped
    ) THEN RAISE EXCEPTION '019 exige pagamentos(id integer)'; END IF;
    IF EXISTS (SELECT FROM pg_class WHERE oid=to_regclass('public.emails_pagamentos')
        AND (relkind<>'r' OR obj_description(oid,'pg_class') IS DISTINCT FROM 'resumao:migration019:v1')) THEN
        RAISE EXCEPTION 'Objeto homonimo incompatível com 019';
    END IF;
    IF to_regclass('public.emails_pagamentos') IS NULL AND EXISTS (
        SELECT FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
        WHERE n.nspname='public' AND t.typname='emails_pagamentos'
    ) THEN RAISE EXCEPTION 'Tipo homonimo incompatível com 019'; END IF;
END $$;
CREATE TABLE IF NOT EXISTS emails_pagamentos (
    pagamento_id integer NOT NULL,
    tipo varchar(10) NOT NULL,
    estado varchar(20) NOT NULL,
    criado_em timestamptz NOT NULL,
    proxima_consulta_em timestamptz NOT NULL,
    lease_ate timestamptz NULL,
    lease_token varchar(64) NULL,
    tentativas integer NOT NULL,
    primeiro_envio_em timestamptz NULL,
    payload jsonb NULL,
    payload_hash varchar(64) NULL,
    aceito_em timestamptz NULL,
    provedor_id varchar(100) NULL,
    erro_codigo varchar(40) NULL,
    CONSTRAINT emails_pagamentos_pkey PRIMARY KEY (pagamento_id,tipo),
    CONSTRAINT fk_email_pagamento FOREIGN KEY (pagamento_id) REFERENCES pagamentos(id),
    CONSTRAINT ck_email_tipo CHECK (tipo IN ('PENDENTE','APROVADO')),
    CONSTRAINT ck_email_estado CHECK (estado IN ('DADOS_PENDENTES','PENDENTE','EM_ENVIO','ACEITO','ERRO','INCERTO','SUSPENSO')),
    CONSTRAINT ck_email_tentativas CHECK (tentativas>=0),
    CONSTRAINT ck_email_aceito CHECK (estado<>'ACEITO' OR (aceito_em IS NOT NULL AND provedor_id IS NOT NULL AND payload_hash IS NOT NULL)),
    CONSTRAINT ck_email_lease CHECK ((lease_ate IS NULL)=(lease_token IS NULL)),
    CONSTRAINT ck_email_payload CHECK (primeiro_envio_em IS NULL OR (payload IS NOT NULL AND payload_hash IS NOT NULL))
);
COMMENT ON TABLE emails_pagamentos IS 'resumao:migration019:v1';
CREATE INDEX IF NOT EXISTS ix_emails_pagamentos_fila ON emails_pagamentos(proxima_consulta_em,criado_em)
    WHERE estado IN ('DADOS_PENDENTES','PENDENTE','EM_ENVIO');
DO $validar$
DECLARE item record;
BEGIN
    IF (SELECT count(*) FROM pg_attribute WHERE attrelid='emails_pagamentos'::regclass AND attnum>0 AND NOT attisdropped)<>14 THEN
        RAISE EXCEPTION 'Colunas 019 incompatíveis';
    END IF;
    FOR item IN SELECT * FROM (VALUES
        ('pagamento_id','integer',true,-1),('tipo','character varying',true,14),('estado','character varying',true,24),
        ('criado_em','timestamp with time zone',true,-1),('proxima_consulta_em','timestamp with time zone',true,-1),
        ('lease_ate','timestamp with time zone',false,-1),('lease_token','character varying',false,68),
        ('tentativas','integer',true,-1),('primeiro_envio_em','timestamp with time zone',false,-1),
        ('payload','jsonb',false,-1),('payload_hash','character varying',false,68),
        ('aceito_em','timestamp with time zone',false,-1),('provedor_id','character varying',false,104),('erro_codigo','character varying',false,44)
    ) v(nome,tipo,obrigatorio,modificador) LOOP
        IF NOT EXISTS (SELECT FROM pg_attribute WHERE attrelid='emails_pagamentos'::regclass AND attname=item.nome
            AND atttypid=item.tipo::regtype AND attnotnull=item.obrigatorio AND atttypmod=item.modificador
            AND NOT atthasdef AND attidentity='' AND attgenerated='' AND NOT attisdropped) THEN
            RAISE EXCEPTION 'Coluna 019 incompatível: %',item.nome;
        END IF;
    END LOOP;
    IF NOT EXISTS (SELECT FROM pg_constraint WHERE conrelid='emails_pagamentos'::regclass
        AND conname='emails_pagamentos_pkey' AND contype='p' AND pg_get_constraintdef(oid)='PRIMARY KEY (pagamento_id, tipo)')
       OR NOT EXISTS (SELECT FROM pg_constraint WHERE conrelid='emails_pagamentos'::regclass
        AND conname='fk_email_pagamento' AND contype='f' AND convalidated AND NOT condeferrable
        AND confrelid='pagamentos'::regclass AND confupdtype='a' AND confdeltype='a'
        AND conkey=ARRAY[(SELECT attnum FROM pg_attribute WHERE attrelid='emails_pagamentos'::regclass AND attname='pagamento_id')]
        AND confkey=ARRAY[(SELECT attnum FROM pg_attribute WHERE attrelid='pagamentos'::regclass AND attname='id')]) THEN
        RAISE EXCEPTION 'Relacionamentos 019 incompatíveis';
    END IF;
    FOR item IN SELECT * FROM (VALUES
        ('ck_email_tipo', $$CHECK (((tipo)::text = ANY ((ARRAY['PENDENTE'::character varying, 'APROVADO'::character varying])::text[])))$$),
        ('ck_email_estado', $$CHECK (((estado)::text = ANY ((ARRAY['DADOS_PENDENTES'::character varying, 'PENDENTE'::character varying, 'EM_ENVIO'::character varying, 'ACEITO'::character varying, 'ERRO'::character varying, 'INCERTO'::character varying, 'SUSPENSO'::character varying])::text[])))$$),
        ('ck_email_tentativas', 'CHECK ((tentativas >= 0))'),
        ('ck_email_aceito', $$CHECK ((((estado)::text <> 'ACEITO'::text) OR ((aceito_em IS NOT NULL) AND (provedor_id IS NOT NULL) AND (payload_hash IS NOT NULL))))$$),
        ('ck_email_lease', 'CHECK (((lease_ate IS NULL) = (lease_token IS NULL)))'),
        ('ck_email_payload', 'CHECK (((primeiro_envio_em IS NULL) OR ((payload IS NOT NULL) AND (payload_hash IS NOT NULL))))')
    ) v(nome,definicao) LOOP
        IF NOT EXISTS (SELECT FROM pg_constraint WHERE conrelid='emails_pagamentos'::regclass AND conname=item.nome
            AND contype='c' AND convalidated AND pg_get_constraintdef(oid)=item.definicao) THEN
            RAISE EXCEPTION 'CHECK 019 incompatível: %',item.nome;
        END IF;
    END LOOP;
    IF (SELECT count(*) FROM pg_constraint WHERE conrelid='emails_pagamentos'::regclass)<>8
        OR EXISTS (SELECT FROM pg_trigger WHERE tgrelid='emails_pagamentos'::regclass AND NOT tgisinternal)
        OR EXISTS (SELECT FROM pg_policy WHERE polrelid='emails_pagamentos'::regclass) THEN
        RAISE EXCEPTION 'Objetos adicionais 019 exigem análise';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_index WHERE indexrelid=to_regclass('public.ix_emails_pagamentos_fila')
        AND indrelid='emails_pagamentos'::regclass AND indisvalid
        AND pg_get_indexdef(indexrelid)=$$CREATE INDEX ix_emails_pagamentos_fila ON public.emails_pagamentos USING btree (proxima_consulta_em, criado_em) WHERE ((estado)::text = ANY ((ARRAY['DADOS_PENDENTES'::character varying, 'PENDENTE'::character varying, 'EM_ENVIO'::character varying])::text[]))$$) THEN
        RAISE EXCEPTION 'Índice 019 incompatível';
    END IF;
END $validar$;
ALTER TABLE emails_pagamentos ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON emails_pagamentos FROM PUBLIC;
DO $$
DECLARE papel text;
BEGIN
    FOREACH papel IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS (SELECT FROM pg_roles WHERE rolname=papel) THEN
            EXECUTE format('REVOKE ALL ON public.emails_pagamentos FROM %I',papel);
        END IF;
    END LOOP;
END $$;
COMMIT;
