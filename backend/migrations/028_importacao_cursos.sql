-- Aplicar antes de disponibilizar a versão do importador.
ALTER TABLE cursos ADD COLUMN IF NOT EXISTS precos_provisorios boolean NOT NULL DEFAULT false;
CREATE TABLE IF NOT EXISTS importacoes_curso (
    chave varchar(64) PRIMARY KEY,
    hash_requisicao varchar(64) NOT NULL,
    usuario_id integer NOT NULL REFERENCES usuarios(id),
    curso_id integer NOT NULL REFERENCES cursos(id),
    criado_em timestamp without time zone NOT NULL DEFAULT now()
);
