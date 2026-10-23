"""Validação offline; não extrai arquivos, não importa a aplicação ou conecta ao banco."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile


def verificar(path, sha256, uso):
    data=Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest()!=sha256:
        raise ValueError('SHA-256 externo divergente')
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
        files={}
        for member in archive.getmembers():
            p=PurePosixPath(member.name)
            if not member.isfile() or p.is_absolute() or '..' in p.parts or str(p)!=member.name or member.name in files:
                raise ValueError('Entrada de arquivo inválida ou duplicada')
            if p.name=='.env' or '.git' in p.parts:
                raise ValueError('Conteúdo local/sigiloso não permitido')
            files[member.name]=archive.extractfile(member).read()
    try:manifest=json.loads(files.pop('RELEASE-MANIFEST.json'))
    except (KeyError,ValueError):raise ValueError('Manifesto ausente ou inválido')
    if uso not in manifest['allowed_uses']:
        raise ValueError('Este pacote não é autorizado para '+uso)
    actual={f:hashlib.sha256(b).hexdigest() for f,b in sorted(files.items())}
    if actual!=manifest['files']:
        raise ValueError('Conteúdo divergente do manifesto')
    if uso in {'backend','recuperacao'}:
        if manifest['kind']!='intermediario-seguro' or not {'backend/app/admin_intermediario.py','backend/migrations/022_tipos_administrador.sql'}<=files.keys():
            raise ValueError('Pacote não contém o intermediário compatível com 022')
    return {k:manifest[k] for k in ('release_id','kind','base_sha','allowed_uses')}|{'arquivos_verificados':len(files)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('arquivo');parser.add_argument('--sha256',required=True)
    parser.add_argument('--uso',required=True,choices=['frontend','backend','recuperacao'])
    a=parser.parse_args()
    try:resultado=verificar(a.arquivo,a.sha256,a.uso)
    except (ValueError,OSError,tarfile.TarError) as e:parser.exit(2,str(e)+'\n')
    print(json.dumps(resultado,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
