"""Verificação offline da versão definitiva; não extrai, importa a aplicação ou acessa banco."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import tarfile

VERSAO = 2
TIPO_BACKEND = 'backend-perfis-definitivos'
TIPO_FRONTEND = 'frontend-perfis-definitivos'
MATRIZ = {
    'admin_geral': ['*'],
    'admin_prod': ['cursos.criar', 'cursos.questoes'],
    'admin_adm': ['alunos.pagamentos', 'alunos.atendimento', 'alunos.mensagens_questoes'],
}
FLAGS = {'admin_geral': True, 'admin_prod': False, 'admin_adm': False}
BACKEND_OBRIGATORIO = frozenset({
    'backend/app/main.py', 'backend/app/admin_intermediario.py',
    'backend/app/perfis_admin.py', 'backend/app/vendedores_admin.py',
    'backend/app/models.py', 'backend/app/schemas.py', 'backend/requirements.txt',
    'backend/migrations/022_tipos_administrador.sql', 'evidencias/manifesto.json',
    'evidencias/diagnostico-pos022-confirmado.json',
})
FRONTEND_OBRIGATORIO = frozenset({
    'site-html/js/admin-acesso.js', 'site-html/js/admin.js', 'site-html/js/app.js',
    'site-html/js/login.js', 'site-html/js/perfis.js', 'site-html/js/sessao.js',
    'site-html/admin/index.html', 'site-html/admin/perfis.html',
    'site-html/admin/alunos.html', 'site-html/admin/pagamentos.html',
    'site-html/admin/atendimento.html', 'site-html/admin/admin-mensagens-questoes.html',
    'site-html/admin/criar-curso-completo.html', 'site-html/admin/admin-questoes-aluno.html',
    'site-html/admin/admin-questoes-pratica.html', 'site-html/login.html',
    'site-html/minha-area.html',
})


def caminho_permitido(nome):
    p = PurePosixPath(nome)
    return (bool(nome) and not p.is_absolute() and '..' not in p.parts
            and str(p) == nome and '\\' not in nome
            and not set(p.parts) & {'.git', '.aws', '.codex', '.agents', '__pycache__', 'artefatos'}
            and not p.name.startswith('.env')
            and p.suffix.lower() not in {'.pyc', '.pem', '.key', '.db', '.sqlite', '.log'})


def hashes(files):
    return {f: hashlib.sha256(b).hexdigest() for f, b in sorted(files.items())}


def hash_arvore(files):
    return hashlib.sha256(json.dumps(hashes(files), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def verificar(path, sha256, uso):
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != sha256:
        raise ValueError('SHA-256 externo divergente')
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        files = {}
        for member in archive.getmembers():
            if not member.isfile() or not caminho_permitido(member.name) or member.name in files:
                raise ValueError('Entrada de arquivo inválida, sigilosa ou duplicada')
            files[member.name] = archive.extractfile(member).read()
    try:
        manifest = json.loads(files.pop('RELEASE-MANIFEST.json'))
        kind = manifest['kind']
        if manifest['manifest_version'] != VERSAO or kind not in {TIPO_BACKEND, TIPO_FRONTEND}:
            raise ValueError('Pacote não representa a versão definitiva')
        expected_uses = ['backend', 'recuperacao'] if kind == TIPO_BACKEND else ['frontend']
        if manifest['allowed_uses'] != expected_uses or uso not in expected_uses:
            raise ValueError('Este pacote não é autorizado para ' + uso)
        if (manifest['restritos_habilitados'] is not True or manifest['matriz_permissoes'] != MATRIZ
                or manifest['is_admin_por_perfil'] != FLAGS
                or manifest['schema_requerido'] != 'pos-022' or manifest['executar_migracoes'] is not False):
            raise ValueError('Contrato de permissões/schema divergente')
        if not re.fullmatch(r'[0-9a-f]{40}', manifest['base_sha']):
            raise ValueError('Base de fontes inválida')
        actual = hashes(files)
        if actual != manifest['files']:
            raise ValueError('Conteúdo divergente do manifesto')
        tree = hash_arvore(files)
        if tree != manifest['source_tree_sha256'] or manifest['release_id'] != kind + '-' + tree[:16]:
            raise ValueError('Identidade ou árvore do release divergente')
        if not FRONTEND_OBRIGATORIO <= files.keys():
            raise ValueError('Frontend definitivo incompleto')
        frontend = {f: b for f, b in files.items() if f.startswith('site-html/')}
        if hash_arvore(frontend) != manifest['frontend_tree_sha256']:
            raise ValueError('Árvore frontend divergente')
        if kind == TIPO_FRONTEND:
            if set(files) != set(frontend):
                raise ValueError('Pacote frontend contém arquivos fora do frontend')
        else:
            if not BACKEND_OBRIGATORIO <= files.keys():
                raise ValueError('Backend definitivo incompleto')
            source_bytes = files['evidencias/manifesto.json']
            if hashlib.sha256(source_bytes).hexdigest() != manifest['source_manifest_sha256']:
                raise ValueError('Manifesto de fontes divergente')
            source = json.loads(source_bytes)
            if (source['manifest_version'] != VERSAO or source['base_sha'] != manifest['base_sha']
                    or source['restritos_habilitados'] is not True):
                raise ValueError('Manifesto de fontes incompatível')
            if source['arquivos'] != hashes({f: b for f, b in files.items() if f != 'evidencias/manifesto.json'}):
                raise ValueError('Inventário de fontes divergente')
            evidence = json.loads(files['evidencias/diagnostico-pos022-confirmado.json'])
            if (evidence['estrutura_pos_022_confirmada'] is not True
                    or evidence['consultas_executadas'] != 7 or evidence['administradores_gerais'] != 5):
                raise ValueError('Confirmação pós-022 ausente ou incompatível')
    except (KeyError, TypeError, json.JSONDecodeError) as e:
        raise ValueError('Manifesto ausente, incompleto ou inválido') from e
    return {k: manifest[k] for k in ('release_id', 'kind', 'base_sha', 'allowed_uses',
                                    'restritos_habilitados', 'schema_requerido')} | {'arquivos_verificados': len(files)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('arquivo')
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--uso', required=True, choices=['frontend', 'backend', 'recuperacao'])
    a = parser.parse_args()
    try:
        resultado = verificar(a.arquivo, a.sha256, a.uso)
    except (ValueError, OSError, tarfile.TarError) as e:
        parser.exit(2, str(e) + '\n')
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
