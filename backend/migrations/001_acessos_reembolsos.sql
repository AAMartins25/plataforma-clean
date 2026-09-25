-- Migração das tabelas de acesso e reembolso.

-- Revisar o esquema de produção antes da execução.

BEGIN;


CREATE TABLE IF NOT EXISTS concessoes_acesso_admin (
	id SERIAL NOT NULL,
	usuario_id INTEGER NOT NULL,
	curso_id INTEGER NOT NULL,
	data_inicio TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	data_fim TIMESTAMP WITHOUT TIME ZONE,
	ativo BOOLEAN NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(usuario_id) REFERENCES usuarios (id),
	FOREIGN KEY(curso_id) REFERENCES cursos (id)
)

;

CREATE INDEX IF NOT EXISTS ix_concessoes_acesso_admin_id ON concessoes_acesso_admin (id);


CREATE TABLE IF NOT EXISTS reembolsos_financeiros (
	id SERIAL NOT NULL,
	pagamento_id INTEGER NOT NULL,
	metodo VARCHAR(30) NOT NULL,
	valor_cents INTEGER NOT NULL,
	status VARCHAR(30) NOT NULL,
	mp_refund_id VARCHAR,
	chave_idempotencia VARCHAR,
	referencia_comprovante VARCHAR,
	criado_em TIMESTAMP WITHOUT TIME ZONE,
	confirmado_em TIMESTAMP WITHOUT TIME ZONE,
	PRIMARY KEY (id),
	FOREIGN KEY(pagamento_id) REFERENCES pagamentos (id),
	UNIQUE (chave_idempotencia)
)

;

CREATE INDEX IF NOT EXISTS ix_reembolsos_financeiros_id ON reembolsos_financeiros (id);

CREATE INDEX IF NOT EXISTS ix_reembolsos_financeiros_pagamento_id ON reembolsos_financeiros (pagamento_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_reembolsos_pagamento_ativo ON reembolsos_financeiros (pagamento_id) WHERE status IN ('PENDENTE', 'EM_PROCESSAMENTO', 'CONFIRMADO', 'VERIFICACAO_NECESSARIA');


CREATE TABLE IF NOT EXISTS periodos_acesso_pagamento (
	id SERIAL NOT NULL,
	pagamento_id INTEGER NOT NULL,
	usuario_id INTEGER NOT NULL,
	curso_id INTEGER NOT NULL,
	data_inicio TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	data_fim TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	criado_em TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(pagamento_id) REFERENCES pagamentos (id),
	FOREIGN KEY(usuario_id) REFERENCES usuarios (id),
	FOREIGN KEY(curso_id) REFERENCES cursos (id)
)

;

CREATE INDEX IF NOT EXISTS ix_periodos_acesso_pagamento_curso_id ON periodos_acesso_pagamento (curso_id);

CREATE INDEX IF NOT EXISTS ix_periodos_acesso_pagamento_id ON periodos_acesso_pagamento (id);

CREATE UNIQUE INDEX IF NOT EXISTS ix_periodos_acesso_pagamento_pagamento_id ON periodos_acesso_pagamento (pagamento_id);

CREATE INDEX IF NOT EXISTS ix_periodos_acesso_pagamento_usuario_id ON periodos_acesso_pagamento (usuario_id);


CREATE TABLE IF NOT EXISTS demonstracoes_curso (
	id SERIAL NOT NULL,
	usuario_id INTEGER NOT NULL,
	curso_id INTEGER NOT NULL,
	data_inicio TIMESTAMP WITHOUT TIME ZONE,
	data_fim TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	liberado_novamente_em TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	ativo BOOLEAN,
	criado_em TIMESTAMP WITHOUT TIME ZONE,
	PRIMARY KEY (id),
	FOREIGN KEY(usuario_id) REFERENCES usuarios (id),
	FOREIGN KEY(curso_id) REFERENCES cursos (id)
)

;

CREATE INDEX IF NOT EXISTS ix_demonstracoes_curso_id
ON demonstracoes_curso (id);

-- Proteger as duas novas tabelas.
ALTER TABLE reembolsos_financeiros
ENABLE ROW LEVEL SECURITY;

ALTER TABLE periodos_acesso_pagamento
ENABLE ROW LEVEL SECURITY;

COMMIT;