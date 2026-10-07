-- PROPOSTA: não aplicada. Executar somente após auditoria e autorização.
BEGIN;
-- Falhar antes de alterações se a estrutura não admitir a regra de unicidade.
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM aulas a JOIN pastas p ON p.id=a.pasta_id
             WHERE p.curso_assunto_proprio_id IS NOT NULL AND p.tipo='TEORIA'
             GROUP BY a.pasta_id HAVING count(*) > 1) THEN
    RAISE EXCEPTION 'Há pastas de assunto com mais de uma aula; auditar antes da migração';
  END IF;
END $$;
ALTER TABLE revisoes_aluno ADD COLUMN status varchar(20);
UPDATE revisoes_aluno SET status = CASE WHEN concluida THEN 'CONCLUIDA' ELSE 'PENDENTE' END;
ALTER TABLE revisoes_aluno ALTER COLUMN status SET DEFAULT 'PENDENTE';
ALTER TABLE revisoes_aluno ALTER COLUMN status SET NOT NULL;
ALTER TABLE revisoes_aluno ADD COLUMN concluida_em timestamp;
ALTER TABLE revisoes_aluno ADD COLUMN cancelada_em timestamp;
ALTER TABLE revisoes_aluno ADD COLUMN motivo_cancelamento varchar(50);
ALTER TABLE revisoes_aluno ADD CONSTRAINT revisao_status CHECK (status IN ('PENDENTE','CONCLUIDA','CANCELADA'));
ALTER TABLE revisoes_aluno ADD CONSTRAINT revisao_etapa CHECK (etapa BETWEEN 1 AND 4);
-- Dados legados sem contexto não são apagados: a validação aborta a migração.
ALTER TABLE revisoes_aluno ADD CONSTRAINT revisao_contexto CHECK ((contratacao_id IS NULL) <> (demonstracao_id IS NULL));
ALTER TABLE tentativas_bateria ADD COLUMN revisao_id integer REFERENCES revisoes_aluno(id);
CREATE INDEX ix_tentativas_bateria_revisao_id ON tentativas_bateria(revisao_id);
CREATE UNIQUE INDEX uq_revisao_pendente_demo ON revisoes_aluno(usuario_id,pasta_id,demonstracao_id) WHERE status='PENDENTE' AND demonstracao_id IS NOT NULL;
CREATE UNIQUE INDEX uq_revisao_pendente_contratacao ON revisoes_aluno(usuario_id,pasta_id,contratacao_id) WHERE status='PENDENTE' AND contratacao_id IS NOT NULL;
-- Etapas podem repetir após perda de objeto; agenda pendente única + bloqueio
-- transacional e conclusão idempotente impedem duplicação, preservando o histórico.
CREATE UNIQUE INDEX uq_tentativa_revisao_bateria ON tentativas_bateria(revisao_id,bateria_id) WHERE revisao_id IS NOT NULL AND ativo;
CREATE UNIQUE INDEX uq_pasta_assunto_proprio ON pastas(curso_assunto_proprio_id) WHERE curso_assunto_proprio_id IS NOT NULL;
-- Índice parcial não pode consultar pastas: trigger restringe a regra ao domínio próprio.
CREATE FUNCTION validar_aula_unica_assunto() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM id FROM pastas WHERE id=NEW.pasta_id FOR UPDATE;
  IF EXISTS (SELECT 1 FROM pastas WHERE id=NEW.pasta_id AND curso_assunto_proprio_id IS NOT NULL AND tipo='TEORIA')
     AND EXISTS (SELECT 1 FROM aulas WHERE pasta_id=NEW.pasta_id AND id<>NEW.id) THEN
    RAISE EXCEPTION 'O assunto já possui sua aula técnica';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER aula_unica_assunto BEFORE INSERT OR UPDATE OF pasta_id ON aulas FOR EACH ROW EXECUTE FUNCTION validar_aula_unica_assunto();
COMMIT;
