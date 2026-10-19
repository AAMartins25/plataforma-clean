"""Ambiente isolado para testes; nunca herda DATABASE_URL de implantação."""
import os
import secrets
from urllib.parse import parse_qs, urlparse

import pytest
import dotenv


_TEST_DATABASE_URL = os.environ.get("RESUMAO_TEST_DATABASE_URL")
_SAFE_TEST_DB_NAME = "resumao_contexto_teste"
_SAFE_TEST_SOCKET = "/tmp/resumao-anotacoes-mensagens-20261018/.pgsocket"


def _valid_local_test_database_url(url):
    if not url:
        return False
    parsed = urlparse(url)
    if parsed.scheme not in {"postgresql", "postgresql+psycopg"}:
        return False
    if parsed.path.lstrip("/") != _SAFE_TEST_DB_NAME:
        return False
    query = parse_qs(parsed.query)
    host = (query.get("host") or [parsed.hostname or ""])[0]
    # TCP loopback também pode ser um túnel; somente o socket local conhecido é aceito.
    return host == _SAFE_TEST_SOCKET


if _TEST_DATABASE_URL and not _valid_local_test_database_url(_TEST_DATABASE_URL):
    raise pytest.UsageError(
        "RESUMAO_TEST_DATABASE_URL deve apontar exclusivamente para "
        "resumao_contexto_teste pelo socket Unix local exclusivo desta worktree."
    )

# Nunca usar nem repassar DATABASE_URL herdado do ambiente/implantação.
os.environ["AMBIENTE_TESTE"] = "1"
for _name in tuple(os.environ):
    if "DATABASE_URL" in _name and _name != "RESUMAO_TEST_DATABASE_URL":
        os.environ.pop(_name, None)
    if _name in {"PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD", "PGSERVICE", "PGSERVICEFILE"}:
        os.environ.pop(_name, None)
os.environ["DATABASE_URL"] = (
    _TEST_DATABASE_URL
    if _TEST_DATABASE_URL
    else "postgresql+psycopg://postgres@/resumao_contexto_teste?host=" + _SAFE_TEST_SOCKET
)
# app.main carrega backend/.env com override=True; nos testes esse carregamento
# é desativado para que nenhum valor local/de implantação substitua o DSN seguro.
dotenv.load_dotenv = lambda *args, **kwargs: False


def postgres_descartavel_url():
    """Retorna o DSN local autorizado ou None para testes que exigem PostgreSQL."""
    return _TEST_DATABASE_URL


def postgres_test_fixture_disponivel(require_contract=True):
    """Confirma apenas a massa-base local exigida pelos testes legados de contexto."""
    if not _TEST_DATABASE_URL:
        return False
    from sqlalchemy import create_engine, text

    engine = create_engine(_TEST_DATABASE_URL, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            tables = conn.execute(text("""
                SELECT
                    to_regclass('public.usuarios') IS NOT NULL
                    AND to_regclass('public.cursos') IS NOT NULL
                    AND to_regclass('public.contratacoes_curso') IS NOT NULL
            """)).scalar_one()
            if not tables:
                return False
            base = conn.execute(text("""
                SELECT EXISTS (SELECT 1 FROM usuarios WHERE id = 2)
                    AND EXISTS (SELECT 1 FROM cursos WHERE id = 1)
            """)).scalar_one()
            if not base:
                return False
            if require_contract:
                return conn.execute(text("""
                    SELECT EXISTS (
                        SELECT 1 FROM contratacoes_curso
                        WHERE usuario_id = 2 AND curso_id = 1
                    )
                """)).scalar_one()
            return True
    finally:
        engine.dispose()


def pytest_configure(config):
    config._jwt_test_environment = pytest.MonkeyPatch()
    config._jwt_test_environment.setenv("SECRET_KEY", secrets.token_hex(32))


def pytest_unconfigure(config):
    environment = getattr(config, "_jwt_test_environment", None)
    if environment is not None:
        environment.undo()
