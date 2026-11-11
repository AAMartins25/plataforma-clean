-- 026: formato explícito de anotações e mensagens, sem alterar seus textos.
-- Executar integralmente antes de implantar o backend novo.
BEGIN;

SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '30s';
SET LOCAL search_path = pg_catalog, public;

ALTER TABLE public.anotacoes_aluno_questao
    ADD COLUMN IF NOT EXISTS texto_formato varchar(20) DEFAULT 'texto_puro';

ALTER TABLE public.mensagens_conversa_questao
    ADD COLUMN IF NOT EXISTS texto_formato varchar(20) DEFAULT 'texto_puro';

-- IF NOT EXISTS evita duplicação, mas não verifica uma coluna preexistente.
-- Em caso de divergência, abortar tudo, sem converter ou corrigir dados.
DO $migracao_026$
DECLARE
    tabela text;
BEGIN
    FOREACH tabela IN ARRAY ARRAY[
        'anotacoes_aluno_questao',
        'mensagens_conversa_questao'
    ] LOOP
        IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns AS c
            WHERE c.table_schema = 'public'
              AND c.table_name = tabela
              AND c.column_name = 'texto_formato'
              AND c.data_type = 'character varying'
              AND c.character_maximum_length = 20
              AND c.is_nullable = 'YES'
              AND c.is_generated = 'NEVER'
              AND c.is_identity = 'NO'
              AND c.column_default = '''texto_puro''::character varying'
        ) THEN
            RAISE EXCEPTION
                'Migração 026: definição incompatível de public.%.texto_formato; nenhuma conversão automática foi realizada.',
                tabela;
        END IF;
    END LOOP;
END;
$migracao_026$;

COMMIT;
