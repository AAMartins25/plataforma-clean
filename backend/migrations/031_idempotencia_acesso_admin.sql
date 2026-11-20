-- Aplicar manualmente antes do backend correspondente; não altera históricos.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
-- A existência prévia interrompe a transação: conferir o esquema antes de prosseguir.
CREATE TABLE public.operacoes_acesso_admin (
    chave varchar(64) PRIMARY KEY,
    administrador_id integer NOT NULL REFERENCES public.usuarios(id),
    hash_requisicao varchar(64) NOT NULL,
    contratacao_id integer NOT NULL REFERENCES public.contratacoes_curso(id),
    acesso_id integer NOT NULL REFERENCES public.acessos_curso(id),
    criada_em timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP
);
COMMIT;
