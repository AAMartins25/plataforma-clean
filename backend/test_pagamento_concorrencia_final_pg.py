"""Reutiliza disputas financeiras em banco descartável por socket exclusivo."""
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from test_compras_fluxo import ambiente_compra
from test_compras_concorrencia_pg import test_checkout_concorrente_reabre_preferencia
from test_transacoes_concorrencia_pg import test_tres_caminhos_concorrentes
from test_cursos_comerciais import (comercial,
    test_pendente_retoma_e_confirma_apos_retirar_venda,
    test_renovacao_preexistente_confirma_apos_retirada_sem_novo_checkout)


@pytest.fixture
def motor():
    endereco = os.environ.get('VENDAS_TEST_PG_DSN')
    if not endereco:
        pytest.skip('Requer PostgreSQL descartável exclusivo')
    url = make_url(endereco)
    assert url.get_backend_name() == 'postgresql'
    assert url.database == 'compras_test_venda_20261108'
    assert url.host is None and url.query.get('host') == '/tmp/resumao-venda-pgsocket-final'
    engine = create_engine(endereco, connect_args={'options':'-c lock_timeout=10000 -c statement_timeout=20000'})
    with engine.begin() as conn:
        assert conn.execute(text('select current_database(), inet_server_addr()')).one() == ('compras_test_venda_20261108', None)
        conn.execute(text('DROP SCHEMA public CASCADE'))
        conn.execute(text('CREATE SCHEMA public'))
    yield engine
    engine.dispose()
