-- Executar antes do backend correspondente, após 028, numa transação única.
-- O registro de importação identifica apenas os cursos importados diretamente;
-- cópias antigas não têm origem comprovada e permanecem na modalidade tradicional.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
DO $$
BEGIN
    IF to_regclass('public.cursos') IS NULL OR to_regclass('public.importacoes_curso') IS NULL THEN
        RAISE EXCEPTION 'Requer public.cursos e public.importacoes_curso (migração 028)';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema='public' AND table_name='cursos'
                     AND column_name='demonstracao_por_ordem') THEN
        ALTER TABLE public.cursos ADD COLUMN demonstracao_por_ordem boolean NOT NULL DEFAULT false;
        UPDATE public.cursos AS c SET demonstracao_por_ordem = true
        WHERE EXISTS (SELECT 1 FROM public.importacoes_curso AS i WHERE i.curso_id = c.id);
    ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns
                      WHERE table_schema='public' AND table_name='cursos'
                        AND column_name='demonstracao_por_ordem' AND data_type='boolean'
                        AND is_nullable='NO' AND column_default = 'false') THEN
        RAISE EXCEPTION 'Coluna demonstracao_por_ordem incompatível; revisar antes de continuar';
    END IF;
END $$;
COMMIT;
