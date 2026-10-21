BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
SET LOCAL search_path = public, pg_catalog;

DO $$
BEGIN
    IF to_regclass('public.notificacoes_mp') IS NULL
       OR to_regclass('public.controle_financeiro') IS NULL
       OR to_regclass('public.usuarios') IS NULL THEN
        RAISE EXCEPTION '018 exige migration 016 e usuarios existentes';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_attribute WHERE attrelid='public.notificacoes_mp'::regclass
        AND attname='id' AND atttypid='bigint'::regtype AND attnotnull AND NOT attisdropped)
       OR NOT EXISTS (SELECT FROM pg_attribute WHERE attrelid='public.usuarios'::regclass
        AND attname='id' AND atttypid='integer'::regtype AND attnotnull AND NOT attisdropped) THEN
        RAISE EXCEPTION 'Dependencias da auditoria 018 incompativeis';
    END IF;
    IF EXISTS (SELECT FROM pg_class WHERE oid=to_regclass('public.notificacoes_mp_isolamentos')
        AND (relkind <> 'r' OR obj_description(oid,'pg_class') IS DISTINCT FROM 'resumao:migration018:v1')) THEN
        RAISE EXCEPTION 'Objeto homonimo nao pertence a 018';
    END IF;
    IF to_regclass('public.notificacoes_mp_isolamentos') IS NULL AND EXISTS (
        SELECT FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
        WHERE n.nspname='public' AND t.typname='notificacoes_mp_isolamentos') THEN
        RAISE EXCEPTION 'Tipo homonimo exige analise';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS notificacoes_mp_isolamentos (
    notificacao_id bigint CONSTRAINT notificacoes_mp_isolamentos_pkey PRIMARY KEY,
    isolada_por integer NOT NULL,
    isolada_em timestamptz NOT NULL DEFAULT now(),
    geracao integer NOT NULL,
    motivo varchar(300) NOT NULL,
    revogada_em timestamptz NULL,
    revogada_por integer NULL,
    motivo_revogacao varchar(300) NULL,
    CONSTRAINT fk_isolamento_notificacao FOREIGN KEY (notificacao_id) REFERENCES notificacoes_mp(id),
    CONSTRAINT fk_isolamento_admin FOREIGN KEY (isolada_por) REFERENCES usuarios(id),
    CONSTRAINT fk_isolamento_revogador FOREIGN KEY (revogada_por) REFERENCES usuarios(id),
    CONSTRAINT ck_isolamento_ids CHECK (notificacao_id IN (1,2,3,4,7,8,9,10)),
    CONSTRAINT ck_isolamento_geracao CHECK (geracao >= 0),
    CONSTRAINT ck_isolamento_motivo CHECK (length(btrim(motivo)) BETWEEN 1 AND 300),
    CONSTRAINT ck_isolamento_revogacao CHECK (
        (revogada_em IS NULL AND revogada_por IS NULL AND motivo_revogacao IS NULL)
        OR (revogada_em IS NOT NULL AND revogada_por IS NOT NULL
            AND motivo_revogacao IS NOT NULL AND length(btrim(motivo_revogacao)) BETWEEN 1 AND 300))
);
COMMENT ON TABLE notificacoes_mp_isolamentos IS 'resumao:migration018:v1';

-- Conferir assinatura antes de aceitar uma reaplicacao; nunca adaptar silenciosamente.
DO $$
DECLARE item record;
BEGIN
    IF (SELECT count(*) FROM pg_attribute WHERE attrelid='notificacoes_mp_isolamentos'::regclass
        AND attnum>0 AND NOT attisdropped) <> 8 THEN
        RAISE EXCEPTION 'Colunas da auditoria 018 incompativeis';
    END IF;
    FOR item IN SELECT * FROM (VALUES
        ('notificacao_id','bigint',true, false), ('isolada_por','integer',true,false),
        ('isolada_em','timestamp with time zone',true,true), ('geracao','integer',true,false),
        ('motivo','character varying',true,false), ('revogada_em','timestamp with time zone',false,false),
        ('revogada_por','integer',false,false), ('motivo_revogacao','character varying',false,false)
    ) v(nome,tipo,obrigatoria,padrao) LOOP
        IF NOT EXISTS (SELECT FROM pg_attribute a WHERE a.attrelid='notificacoes_mp_isolamentos'::regclass
            AND a.attname=item.nome AND a.atttypid=item.tipo::regtype
            AND a.attnotnull=item.obrigatoria AND a.atthasdef=item.padrao
            AND a.attidentity='' AND a.attgenerated='' AND NOT a.attisdropped
            AND (item.tipo <> 'character varying' OR a.atttypmod=304)) THEN
            RAISE EXCEPTION 'Coluna 018 incompatível: %',item.nome;
        END IF;
    END LOOP;
    IF NOT EXISTS (SELECT FROM pg_attrdef WHERE adrelid='notificacoes_mp_isolamentos'::regclass
        AND pg_get_expr(adbin,adrelid)='now()') THEN
        RAISE EXCEPTION 'Default 018 incompativel';
    END IF;
    FOR item IN SELECT * FROM (VALUES
        ('fk_isolamento_notificacao','notificacao_id','public.notificacoes_mp','id'),
        ('fk_isolamento_admin','isolada_por','public.usuarios','id'),
        ('fk_isolamento_revogador','revogada_por','public.usuarios','id')
    ) v(nome,coluna,destino,coluna_destino) LOOP
        IF NOT EXISTS (SELECT FROM pg_constraint k WHERE k.conrelid='notificacoes_mp_isolamentos'::regclass
            AND k.conname=item.nome AND k.contype='f' AND k.convalidated AND NOT k.condeferrable
            AND k.confrelid=item.destino::regclass AND k.confupdtype='a' AND k.confdeltype='a'
            AND k.conkey=ARRAY[(SELECT attnum FROM pg_attribute WHERE attrelid=k.conrelid AND attname=item.coluna)]
            AND k.confkey=ARRAY[(SELECT attnum FROM pg_attribute WHERE attrelid=k.confrelid AND attname=item.coluna_destino)]) THEN
            RAISE EXCEPTION 'FK 018 incompativel: %',item.nome;
        END IF;
    END LOOP;
    IF NOT EXISTS (SELECT FROM pg_constraint WHERE conrelid='notificacoes_mp_isolamentos'::regclass
        AND conname='notificacoes_mp_isolamentos_pkey' AND contype='p'
        AND pg_get_constraintdef(oid)='PRIMARY KEY (notificacao_id)') THEN
        RAISE EXCEPTION 'PK 018 incompativel';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_index WHERE indexrelid=to_regclass('public.notificacoes_mp_isolamentos_pkey')
        AND indisvalid AND indisunique AND indisprimary) THEN
        RAISE EXCEPTION 'Indice 018 incompativel';
    END IF;
    FOR item IN SELECT * FROM (VALUES
        ('ck_isolamento_ids','CHECK ((notificacao_id = ANY (ARRAY[(1)::bigint, (2)::bigint, (3)::bigint, (4)::bigint, (7)::bigint, (8)::bigint, (9)::bigint, (10)::bigint])))'),
        ('ck_isolamento_geracao','CHECK ((geracao >= 0))'),
        ('ck_isolamento_motivo','CHECK (((length(btrim((motivo)::text)) >= 1) AND (length(btrim((motivo)::text)) <= 300)))'),
        ('ck_isolamento_revogacao','CHECK ((((revogada_em IS NULL) AND (revogada_por IS NULL) AND (motivo_revogacao IS NULL)) OR ((revogada_em IS NOT NULL) AND (revogada_por IS NOT NULL) AND (motivo_revogacao IS NOT NULL) AND ((length(btrim((motivo_revogacao)::text)) >= 1) AND (length(btrim((motivo_revogacao)::text)) <= 300)))))')
    ) v(nome,definicao) LOOP
        IF NOT EXISTS (SELECT FROM pg_constraint WHERE conrelid='notificacoes_mp_isolamentos'::regclass
            AND conname=item.nome AND contype='c' AND convalidated
            AND pg_get_constraintdef(oid)=item.definicao) THEN
            RAISE EXCEPTION 'CHECK 018 incompativel: %',item.nome;
        END IF;
    END LOOP;
    IF (SELECT count(*) FROM pg_constraint WHERE conrelid='notificacoes_mp_isolamentos'::regclass) <> 8
       OR EXISTS (SELECT FROM pg_trigger WHERE tgrelid='notificacoes_mp_isolamentos'::regclass AND NOT tgisinternal)
       OR EXISTS (SELECT FROM pg_policy WHERE polrelid='notificacoes_mp_isolamentos'::regclass) THEN
        RAISE EXCEPTION 'Objetos adicionais 018 exigem analise';
    END IF;
END $$;

ALTER TABLE notificacoes_mp_isolamentos ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON notificacoes_mp_isolamentos FROM PUBLIC;
DO $$
DECLARE papel text;
BEGIN
    FOREACH papel IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS (SELECT FROM pg_roles WHERE rolname=papel) THEN
            EXECUTE format('REVOKE ALL ON public.notificacoes_mp_isolamentos FROM %I',papel);
        END IF;
    END LOOP;
END $$;
COMMIT;
