-- Preparação somente: executar após autorização, no banco de destino escolhido.
-- Não é executado pelo startup da aplicação. html_v1 e registros antigos intactos.
BEGIN;
CREATE TABLE IF NOT EXISTS imagens_teoria (
    id VARCHAR(36) PRIMARY KEY,
    chave VARCHAR(160) NOT NULL UNIQUE,
    autor_id INTEGER NOT NULL REFERENCES usuarios(id),
    mime VARCHAR(20) NOT NULL,
    tamanho INTEGER NOT NULL CHECK (tamanho > 0 AND tamanho <= 5242880),
    largura INTEGER NOT NULL CHECK (largura BETWEEN 1 AND 8192),
    altura INTEGER NOT NULL CHECK (altura BETWEEN 1 AND 8192),
    sha256 VARCHAR(64) NOT NULL,
    criada_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ultima_atividade TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_imagens_teoria_autor_id ON imagens_teoria(autor_id);
CREATE TABLE IF NOT EXISTS imagens_teoria_materiais (
    material_id INTEGER NOT NULL REFERENCES materiais(id) ON DELETE CASCADE,
    imagem_id VARCHAR(36) NOT NULL REFERENCES imagens_teoria(id),
    PRIMARY KEY (material_id, imagem_id)
);
CREATE INDEX IF NOT EXISTS ix_imagens_teoria_materiais_imagem_id ON imagens_teoria_materiais(imagem_id);
-- Metadados são acessados pelo backend SQLAlchemy, não pela Data API pública.
ALTER TABLE imagens_teoria ENABLE ROW LEVEL SECURITY;
ALTER TABLE imagens_teoria_materiais ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON imagens_teoria, imagens_teoria_materiais FROM PUBLIC;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON imagens_teoria, imagens_teoria_materiais FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON imagens_teoria, imagens_teoria_materiais FROM authenticated;
    END IF;
END $$;
COMMIT;
