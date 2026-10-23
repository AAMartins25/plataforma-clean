-- SOMENTE SELECT, após confirmar COMMIT da 022 e antes de reabrir escritores.
SELECT count(*) AS usuarios,
       count(*) FILTER(WHERE is_admin IS TRUE AND tipo_admin='admin_geral') AS gerais,
       count(*) FILTER(WHERE is_admin IS TRUE AND tipo_admin='admin_geral' AND ativo IS TRUE) AS gerais_ativos,
       count(*) FILTER(WHERE tipo_admin IN ('admin_prod','admin_adm')) AS restritos,
       count(*) FILTER(WHERE is_admin IS NULL
         OR (is_admin IS TRUE AND tipo_admin IS DISTINCT FROM 'admin_geral')
         OR (is_admin IS FALSE AND tipo_admin IS NOT NULL AND tipo_admin NOT IN ('admin_prod','admin_adm'))) AS combinacoes_invalidas
FROM public.usuarios;
SELECT EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='public.usuarios'::regclass
              AND conname='ck_usuarios_tipo_admin' AND contype='c' AND convalidated) AS check_validado;
SELECT count(*) AS registros_auditoria FROM public.auditoria_perfis_admin;
SELECT (SELECT count(*) FROM public.vendedores) AS vendedores,
       (SELECT count(*) FROM public.pagamentos) AS pagamentos,
       (SELECT count(*) FROM public.acessos_curso) AS acessos;
