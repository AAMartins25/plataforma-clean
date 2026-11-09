-- Aplicação manual, antes do backend definitivo; nunca executar no startup.
-- Na mesma sessão, informar explicitamente o papel exclusivo do backend:
-- SELECT set_config('resumao.app_role', 'PAPEL_REAL_DO_BACKEND', false);
-- Não usar os papéis públicos do Supabase. Nenhum dado histórico é reescrito.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
CREATE TABLE public.bloqueios_acesso_reembolso (
    pagamento_id integer PRIMARY KEY REFERENCES public.pagamentos(id),
    reembolso_id integer NOT NULL UNIQUE REFERENCES public.reembolsos_financeiros(id),
    executado_em timestamp without time zone NOT NULL,
    executado_por integer NOT NULL REFERENCES public.usuarios(id)
);
ALTER TABLE public.bloqueios_acesso_reembolso ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.bloqueios_acesso_reembolso FROM PUBLIC;
DO $$
DECLARE
    app_role text := current_setting('resumao.app_role', true);
    papel text;
BEGIN
    IF app_role IS NULL OR btrim(app_role) = ''
       OR app_role IN ('anon', 'authenticated', 'service_role', 'authenticator', 'PUBLIC')
       OR NOT EXISTS (SELECT FROM pg_roles WHERE rolname = app_role) THEN
        RAISE EXCEPTION 'Informe resumao.app_role com o papel exclusivo do backend antes da migração 023';
    END IF;
    -- Neutraliza também privilégios que possam vir de ALTER DEFAULT PRIVILEGES.
    FOREACH papel IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
        IF EXISTS (SELECT FROM pg_roles WHERE rolname = papel) THEN
            EXECUTE format('REVOKE ALL ON public.bloqueios_acesso_reembolso FROM %I', papel);
        END IF;
    END LOOP;
    EXECUTE format('REVOKE ALL ON public.bloqueios_acesso_reembolso FROM %I', app_role);
    EXECUTE format('GRANT SELECT, INSERT ON public.bloqueios_acesso_reembolso TO %I', app_role);
    EXECUTE format('CREATE POLICY bloqueios_backend_leitura ON public.bloqueios_acesso_reembolso FOR SELECT TO %I USING (true)', app_role);
    EXECUTE format('CREATE POLICY bloqueios_backend_registro ON public.bloqueios_acesso_reembolso FOR INSERT TO %I WITH CHECK (true)', app_role);
END $$;
COMMIT;
