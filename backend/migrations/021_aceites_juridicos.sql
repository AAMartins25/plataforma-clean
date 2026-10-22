BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
SET LOCAL search_path = public, pg_catalog;

-- Esta migração é executada pelo proprietário esperado do backend, sem SET ROLE.
DO $$
DECLARE nome text;
BEGIN
  IF current_user <> 'postgres' OR current_schema() <> 'public' THEN
    RAISE EXCEPTION '021 exige execução como postgres no schema public';
  END IF;
  IF to_regprocedure('pg_catalog.sha256(bytea)') IS NULL THEN
    RAISE EXCEPTION '021 exige pg_catalog.sha256(bytea)';
  END IF;
  FOREACH nome IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = nome) THEN
      RAISE EXCEPTION '021: role de API ausente: %', nome;
    END IF;
    IF pg_has_role(nome, 'postgres', 'MEMBER') THEN
      RAISE EXCEPTION '021: role de API pertence à role proprietária: %', nome;
    END IF;
  END LOOP;
  FOREACH nome IN ARRAY ARRAY['usuarios', 'cursos', 'tempo_acesso_curso',
                              'oportunidades_compra', 'pagamentos'] LOOP
    IF NOT EXISTS (
      SELECT FROM pg_attribute a
      WHERE a.attrelid = to_regclass('public.' || nome)
        AND a.attname = 'id' AND NOT a.attisdropped
        AND a.atttypid = 'integer'::regtype AND a.attnotnull
    ) THEN
      RAISE EXCEPTION '021: dependência incompatível: public.%(id integer NOT NULL)', nome;
    END IF;
  END LOOP;
END;
$$;


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
ALTER TABLE documentos_juridicos_versoes ADD CONSTRAINT documento_hash_correto CHECK (sha256 = pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(conteudo, 'UTF8')), 'hex'));
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

-- Isolamento limitado aos objetos desta migração. Nenhum default global é alterado.
REVOKE ALL PRIVILEGES ON TABLE
  public.documentos_juridicos_versoes,
  public.politica_aceite_juridico,
  public.aceites_juridicos,
  public.aceites_juridicos_documentos,
  public.aceites_juridicos_pagamentos
FROM PUBLIC, anon, authenticated, service_role;

REVOKE ALL PRIVILEGES ON SEQUENCE
  public.documentos_juridicos_versoes_id_seq,
  public.politica_aceite_juridico_id_seq,
  public.aceites_juridicos_id_seq
FROM PUBLIC, anon, authenticated, service_role;

REVOKE ALL PRIVILEGES ON FUNCTION public.impedir_alteracao_evidencia_juridica()
FROM PUBLIC, anon, authenticated, service_role;

-- Sem políticas e sem FORCE: clientes negados; proprietário postgres preservado.
ALTER TABLE public.documentos_juridicos_versoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.politica_aceite_juridico ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.aceites_juridicos ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.aceites_juridicos_documentos ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.aceites_juridicos_pagamentos ENABLE ROW LEVEL SECURITY;

-- REVOKE não remove privilégios herdados de outras roles. Falhar em vez de
-- publicar objetos que continuem acessíveis por algum caminho de associação.
DO $$
DECLARE
  objeto record;
  api record;
  funcao oid := 'public.impedir_alteracao_evidencia_juridica()'::regprocedure;
  proprietario oid := 'postgres'::regrole;
BEGIN
  FOR objeto IN
    SELECT c.* FROM pg_class c
    WHERE c.oid IN (
      'public.documentos_juridicos_versoes'::regclass,
      'public.politica_aceite_juridico'::regclass,
      'public.aceites_juridicos'::regclass,
      'public.aceites_juridicos_documentos'::regclass,
      'public.aceites_juridicos_pagamentos'::regclass,
      'public.documentos_juridicos_versoes_id_seq'::regclass,
      'public.politica_aceite_juridico_id_seq'::regclass,
      'public.aceites_juridicos_id_seq'::regclass
    )
  LOOP
    IF objeto.relowner <> proprietario THEN
      RAISE EXCEPTION '021: proprietário inesperado: %', objeto.relname;
    END IF;
    IF EXISTS (
      SELECT FROM aclexplode(COALESCE(objeto.relacl,
        acldefault(CASE WHEN objeto.relkind = 'S' THEN 'S'::"char" ELSE 'r'::"char" END,
                   objeto.relowner))) WHERE grantee = 0
    ) THEN
      RAISE EXCEPTION '021: PUBLIC ainda possui privilégios: %', objeto.relname;
    END IF;
    IF objeto.relkind <> 'S' THEN
      IF NOT objeto.relrowsecurity OR objeto.relforcerowsecurity
         OR EXISTS (SELECT FROM pg_policy WHERE polrelid = objeto.oid) THEN
        RAISE EXCEPTION '021: RLS incompatível: %', objeto.relname;
      END IF;
      IF NOT has_table_privilege(proprietario, objeto.oid, 'SELECT')
         OR NOT has_table_privilege(proprietario, objeto.oid, 'INSERT')
         OR NOT has_table_privilege(proprietario, objeto.oid, 'UPDATE') THEN
        RAISE EXCEPTION '021: acesso do backend insuficiente: %', objeto.relname;
      END IF;
    ELSIF NOT has_sequence_privilege(proprietario, objeto.oid, 'USAGE') THEN
      RAISE EXCEPTION '021: backend sem acesso à sequência: %', objeto.relname;
    END IF;
    -- Inclui roles alcançáveis por associação, mesmo com NOINHERIT.
    FOR api IN
      WITH RECURSIVE acessiveis(oid) AS (
        SELECT oid FROM pg_roles WHERE rolname IN ('anon', 'authenticated', 'service_role')
        UNION
        SELECT m.roleid FROM pg_auth_members m JOIN acessiveis a ON m.member = a.oid
      ) SELECT r.oid, r.rolname FROM pg_roles r JOIN acessiveis a ON a.oid = r.oid
    LOOP
      IF objeto.relkind = 'S' THEN
        IF has_sequence_privilege(api.oid, objeto.oid, 'USAGE,SELECT,UPDATE') THEN
          RAISE EXCEPTION '021: acesso de API à sequência % via %', objeto.relname, api.rolname;
        END IF;
      ELSE
        IF has_table_privilege(api.oid, objeto.oid,
             'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
           OR has_any_column_privilege(api.oid, objeto.oid, 'SELECT,INSERT,UPDATE,REFERENCES') THEN
          RAISE EXCEPTION '021: acesso de API à tabela % via %', objeto.relname, api.rolname;
        END IF;
        IF current_setting('server_version_num')::integer >= 170000 THEN
          IF has_table_privilege(api.oid, objeto.oid, 'MAINTAIN') THEN
            RAISE EXCEPTION '021: privilégio MAINTAIN de API: %', objeto.relname;
          END IF;
        END IF;
      END IF;
      IF has_function_privilege(api.oid, funcao, 'EXECUTE') THEN
        RAISE EXCEPTION '021: acesso de API à função via %', api.rolname;
      END IF;
    END LOOP;
  END LOOP;
  IF EXISTS (
    SELECT FROM pg_proc p WHERE p.oid = funcao AND (
      p.proowner <> proprietario OR p.prosecdef OR EXISTS (
        SELECT FROM aclexplode(COALESCE(p.proacl, acldefault('f', p.proowner))) WHERE grantee = 0
      )
    )
  ) OR NOT has_function_privilege(proprietario, funcao, 'EXECUTE') THEN
    RAISE EXCEPTION '021: proprietário, ACL ou modo da função incompatível';
  END IF;
  IF (SELECT count(*) FROM public.politica_aceite_juridico) <> 1
     OR NOT EXISTS (SELECT FROM public.politica_aceite_juridico
                    WHERE id = 1 AND habilitada = FALSE
                      AND termos_id IS NULL AND privacidade_id IS NULL) THEN
    RAISE EXCEPTION '021: política deve permanecer desabilitada e sem par selecionado';
  END IF;
END;
$$;
COMMIT;
