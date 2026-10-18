"""JWT dos testes nunca utiliza a chave configurada para uma implantação."""
import secrets

import pytest


def pytest_configure(config):
    config._jwt_test_environment = pytest.MonkeyPatch()
    config._jwt_test_environment.setenv("SECRET_KEY", secrets.token_hex(32))


def pytest_unconfigure(config):
    environment = getattr(config, "_jwt_test_environment", None)
    if environment is not None:
        environment.undo()
