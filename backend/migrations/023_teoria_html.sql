-- Executar somente após autorização, antes de publicar o backend da Fase A.
-- NULL identifica todos os materiais legados como texto puro, sem alterar seu conteúdo.
ALTER TABLE materiais
    ADD COLUMN IF NOT EXISTS conteudo_formato VARCHAR(20);
