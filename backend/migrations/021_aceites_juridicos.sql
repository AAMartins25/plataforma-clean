BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

CREATE TABLE documentos_juridicos_versoes (
	id SERIAL NOT NULL,
	tipo VARCHAR(20) NOT NULL,
	versao VARCHAR(40) NOT NULL,
	titulo TEXT NOT NULL,
	conteudo TEXT NOT NULL,
	sha256 VARCHAR(64) NOT NULL,
	pdf_sha256 VARCHAR(64),
	publicado_em TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (tipo, versao),
	CHECK (tipo IN ('TERMOS', 'PRIVACIDADE'))
)

;

CREATE TABLE politica_aceite_juridico (
	id SERIAL NOT NULL,
	habilitada BOOLEAN NOT NULL,
	termos_id INTEGER,
	privacidade_id INTEGER,
	PRIMARY KEY (id),
	CHECK (id = 1),
	FOREIGN KEY(termos_id) REFERENCES documentos_juridicos_versoes (id),
	FOREIGN KEY(privacidade_id) REFERENCES documentos_juridicos_versoes (id)
)

;

CREATE TABLE aceites_juridicos (
	id SERIAL NOT NULL,
	usuario_id INTEGER NOT NULL,
	curso_id INTEGER NOT NULL,
	tempo_acesso_id INTEGER NOT NULL,
	oportunidade_id INTEGER NOT NULL,
	meses INTEGER NOT NULL,
	modalidade VARCHAR(20) NOT NULL,
	valor_original_cents INTEGER NOT NULL,
	valor_cents INTEGER NOT NULL,
	declaracao TEXT NOT NULL,
	aceito_em TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(usuario_id) REFERENCES usuarios (id),
	FOREIGN KEY(curso_id) REFERENCES cursos (id),
	FOREIGN KEY(tempo_acesso_id) REFERENCES tempo_acesso_curso (id),
	FOREIGN KEY(oportunidade_id) REFERENCES oportunidades_compra (id)
)

;

CREATE TABLE aceites_juridicos_documentos (
	aceite_id INTEGER NOT NULL,
	documento_id INTEGER NOT NULL,
	PRIMARY KEY (aceite_id, documento_id),
	FOREIGN KEY(aceite_id) REFERENCES aceites_juridicos (id),
	FOREIGN KEY(documento_id) REFERENCES documentos_juridicos_versoes (id)
)

;

CREATE TABLE aceites_juridicos_pagamentos (
	aceite_id INTEGER NOT NULL,
	pagamento_id INTEGER NOT NULL,
	PRIMARY KEY (aceite_id, pagamento_id),
	FOREIGN KEY(aceite_id) REFERENCES aceites_juridicos (id),
	FOREIGN KEY(pagamento_id) REFERENCES pagamentos (id)
)

;
ALTER TABLE documentos_juridicos_versoes ADD CONSTRAINT documento_hash_correto CHECK (sha256 = encode(sha256(convert_to(conteudo, 'UTF8')), 'hex'));
ALTER TABLE politica_aceite_juridico ADD CONSTRAINT politica_par_obrigatorio CHECK (NOT habilitada OR (termos_id IS NOT NULL AND privacidade_id IS NOT NULL AND termos_id <> privacidade_id));
CREATE INDEX ix_aceites_usuario_curso ON aceites_juridicos (usuario_id, curso_id, aceito_em);
CREATE INDEX ix_aceites_pagamento ON aceites_juridicos_pagamentos (pagamento_id);
INSERT INTO politica_aceite_juridico (id, habilitada) VALUES (1, FALSE);
CREATE FUNCTION impedir_alteracao_evidencia_juridica() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'Evidência jurídica imutável: publique uma nova versão';
END;
$$;
CREATE TRIGGER imutavel BEFORE UPDATE OR DELETE ON documentos_juridicos_versoes FOR EACH ROW EXECUTE FUNCTION impedir_alteracao_evidencia_juridica();
CREATE TRIGGER imutavel BEFORE UPDATE OR DELETE ON aceites_juridicos FOR EACH ROW EXECUTE FUNCTION impedir_alteracao_evidencia_juridica();
CREATE TRIGGER imutavel BEFORE UPDATE OR DELETE ON aceites_juridicos_documentos FOR EACH ROW EXECUTE FUNCTION impedir_alteracao_evidencia_juridica();
CREATE TRIGGER imutavel BEFORE UPDATE OR DELETE ON aceites_juridicos_pagamentos FOR EACH ROW EXECUTE FUNCTION impedir_alteracao_evidencia_juridica();
COMMIT;
