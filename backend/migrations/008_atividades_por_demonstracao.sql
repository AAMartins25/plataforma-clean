ALTER TABLE progresso_aulas ADD COLUMN demonstracao_id INTEGER REFERENCES demonstracoes_curso(id);
CREATE INDEX ix_progresso_aulas_demonstracao ON progresso_aulas (demonstracao_id);

ALTER TABLE respostas_aluno_questoes ADD COLUMN demonstracao_id INTEGER REFERENCES demonstracoes_curso(id);
CREATE INDEX ix_respostas_aluno_questoes_demonstracao ON respostas_aluno_questoes (demonstracao_id);

ALTER TABLE tentativas_bateria ADD COLUMN demonstracao_id INTEGER REFERENCES demonstracoes_curso(id);
CREATE INDEX ix_tentativas_bateria_demonstracao ON tentativas_bateria (demonstracao_id);

ALTER TABLE revisoes_aluno ADD COLUMN demonstracao_id INTEGER REFERENCES demonstracoes_curso(id);
CREATE INDEX ix_revisoes_aluno_demonstracao ON revisoes_aluno (demonstracao_id);

ALTER TABLE anotacoes_aluno_questao ADD COLUMN demonstracao_id INTEGER REFERENCES demonstracoes_curso(id);
CREATE INDEX ix_anotacoes_aluno_questao_demonstracao ON anotacoes_aluno_questao (demonstracao_id);

ALTER TABLE conversas_questao_professor ADD COLUMN demonstracao_id INTEGER REFERENCES demonstracoes_curso(id);
CREATE INDEX ix_conversas_questao_professor_demonstracao ON conversas_questao_professor (demonstracao_id);

ALTER TABLE questoes_pratica_marcacoes_aluno ADD COLUMN demonstracao_id INTEGER REFERENCES demonstracoes_curso(id);
CREATE INDEX ix_questoes_pratica_marcacoes_aluno_demonstracao ON questoes_pratica_marcacoes_aluno (demonstracao_id);

ALTER TABLE questoes_pratica_rotatividade_aluno ADD COLUMN demonstracao_id INTEGER REFERENCES demonstracoes_curso(id);
CREATE INDEX ix_questoes_pratica_rotatividade_aluno_demonstracao ON questoes_pratica_rotatividade_aluno (demonstracao_id);
