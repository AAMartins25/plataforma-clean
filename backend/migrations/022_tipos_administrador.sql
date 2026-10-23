-- Executar manualmente, primeiro em PostgreSQL de testes.
-- Requer interrupção dos escritores legados antes da implantação definitiva.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
LOCK TABLE public.usuarios IN ACCESS EXCLUSIVE MODE;
ALTER TABLE public.usuarios ADD COLUMN IF NOT EXISTS tipo_admin varchar(20);
-- Não reclassifica administradores restritos em uma reaplicação.
UPDATE public.usuarios SET is_admin = false WHERE is_admin IS NULL;
UPDATE public.usuarios SET tipo_admin = 'admin_geral'
 WHERE is_admin = true AND tipo_admin IS NULL;
DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM public.usuarios WHERE
    (is_admin = false AND tipo_admin IS NOT NULL AND tipo_admin NOT IN ('admin_prod','admin_adm')) OR
    (is_admin = true AND (tipo_admin IS NULL OR tipo_admin <> 'admin_geral'))) THEN
  RAISE EXCEPTION 'Combinações administrativas inválidas; revisar antes de continuar';
 END IF;
END $$;
ALTER TABLE public.usuarios ALTER COLUMN is_admin SET DEFAULT false;
ALTER TABLE public.usuarios ALTER COLUMN is_admin SET NOT NULL;
ALTER TABLE public.usuarios DROP CONSTRAINT IF EXISTS ck_usuarios_tipo_admin;
ALTER TABLE public.usuarios ADD CONSTRAINT ck_usuarios_tipo_admin CHECK (
 (is_admin = false AND (tipo_admin IS NULL OR tipo_admin IN ('admin_prod','admin_adm'))) OR
 (is_admin = true AND tipo_admin IS NOT NULL AND tipo_admin = 'admin_geral')
);
CREATE TABLE IF NOT EXISTS public.auditoria_perfis_admin (
 id serial PRIMARY KEY,
 autor_id integer NOT NULL REFERENCES public.usuarios(id),
 usuario_id integer NOT NULL REFERENCES public.usuarios(id),
 tipo_anterior varchar(20),
 tipo_novo varchar(20),
 criado_em timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP
);
COMMIT;
