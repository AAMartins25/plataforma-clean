-- Vincula atividades à contratação sem excluir históricos.
-- Aplicar inicialmente apenas no banco local de testes.

BEGIN;

ALTER TABLE progresso_aulas ADD COLUMN contratacao_id INTEGER REFERENCES contratacoes_curso(id);
CREATE INDEX ix_progresso_aulas_contratacao ON progresso_aulas (contratacao_id);

ALTER TABLE respostas_aluno_questoes ADD COLUMN contratacao_id INTEGER REFERENCES contratacoes_curso(id);
CREATE INDEX ix_respostas_aluno_questoes_contratacao ON respostas_aluno_questoes (contratacao_id);

ALTER TABLE tentativas_bateria ADD COLUMN contratacao_id INTEGER REFERENCES contratacoes_curso(id);
CREATE INDEX ix_tentativas_bateria_contratacao ON tentativas_bateria (contratacao_id);

ALTER TABLE revisoes_aluno ADD COLUMN contratacao_id INTEGER REFERENCES contratacoes_curso(id);
CREATE INDEX ix_revisoes_aluno_contratacao ON revisoes_aluno (contratacao_id);

ALTER TABLE anotacoes_aluno_questao ADD COLUMN contratacao_id INTEGER REFERENCES contratacoes_curso(id);
CREATE INDEX ix_anotacoes_aluno_questao_contratacao ON anotacoes_aluno_questao (contratacao_id);

ALTER TABLE conversas_questao_professor ADD COLUMN contratacao_id INTEGER REFERENCES contratacoes_curso(id);
CREATE INDEX ix_conversas_questao_professor_contratacao ON conversas_questao_professor (contratacao_id);

ALTER TABLE questoes_pratica_marcacoes_aluno ADD COLUMN contratacao_id INTEGER REFERENCES contratacoes_curso(id);
CREATE INDEX ix_questoes_pratica_marcacoes_aluno_contratacao ON questoes_pratica_marcacoes_aluno (contratacao_id);

ALTER TABLE questoes_pratica_rotatividade_aluno ADD COLUMN contratacao_id INTEGER REFERENCES contratacoes_curso(id);
CREATE INDEX ix_questoes_pratica_rotatividade_aluno_contratacao ON questoes_pratica_rotatividade_aluno (contratacao_id);

COMMIT;
