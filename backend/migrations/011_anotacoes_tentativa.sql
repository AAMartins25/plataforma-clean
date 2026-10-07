-- Não aplicada automaticamente. Preserva registros legados sem tentativa.
BEGIN;
ALTER TABLE anotacoes_aluno_questao ADD COLUMN tentativa_id integer REFERENCES tentativas_bateria(id);
CREATE UNIQUE INDEX uq_anotacao_tentativa_questao
ON anotacoes_aluno_questao(tentativa_id, questao_id)
WHERE tentativa_id IS NOT NULL;
COMMIT;
