"""Pacotes determinísticos da versão definitiva, limitados ao manifesto de fontes aprovado."""
import difflib
import gzip
import hashlib
from html.parser import HTMLParser
import importlib.metadata
import io
import json
from pathlib import Path, PurePosixPath
import platform
import posixpath
import re
import subprocess
import sys
import tarfile
from urllib.parse import urlsplit
from verificar_artefato import (
    VERSAO, TIPO_BACKEND, TIPO_FRONTEND, MATRIZ, FLAGS, BACKEND_OBRIGATORIO,
    FRONTEND_OBRIGATORIO, caminho_permitido, hashes, hash_arvore, verificar,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFESTO = 'evidencias/manifesto.json'
PACOTE_FRONTEND = 'frontend-perfis-definitivos.tar.gz'
PACOTE_BACKEND = 'backend-perfis-definitivos.tar.gz'
PACOTE_RECUPERACAO = 'recuperacao-perfis-definitivos.tar.gz'
PATCH_FRONTEND = 'frontend-perfis-definitivos.patch'
PATCH_COMPLETO = 'perfis-definitivos-completo.patch'


class Referencias(HTMLParser):
    def __init__(self):
        super().__init__()
        self.locais = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        url = attrs.get('src') if tag == 'script' else attrs.get('href') if tag == 'link' and attrs.get('rel') == 'stylesheet' else None
        if url and not urlsplit(url).scheme and not url.startswith('//'):
            self.locais.append(urlsplit(url).path)


def validar_frontend(files):
    if not FRONTEND_OBRIGATORIO <= files.keys():
        raise ValueError('Frontend definitivo incompleto')
    paginas = sorted(f for f in files if f.startswith('site-html/admin/') and f.endswith('.html'))
    if len(paginas) != 19:
        raise ValueError('Inventário das 19 páginas administrativas mudou; revisar')
    for f, data in files.items():
        if not f.startswith('site-html/') or not f.endswith('.html'):
            continue
        parser = Referencias()
        parser.feed(data.decode())
        for ref in parser.locais:
            destino = posixpath.normpath(posixpath.join('site-html', ref.lstrip('/')) if ref.startswith('/')
                                         else posixpath.join(posixpath.dirname(f), ref))
            if destino not in files:
                raise ValueError('Dependência frontend ausente: ' + f + ' -> ' + destino)
        if f in paginas:
            texto = data.decode()
            if ('admin-acesso.js?v=perfis-1' not in texto or
                    texto.index('admin-acesso.js') > texto.index('../js/app.js') or
                    'admin-intermediario-022.' in texto):
                raise ValueError('Guarda/cache administrativo divergente: ' + f)
    return paginas


def patch_local(baseline, entries):
    lines = []
    for f, data in sorted(entries.items()):
        if baseline.get(f) == data:
            continue
        old, new = baseline.get(f, b'').decode(), data.decode()
        lines.append('diff --git a/' + f + ' b/' + f + '\n')
        if f not in baseline:
            lines.append('new file mode 100644\n')
        for line in difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                        fromfile='a/' + f if f in baseline else '/dev/null', tofile='b/' + f):
            lines.append(line if line.endswith('\n') else line + '\n\\ No newline at end of file\n')
    return ''.join(lines).encode()


def construir(out=None):
    source_bytes = (ROOT / MANIFESTO).read_bytes()
    source = json.loads(source_bytes)
    if (source['manifest_version'] != VERSAO or source['restritos_habilitados'] is not True
            or source['matriz_permissoes'] != MATRIZ or source['is_admin_por_perfil'] != FLAGS):
        raise ValueError('Manifesto de fontes não corresponde à versão definitiva')
    base = source['base_sha']
    if not re.fullmatch('[0-9a-f]{40}', base):
        raise ValueError('Base inválida')
    baseline, modes = {}, {}
    raw = subprocess.check_output(['git', 'archive', base], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive.getmembers():
            if member.isdir():
                continue
            if not member.isfile() or not caminho_permitido(member.name):
                raise ValueError('Base contém entrada não permitida')
            baseline[member.name] = archive.extractfile(member).read()
            modes[member.name] = member.mode
    files = {}
    if MANIFESTO in source['arquivos']:
        raise ValueError('Manifesto de fontes não pode conter seu próprio hash')
    for f, expected in source['arquivos'].items():
        if not caminho_permitido(f) or (ROOT / f).is_symlink():
            raise ValueError('Fonte não permitida: ' + f)
        data = (ROOT / f).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Arquivo do manifesto aprovado mudou: ' + f)
        files[f] = data
    files[MANIFESTO] = source_bytes
    if not set(baseline) <= files.keys():
        raise ValueError('Manifesto omite arquivos da base; remoções exigem revisão explícita')
    if not BACKEND_OBRIGATORIO <= files.keys():
        raise ValueError('Backend definitivo incompleto')
    paginas = validar_frontend(files)
    frontend = {f: b for f, b in files.items() if f.startswith('site-html/')}
    timestamp = int(subprocess.check_output(['git', 'show', '-s', '--format=%ct', base], cwd=ROOT, text=True))
    out = Path(out) if out is not None else ROOT / 'artefatos'
    out.mkdir(parents=True, exist_ok=True)
    common = dict(manifest_version=VERSAO, base_sha=base, restritos_habilitados=True,
                  matriz_permissoes=MATRIZ, is_admin_por_perfil=FLAGS,
                  schema_requerido='pos-022', executar_migracoes=False,
                  source_manifest_sha256=hashlib.sha256(source_bytes).hexdigest(),
                  frontend_tree_sha256=hash_arvore(frontend))
    outputs = {}

    def pacote(name, entries, kind, uses):
        tree = hash_arvore(entries)
        manifest = common | dict(release_id=kind + '-' + tree[:16], kind=kind, allowed_uses=uses,
                                source_tree_sha256=tree, files=hashes(entries))
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode='wb', filename='', mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode='w', format=tarfile.PAX_FORMAT) as archive:
                for f, data in sorted((entries | {'RELEASE-MANIFEST.json': (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()}).items()):
                    if not caminho_permitido(f):
                        raise ValueError('Arquivo não permitido: ' + f)
                    info = tarfile.TarInfo(f)
                    info.size, info.mode, info.mtime = len(data), modes.get(f, 0o644), timestamp
                    archive.addfile(info, io.BytesIO(data))
        outputs[name] = buf.getvalue()
        return dict(sha256=hashlib.sha256(outputs[name]).hexdigest(), release_id=manifest['release_id'],
                    allowed_uses=uses, arquivos=len(entries))

    index = common | {'pacotes': {}, 'paginas_admin': paginas}
    index['pacotes'][PACOTE_FRONTEND] = pacote(PACOTE_FRONTEND, frontend, TIPO_FRONTEND, ['frontend'])
    index['pacotes'][PACOTE_BACKEND] = pacote(PACOTE_BACKEND, files, TIPO_BACKEND, ['backend', 'recuperacao'])
    outputs[PACOTE_RECUPERACAO] = outputs[PACOTE_BACKEND]
    index['pacotes'][PACOTE_RECUPERACAO] = dict(index['pacotes'][PACOTE_BACKEND])
    outputs[PATCH_FRONTEND] = patch_local(baseline, frontend)
    outputs[PATCH_COMPLETO] = patch_local(baseline, files)
    outputs['verificar_artefato.py'] = files['preparacao/verificar_artefato.py']
    deps = {}
    names = [re.split(r'[\[<>=!~ ]', line.strip())[0] for line in files['backend/requirements.txt'].decode().splitlines()
             if line.strip() and not line.startswith('#')] + ['psycopg-binary']
    for name in names:
        try:
            deps[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            deps[name] = 'não instalado neste ambiente'
    outputs['DEPENDENCIAS-TESTADAS.json'] = (json.dumps(dict(
        python=sys.version.split()[0], plataforma=platform.system() + '/' + platform.machine(),
        versoes_locais=deps, observacao='Registro local; não é lock ou imagem do runtime Render.'),
        indent=2, ensure_ascii=False) + '\n').encode()
    index['patches'] = {f: hashlib.sha256(outputs[f]).hexdigest() for f in (PATCH_FRONTEND, PATCH_COMPLETO)}
    index['verificador_sha256'] = hashlib.sha256(outputs['verificar_artefato.py']).hexdigest()
    outputs['INDICE.json'] = (json.dumps(index, indent=2, ensure_ascii=False) + '\n').encode()
    outputs['SHA256SUMS'] = ''.join(f'{hashlib.sha256(data).hexdigest()}  {f}\n' for f, data in sorted(outputs.items())).encode()
    for f, data in outputs.items():
        (out / f).write_bytes(data)
    for f, meta in index['pacotes'].items():
        for uso in meta['allowed_uses']:
            verificar(out / f, meta['sha256'], uso)
    return index


if __name__ == '__main__':
    print(json.dumps(construir(), indent=2, ensure_ascii=False))
