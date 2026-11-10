-- Migração aditiva: NULL identifica texto legado; nenhum conteúdo é reescrito.
BEGIN;
ALTER TABLE questoes ADD COLUMN IF NOT EXISTS enunciado_formato varchar(20);
ALTER TABLE questoes ADD COLUMN IF NOT EXISTS comentario_formato varchar(20);
ALTER TABLE alternativas ADD COLUMN IF NOT EXISTS texto_formato varchar(20);
CREATE TABLE IF NOT EXISTS imagens_questoes (
    imagem_id varchar(36) NOT NULL REFERENCES imagens_teoria(id) ON DELETE RESTRICT,
    questao_id integer NOT NULL REFERENCES questoes(id) ON DELETE CASCADE,
    PRIMARY KEY (imagem_id, questao_id)
);
CREATE INDEX IF NOT EXISTS ix_imagens_questoes_questao_id ON imagens_questoes(questao_id);
-- Mesmo isolamento dos metadados de imagens da teoria.
ALTER TABLE imagens_questoes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON imagens_questoes FROM PUBLIC;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON imagens_questoes FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON imagens_questoes FROM authenticated;
    END IF;
END $$;
COMMIT;
