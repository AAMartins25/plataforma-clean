"""Transporte dos documentos aprovado contra a 021 real, apenas PostgreSQL local."""
import base64
import json
import re
from hashlib import sha256
from pathlib import Path

import psycopg
import pytest

from preparar_documentos_juridicos import gerar, gerar_conferencia
from test_migracao021_seguranca_pg import banco, executar, preparar_minimo, defaults_amplos

BASE = Path(__file__).parent
PACOTE = BASE/'documentos_juridicos/1.0'
MANIFESTO = json.loads((PACOTE/'manifesto.json').read_text())['documentos']
MIGRACAO = (BASE/'migrations/021_aceites_juridicos.sql').read_text()
IMPORTACAO = (PACOTE/'documentos-1.0.sql').read_text()
CONFERENCIA = (PACOTE/'conferir-importacao.sql').read_text()


@pytest.fixture
def destino(banco):
    dsn, _ = banco
    preparar_minimo(dsn)
    defaults_amplos(dsn)
    executar(dsn, MIGRACAO)
    return dsn


@pytest.mark.parametrize('transporte', ['original', 'CRLF', 'linha_unica', 'sem_espacos_finais'])
def test_importacao_preserva_bytes_sob_transformacoes(destino, transporte):
    def transformar(s):
        if transporte == 'CRLF':return s.replace('\n','\r\n')
        if transporte == 'linha_unica':return s.replace('\n',' ')
        if transporte == 'sem_espacos_finais':return '\n'.join(l.rstrip() for l in s.splitlines())
        return s
    with psycopg.connect(destino, autocommit=True) as c:
        antes = c.execute('SELECT * FROM public.politica_aceite_juridico').fetchall()
        # Conferência é somente leitura e deve funcionar com o mesmo transporte.
        for row in c.execute(transformar(CONFERENCIA)):
            assert row[4] == row[3] and row[5] is True
        assert c.execute('SELECT count(*) FROM public.documentos_juridicos_versoes').fetchone() == (0,)
        c.execute(transformar(IMPORTACAO))
        assert c.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
        docs = c.execute("SELECT tipo,versao,convert_to(conteudo,'UTF8'),sha256,pdf_sha256,encode(sha256(convert_to(conteudo,'UTF8')),'hex') FROM public.documentos_juridicos_versoes ORDER BY tipo").fetchall()
        assert len(docs) == 2
        for tipo,versao,raw,hash_texto,hash_pdf,hash_db in docs:
            item = next(d for d in MANIFESTO if d['tipo']==tipo)
            assert versao == '1.0'
            assert bytes(raw) == (PACOTE/item['texto']).read_bytes()
            assert hash_texto == hash_db == item['texto_sha256'] == sha256(bytes(raw)).hexdigest()
            assert hash_pdf == item['pdf_sha256'] == sha256((PACOTE/item['pdf']).read_bytes()).hexdigest()
        assert c.execute('SELECT * FROM public.politica_aceite_juridico').fetchall() == antes
        assert antes[0][1] is False
        assert c.execute("SELECT count(*) FROM pg_trigger WHERE tgname='imutavel' AND NOT tgisinternal").fetchone() == (4,)
        assert c.execute("SELECT bool_and(relrowsecurity AND NOT relforcerowsecurity) FROM pg_class WHERE relname=ANY(%s)",(['documentos_juridicos_versoes','politica_aceite_juridico','aceites_juridicos','aceites_juridicos_documentos','aceites_juridicos_pagamentos'],)).fetchone() == (True,)


@pytest.mark.parametrize('tipo', ['TERMOS','PRIVACIDADE'])
def test_reproduz_causa_linhas_achatadas_do_sql_legado(destino, tipo):
    item = next(d for d in MANIFESTO if d['tipo']==tipo)
    original = (PACOTE/item['texto']).read_bytes().decode()
    alterado = original.replace('\n',' ')
    assert sha256(alterado.encode()).hexdigest() != item['texto_sha256']
    literal = lambda s:"'"+s.replace("'","''")+"'"
    # Mesma estratégia do SQL legado: conteúdo literal; hash original preservado.
    sql = 'BEGIN; INSERT INTO public.documentos_juridicos_versoes(tipo,versao,titulo,conteudo,sha256,pdf_sha256,publicado_em) VALUES (' + ','.join(literal(s) for s in [tipo,'1.0',item['titulo'],alterado,item['texto_sha256'],item['pdf_sha256']]) + ',CURRENT_TIMESTAMP); COMMIT;'
    with pytest.raises(psycopg.errors.CheckViolation) as erro:
        executar(destino, sql)
    assert erro.value.sqlstate == '23514'
    assert erro.value.diag.constraint_name == 'documento_hash_correto'
    with psycopg.connect(destino) as c:
        assert c.execute('SELECT count(*) FROM public.documentos_juridicos_versoes').fetchone() == (0,)


def test_corrupcao_da_segunda_carga_reverte_ambos(destino):
    # Altera um byte ASCII do segundo conteúdo codificado, nunca o hash aprovado.
    expressoes = list(re.finditer(r"pg_catalog.decode\(\s*'([A-Za-z0-9+/=]+)'", IMPORTACAO))
    assert len(expressoes) == 2
    pos = expressoes[1].start(1)
    assert IMPORTACAO[pos] == 'I'  # Primeiro byte original é espaço.
    corrompido = IMPORTACAO[:pos]+'J'+IMPORTACAO[pos+1:]
    with pytest.raises(psycopg.errors.CheckViolation) as erro:
        executar(destino, corrompido)
    assert erro.value.diag.constraint_name == 'documento_hash_correto'
    with psycopg.connect(destino) as c:
        assert c.execute('SELECT count(*) FROM public.documentos_juridicos_versoes').fetchone() == (0,)
        assert c.execute('SELECT habilitada FROM public.politica_aceite_juridico').fetchone() == (False,)


def test_fixtures_unicode_e_controles_preservados():
    original = "Fixture sem validade jurídica: 'á' a\u0301\u00a0\t\r\n\f\\fim  \n".encode()
    s = gerar(original, original)
    cargas = re.findall(r"pg_catalog.decode\((.*?), 'base64'\)", s, re.S)
    assert len(cargas) == 2
    for carga in cargas:
        assert base64.b64decode(''.join(re.findall(r"'([A-Za-z0-9+/=]+)'",carga)),validate=True) == original
    assert '\f' not in s and '\r' not in s
    assert '--' not in s  # Achatar linhas não pode comentar o COMMIT.
    with pytest.raises(ValueError):gerar(b'teste\x00',original)
    with pytest.raises(UnicodeDecodeError):gerar(b'\xff',original)
    assert 'INSERT' not in gerar_conferencia(original,original)
