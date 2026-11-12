-- Execução MANUAL no SQL Editor do Supabase, antes do deploy do backend.
-- Não modifica dados históricos, políticas, permissões nem regras financeiras.
-- Todos os novos campos são nullable. Obrigatoriedade na criação: API.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
-- Resolução determinística das funções e operadores usados nos CHECKs.
SET LOCAL search_path = pg_catalog, public, pg_temp;

-- Recusa esquemas diferentes do contrato observado no código e migrações.
DO $$
BEGIN
  IF to_regclass('public.cursos') IS NULL OR to_regclass('public.usuarios') IS NULL THEN
    RAISE EXCEPTION 'Requer public.cursos e public.usuarios existentes';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public'
      AND table_name='cursos' AND column_name='id' AND data_type='integer')
     OR NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public'
      AND table_name='cursos' AND column_name='nome' AND data_type='character varying'
      AND character_maximum_length=255 AND is_nullable='NO')
     OR NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public'
      AND table_name='usuarios' AND column_name='id' AND data_type='integer') THEN
    RAISE EXCEPTION 'Tipos de cursos.id/nome ou usuarios.id incompatíveis; revisar esquema';
  END IF;
  -- Antecipação diagnóstica: a criação da FK também verifica este requisito.
  -- Inclui PK, UNIQUE e índice único independente aceito pelo PostgreSQL.
  IF NOT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_index i
    JOIN pg_catalog.pg_attribute a
      ON a.attrelid = i.indrelid AND a.attname = 'id'
      AND a.attnum > 0 AND NOT a.attisdropped
    WHERE i.indrelid = 'public.usuarios'::regclass
      AND i.indisunique AND i.indisvalid AND i.indisready AND i.indislive
      AND i.indimmediate AND NOT i.indisexclusion
      AND i.indnkeyatts = 1 AND i.indkey[0] = a.attnum
      AND i.indpred IS NULL AND i.indexprs IS NULL
  ) THEN
    RAISE EXCEPTION 'Requer chave única imediata, válida e não parcial em public.usuarios(id)';
  END IF;
END $$;

ALTER TABLE public.cursos
  ADD COLUMN IF NOT EXISTS banca varchar(255),
  ADD COLUMN IF NOT EXISTS cargo varchar(255),
  ADD COLUMN IF NOT EXISTS orgao varchar(255),
  ADD COLUMN IF NOT EXISTS ano integer,
  ADD COLUMN IF NOT EXISTS uf varchar(2),
  ADD COLUMN IF NOT EXISTS produtor_id integer;

-- Em reaplicações, não aceita silenciosamente colunas homônimas incompatíveis.
DO $$
DECLARE campo record;
BEGIN
  FOR campo IN SELECT * FROM (VALUES
    ('banca','character varying',255), ('cargo','character varying',255),
    ('orgao','character varying',255), ('ano','integer',NULL),
    ('uf','character varying',2), ('produtor_id','integer',NULL)
  ) AS esperado(nome,tipo,tamanho)
  LOOP
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns c
      WHERE c.table_schema='public' AND c.table_name='cursos' AND c.column_name=campo.nome
        AND c.data_type=campo.tipo
        AND c.character_maximum_length IS NOT DISTINCT FROM campo.tamanho
        AND c.is_nullable='YES' AND c.column_default IS NULL
        AND c.is_generated='NEVER') THEN
      RAISE EXCEPTION 'Coluna cursos.% incompatível; transação cancelada', campo.nome;
    END IF;
  END LOOP;
END $$;

-- Constraints NOT VALID evitam varredura ou preenchimento do acervo.
-- São aplicadas a INSERT/UPDATE; nulos legados permanecem válidos.
DO $$
DECLARE
  regra record;
  definicoes text := '';
BEGIN
  -- Copia somente a estrutura e os CHECKs, sem dados, FKs ou índices.
  -- A cópia é temporária e não é ancestral nem descendente de public.cursos.
  CREATE TEMP TABLE m027_cursos_checks_existentes
    (LIKE public.cursos INCLUDING CONSTRAINTS) ON COMMIT DROP;

  FOR regra IN SELECT * FROM (VALUES
    ('ck_cursos_banca_metadado', 'banca IS NULL OR length(btrim(banca)) > 0'),
    ('ck_cursos_cargo_metadado', 'cargo IS NULL OR length(btrim(cargo)) > 0'),
    ('ck_cursos_orgao_metadado', 'orgao IS NULL OR length(btrim(orgao)) > 0'),
    ('ck_cursos_ano_metadado', 'ano IS NULL OR ano BETWEEN 1000 AND 9999'),
    ('ck_cursos_uf_metadado', $cond$uf IS NULL OR uf IN ('AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO')$cond$)
  ) AS regras(nome,expressao)
  LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.cursos'::regclass AND conname=regra.nome) THEN
      EXECUTE format('ALTER TABLE public.cursos ADD CONSTRAINT %I CHECK (%s) NOT VALID', regra.nome, regra.expressao);
    ELSIF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.cursos'::regclass AND conname=regra.nome AND contype='c' AND NOT connoinherit) THEN
      RAISE EXCEPTION 'Constraint % com tipo ou NO INHERIT incompatível', regra.nome;
    END IF;
    definicoes := concat_ws(', ', NULLIF(definicoes, ''),
      format('CONSTRAINT %I CHECK (%s)', regra.nome, regra.expressao));
  END LOOP;

  -- O próprio PostgreSQL compara as expressões ao mesclar CHECKs homônimos.
  -- Expressão diferente causa erro e rollback; não há comparação textual.
  -- Só as duas tabelas temporárias participam desta herança, ambas vazias.
  EXECUTE format(
    'CREATE TEMP TABLE m027_cursos_checks_compativeis (%s) '
    'INHERITS (pg_temp.m027_cursos_checks_existentes) ON COMMIT DROP',
    definicoes
  );

  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.cursos'::regclass AND conname='fk_cursos_produtor_usuario') THEN
    ALTER TABLE public.cursos ADD CONSTRAINT fk_cursos_produtor_usuario
      FOREIGN KEY (produtor_id) REFERENCES public.usuarios(id) ON DELETE NO ACTION NOT VALID;
  ELSIF NOT EXISTS (SELECT 1 FROM pg_constraint
      WHERE conrelid='public.cursos'::regclass AND conname='fk_cursos_produtor_usuario'
      AND contype='f' AND confrelid='public.usuarios'::regclass
      AND conkey=ARRAY[(SELECT attnum FROM pg_attribute WHERE attrelid='public.cursos'::regclass AND attname='produtor_id')]::smallint[]
      AND confkey=ARRAY[(SELECT attnum FROM pg_attribute WHERE attrelid='public.usuarios'::regclass AND attname='id')]::smallint[]
      AND confdeltype='a' AND confupdtype='a') THEN
    RAISE EXCEPTION 'FK de produtor incompatível; revisar antes de continuar';
  END IF;
END $$;
COMMIT;

-- Verificação após COMMIT (somente leitura).
SELECT column_name, data_type, character_maximum_length, is_nullable
FROM information_schema.columns
WHERE table_schema='public' AND table_name='cursos'
  AND column_name IN ('banca','cargo','orgao','ano','uf','produtor_id')
ORDER BY ordinal_position;
SELECT conname, contype, convalidated, pg_get_constraintdef(oid)
FROM pg_constraint WHERE conrelid='public.cursos'::regclass
  AND (conname LIKE 'ck_cursos_%_metadado' OR conname='fk_cursos_produtor_usuario')
ORDER BY conname;
