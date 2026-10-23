-- SOMENTE SELECT. Não executar em produção sem autorização específica.
-- Registrar resultados depois de drenar escritores; não imprimir conexões/credenciais.
SELECT current_database()='postgres' AS banco_esperado,
       current_setting('server_version_num')::integer/10000=17 AS postgresql_17,
       current_setting('transaction_isolation')='read committed' AS read_committed,
       current_user=session_user AS papel_atual_igual_ao_da_sessao;
SELECT NOT c.relrowsecurity AS usuarios_sem_rls,
       c.relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user) AS conexao_dona_da_tabela,
       has_table_privilege(current_user,'public.usuarios','SELECT')
       AND has_table_privilege(current_user,'public.usuarios','UPDATE') AS leitura_e_atualizacao
FROM pg_class c WHERE c.oid='public.usuarios'::regclass;
SELECT NOT EXISTS(SELECT 1 FROM information_schema.columns
                  WHERE table_schema='public' AND table_name='usuarios' AND column_name='tipo_admin') AS coluna_ainda_ausente,
       to_regclass('public.auditoria_perfis_admin') IS NULL AS auditoria_ainda_ausente,
       NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid='public.usuarios'::regclass AND NOT tgisinternal) AS sem_triggers_customizados;
SELECT count(*) AS usuarios,
       count(*) FILTER(WHERE is_admin IS TRUE) AS administradores_legados,
       count(*) FILTER(WHERE is_admin IS TRUE AND ativo IS TRUE) AS administradores_ativos,
       count(*) FILTER(WHERE is_admin IS NULL) AS booleanos_nulos,
       count(*) FILTER(WHERE to_jsonb(u)->>'tipo_admin' IN ('admin_prod','admin_adm')) AS restritos_preexistentes
FROM public.usuarios u;
SELECT (SELECT count(*) FROM public.vendedores) AS vendedores,
       (SELECT count(*) FROM public.pagamentos) AS pagamentos,
       (SELECT count(*) FROM public.acessos_curso) AS acessos;
