SELECT c.relname AS objeto,
       c.relkind AS tipo_objeto,
       pg_get_userbyid(c.relowner) AS proprietario,
       c.relrowsecurity AS rls,
       c.relforcerowsecurity AS rls_forcado
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname IN ('usuarios', 'auditoria_perfis_admin')
ORDER BY c.relname;

SELECT c.relname AS tabela,
       a.attnum AS posicao,
       a.attname AS coluna,
       format_type(a.atttypid, a.atttypmod) AS tipo,
       a.attnotnull AS obrigatoria,
       pg_get_expr(d.adbin, d.adrelid) AS valor_padrao,
       a.attidentity AS identidade,
       a.attgenerated AS gerada
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_attrdef d
       ON d.adrelid = a.attrelid AND d.adnum = a.attnum
WHERE n.nspname = 'public'
  AND a.attnum > 0
  AND NOT a.attisdropped
  AND (
    c.relname = 'auditoria_perfis_admin'
    OR (
      c.relname = 'usuarios'
      AND a.attname IN ('id', 'is_admin', 'tipo_admin')
    )
  )
ORDER BY c.relname, a.attnum;

SELECT c.relname AS tabela,
       k.conname AS constraint_nome,
       k.contype AS tipo,
       k.convalidated AS validada,
       k.condeferrable AS adiavel,
       k.condeferred AS inicialmente_adiada,
       pg_get_constraintdef(k.oid, true) AS definicao,
       CASE WHEN k.conindid <> 0
            THEN pg_get_indexdef(k.conindid)
       END AS indice_associado
FROM pg_constraint k
JOIN pg_class c ON c.oid = k.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname IN ('usuarios', 'auditoria_perfis_admin')
ORDER BY c.relname, k.conname;

SELECT t.relname AS tabela,
       a.attname AS coluna,
       ns.nspname AS schema_sequencia,
       s.relname AS sequencia,
       d.deptype AS dependencia,
       format_type(q.seqtypid, NULL) AS tipo,
       q.seqstart AS inicio,
       q.seqincrement AS incremento,
       q.seqmin AS minimo,
       q.seqmax AS maximo,
       q.seqcache AS cache,
       q.seqcycle AS ciclica
FROM pg_class t
JOIN pg_namespace nt ON nt.oid = t.relnamespace
JOIN pg_attribute a
  ON a.attrelid = t.oid AND a.attname = 'id'
JOIN pg_depend d
  ON d.refclassid = 'pg_class'::regclass
 AND d.refobjid = t.oid
 AND d.refobjsubid = a.attnum
 AND d.classid = 'pg_class'::regclass
 AND d.deptype IN ('a', 'i')
JOIN pg_class s ON s.oid = d.objid AND s.relkind = 'S'
JOIN pg_namespace ns ON ns.oid = s.relnamespace
JOIN pg_sequence q ON q.seqrelid = s.oid
WHERE nt.nspname = 'public'
  AND t.relname = 'auditoria_perfis_admin';

SELECT c.relname AS tabela,
       t.tgname AS trigger_nome,
       t.tgenabled AS habilitacao,
       pg_get_triggerdef(t.oid, true) AS definicao
FROM pg_trigger t
JOIN pg_class c ON c.oid = t.tgrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname IN ('usuarios', 'auditoria_perfis_admin')
  AND NOT t.tgisinternal
ORDER BY c.relname, t.tgname;

WITH estado AS (
  SELECT is_admin,
         tipo_admin,
         COALESCE(is_admin, false) AS admin_apos,
         CASE
           WHEN is_admin IS TRUE AND tipo_admin IS NULL
             THEN 'admin_geral'
           ELSE tipo_admin
         END AS tipo_apos
  FROM public.usuarios
)
SELECT count(*) AS usuarios,
       count(*) FILTER (
         WHERE is_admin IS NULL
       ) AS linhas_do_primeiro_update,
       count(*) FILTER (
         WHERE is_admin IS TRUE AND tipo_admin IS NULL
       ) AS linhas_do_segundo_update,
       count(*) FILTER (
         WHERE NOT (
           (admin_apos = false AND
             (tipo_apos IS NULL OR
              tipo_apos IN ('admin_prod', 'admin_adm')))
           OR
           (admin_apos = true AND
             tipo_apos IS NOT NULL AND
             tipo_apos = 'admin_geral')
         )
       ) AS invalidos_apos_updates,
       count(*) FILTER (
         WHERE tipo_admin IN ('admin_prod', 'admin_adm')
       ) AS restritos_existentes,
       count(*) FILTER (
         WHERE is_admin IS TRUE AND tipo_admin = 'admin_geral'
       ) AS gerais_ja_classificados
FROM estado;

SELECT count(*) AS registros_de_auditoria
FROM public.auditoria_perfis_admin;
