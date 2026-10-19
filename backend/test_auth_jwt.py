"""Configuração e rotação JWT em processos novos, sem banco ou rede reais."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

from jose import jwt
import pytest

BACKEND = Path(__file__).resolve().parent
KEY_A = 'chave-ficticia-exclusiva-testes-jwt-ambiente-A-2026'
KEY_B = 'chave-ficticia-exclusiva-testes-jwt-ambiente-B-2026'


def isolated(code, key=KEY_A, extra=None, args=()):
    environment = dict(os.environ)
    for name in ('SECRET_KEY', 'MP_ACCESS_TOKEN', 'RESEND_API_KEY'):
        environment.pop(name, None)
    environment.update(PYTHONPATH=str(BACKEND), PYTHONDONTWRITEBYTECODE='1',
                       AMBIENTE_TESTE='1')
    if key is not None:
        environment['SECRET_KEY'] = key
    environment.update(extra or {})
    return subprocess.run([sys.executable, '-c', code, *map(str, args)],
                          cwd=BACKEND, env=environment, capture_output=True,
                          text=True, timeout=30)


@pytest.mark.parametrize('key', [None, '', ' ', 'x' * 31, 'espaco no meio ' * 4,
                                  'x' * 32 + '\n', 'á' * 64],
                         ids=['ausente', 'vazia', 'espacos', 'curta', 'espaco-interno',
                              'quebra-linha', 'nao-ascii'])
def test_configuracao_invalida_impede_importacao_sem_expor_valor(key):
    result = isolated('from app import auth', key)
    assert result.returncode != 0
    assert 'RuntimeError: SECRET_KEY ausente ou inadequada.' in result.stderr
    assert not result.stdout
    if key and len(key) > 10:
        assert key not in result.stderr


@pytest.mark.parametrize('key', [KEY_A, secrets.token_hex(32), 'aB9_' * 8])
def test_chave_do_ambiente_e_usada_sem_transformacao(key):
    result = isolated('''import os
from app import auth
assert auth.SECRET_KEY == os.environ['SECRET_KEY']
assert auth.ALGORITHM == 'HS256'
assert auth.ACCESS_TOKEN_EXPIRE_MINUTES == 1440
print('OK')''', key)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'OK'


def test_emissao_validacao_expiracao_e_rejeicoes():
    result = isolated('''from datetime import datetime, timedelta, timezone
from jose import jwt
from app import auth
now = datetime.now(timezone.utc)
token = auth.criar_token({'sub': '901'})
data = jwt.decode(token, auth.SECRET_KEY, algorithms=['HS256'])
assert auth.decodificar_token(token)['sub'] == '901'
assert 86395 <= data['exp'] - int(now.timestamp()) <= 86405
short = auth.criar_token({'sub': '901'}, expires_minutes=5)
assert 295 <= auth.decodificar_token(short)['exp'] - int(now.timestamp()) <= 305
expired = jwt.encode({'sub': '901', 'exp': now - timedelta(seconds=10)}, auth.SECRET_KEY, algorithm='HS256')
assert auth.decodificar_token(expired) == {}
other = jwt.encode({'sub': '901', 'exp': now + timedelta(hours=1)}, 'outra-chave-ficticia-nao-aceita-2026', algorithm='HS256')
assert auth.decodificar_token(other) == {}
wrong_algorithm = jwt.encode({'sub': '901', 'exp': now + timedelta(hours=1)}, auth.SECRET_KEY, algorithm='HS512')
assert auth.decodificar_token(wrong_algorithm) == {}
parts = token.split('.')
parts[1] = parts[1][:-2] + ('AA' if parts[1][-2:] != 'AA' else 'BB')
assert auth.decodificar_token('.'.join(parts)) == {}
import base64, json
encode = lambda obj: base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b'=').decode()
unsigned = encode({'alg': 'none', 'typ': 'JWT'}) + '.' + encode({'sub': '901', 'exp': int(now.timestamp())+3600}) + '.'
assert auth.decodificar_token(unsigned) == {}
for invalid in ['', 'invalido', 'a.b.c']:
    assert auth.decodificar_token(invalid) == {}
print('OK')''')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'OK'


def test_rotacao_rejeita_tokens_anteriores_e_preserva_novos_entre_processos():
    # Tokens/segredos exclusivamente sintéticos; nunca impressos em caso de sucesso.
    old_token = jwt.encode({'sub': '901', 'exp': datetime.now(timezone.utc) + timedelta(hours=1)},
                           KEY_A, algorithm='HS256')
    first = isolated('''import json, os
from app import auth
assert auth.decodificar_token(os.environ['OLD_TOKEN']) == {}
print(json.dumps({'token': auth.criar_token({'sub': '901'})}))''',
                     KEY_B, extra={'OLD_TOKEN': old_token})
    assert first.returncode == 0
    new_token = json.loads(first.stdout)['token']
    second = isolated('''import os
from app import auth
assert auth.decodificar_token(os.environ['TOKEN'])['sub'] == '901'
print('OK')''', KEY_B, extra={'TOKEN': new_token})
    assert second.returncode == 0
    assert second.stdout.strip() == 'OK'


MAIN_IMPORT = '''import importlib.util, json, os, sys, types
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.pausa_financeira import metadata, controle, agora
engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
metadata.create_all(engine)
with engine.begin() as c:
    c.execute(controle.insert().values(id=1, modo='NORMAL', geracao=0, alterado_em=agora(), motivo='Teste JWT isolado'))
stub = types.ModuleType('app.database')
stub.engine = engine
stub.SessionLocal = sessionmaker(bind=engine)
sys.modules['app.database'] = stub
spec = importlib.util.spec_from_file_location('app._jwt_configuration_test_main', sys.argv[1])
main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main)
from app import auth
assert auth.SECRET_KEY == os.environ['EXPECTED_TEST_KEY']
assert os.environ['SECRET_KEY'] == os.environ['EXPECTED_TEST_KEY']
# Mantém a precedência antiga das outras variáveis, sem utilizar provedor real.
assert main.MP_ACCESS_TOKEN == 'token-financeiro-ficticio-do-arquivo'
print('OK')
'''


@pytest.mark.parametrize('environment_key,file_key,expected', [
    (KEY_A, KEY_B, KEY_A), (None, KEY_B, KEY_B), (KEY_A, '', KEY_A),
], ids=['ambiente-prevalece', 'dotenv-local-quando-ausente', 'dotenv-vazio-nao-apaga-ambiente'])
def test_main_preserva_chave_do_ambiente_e_demais_configuracoes(tmp_path, environment_key, file_key, expected):
    app_path = tmp_path / 'app'
    app_path.mkdir()
    # Copia o módulo inteiro para usar ENV_PATH temporário, sem editar a aplicação.
    main_path = app_path / 'main.py'
    main_path.write_bytes((BACKEND / 'app/main.py').read_bytes())
    (tmp_path / '.env').write_text(f'SECRET_KEY={file_key}\nMP_ACCESS_TOKEN=token-financeiro-ficticio-do-arquivo\n')
    result = isolated(MAIN_IMPORT, environment_key,
                      extra={'EXPECTED_TEST_KEY': expected, 'MP_ACCESS_TOKEN': 'token-ficticio-do-ambiente'},
                      args=[main_path])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'OK'


def test_main_nao_encobre_chave_invalida_do_ambiente_com_dotenv(tmp_path):
    app_path = tmp_path / 'app'
    app_path.mkdir()
    main_path = app_path / 'main.py'
    main_path.write_bytes((BACKEND / 'app/main.py').read_bytes())
    (tmp_path / '.env').write_text(f'SECRET_KEY={KEY_B}\n')
    result = isolated(MAIN_IMPORT, '', extra={'EXPECTED_TEST_KEY': KEY_B}, args=[main_path])
    assert result.returncode != 0
    assert 'RuntimeError: SECRET_KEY ausente ou inadequada.' in result.stderr
    assert KEY_B not in result.stderr


def test_http_login_rotacao_permissoes_e_acesso_pago():
    """Backend real; usuários/contratação fictícios e SQLite apenas em memória."""
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app import models as m
    from app.pausa_financeira import metadata, controle, agora
    from test_questoes_pratica_patch import carregar_main_isolado

    engine = create_engine('sqlite://', connect_args={'check_same_thread': False},
                           poolclass=StaticPool)
    factory = sessionmaker(bind=engine)
    tables = [model.__table__ for model in (m.Usuario, m.Vendedor, m.Curso,
              m.AcessoCurso, m.ContratacaoCurso, m.DemonstracaoCurso,
              m.CursoDisciplinaPropria)]
    # Autorização por compra consulta contestações e períodos, além do cache.
    tables = set(tables) | {model.__table__ for model in (
        m.Pagamento, m.ContestacaoPagamento, m.PeriodoAcessoPagamento,
        m.ConcessaoAcessoAdmin)}
    while True:
        dependencias = {fk.column.table for table in tables for fk in table.foreign_keys}
        if dependencias <= tables:
            break
        tables |= dependencias
    from sqlalchemy import event
    @event.listens_for(engine, 'connect')
    def sqlite_funcoes(connection, _):
        connection.create_function('BTRIM', 1, lambda value: value.strip() if value else value)
    m.Base.metadata.create_all(engine, tables=list(tables))
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(controle.insert().values(id=1, modo='NORMAL', geracao=0,
                           alterado_em=agora(), motivo='Teste HTTP JWT isolado'))
    try:
        with carregar_main_isolado(factory, engine) as main:
            password = 'Senha-ficticia-somente-para-teste-JWT'
            password_hash = main.hash_senha(password)
            with factory() as db:
                db.add_all([
                    m.Usuario(id=1, nome='Aluno JWT', email='aluno-jwt@example.com',
                              cpf='1', telefone='0', senha_hash=password_hash, is_admin=False),
                    m.Usuario(id=2, nome='Admin JWT', email='admin-jwt@example.com',
                              cpf='2', telefone='0', senha_hash=password_hash, is_admin=True),
                    m.Usuario(id=3, nome='Outro aluno JWT', email='outro-jwt@example.com',
                              cpf='3', telefone='0', senha_hash=password_hash, is_admin=False),
                    m.Curso(id=1, nome='Curso JWT', ativo=True),
                ])
                db.flush()
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                db.add_all([
                    m.ContratacaoCurso(id=1, usuario_id=1, curso_id=1, origem='PAGAMENTO',
                                       data_inicio=now-timedelta(days=1), data_fim=now+timedelta(days=120)),
                    m.AcessoCurso(usuario_id=1, curso_id=1, ativo=True,
                                  data_inicio=now-timedelta(days=1), data_fim=now+timedelta(days=120)),
                    m.CursoDisciplinaPropria(id=1, curso_id=1, nome='Disciplina JWT', ativo=True),
                ])
                db.commit()

            def get_db():
                with factory() as db:
                    yield db

            main.app.dependency_overrides[main.get_db] = get_db
            with TestClient(main.app) as client:
                assert client.get('/me').status_code == 401
                response = client.post('/login', data={'username': 'aluno-jwt@example.com', 'password': password})
                assert response.status_code == 200
                assert set(response.json()) == {'access_token', 'token_type'}
                student = {'Authorization': 'Bearer ' + response.json()['access_token']}
                assert client.get('/me', headers=student).json()['id'] == 1
                assert client.get('/admin/cursos', headers=student).status_code == 403
                assert client.get('/cursos/1/disciplinas-proprias?contratacao_id=1', headers=student).status_code == 200
                assert client.get('/me/cursos', headers=student).json()[0]['contratacoes'][0]['origem'] == 'PAGAMENTO'
                old = jwt.encode({'sub': '1', 'exp': datetime.now(timezone.utc)+timedelta(hours=1)},
                                 KEY_B, algorithm='HS256')
                assert client.get('/me', headers={'Authorization': 'Bearer '+old}).status_code == 401
                assert client.post('/login', data={'username': 'aluno-jwt@example.com', 'password': 'senha-errada'}).status_code == 401
                # Uma tentativa rejeitada não invalida o JWT correto já emitido.
                assert client.get('/me', headers=student).status_code == 200
                response = client.post('/login', data={'username': 'admin-jwt@example.com', 'password': password})
                assert response.status_code == 200
                admin = {'Authorization': 'Bearer '+response.json()['access_token']}
                assert client.get('/admin/cursos', headers=admin).status_code == 200
                # Preserva a consulta administrativa existente, sem transferir a contratação.
                assert client.get('/cursos/1/disciplinas-proprias?contratacao_id=1', headers=admin).status_code == 200
                another = {'Authorization': 'Bearer '+main.criar_token({'sub': '3'})}
                assert client.get('/cursos/1/disciplinas-proprias?contratacao_id=1', headers=another).status_code == 403
            main.app.dependency_overrides.clear()
    finally:
        engine.dispose()


def test_main_sem_chave_no_ambiente_ou_arquivo_nao_inicializa(tmp_path):
    app_path = tmp_path / 'app'
    app_path.mkdir()
    main_path = app_path / 'main.py'
    main_path.write_bytes((BACKEND / 'app/main.py').read_bytes())
    result = isolated(MAIN_IMPORT, None, args=[main_path])
    assert result.returncode != 0
    assert 'RuntimeError: SECRET_KEY ausente ou inadequada.' in result.stderr
