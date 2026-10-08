-- Proposta: aplicar somente após autorização e auditoria dos dados legados.
BEGIN;
ALTER TABLE conversas_questao_professor ADD COLUMN tentativa_id integer REFERENCES tentativas_bateria(id);
CREATE UNIQUE INDEX uq_conversa_tentativa_questao
ON conversas_questao_professor(tentativa_id, questao_id)
WHERE tentativa_id IS NOT NULL;
ALTER TABLE conversas_questao_professor ADD CONSTRAINT conversa_contexto
CHECK ((contratacao_id IS NULL) <> (demonstracao_id IS NULL));
ALTER TABLE conversas_questao_professor ADD CONSTRAINT conversa_status
CHECK (status IN ('ABERTA','AGUARDANDO_RESPOSTA_FINAL','ENCERRADA'));
ALTER TABLE mensagens_conversa_questao ADD CONSTRAINT mensagem_autor
CHECK (autor IN ('ALUNO','PROFESSOR'));
COMMIT;
