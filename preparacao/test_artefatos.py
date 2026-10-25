"""Testes offline do empacotamento definitivo; sem aplicação, banco, rede ou migrações."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import pytest
import construir_artefatos as builder
from construir_artefatos import (construir, ROOT, PACOTE_FRONTEND, PACOTE_BACKEND,
                                 PACOTE_RECUPERACAO, PATCH_FRONTEND, PATCH_COMPLETO)
from verificar_artefato import (verificar, caminho_permitido, TIPO_BACKEND, TIPO_FRONTEND,
                                MATRIZ, FLAGS, hashes, hash_arvore)


def pacote(nome):
    index = json.loads((ROOT/'artefatos/INDICE.json').read_text())
    return ROOT/'artefatos'/nome, index['pacotes'][nome]


def membros(path):
    with tarfile.open(path) as t:
        return {m.name: t.extractfile(m).read() for m in t.getmembers()}


def reempacotar(tmp_path, files):
    out = tmp_path/'adulterado.tar.gz'
    with tarfile.open(out, 'w:gz') as t:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return out, hashlib.sha256(out.read_bytes()).hexdigest()


def test_frontend_so_pode_ser_usado_como_frontend():
    path, meta = pacote(PACOTE_FRONTEND)
    assert verificar(path, meta['sha256'], 'frontend')['kind'] == TIPO_FRONTEND
    for uso in ('backend', 'recuperacao'):
        with pytest.raises(ValueError, match='não é autorizado'):
            verificar(path, meta['sha256'], uso)
    assert all(f.startswith('site-html/') or f == 'RELEASE-MANIFEST.json' for f in membros(path))


def test_backend_e_recuperacao_identicos_com_matriz_definitiva():
    path, meta = pacote(PACOTE_BACKEND)
    rec, recmeta = pacote(PACOTE_RECUPERACAO)
    assert path.read_bytes() == rec.read_bytes()
    assert meta == recmeta
    assert verificar(path, meta['sha256'], 'backend')['kind'] == TIPO_BACKEND
    assert verificar(rec, recmeta['sha256'], 'recuperacao')['kind'] == TIPO_BACKEND
    with pytest.raises(ValueError, match='não é autorizado'):
        verificar(path, meta['sha256'], 'frontend')
    data = membros(path)
    manifest = json.loads(data.pop('RELEASE-MANIFEST.json'))
    assert manifest['restritos_habilitados'] is True
    assert manifest['matriz_permissoes'] == MATRIZ
    assert manifest['is_admin_por_perfil'] == FLAGS
    assert manifest['executar_migracoes'] is False
    assert manifest['schema_requerido'] == 'pos-022'
    assert {'backend/app/perfis_admin.py', 'backend/app/vendedores_admin.py',
            'site-html/js/admin-acesso.js'} <= data.keys()
    source = json.loads(data['evidencias/manifesto.json'])
    assert source['arquivos'] == hashes({f: b for f, b in data.items() if f != 'evidencias/manifesto.json'})
    for f, expected in source['arquivos'].items():
        assert hashlib.sha256((ROOT/f).read_bytes()).hexdigest() == expected, f


def test_frontend_identico_nos_tres_pacotes_e_dependencias_presentes():
    front, _ = pacote(PACOTE_FRONTEND)
    data = membros(front)
    frontend = {f: b for f, b in data.items() if f != 'RELEASE-MANIFEST.json'}
    for name in (PACOTE_BACKEND, PACOTE_RECUPERACAO):
        path, _ = pacote(name)
        assert {f: b for f, b in membros(path).items() if f.startswith('site-html/')} == frontend
    pages = builder.validar_frontend(frontend)
    assert len(pages) == 19
    assert all(b'admin-acesso.js?v=perfis-1' in frontend[p] for p in pages)
    # Só se verificam as referências de cache, sem modificar os scripts funcionais.
    assert frontend['site-html/js/admin.js'] == (ROOT/'site-html/js/admin.js').read_bytes()


def test_confirmacao_diagnostico_reutilizada_sem_consultas():
    path, _ = pacote(PACOTE_BACKEND)
    evidence = json.loads(membros(path)['evidencias/diagnostico-pos022-confirmado.json'])
    assert evidence['consultas_executadas'] == 7
    assert evidence['administradores_gerais'] == 5
    assert evidence['estrutura_pos_022_confirmada'] is True
    assert evidence['nova_consulta_executada_nesta_preparacao'] is False
    assert 'usuário' in evidence['origem']


def test_pacotes_e_patches_reproduziveis(tmp_path):
    old = json.loads((ROOT/'artefatos/INDICE.json').read_text())
    assert construir(tmp_path) == old
    for name in [*old['pacotes'], PATCH_COMPLETO, PATCH_FRONTEND, 'verificar_artefato.py',
                 'DEPENDENCIAS-TESTADAS.json', 'INDICE.json', 'SHA256SUMS']:
        assert (tmp_path/name).read_bytes() == (ROOT/'artefatos'/name).read_bytes(), name


def test_sha256sums_cobre_exatamente_saidas_atuais():
    output = ROOT/'artefatos'
    listed = {line.split('  ', 1)[1] for line in (output/'SHA256SUMS').read_text().splitlines()}
    assert listed == {p.name for p in output.iterdir() if p.is_file()} - {'SHA256SUMS'}
    r = subprocess.run(['sha256sum', '--check', 'SHA256SUMS'], cwd=output, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout+r.stderr


def test_verificador_distribuido_funciona_isoladamente():
    path, meta = pacote(PACOTE_BACKEND)
    r = subprocess.run([sys.executable, str(ROOT/'artefatos/verificar_artefato.py'), str(path),
                        '--sha256', meta['sha256'], '--uso', 'backend'],
                       cwd='/tmp', capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)['restritos_habilitados'] is True


def test_digest_externo_incorreto_recusado():
    path, _ = pacote(PACOTE_BACKEND)
    with pytest.raises(ValueError, match='externo divergente'):
        verificar(path, '0'*64, 'backend')


def test_conteudo_adulterado_recusado(tmp_path):
    path, _ = pacote(PACOTE_BACKEND)
    data = membros(path)
    data['backend/app/main.py'] += b'\n# adulterado\n'
    out, digest = reempacotar(tmp_path, data)
    with pytest.raises(ValueError, match='Conteúdo divergente'):
        verificar(out, digest, 'backend')


@pytest.mark.parametrize('campo,valor', [('restritos_habilitados', False),
    ('kind', 'intermediario-seguro'), ('matriz_permissoes', {'admin_prod': ['*']}),
    ('is_admin_por_perfil', {'admin_geral': True, 'admin_prod': True, 'admin_adm': False}),
    ('executar_migracoes', True), ('source_tree_sha256', '0'*64)])
def test_manifesto_incompativel_recusado(tmp_path, campo, valor):
    path, _ = pacote(PACOTE_BACKEND)
    data = membros(path)
    manifest = json.loads(data['RELEASE-MANIFEST.json'])
    manifest[campo] = valor
    data['RELEASE-MANIFEST.json'] = json.dumps(manifest).encode()
    out, digest = reempacotar(tmp_path, data)
    with pytest.raises(ValueError):
        verificar(out, digest, 'backend')


def test_modulo_obrigatorio_omitido_recusado_mesmo_com_hashes_recalculados(tmp_path):
    path, _ = pacote(PACOTE_BACKEND)
    data = membros(path)
    manifest = json.loads(data.pop('RELEASE-MANIFEST.json'))
    data.pop('backend/app/perfis_admin.py')
    manifest['files'] = hashes(data)
    manifest['source_tree_sha256'] = hash_arvore(data)
    manifest['release_id'] = manifest['kind']+'-'+hash_arvore(data)[:16]
    data['RELEASE-MANIFEST.json'] = json.dumps(manifest).encode()
    out, digest = reempacotar(tmp_path, data)
    with pytest.raises(ValueError, match='Backend definitivo incompleto'):
        verificar(out, digest, 'backend')


@pytest.mark.parametrize('nome', ['../segredo', '/tmp/segredo', '.env', 'backend/.env.local',
                                  '.git/config', 'backend/__pycache__/app.pyc', 'artefatos/pacote',
                                  'backend/../segredo', 'backend\\segredo', 'backend/chave.pem'])
def test_caminhos_inseguros_recusados(nome):
    assert not caminho_permitido(nome)


def test_archive_com_caminho_inseguro_recusado(tmp_path):
    out, digest = reempacotar(tmp_path, {'../segredo': b'proibido'})
    with pytest.raises(ValueError, match='Entrada de arquivo'):
        verificar(out, digest, 'backend')


def test_construtor_recusa_fonte_divergente_sem_escrever_saida(monkeypatch, tmp_path):
    original = Path.read_bytes
    alvo = ROOT/'backend/app/main.py'
    def adulterar(path):
        data = original(path)
        return data+b'\n# divergente\n' if path == alvo else data
    monkeypatch.setattr(Path, 'read_bytes', adulterar)
    with pytest.raises(ValueError, match='manifesto aprovado mudou'):
        construir(tmp_path/'saida')
    assert not (tmp_path/'saida').exists()


def test_referencia_frontend_ausente_recusada():
    path, _ = pacote(PACOTE_FRONTEND)
    data = membros(path)
    data.pop('site-html/js/admin-acesso.js')
    with pytest.raises(ValueError, match='incompleto'):
        builder.validar_frontend(data)


def test_patches_validos_para_base_e_worktree_sem_aplicar(tmp_path):
    index = json.loads((ROOT/'artefatos/INDICE.json').read_text())
    raw = subprocess.check_output(['git', 'archive', index['base_sha']], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as t:
        t.extractall(tmp_path, filter='data')
    for name in (PATCH_FRONTEND, PATCH_COMPLETO):
        patch = str(ROOT/'artefatos'/name)
        forward = subprocess.run(['git', 'apply', '--check', patch], cwd=tmp_path, capture_output=True, text=True)
        reverse = subprocess.run(['git', 'apply', '--reverse', '--check', patch], cwd=ROOT, capture_output=True, text=True)
        assert forward.returncode == 0, forward.stderr
        assert reverse.returncode == 0, reverse.stderr
