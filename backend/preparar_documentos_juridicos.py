"""Gera SQL para revisão a partir de textos aprovados. Nunca conecta ao banco.

Exemplo: python backend/preparar_documentos_juridicos.py --termos termos.txt
  --privacidade privacidade.txt --saida documentos-1.0.sql
Os arquivos precisam ser UTF-8; nenhum conteúdo é fornecido por este script.
"""
import argparse
import re
from hashlib import sha256
from pathlib import Path


def gerar(termos: bytes, privacidade: bytes, versao='1.0', *, termos_pdf_sha256=None, privacidade_pdf_sha256=None):
    def literal(s):
        if '\x00' in s:
            raise ValueError('NUL não permitido em texto PostgreSQL')
        return "'" + s.replace("'", "''") + "'"
    comandos = ['BEGIN;', 'SET LOCAL standard_conforming_strings = on;']
    for tipo, titulo, original, pdf_hash in (
        ('TERMOS', 'Termos e Condições de Contratação e Uso', termos, termos_pdf_sha256),
        ('PRIVACIDADE', 'Política de Privacidade e Proteção de Dados Pessoais', privacidade, privacidade_pdf_sha256),
    ):
        conteudo = original.decode('utf-8')
        if not conteudo.strip():
            raise ValueError('Documento vazio')
        valores = ', '.join(literal(v) for v in (tipo, versao, titulo, conteudo, sha256(original).hexdigest()))
        if pdf_hash is not None and not re.fullmatch(r"[0-9a-f]{64}", pdf_hash):
            raise ValueError('Hash PDF inválido')
        valores += ', ' + (literal(pdf_hash) if pdf_hash else 'NULL')
        comandos.append('INSERT INTO documentos_juridicos_versoes '
            '(tipo, versao, titulo, conteudo, sha256, pdf_sha256, publicado_em) VALUES (' + valores + ', CURRENT_TIMESTAMP);')
    comandos += ['-- Publicar conteúdo não ativa a obrigatoriedade.', 'COMMIT;']
    return '\n'.join(comandos) + '\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--termos', required=True, type=Path)
    parser.add_argument('--privacidade', required=True, type=Path)
    parser.add_argument('--termos-pdf', type=Path)
    parser.add_argument('--privacidade-pdf', type=Path)
    parser.add_argument('--versao', default='1.0')
    parser.add_argument('--saida', required=True, type=Path)
    args = parser.parse_args()
    sql = gerar(args.termos.read_bytes(), args.privacidade.read_bytes(), args.versao,
        termos_pdf_sha256=sha256(args.termos_pdf.read_bytes()).hexdigest() if args.termos_pdf else None,
        privacidade_pdf_sha256=sha256(args.privacidade_pdf.read_bytes()).hexdigest() if args.privacidade_pdf else None)
    # x impede sobrescrever artefatos já preparados.
    with args.saida.open('x', encoding='utf-8', newline='') as arquivo:
        arquivo.write(sql)
