-- Apenas esquema: preserva todos os valores, chaves e vínculos existentes.
-- Executar manualmente em uma única sessão antes de publicar o backend.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
SET LOCAL search_path = pg_catalog, public;
LOCK TABLE public.cursos IN ACCESS EXCLUSIVE MODE;

-- O PostgreSQL normaliza as expressões; rejeitamos constraints inesperadas
-- antes de remover qualquer uma, inclusive em uma reaplicação.
CREATE TEMP TABLE m032_uf_antiga (uf varchar(2),
  CONSTRAINT m032_antiga CHECK (uf IS NULL OR uf IN
    ('AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO'))
) ON COMMIT DROP;
CREATE TEMP TABLE m032_uf_nova (uf varchar(8),
  CONSTRAINT m032_nova CHECK (uf IS NULL OR uf IN
    ('NACIONAL','AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO'))
) ON COMMIT DROP;

DO $migracao$
DECLARE
  coluna smallint;
  largura integer;
  atual text;
  antiga text;
  nova text;
  validada boolean;
BEGIN
  SELECT a.attnum, a.atttypmod - 4 INTO coluna, largura
    FROM pg_attribute a
   WHERE a.attrelid = 'public.cursos'::regclass AND a.attname = 'uf'
     AND a.atttypid = 'character varying'::regtype AND NOT a.attisdropped;
  IF coluna IS NULL OR largura NOT IN (2, 8) THEN
    RAISE EXCEPTION 'Coluna cursos.uf ausente ou incompatível';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint c
              WHERE c.conrelid = 'public.cursos'::regclass AND c.contype = 'c'
                AND coluna = ANY(c.conkey) AND c.conname <> 'ck_cursos_uf_metadado') THEN
    RAISE EXCEPTION 'Outra constraint CHECK de cursos.uf requer revisão';
  END IF;
  SELECT pg_get_expr(c.conbin,c.conrelid), c.convalidated INTO atual, validada
    FROM pg_constraint c
   WHERE c.conrelid = 'public.cursos'::regclass AND c.conname = 'ck_cursos_uf_metadado'
     AND c.contype = 'c' AND NOT c.connoinherit AND c.conkey = ARRAY[coluna]::smallint[];
  SELECT pg_get_expr(conbin,conrelid) INTO antiga FROM pg_constraint WHERE conrelid='m032_uf_antiga'::regclass AND conname='m032_antiga';
  SELECT pg_get_expr(conbin,conrelid) INTO nova FROM pg_constraint WHERE conrelid='m032_uf_nova'::regclass AND conname='m032_nova';
  IF atual IS NULL OR atual NOT IN (antiga, nova) THEN
    RAISE EXCEPTION 'Constraint de cursos.uf ausente ou incompatível';
  END IF;
  IF largura = 8 AND atual = nova THEN
    RETURN;
  END IF;
  IF largura <> 2 OR atual <> antiga THEN
    RAISE EXCEPTION 'Combinação de tipo e constraint de cursos.uf incompatível';
  END IF;
  ALTER TABLE public.cursos DROP CONSTRAINT ck_cursos_uf_metadado;
  ALTER TABLE public.cursos ALTER COLUMN uf TYPE varchar(8);
  ALTER TABLE public.cursos ADD CONSTRAINT ck_cursos_uf_metadado CHECK
    (uf IS NULL OR uf IN ('NACIONAL','AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO')) NOT VALID;
  IF validada THEN
    ALTER TABLE public.cursos VALIDATE CONSTRAINT ck_cursos_uf_metadado;
  END IF;
END
$migracao$;
COMMIT;
