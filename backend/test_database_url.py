"""Regressões da conexão: valores fictícios, engine simulado, nenhuma conexão."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import quote

import pytest
import sqlalchemy
import sqlalchemy.orm
from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg


@pytest.fixture
def carregar_database(monkeypatch):
    engine = Mock()
    criar = Mock(return_value=engine)
    sessoes = Mock()
    monkeypatch.setattr(sqlalchemy, 'create_engine', criar)
    monkeypatch.setattr(sqlalchemy.orm, 'sessionmaker', sessoes)
    monkeypatch.setenv('AMBIENTE_TESTE', '1')
    for key in ('DB_POOL_SIZE', 'DB_MAX_OVERFLOW', 'DB_POOL_TIMEOUT_S'):
        monkeypatch.delenv(key, raising=False)

    def carregar(url):
        monkeypatch.setenv('DATABASE_URL', url)
        spec = importlib.util.spec_from_file_location(
            '_database_url_teste', Path(__file__).parent / 'app/database.py')
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        args, kwargs = PGDialect_psycopg().create_connect_args(modulo.DATABASE_URL)
        assert args == []
        assert criar.call_args.args == (modulo.DATABASE_URL,)
        assert sessoes.call_args.kwargs == {
            'autocommit': False, 'autoflush': False, 'bind': engine}
        engine.connect.assert_not_called()
        return modulo, kwargs, criar

    return carregar


@pytest.mark.parametrize('senha', [
    'ficticia@com:mais+percent%igual=!',
    'ficticia com espaco',
    'ficticia/#?&@:+%',
    'ficticia%40literal%2F',
    'ficticia-acentuação',
    '',
])
@pytest.mark.parametrize('prefixo', ['postgres', 'postgresql', 'postgresql+psycopg'])
def test_senha_codificada_decodificada_uma_vez(carregar_database, senha, prefixo):
    modulo, params, _ = carregar_database(
        f'{prefixo}://postgres.projeto_ficticio:{quote(senha, safe="")}@'
        'pooler.example.invalid:5432/postgres')
    assert modulo.DATABASE_URL.password == senha
    # O dialeto omite senha vazia dos argumentos, como já faz para qualquer URL.
    assert params.get('password', '') == senha
    assert params['user'] == 'postgres.projeto_ficticio'


@pytest.mark.parametrize('senha', [
    'ficticia@com:mais+percent%igual=!',
    'ficticia+com+mais',
    'ficticia%sem-escape',
])
def test_sinais_literais_na_senha(carregar_database, senha):
    _, params, _ = carregar_database(
        f'postgresql://usuario_ficticio:{senha}@pooler.example.invalid:5432/postgres')
    assert params['password'] == senha


@pytest.mark.parametrize('query', [
    'sslmode=verify-full&sslrootcert=%2Ftmp%2Fca%20ficticia.crt',
    'pgbouncer=true&sslmode=verify-full&sslrootcert=%2Ftmp%2Fca%20ficticia.crt',
    'sslmode=verify-full&pgbouncer=true&sslrootcert=%2Ftmp%2Fca%20ficticia.crt',
    'sslmode=verify-full&sslrootcert=%2Ftmp%2Fca%20ficticia.crt&pgbouncer=true',
    'pgbouncer=false&sslmode=verify-full&sslrootcert=%2Ftmp%2Fca%20ficticia.crt',
])
@pytest.mark.parametrize('porta', [5432, 6543])
def test_query_ssl_e_endpoint_preservados(carregar_database, query, porta):
    _, params, criar = carregar_database(
        f'postgresql://postgres.projeto_ficticio:senha%40ficticia@'
        f'pooler.example.invalid:{porta}/postgres?{query}')
    assert params == {
        'user': 'postgres.projeto_ficticio', 'password': 'senha@ficticia',
        'host': 'pooler.example.invalid', 'port': porta, 'dbname': 'postgres',
        'sslmode': 'verify-full', 'sslrootcert': '/tmp/ca ficticia.crt'}
    assert criar.call_args.kwargs == {
        'pool_size': 5, 'max_overflow': 0, 'pool_timeout': 3., 'pool_pre_ping': True,
        'connect_args': {'prepare_threshold': None, 'connect_timeout': 5}}


@pytest.mark.parametrize('query', ['', '?pgbouncer=true'])
def test_sem_parametros_ssl_nao_inventa_opcoes(carregar_database, query):
    modulo, params, _ = carregar_database(
        'postgres://usuario_ficticio:senha_ficticia@pooler.example.invalid/postgres' + query)
    assert not modulo.DATABASE_URL.query
    assert params == {'user': 'usuario_ficticio', 'password': 'senha_ficticia',
                      'host': 'pooler.example.invalid', 'dbname': 'postgres'}


def test_componentes_codificados_ipv6_e_opcoes_repetidas(carregar_database):
    modulo, params, _ = carregar_database(
        'postgresql://usuario%2Bficticio:senha%2540literal@[::1]:5432/banco%20ficticio'
        '?pgbouncer=true&pgbouncer=true&application_name=nome%2Bficticio'
        '&host=primario.invalid&host=secundario.invalid&sslmode=verify-full')
    assert modulo.DATABASE_URL.username == 'usuario+ficticio'
    assert modulo.DATABASE_URL.password == 'senha%40literal'
    assert modulo.DATABASE_URL.host == '::1'
    assert modulo.DATABASE_URL.port == 5432
    assert params['dbname'] == 'banco ficticio'
    assert params['application_name'] == 'nome+ficticio'
    assert modulo.DATABASE_URL.query['host'] == ('primario.invalid', 'secundario.invalid')
    assert 'pgbouncer' not in params


def test_pool_personalizado_preservado(carregar_database, monkeypatch):
    modulo, _, _ = carregar_database(
        'postgresql://usuario_ficticio:senha_ficticia@pooler.example.invalid/postgres')
    monkeypatch.setenv('DB_POOL_SIZE', '2')
    monkeypatch.setenv('DB_MAX_OVERFLOW', '1')
    monkeypatch.setenv('DB_POOL_TIMEOUT_S', '7')
    _, _, criar = carregar_database(modulo.DATABASE_URL.render_as_string(hide_password=False))
    assert criar.call_args.kwargs == {
        'pool_size': 2, 'max_overflow': 1, 'pool_timeout': 7., 'pool_pre_ping': True,
        'connect_args': {'prepare_threshold': None, 'connect_timeout': 5}}


def test_sem_senha_e_parametros_vazios(carregar_database):
    modulo, params, _ = carregar_database(
        'postgresql://usuario_ficticio@pooler.example.invalid:5432/postgres'
        '?pgbouncer=true&sslmode=verify-full&application_name=')
    assert modulo.DATABASE_URL.password is None
    assert 'password' not in params
    assert params['sslmode'] == 'verify-full'
    assert params['application_name'] == ''
