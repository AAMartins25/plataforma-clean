from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.models import ContestacaoPagamento


def test_registro_de_contestacao_nao_altera_acesso():
    db = MagicMock()

    acesso = SimpleNamespace(
        ativo=True,
        data_fim=datetime.utcnow() + timedelta(days=90),
    )

    contestacao = ContestacaoPagamento(
        pagamento_id=10,
        mp_dispute_id="disputa_teste_001",
        status="ABERTA",
        valor_cents=4990,
    )

    db.add(contestacao)
    db.commit()

    assert contestacao.devolucao_confirmada_em is None
    assert contestacao.bloqueio_executado_em is None
    assert acesso.ativo is True
    db.query.assert_not_called()


def test_usuario_comum_nao_pode_registrar_contestacao():
    import pytest
    from fastapi import HTTPException
    from app.main import admin_registrar_contestacao
    from app.schemas import ContestacaoPagamentoCreate

    db = MagicMock()
    usuario = SimpleNamespace(is_admin=False)

    payload = ContestacaoPagamentoCreate(
        pagamento_id=10,
        valor_cents=4990,
    )

    with pytest.raises(HTTPException) as erro:
        admin_registrar_contestacao(
            payload=payload,
            db=db,
            admin=usuario,
        )

    assert erro.value.status_code == 403
    db.query.assert_not_called()
    db.commit.assert_not_called()


def test_admin_registra_contestacao_sem_alterar_acesso():
    from app.main import admin_registrar_contestacao
    from app.schemas import ContestacaoPagamentoCreate

    db = MagicMock()
    admin = SimpleNamespace(is_admin=True)

    pagamento = SimpleNamespace(
        id=10,
        aprovado_em=datetime(2026, 9, 25),
        valor_cents=4990,
    )

    acesso = SimpleNamespace(
        ativo=True,
        data_fim=datetime(2026, 12, 25),
    )

    consulta_pagamento = db.query.return_value.filter.return_value
    consulta_pagamento.with_for_update.return_value.first.return_value = pagamento

    # A segunda consulta verifica se já existe contestação.
    consulta_pagamento.first.return_value = None

    payload = ContestacaoPagamentoCreate(
        pagamento_id=10,
        mp_dispute_id="disputa_teste_002",
        motivo="Compra contestada pelo titular",
        valor_cents=4990,
    )

    resultado = admin_registrar_contestacao(
        payload=payload,
        db=db,
        admin=admin,
    )

    db.add.assert_called_once()
    contestacao = db.add.call_args.args[0]

    assert isinstance(contestacao, ContestacaoPagamento)
    assert contestacao.pagamento_id == 10
    assert contestacao.status == "ABERTA"
    assert contestacao.devolucao_confirmada_em is None
    assert contestacao.bloqueio_executado_em is None

    assert acesso.ativo is True
    assert acesso.data_fim == datetime(2026, 12, 25)

    assert resultado["ok"] is True
    db.commit.assert_called_once()


def test_usuario_comum_nao_pode_bloquear_acesso():
    import pytest
    from fastapi import HTTPException
    from app.main import admin_bloquear_acesso_contestacao

    db = MagicMock()
    aluno = SimpleNamespace(id=2, is_admin=False)

    with pytest.raises(HTTPException) as erro:
        admin_bloquear_acesso_contestacao(
            contestacao_id=1,
            db=db,
            admin=aluno,
        )

    assert erro.value.status_code == 403
    db.query.assert_not_called()
    db.commit.assert_not_called()


def test_nao_bloqueia_sem_devolucao_confirmada():
    import pytest
    from fastapi import HTTPException
    from app.main import admin_bloquear_acesso_contestacao

    db = MagicMock()
    admin = SimpleNamespace(id=1, is_admin=True)

    contestacao = SimpleNamespace(
        id=1,
        pagamento_id=1,
        devolucao_confirmada_em=None,
        bloqueio_executado_em=None,
    )

    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = contestacao

    with pytest.raises(HTTPException) as erro:
        admin_bloquear_acesso_contestacao(
            contestacao_id=1,
            db=db,
            admin=admin,
        )

    assert erro.value.status_code == 409
    assert "confirmar a devolução" in erro.value.detail
    db.commit.assert_not_called()


def test_bloqueio_apos_devolucao_sem_outros_direitos():
    from unittest.mock import patch
    from app.main import admin_bloquear_acesso_contestacao

    db = MagicMock()
    admin = SimpleNamespace(id=10, is_admin=True)

    contestacao = SimpleNamespace(
        id=1,
        pagamento_id=5,
        devolucao_confirmada_em="2026-09-26",
        bloqueio_executado_em=None,
        bloqueio_executado_por=None,
        status="DEVOLUCAO_CONFIRMADA",
    )
    pagamento = SimpleNamespace(
        id=5,
        usuario_id=2,
        curso_id=1,
    )

    consulta = (
        db.query.return_value
        .filter.return_value
        .with_for_update.return_value
    )
    consulta.first.side_effect = [contestacao, pagamento]

    with patch(
        "app.main.recalcular_acesso_apos_reembolso",
        return_value={"situacao": "SEM_DIREITOS_VIGENTES"},
    ) as recalcular:
        resultado = admin_bloquear_acesso_contestacao(
            contestacao_id=1,
            db=db,
            admin=admin,
        )

    recalcular.assert_called_once_with(
        db=db,
        usuario_id=2,
        curso_id=1,
        pagamento_reembolsado_id=5,
    )
    assert resultado["situacao_acesso"] == "SEM_DIREITOS_VIGENTES"
    assert contestacao.bloqueio_executado_em is not None
    assert contestacao.bloqueio_executado_por == 10
    assert contestacao.status == "BLOQUEIO_EXECUTADO"
    db.commit.assert_called_once()


def test_bloqueio_preserva_outra_compra_valida():
    from datetime import datetime
    from unittest.mock import patch
    from app.main import admin_bloquear_acesso_contestacao

    db = MagicMock()
    admin = SimpleNamespace(id=10, is_admin=True)
    data_fim = datetime(2027, 3, 15)

    contestacao = SimpleNamespace(
        id=1,
        pagamento_id=5,
        devolucao_confirmada_em=datetime(2026, 9, 26),
        bloqueio_executado_em=None,
        bloqueio_executado_por=None,
        status="DEVOLUCAO_CONFIRMADA",
    )
    pagamento = SimpleNamespace(
        id=5,
        usuario_id=2,
        curso_id=1,
    )

    consulta = (
        db.query.return_value
        .filter.return_value
        .with_for_update.return_value
    )
    consulta.first.side_effect = [contestacao, pagamento]

    with patch(
        "app.main.recalcular_acesso_apos_reembolso",
        return_value={
            "situacao": "ACESSO_PRESERVADO",
            "data_fim": data_fim,
        },
    ) as recalcular:
        resultado = admin_bloquear_acesso_contestacao(
            contestacao_id=1,
            db=db,
            admin=admin,
        )

    recalcular.assert_called_once_with(
        db=db,
        usuario_id=2,
        curso_id=1,
        pagamento_reembolsado_id=5,
    )
    assert resultado["situacao_acesso"] == "ACESSO_PRESERVADO"
    assert contestacao.bloqueio_executado_por == 10
    assert contestacao.bloqueio_executado_em is not None
    db.commit.assert_called_once()


def test_bloqueio_impedido_quando_exige_conferencia():
    import pytest
    from datetime import datetime
    from unittest.mock import patch
    from fastapi import HTTPException
    from app.main import admin_bloquear_acesso_contestacao

    db = MagicMock()
    admin = SimpleNamespace(id=10, is_admin=True)

    contestacao = SimpleNamespace(
        id=1,
        pagamento_id=5,
        devolucao_confirmada_em=datetime(2026, 9, 26),
        bloqueio_executado_em=None,
        bloqueio_executado_por=None,
        status="DEVOLUCAO_CONFIRMADA",
    )
    pagamento = SimpleNamespace(
        id=5,
        usuario_id=2,
        curso_id=1,
    )

    consulta = (
        db.query.return_value
        .filter.return_value
        .with_for_update.return_value
    )
    consulta.first.side_effect = [contestacao, pagamento]

    with patch(
        "app.main.recalcular_acesso_apos_reembolso",
        return_value={
            "situacao": "CONFERENCIA_NECESSARIA",
            "pagamentos_sem_historico": [8],
        },
    ):
        with pytest.raises(HTTPException) as erro:
            admin_bloquear_acesso_contestacao(
                contestacao_id=1,
                db=db,
                admin=admin,
            )

    assert erro.value.status_code == 409
    assert contestacao.bloqueio_executado_em is None
    assert contestacao.bloqueio_executado_por is None
    db.commit.assert_not_called()
    db.rollback.assert_called()


def test_confirmacao_devolucao_registra_admin_sem_bloquear_acesso():
    from app.main import admin_confirmar_devolucao_contestacao
    from app.schemas import ContestacaoDevolucaoConfirmadaCreate

    db = MagicMock()
    admin = SimpleNamespace(id=7, is_admin=True)

    contestacao = ContestacaoPagamento(
        id=15,
        pagamento_id=10,
        status="ABERTA",
        valor_cents=4990,
    )

    acesso = SimpleNamespace(
        ativo=True,
        data_fim=datetime.utcnow() + timedelta(days=90),
    )
    data_fim_original = acesso.data_fim

    db.query.return_value.filter.return_value \
        .with_for_update.return_value.first.return_value = contestacao

    payload = ContestacaoDevolucaoConfirmadaCreate(
        referencia_devolucao=" COMPROVANTE_TESTE_001 "
    )

    resultado = admin_confirmar_devolucao_contestacao(
        contestacao_id=15,
        payload=payload,
        db=db,
        admin=admin,
    )

    assert contestacao.devolucao_confirmada_em is not None
    assert contestacao.devolucao_confirmada_por == 7
    assert contestacao.referencia_devolucao == "COMPROVANTE_TESTE_001"
    assert contestacao.status == "DEVOLUCAO_CONFIRMADA"

    assert contestacao.bloqueio_executado_em is None
    assert contestacao.bloqueio_executado_por is None
    assert acesso.ativo is True
    assert acesso.data_fim == data_fim_original

    assert resultado["ok"] is True
    assert resultado["status"] == "DEVOLUCAO_CONFIRMADA"
    db.commit.assert_called_once()
