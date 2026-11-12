"""Migração 027 em PostgreSQL descartável via Docker; nunca usa DATABASE_URL.
Ativar TEST_MIGRACAO027_PG=1. Cada caso cria e remove seu próprio banco vazio.
TEST_MIGRACAO027_CONTAINER escolhe um dos contêineres de teste permitidos.
"""
from pathlib import Path
import os
import subprocess
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get('TEST_MIGRACAO027_PG') != '1',
    reason='Requer PostgreSQL descartável explícito e TEST_MIGRACAO027_PG=1')
SQL = (Path(__file__).parent / 'migrations/027_metadados_cursos.sql').read_text()
CONTAINER = os.environ.get('TEST_MIGRACAO027_CONTAINER', 'gestao-cursos-027-test')
PERMITIDOS = {'gestao-cursos-027-test', 'gestao-cursos-027-refino15', 'gestao-cursos-027-refino17'}


def psql(sql, banco, ok=True):
    assert CONTAINER in PERMITIDOS, 'Somente contêineres locais de teste explícitos'
    p = subprocess.run(
        ['docker', 'exec', '-i', CONTAINER, 'psql', '-X', '-U', 'postgres',
         '-d', banco, '-v', 'ON_ERROR_STOP=1', '-At'],
        input=sql, text=True, capture_output=True)
    if ok:
        assert p.returncode == 0, p.stderr
    else:
        assert p.returncode != 0, 'SQL incompatível foi aceito'
    return p.stdout.strip() if ok else p.stderr


@pytest.fixture
def banco():
    nome = 'm027_' + uuid4().hex
    psql(f'CREATE DATABASE {nome}', 'postgres')
    try:
        yield nome
    finally:
        psql(f'DROP DATABASE {nome}', 'postgres')


def preparar(banco, chave='PRIMARY KEY'):
    psql(f'''CREATE TABLE public.usuarios(id integer NOT NULL {chave}, nome varchar NOT NULL);
        CREATE TABLE public.cursos(id integer PRIMARY KEY,nome varchar(255) NOT NULL,
          ativo boolean,publicado boolean,descricao_publica text);
        INSERT INTO public.usuarios VALUES (7,'Produtor');
        INSERT INTO public.cursos VALUES (1,'Legado',true,false,'Descrição histórica');
        CREATE TABLE public.diag_alunos(id integer PRIMARY KEY);
        INSERT INTO public.diag_alunos VALUES (9);
        CREATE TABLE public.diag_vinculos(aluno_id integer REFERENCES public.diag_alunos(id),
          curso_id integer REFERENCES public.cursos(id));
        INSERT INTO public.diag_vinculos VALUES(9,1);''', banco)


def snapshot(banco):
    return psql('''SELECT jsonb_build_object(
      'colunas',(SELECT jsonb_agg(to_jsonb(c) ORDER BY table_name,ordinal_position)
        FROM information_schema.columns c WHERE table_schema='public'),
      'constraints',(SELECT jsonb_agg(jsonb_build_array(conrelid,conname,
        pg_get_constraintdef(oid),convalidated) ORDER BY conrelid,conname)
        FROM pg_constraint WHERE connamespace='public'::regnamespace),
      'indices',(SELECT jsonb_agg(jsonb_build_array(indexname,indexdef) ORDER BY indexname)
        FROM pg_indexes WHERE schemaname='public'),
      'curso',(SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM public.cursos c),
      'usuarios',(SELECT jsonb_agg(to_jsonb(u) ORDER BY id) FROM public.usuarios u),
      'vinculos',(SELECT jsonb_agg(to_jsonb(v)) FROM public.diag_vinculos v));''', banco)


def rejeitar_sem_alterar(banco, mensagem):
    antes = snapshot(banco)
    erro = psql(SQL, banco, ok=False)
    assert mensagem in erro, erro
    assert snapshot(banco) == antes


def test_inicial_reaplicacao_na_mesma_sessao_e_dados_legados(banco):
    preparar(banco)
    saida = psql(SQL + SQL + '''
        SELECT 'temporarias='||count(*) FROM pg_class
        WHERE relnamespace=pg_my_temp_schema()
          AND relname LIKE 'm027_cursos_checks_%';''', banco)
    assert 'temporarias=0' in saida
    assert psql("SELECT nome||':'||descricao_publica FROM cursos", banco) == 'Legado:Descrição histórica'
    assert psql('SELECT count(*) FROM cursos WHERE banca IS NULL AND cargo IS NULL AND orgao IS NULL AND ano IS NULL AND uf IS NULL AND produtor_id IS NULL', banco) == '1'
    assert psql('SELECT aluno_id||\':\'||curso_id FROM diag_vinculos', banco) == '9:1'
    antes = snapshot(banco)
    psql(SQL, banco)
    assert snapshot(banco) == antes
    assert psql("SELECT count(*) FROM pg_constraint WHERE conrelid='public.cursos'::regclass AND (conname LIKE 'ck_cursos_%_metadado' OR conname='fk_cursos_produtor_usuario')", banco) == '6'
    assert psql("SELECT count(*) FROM pg_indexes WHERE schemaname='public' AND tablename='cursos'", banco) == '1'
    psql("INSERT INTO cursos(id,nome,banca,cargo,orgao,ano,uf,produtor_id) VALUES(2,'Novo','Banca','Cargo','Órgão',2026,'RO',7)", banco)
    for campo, valor in [('ano','999'), ('ano','10000'), ('uf',"'XX'"), ('banca',"' '"), ('produtor_id','999')]:
        psql(f'UPDATE cursos SET {campo}={valor} WHERE id=2', banco, ok=False)
    psql("UPDATE cursos SET nome='Legado atualizado' WHERE id=1", banco)


@pytest.mark.parametrize('campo,tipo,expressao', [
    ('banca','varchar(255)', 'banca IS NULL OR length(btrim(banca)) > 1'),
    ('cargo','varchar(255)', 'cargo IS NULL OR length(btrim(cargo)) > 1'),
    ('orgao','varchar(255)', 'orgao IS NULL OR length(btrim(orgao)) > 1'),
    ('ano','integer', 'ano IS NULL OR ano BETWEEN 1900 AND 9999'),
    ('uf','varchar(2)', "uf IS NULL OR uf IN ('RO','SP')"),
])
def test_check_homonimo_diferente_aborta_sem_alterar(banco,campo,tipo,expressao):
    preparar(banco)
    psql(f'ALTER TABLE cursos ADD COLUMN {campo} {tipo}; ALTER TABLE cursos ADD CONSTRAINT ck_cursos_{campo}_metadado CHECK({expressao}) NOT VALID', banco)
    rejeitar_sem_alterar(banco, f'ck_cursos_{campo}_metadado')


def test_check_compativel_com_parenteses_e_espacos_diferentes(banco):
    preparar(banco)
    psql('''ALTER TABLE cursos ADD COLUMN ano integer;
      ALTER TABLE cursos ADD CONSTRAINT ck_cursos_ano_metadado
        CHECK( ( ANO IS NULL ) OR ( ( ANO BETWEEN 1000 AND 9999 ) ) ) NOT VALID;''', banco)
    oid = psql("SELECT oid FROM pg_constraint WHERE conrelid='cursos'::regclass AND conname='ck_cursos_ano_metadado'", banco)
    psql(SQL, banco)
    assert psql("SELECT oid FROM pg_constraint WHERE conrelid='cursos'::regclass AND conname='ck_cursos_ano_metadado'", banco) == oid


@pytest.mark.parametrize('extra', ['NO INHERIT', 'UNIQUE'])
def test_tipo_ou_heranca_incompativel(banco,extra):
    preparar(banco)
    definicao = 'UNIQUE(ano)' if extra == 'UNIQUE' else 'CHECK(ano IS NULL OR ano BETWEEN 1000 AND 9999) NO INHERIT'
    psql(f'ALTER TABLE cursos ADD COLUMN ano integer; ALTER TABLE cursos ADD CONSTRAINT ck_cursos_ano_metadado {definicao}', banco)
    rejeitar_sem_alterar(banco, 'tipo ou NO INHERIT incompatível')


@pytest.mark.parametrize('indice', [
    '',
    'CREATE UNIQUE INDEX diag_id ON usuarios(id) WHERE id > 0',
    'CREATE UNIQUE INDEX diag_id ON usuarios((id + 0))',
    'CREATE UNIQUE INDEX diag_id ON usuarios(id,nome)',
    'ALTER TABLE usuarios ADD CONSTRAINT diag_id UNIQUE(id) DEFERRABLE',
])
def test_chave_ausente_ou_inadequada_aborta_antes_das_colunas(banco,indice):
    preparar(banco, '')
    if indice:
        psql(indice, banco)
    rejeitar_sem_alterar(banco, 'Requer chave única imediata, válida e não parcial')


@pytest.mark.parametrize('chave,indice', [
    ('PRIMARY KEY',''),
    ('UNIQUE',''),
    ('','CREATE UNIQUE INDEX diag_id ON usuarios(id)'),
    ('','CREATE UNIQUE INDEX diag_id ON usuarios(id) INCLUDE(nome)'),
])
def test_chaves_aceitas_pelo_postgresql(banco,chave,indice):
    preparar(banco,chave)
    if indice:
        psql(indice,banco)
    psql(SQL+SQL,banco)


def test_indice_unico_invalido_rejeitado(banco):
    preparar(banco,'')
    psql("INSERT INTO usuarios VALUES(7,'Outro')", banco)
    psql('CREATE UNIQUE INDEX CONCURRENTLY diag_invalido ON usuarios(id)', banco, ok=False)
    assert psql("SELECT indisvalid FROM pg_index WHERE indexrelid='diag_invalido'::regclass", banco) == 'f'
    rejeitar_sem_alterar(banco, 'Requer chave única imediata, válida e não parcial')


def test_fk_homonima_incompativel_preservada(banco):
    preparar(banco)
    psql('''ALTER TABLE cursos ADD COLUMN produtor_id integer;
      ALTER TABLE cursos ADD CONSTRAINT fk_cursos_produtor_usuario
        FOREIGN KEY(produtor_id) REFERENCES usuarios(id) ON DELETE CASCADE NOT VALID;''', banco)
    rejeitar_sem_alterar(banco, 'FK de produtor incompatível')


def test_coluna_homonima_incompativel_preservada(banco):
    preparar(banco)
    psql('ALTER TABLE cursos ADD COLUMN cargo text', banco)
    rejeitar_sem_alterar(banco, 'Coluna cursos.cargo incompatível')


def test_coluna_descartada_nao_afeta_comparacao_nativa(banco):
    preparar(banco)
    psql('ALTER TABLE cursos ADD COLUMN descartada text; ALTER TABLE cursos DROP COLUMN descartada', banco)
    psql(SQL+SQL, banco)


def test_restricoes_ja_validadas_sao_preservadas(banco):
    preparar(banco)
    psql(SQL, banco)
    for nome in ['banca','cargo','orgao','ano','uf']:
        psql(f'ALTER TABLE cursos VALIDATE CONSTRAINT ck_cursos_{nome}_metadado', banco)
    psql('ALTER TABLE cursos VALIDATE CONSTRAINT fk_cursos_produtor_usuario', banco)
    antes = snapshot(banco)
    psql(SQL,banco)
    assert snapshot(banco) == antes



def test_reaplicacao_detecta_check_alterado(banco):
    preparar(banco)
    psql(SQL, banco)
    psql("""ALTER TABLE cursos DROP CONSTRAINT ck_cursos_ano_metadado;
      ALTER TABLE cursos ADD CONSTRAINT ck_cursos_ano_metadado
        CHECK(ano IS NULL OR ano BETWEEN 1900 AND 9999) NOT VALID;""", banco)
    rejeitar_sem_alterar(banco, 'ck_cursos_ano_metadado')


def test_rls_permissoes_view_e_trigger_preservados(banco):
    preparar(banco)
    psql("""ALTER TABLE cursos ENABLE ROW LEVEL SECURITY;
      CREATE POLICY diag_leitura ON cursos FOR SELECT USING(ativo IS TRUE);
      GRANT SELECT(nome) ON cursos TO PUBLIC;
      CREATE VIEW public.diag_view AS SELECT id,nome FROM public.cursos;
      CREATE FUNCTION public.diag_trigger() RETURNS trigger LANGUAGE plpgsql
        AS $$ BEGIN RETURN NEW; END $$;
      CREATE TRIGGER diag_trigger BEFORE INSERT ON public.cursos
        FOR EACH ROW EXECUTE FUNCTION public.diag_trigger();""", banco)
    consulta = """SELECT jsonb_build_object(
      'rls',(SELECT jsonb_build_array(relrowsecurity,relforcerowsecurity,relacl)
        FROM pg_class WHERE oid='public.cursos'::regclass),
      'politicas',(SELECT jsonb_agg(to_jsonb(p) ORDER BY policyname)
        FROM pg_policies p WHERE schemaname='public'),
      'grants',(SELECT jsonb_agg(to_jsonb(g) ORDER BY column_name,grantee,privilege_type)
        FROM information_schema.column_privileges g
        WHERE table_schema='public' AND table_name='cursos'),
      'view',pg_get_viewdef('public.diag_view'::regclass),
      'trigger',(SELECT pg_get_triggerdef(oid) FROM pg_trigger
        WHERE tgrelid='public.cursos'::regclass AND tgname='diag_trigger'))"""
    antes = psql(consulta, banco)
    # Compara grants das colunas originais: as novas herdam grants de tabela,
    # se existentes, pela regra normal do PostgreSQL.
    consulta = consulta.replace("table_name='cursos'", "table_name='cursos' AND column_name IN ('id','nome','ativo','publicado','descricao_publica')")
    psql(SQL+SQL, banco)
    assert psql(consulta, banco) == antes
