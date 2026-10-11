"""Configuração pura, sem carregar database.py nem produção."""
import pytest
from app.financeiro_transacional import configuracao_pool


def test_pool_padrao_tem_teto_sem_overflow(monkeypatch):
    for key in ('DB_POOL_SIZE','DB_MAX_OVERFLOW','DB_POOL_TIMEOUT_S'):monkeypatch.delenv(key,raising=False)
    assert configuracao_pool()==dict(pool_size=5,max_overflow=0,pool_timeout=3.,pool_pre_ping=True)


@pytest.mark.parametrize('key,value',[('DB_POOL_SIZE','0'),('DB_POOL_SIZE','-1'),
    ('DB_MAX_OVERFLOW','-1'),('DB_POOL_TIMEOUT_S','0'),('DB_POOL_TIMEOUT_S','31')])
def test_pool_interrompe_configuracao_ilimitada_ou_incompativel(monkeypatch,key,value):
    monkeypatch.setenv(key,value)
    with pytest.raises(ValueError):configuracao_pool()
