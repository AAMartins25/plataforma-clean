-- Preserva a referência original mesmo após salvamentos intermediários dos preços.
ALTER TABLE tempo_acesso_curso
    ADD COLUMN IF NOT EXISTS valor_provisorio_original_cents integer;

UPDATE tempo_acesso_curso AS t
SET valor_provisorio_original_cents = CASE
    WHEN t.meses IN (4, 8, 12) THEN t.meses
    ELSE t.valor_cents
END
FROM cursos AS c
WHERE c.id = t.curso_id
  AND c.precos_provisorios = TRUE
  AND t.valor_provisorio_original_cents IS NULL;
