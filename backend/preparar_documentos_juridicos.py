"""Gera SQL para revisão a partir de textos aprovados. Nunca conecta ao banco.

Exemplo: python backend/preparar_documentos_juridicos.py --termos termos.txt
  --privacidade privacidade.txt --saida documentos-1.0.sql
Os arquivos precisam ser UTF-8; nenhum conteúdo é fornecido por este script.
"""
import argparse
import base64
import re
from hashlib import sha256
from pathlib import Path


def _literal(s):
    if '\x00' in s:
        raise ValueError('NUL não permitido em texto PostgreSQL')
    return "'" + s.replace("'", "''") + "'"


def _conteudo_sql(original: bytes):
    """Transporta bytes aprovados em ASCII; PostgreSQL reconstrói o UTF-8 exato."""
    conteudo = original.decode('utf-8')
    if not conteudo.strip():
        raise ValueError('Documento vazio')
    if '\x00' in conteudo:
        raise ValueError('NUL não permitido em texto PostgreSQL')
    payload = base64.b64encode(original).decode('ascii')
    partes = [_literal(payload[i:i+96]) for i in range(0, len(payload), 96)]
    return "pg_catalog.convert_from(pg_catalog.decode(\n    " + " ||\n    ".join(partes) + ", 'base64'), 'UTF8')"


def gerar_conferencia(termos: bytes, privacidade: bytes, versao='1.0'):
    """SELECT independente, sem INSERT, para conferir o transporte no SQL Editor."""
    linhas = []
    for tipo, original in (('TERMOS', termos), ('PRIVACIDADE', privacidade)):
        linhas.append('(' + ', '.join((_literal(tipo), _literal(versao),
            _conteudo_sql(original), _literal(sha256(original).hexdigest()))) + ')')
    return ("WITH entrada(tipo, versao, conteudo, hash_esperado) AS (VALUES\n"
        + ',\n'.join(linhas) + "\n)\n"
        + "SELECT tipo, versao, octet_length(conteudo) AS bytes_utf8, hash_esperado,\n"
        + "pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(conteudo, 'UTF8')), 'hex') AS hash_calculado,\n"
        + "hash_esperado = pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(conteudo, 'UTF8')), 'hex') AS confere\n"
        + "FROM entrada ORDER BY tipo;\n")


def gerar(termos: bytes, privacidade: bytes, versao='1.0', *, termos_pdf_sha256=None, privacidade_pdf_sha256=None):
    comandos = ['BEGIN;', 'SET LOCAL standard_conforming_strings = on;']
    for tipo, titulo, original, pdf_hash in (
        ('TERMOS', 'Termos e Condições de Contratação e Uso', termos, termos_pdf_sha256),
        ('PRIVACIDADE', 'Política de Privacidade e Proteção de Dados Pessoais', privacidade, privacidade_pdf_sha256),
    ):
        valores = ', '.join((_literal(tipo), _literal(versao), _literal(titulo),
            _conteudo_sql(original), _literal(sha256(original).hexdigest())))
        if pdf_hash is not None and not re.fullmatch(r"[0-9a-f]{64}", pdf_hash):
            raise ValueError('Hash PDF inválido')
        valores += ', ' + (_literal(pdf_hash) if pdf_hash else 'NULL')
        comandos.append('INSERT INTO documentos_juridicos_versoes '
            '(tipo, versao, titulo, conteudo, sha256, pdf_sha256, publicado_em) VALUES (' + valores + ', CURRENT_TIMESTAMP);')
    comandos += ['/* Publicar conteúdo não ativa a obrigatoriedade. */', 'COMMIT;']
    return '\n'.join(comandos) + '\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--termos', required=True, type=Path)
    parser.add_argument('--privacidade', required=True, type=Path)
    parser.add_argument('--termos-pdf', type=Path)
    parser.add_argument('--privacidade-pdf', type=Path)
    parser.add_argument('--versao', default='1.0')
    parser.add_argument('--saida', required=True, type=Path)
    parser.add_argument('--conferencia', type=Path, help='Arquivo SELECT opcional, sem escrita no banco')
    args = parser.parse_args()
    sql = gerar(args.termos.read_bytes(), args.privacidade.read_bytes(), args.versao,
        termos_pdf_sha256=sha256(args.termos_pdf.read_bytes()).hexdigest() if args.termos_pdf else None,
        privacidade_pdf_sha256=sha256(args.privacidade_pdf.read_bytes()).hexdigest() if args.privacidade_pdf else None)
    # x impede sobrescrever artefatos já preparados.
    with args.saida.open('x', encoding='utf-8', newline='') as arquivo:
        arquivo.write(sql)

    if args.conferencia:
        with args.conferencia.open('x', encoding='utf-8', newline='') as arquivo:
            arquivo.write(gerar_conferencia(args.termos.read_bytes(), args.privacidade.read_bytes(), args.versao))
