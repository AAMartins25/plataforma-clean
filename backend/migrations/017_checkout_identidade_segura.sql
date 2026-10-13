-- Identidades somente para checkouts futuros; nenhum backfill financeiro.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
SET LOCAL search_path = public, pg_catalog;
DO $$
DECLARE n text;
BEGIN
 IF to_regclass('public.pagamentos') IS NULL THEN
  RAISE EXCEPTION 'pagamentos ausente';
 END IF;
 FOREACH n IN ARRAY ARRAY['id','usuario_id','curso_id','tempo_acesso_id','valor_cents',
 'moeda','provedor','oportunidade_id','pagamento_origem_id','mp_preference_id',
 'tipo_compra','vencimento_original','codigo_cupom','vendedor_id'] LOOP
  IF NOT EXISTS (SELECT FROM pg_attribute WHERE attrelid='public.pagamentos'::regclass
    AND attname=n AND NOT attisdropped) THEN RAISE EXCEPTION 'Dependência ausente: %',n; END IF;
 END LOOP;
 IF EXISTS (SELECT FROM information_schema.columns WHERE table_schema='public'
 AND table_name='pagamentos' AND column_name IN ('checkout_identidade','checkout_recebedor_id')
 AND (data_type<>'character varying' OR is_nullable<>'YES' OR column_default IS NOT NULL
 OR character_maximum_length <> CASE column_name WHEN 'checkout_identidade' THEN 43 ELSE 64 END))
 THEN RAISE EXCEPTION 'Colunas de checkout incompatíveis'; END IF;
 IF EXISTS (SELECT FROM information_schema.columns WHERE table_schema='public'
 AND table_name='pagamentos' AND column_name='checkout_meses'
 AND (data_type<>'integer' OR is_nullable<>'YES' OR column_default IS NOT NULL)) THEN
 RAISE EXCEPTION 'checkout_meses incompatível'; END IF;
END $$;
ALTER TABLE public.pagamentos ADD COLUMN IF NOT EXISTS checkout_identidade varchar(43) NULL;
ALTER TABLE public.pagamentos ADD COLUMN IF NOT EXISTS checkout_recebedor_id varchar(64) NULL;
ALTER TABLE public.pagamentos ADD COLUMN IF NOT EXISTS checkout_meses integer NULL;
DO $$
BEGIN
 IF to_regclass('public.uq_pagamentos_checkout_identidade') IS NOT NULL AND NOT EXISTS (
 SELECT FROM pg_index i WHERE i.indexrelid=to_regclass('public.uq_pagamentos_checkout_identidade')
 AND i.indrelid='public.pagamentos'::regclass AND i.indisunique AND i.indisvalid
 AND i.indpred IS NULL AND i.indexprs IS NULL AND i.indnatts=1
 AND i.indkey[0]=(SELECT attnum FROM pg_attribute WHERE attrelid='public.pagamentos'::regclass
 AND attname='checkout_identidade' AND NOT attisdropped)) THEN
 RAISE EXCEPTION 'Índice checkout incompatível'; END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS uq_pagamentos_checkout_identidade ON public.pagamentos(checkout_identidade);
DO $$ BEGIN
 IF EXISTS (SELECT FROM public.pagamentos WHERE
 (checkout_identidade IS NULL) <> (checkout_recebedor_id IS NULL)
 OR (checkout_identidade IS NOT NULL AND
 (checkout_identidade !~ '^[A-Za-z0-9_-]{43}$' OR checkout_recebedor_id !~ '^[1-9][0-9]{0,63}$'
 OR pagamento_origem_id IS NOT NULL OR oportunidade_id IS NULL
 OR checkout_meses IS NULL OR checkout_meses <= 0
 OR moeda IS DISTINCT FROM 'BRL' OR provedor IS DISTINCT FROM 'MERCADO_PAGO'))) THEN
 RAISE EXCEPTION 'Dados preexistentes de checkout incompatíveis'; END IF;
END $$;

DO $$
BEGIN
 IF EXISTS (SELECT FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='public' AND p.proname='proteger_checkout_identidade'
 AND obj_description(p.oid,'pg_proc') IS DISTINCT FROM 'resumao:017:checkout-identidade:v1') THEN
 RAISE EXCEPTION 'Função homônima incompatível'; END IF;
 IF EXISTS (SELECT FROM pg_trigger WHERE tgrelid='public.pagamentos'::regclass
 AND tgname='proteger_checkout_identidade' AND
 (tgfoid IS DISTINCT FROM to_regprocedure('public.proteger_checkout_identidade()')
 OR tgenabled<>'O' OR tgtype<>31 OR tgisinternal)) THEN
 RAISE EXCEPTION 'Trigger checkout incompatível'; END IF;
END $$;
CREATE OR REPLACE FUNCTION public.proteger_checkout_identidade() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
 IF TG_OP='DELETE' THEN
  IF OLD.checkout_identidade IS NOT NULL THEN RAISE EXCEPTION 'Checkout seguro não pode ser excluído'; END IF;
  RETURN OLD;
 END IF;
 IF TG_OP='UPDATE' THEN
  IF OLD.checkout_identidade IS NULL AND NEW.checkout_identidade IS NOT NULL THEN
   RAISE EXCEPTION 'Não converter checkout histórico';
  END IF;
  IF OLD.checkout_identidade IS NOT NULL AND
   (ROW(NEW.id,NEW.checkout_identidade,NEW.checkout_recebedor_id,NEW.checkout_meses,NEW.usuario_id,NEW.curso_id,
   NEW.tempo_acesso_id,NEW.valor_cents,NEW.moeda,NEW.provedor,NEW.oportunidade_id,
   NEW.pagamento_origem_id,NEW.tipo_compra,NEW.vencimento_original,NEW.codigo_cupom,NEW.vendedor_id)
   IS DISTINCT FROM ROW(OLD.id,OLD.checkout_identidade,OLD.checkout_recebedor_id,OLD.checkout_meses,OLD.usuario_id,
   OLD.curso_id,OLD.tempo_acesso_id,OLD.valor_cents,OLD.moeda,OLD.provedor,OLD.oportunidade_id,
   OLD.pagamento_origem_id,OLD.tipo_compra,OLD.vencimento_original,OLD.codigo_cupom,OLD.vendedor_id)
   OR (OLD.mp_preference_id IS NOT NULL AND NEW.mp_preference_id IS DISTINCT FROM OLD.mp_preference_id))
   THEN RAISE EXCEPTION 'Vínculo imutável de checkout'; END IF;
 END IF;
 IF (NEW.checkout_identidade IS NULL) <> (NEW.checkout_recebedor_id IS NULL) THEN
  RAISE EXCEPTION 'Identidade e recebedor devem coexistir'; END IF;
 IF NEW.checkout_identidade IS NOT NULL AND
 (NEW.checkout_identidade !~ '^[A-Za-z0-9_-]{43}$' OR NEW.checkout_recebedor_id !~ '^[1-9][0-9]{0,63}$'
 OR NEW.pagamento_origem_id IS NOT NULL OR NEW.oportunidade_id IS NULL
 OR NEW.checkout_meses IS NULL OR NEW.checkout_meses <= 0
 OR NEW.moeda IS DISTINCT FROM 'BRL' OR NEW.provedor IS DISTINCT FROM 'MERCADO_PAGO') THEN
 RAISE EXCEPTION 'Checkout seguro incompatível'; END IF;
 RETURN NEW;
END $$;
COMMENT ON FUNCTION public.proteger_checkout_identidade() IS 'resumao:017:checkout-identidade:v1';
DO $$ BEGIN
 IF NOT EXISTS (SELECT FROM pg_trigger WHERE tgrelid='public.pagamentos'::regclass
 AND tgname='proteger_checkout_identidade') THEN
 CREATE TRIGGER proteger_checkout_identidade BEFORE INSERT OR UPDATE OR DELETE ON public.pagamentos
 FOR EACH ROW EXECUTE FUNCTION public.proteger_checkout_identidade();
 END IF;
END $$;
COMMIT;
