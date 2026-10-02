from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from dateutil.relativedelta import relativedelta
from app.models import PeriodoAcessoPagamento
from app.main import admin_revalidar_pagamento


def preparar_db_revalidacao(pagamento, acesso_atual, meses=4):
    db = MagicMock()

    pag = {
        "id": pagamento.id,
        "usuario_id": pagamento.usuario_id,
        "curso_id": pagamento.curso_id,
        "tempo_acesso_id": pagamento.tempo_acesso_id,
        "aprovado_em": pagamento.aprovado_em,
        "criado_em": pagamento.criado_em,
    }

    db.execute.return_value.mappings.return_value.first.return_value = pag
    db.execute.return_value.scalar_one.return_value = "PENDENTE"

    # Usuario: lock de serialização.
    db.query.return_value.filter.return_value.with_for_update.return_value.one.return_value = (
        SimpleNamespace(id=pagamento.usuario_id)
    )

    # Pagamento: objeto ORM usado pela implementação atual.
    db.query.return_value.filter.return_value.with_for_update.return_value.populate_existing.return_value.one.return_value = (
        pagamento
    )

    # Consultas simples: acesso atual e prazo contratado.
    db.query.return_value.filter.return_value.first.side_effect = [
        acesso_atual,
        SimpleNamespace(meses=meses),
    ]

    return db


def resposta_mp(payment_id, pagamento_id, data_aprovacao):
    resposta = MagicMock()
    resposta.status_code = 200
    resposta.json.return_value = {
        "id": payment_id,
        "status": "approved",
        "external_reference": (
            f"user:87|curso:1|tempo:1|pagamento:{pagamento_id}"
        ),
        "date_approved": data_aprovacao,
        "transaction_amount": 49.90,
        "currency_id": "BRL",
    }
    return resposta


def novo_pagamento(id_pagamento, criado_em):
    return SimpleNamespace(
        id=id_pagamento,
        usuario_id=87,
        curso_id=1,
        tempo_acesso_id=1,
        valor_cents=4990,
        tipo_compra="NOVA",
        vencimento_original=None,
        ocorrencia_financeira=None,
        oportunidade_id=None,
        contratacao_id=None,
        mp_payment_id=None,
        aprovado_em=None,
        status="PENDENTE",
        criado_em=criado_em,
        atualizado_em=None,
    )


def test_compra_vencida_nao_reativa_acesso():
    data_aprovacao = datetime.utcnow() - timedelta(days=200)
    pagamento = novo_pagamento(154, data_aprovacao)
    db = preparar_db_revalidacao(pagamento, None)

    resposta = resposta_mp(
        "pagamento_teste",
        154,
        data_aprovacao.isoformat() + "Z",
    )

    with (
        patch("app.main.requests.get", return_value=resposta),
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
    assert pagamento.aprovado_em == data_aprovacao
    db.commit.assert_called_once()


def test_compra_vigente_libera_acesso():
    data_aprovacao = datetime.utcnow() - timedelta(days=1)
    pagamento = novo_pagamento(155, datetime.utcnow())
    db = preparar_db_revalidacao(pagamento, None)

    resposta = resposta_mp(
        "pagamento_teste_vigente",
        155,
        data_aprovacao.isoformat() + "Z",
    )

    with (
        patch("app.main.requests.get", return_value=resposta),
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
    assert pagamento.aprovado_em == data_aprovacao
    db.commit.assert_called_once()

    assert db.add.call_count == 2
    tipos = {
        type(chamada.args[0]).__name__
        for chamada in db.add.call_args_list
    }
    assert tipos == {"ContratacaoCurso", "PeriodoAcessoPagamento"}

    periodo = db.add.call_args.args[0]

    assert isinstance(periodo, PeriodoAcessoPagamento)
    assert periodo.pagamento_id == 155
    assert periodo.usuario_id == 87
    assert periodo.curso_id == 1
    assert periodo.data_fim == (
        periodo.data_inicio + relativedelta(months=4)
    )


def test_compra_antiga_nao_reduz_prazo_atual():
    data_aprovacao = datetime.utcnow() - timedelta(days=30)
    pagamento = novo_pagamento(156, datetime.utcnow())

    inicio_atual = datetime.utcnow() - timedelta(days=10)
    fim_atual = datetime.utcnow() + timedelta(days=300)

    acesso_atual = SimpleNamespace(
        data_inicio=inicio_atual,
        data_fim=fim_atual,
    )

    db = preparar_db_revalidacao(pagamento, acesso_atual)

    resposta = resposta_mp(
        "pagamento_antigo",
        156,
        data_aprovacao.isoformat() + "Z",
    )

    with (
        patch("app.main.requests.get", return_value=resposta),
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

    sql = str(insercoes[0].args[0])
    parametros = insercoes[0].args[1]

    # A nova compra envia seu próprio período ao UPSERT.
    # O CASE do SQL é quem preserva o acesso agregado mais longo já existente.
    assert parametros["inicio"] == data_aprovacao
    assert parametros["fim"] < fim_atual
    assert "acessos_curso.data_fim > :fim" in sql
    assert "THEN acessos_curso.data_inicio" in sql
    assert "THEN acessos_curso.data_fim" in sql
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