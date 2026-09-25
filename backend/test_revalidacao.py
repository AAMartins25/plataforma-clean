from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from dateutil.relativedelta import relativedelta
from app.models import PeriodoAcessoPagamento
from app.main import admin_revalidar_pagamento

def test_compra_vencida_nao_reativa_acesso():
    db = MagicMock()

    pagamento = {
        "id": 154,
        "usuario_id": 87,
        "curso_id": 1,
        "tempo_acesso_id": 1,
        "aprovado_em": None,
        "criado_em": datetime.utcnow() - timedelta(days=200),
    }

    db.execute.return_value.mappings.return_value.first.return_value = pagamento
    db.execute.return_value.scalar_one.return_value = "PENDENTE"

    # Primeira consulta: acesso existente. Segunda: prazo contratado.
    db.query.return_value.filter.return_value.first.side_effect = [
        None,
        SimpleNamespace(meses=4),
    ]

    data_antiga = (datetime.utcnow() - timedelta(days=200)).isoformat() + "Z"

    resposta_mp = MagicMock()
    resposta_mp.status_code = 200
    resposta_mp.json.return_value = {
        "status": "approved",
        "date_approved": data_antiga,
    }

    with (
        patch("app.main.requests.get", return_value=resposta_mp),
        patch("app.main.mp_headers", return_value={}),
    ):
        resultado = admin_revalidar_pagamento(
            payload={"mp_payment_id": "pagamento_teste"},
            db=db,
            usuario=SimpleNamespace(is_admin=True),
        )

    comandos = [
        str(chamada.args[0])
        for chamada in db.execute.call_args_list
    ]

    assert resultado["status"] == "APPROVED"
    assert resultado["liberou_acesso"] is False
    assert not any("INSERT INTO acessos_curso" in sql for sql in comandos)
    assert any("UPDATE pagamentos" in sql for sql in comandos)
    db.commit.assert_called_once()


def test_compra_vigente_libera_acesso():
    db = MagicMock()

    pagamento = {
        "id": 155,
        "usuario_id": 87,
        "curso_id": 1,
        "tempo_acesso_id": 1,
        "aprovado_em": None,
        "criado_em": datetime.utcnow(),
    }

    db.execute.return_value.mappings.return_value.first.return_value = pagamento
    db.execute.return_value.scalar_one.return_value = "PENDENTE"

    db.query.return_value.filter.return_value.first.side_effect = [
        None,
        SimpleNamespace(meses=4),
    ]

    resposta_mp = MagicMock()
    resposta_mp.status_code = 200
    resposta_mp.json.return_value = {
        "status": "approved",
        "date_approved": (
            datetime.utcnow() - timedelta(days=1)
        ).isoformat() + "Z",
    }

    with (
        patch("app.main.requests.get", return_value=resposta_mp),
        patch("app.main.mp_headers", return_value={}),
    ):
        resultado = admin_revalidar_pagamento(
            payload={"mp_payment_id": "pagamento_teste_vigente"},
            db=db,
            usuario=SimpleNamespace(is_admin=True),
        )

    comandos = [
        str(chamada.args[0])
        for chamada in db.execute.call_args_list
    ]

    assert resultado["status"] == "APPROVED"
    assert resultado["liberou_acesso"] is True
    assert any("INSERT INTO acessos_curso" in sql for sql in comandos)
    db.commit.assert_called_once()

    db.add.assert_called_once()

    periodo = db.add.call_args.args[0]

    assert isinstance(periodo, PeriodoAcessoPagamento)
    assert periodo.pagamento_id == 155
    assert periodo.usuario_id == 87
    assert periodo.curso_id == 1
    assert periodo.data_fim == (
        periodo.data_inicio + relativedelta(months=4)
    )

    insercoes = [
        chamada
        for chamada in db.execute.call_args_list
        if "INSERT INTO acessos_curso" in str(chamada.args[0])
    ]

    assert len(insercoes) == 1

    parametros = insercoes[0].args[1]

    assert parametros["u"] == 87
    assert parametros["c"] == 1
    assert parametros["fim"] > parametros["inicio"]


def test_compra_antiga_nao_reduz_prazo_atual():
    db = MagicMock()

    pagamento = {
        "id": 156,
        "usuario_id": 87,
        "curso_id": 1,
        "tempo_acesso_id": 1,
        "aprovado_em": None,
        "criado_em": datetime.utcnow(),
    }

    db.execute.return_value.mappings.return_value.first.return_value = pagamento
    db.execute.return_value.scalar_one.return_value = "PENDENTE"

    inicio_atual = datetime.utcnow() - timedelta(days=10)
    fim_atual = datetime.utcnow() + timedelta(days=300)

    acesso_atual = SimpleNamespace(
        data_inicio=inicio_atual,
        data_fim=fim_atual,
    )

    db.query.return_value.filter.return_value.first.side_effect = [
        acesso_atual,
        SimpleNamespace(meses=4),
    ]

    resposta_mp = MagicMock()
    resposta_mp.status_code = 200
    resposta_mp.json.return_value = {
        "status": "approved",
        "date_approved": (
            datetime.utcnow() - timedelta(days=30)
        ).isoformat() + "Z",
    }

    with (
        patch("app.main.requests.get", return_value=resposta_mp),
        patch("app.main.mp_headers", return_value={}),
    ):
        resultado = admin_revalidar_pagamento(
            payload={"mp_payment_id": "pagamento_antigo"},
            db=db,
            usuario=SimpleNamespace(is_admin=True),
        )

    insercoes = [
        chamada
        for chamada in db.execute.call_args_list
        if "INSERT INTO acessos_curso" in str(chamada.args[0])
    ]

    assert len(insercoes) == 1

    parametros = insercoes[0].args[1]

    assert parametros["inicio"] == inicio_atual
    assert parametros["fim"] == fim_atual
    assert resultado["status"] == "APPROVED"
    db.commit.assert_called_once()

import pytest
from fastapi import HTTPException


@pytest.mark.parametrize(
    "status_reembolso",
    ["REFUND_REQUESTED", "REFUND_IN_PROCESS", "REFUNDED"],
)
def test_pagamento_reembolsado_nao_pode_ser_revalidado(status_reembolso):
    db = MagicMock()

    pagamento = {
        "id": 157,
        "usuario_id": 87,
        "curso_id": 1,
        "tempo_acesso_id": 1,
        "aprovado_em": datetime.utcnow(),
        "criado_em": datetime.utcnow(),
    }

    db.execute.return_value.mappings.return_value.first.return_value = pagamento
    db.execute.return_value.scalar_one.return_value = status_reembolso

    with patch("app.main.requests.get") as consulta_mp:
        with pytest.raises(HTTPException) as erro:
            admin_revalidar_pagamento(
                payload={"mp_payment_id": "pagamento_reembolsado"},
                db=db,
                usuario=SimpleNamespace(is_admin=True),
            )

    assert erro.value.status_code == 409
    consulta_mp.assert_not_called()
    db.commit.assert_not_called()