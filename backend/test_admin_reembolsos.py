from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.main import aprovar_reembolso, recusar_reembolso


@pytest.mark.parametrize(
    "funcao,status_esperado",
    [
        (aprovar_reembolso, "REFUND_IN_PROCESS"),
        (recusar_reembolso, "REFUND_DENIED"),
    ],
)
def test_decisao_admin_preserva_acesso(funcao, status_esperado):
    pagamento = SimpleNamespace(
        id=10,
        usuario_id=2,
        curso_id=1,
        status="REFUND_REQUESTED",
        atualizado_em=None,
    )

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = pagamento

    resultado = funcao(
        pagamento_id=10,
        db=db,
        admin=SimpleNamespace(is_admin=True),
    )

    assert resultado["ok"] is True
    assert resultado["status"] == status_esperado
    assert pagamento.status == status_esperado
    assert isinstance(pagamento.atualizado_em, datetime)

    # Nenhuma das decisões deve consultar ou modificar o acesso.
    db.query.assert_called_once()
    db.commit.assert_called_once()
    db.execute.assert_not_called()
    db.delete.assert_not_called()


@pytest.mark.parametrize(
    "funcao",
    [aprovar_reembolso, recusar_reembolso],
)
def test_usuario_comum_nao_pode_decidir(funcao):
    db = MagicMock()

    with pytest.raises(HTTPException) as erro:
        funcao(
            pagamento_id=10,
            db=db,
            admin=SimpleNamespace(is_admin=False),
        )

    assert erro.value.status_code == 403
    db.query.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize(
    "funcao",
    [aprovar_reembolso, recusar_reembolso],
)
def test_nao_permite_decidir_sem_solicitacao_pendente(funcao):
    pagamento = SimpleNamespace(status="APPROVED")

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = pagamento

    with pytest.raises(HTTPException) as erro:
        funcao(
            pagamento_id=10,
            db=db,
            admin=SimpleNamespace(is_admin=True),
        )

    assert erro.value.status_code == 400
    db.commit.assert_not_called()

def test_usuario_comum_nao_pode_registrar_pix_manual():
    from app.main import registrar_reembolso_pix_manual
    from app.schemas import ReembolsoPixManualCreate

    db = MagicMock()

    dados = ReembolsoPixManualCreate(
        valor_cents=4990,
        referencia_comprovante="PIX-TESTE-123"
    )

    with pytest.raises(HTTPException) as erro:
        registrar_reembolso_pix_manual(
            pagamento_id=10,
            dados=dados,
            db=db,
            admin=SimpleNamespace(is_admin=False),
        )

    assert erro.value.status_code == 403

    # O usuário comum não pode sequer consultar ou alterar pagamentos.
    db.query.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()

def test_pix_manual_exige_solicitacao_aprovada():
    from app.main import registrar_reembolso_pix_manual
    from app.schemas import ReembolsoPixManualCreate

    pagamento = SimpleNamespace(
        id=10,
        status="REFUND_REQUESTED",
        valor_cents=4990,
    )

    db = MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = pagamento

    dados = ReembolsoPixManualCreate(
        valor_cents=4990,
        referencia_comprovante="PIX-TESTE-123",
    )

    with pytest.raises(HTTPException) as erro:
        registrar_reembolso_pix_manual(
            pagamento_id=10,
            dados=dados,
            db=db,
            admin=SimpleNamespace(is_admin=True),
        )

    assert erro.value.status_code == 400
    db.add.assert_not_called()
    db.commit.assert_not_called()

def test_pix_manual_rejeita_valor_diferente_da_compra():
    from app.main import registrar_reembolso_pix_manual
    from app.schemas import ReembolsoPixManualCreate

    pagamento = SimpleNamespace(
        id=10,
        status="REFUND_IN_PROCESS",
        valor_cents=4990,
    )

    db = MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = pagamento

    dados = ReembolsoPixManualCreate(
        valor_cents=3990,
        referencia_comprovante="PIX-TESTE-123",
    )

    with pytest.raises(HTTPException) as erro:
        registrar_reembolso_pix_manual(
            pagamento_id=10,
            dados=dados,
            db=db,
            admin=SimpleNamespace(is_admin=True),
        )

    assert erro.value.status_code == 400
    assert "valor integral" in erro.value.detail

    db.add.assert_not_called()
    db.commit.assert_not_called()

def test_pix_manual_rejeita_reembolso_duplicado():
    from app.main import registrar_reembolso_pix_manual
    from app.schemas import ReembolsoPixManualCreate

    pagamento = SimpleNamespace(
        id=10,
        status="REFUND_IN_PROCESS",
        valor_cents=4990,
    )

    db = MagicMock()

    # Primeira consulta: pagamento aprovado para reembolso.
    consulta_pagamento = (
        db.query.return_value
        .filter.return_value
        .with_for_update.return_value
    )
    consulta_pagamento.first.return_value = pagamento

    # Segunda consulta: já existe uma operação ativa.
    consulta_existente = MagicMock()
    consulta_existente.filter.return_value.first.return_value = (
        SimpleNamespace(id=5, status="PENDENTE")
    )

    db.query.side_effect = [
        MagicMock(
            filter=MagicMock(
                return_value=MagicMock(
                    with_for_update=MagicMock(
                        return_value=consulta_pagamento
                    )
                )
            )
        ),
        consulta_existente,
    ]

    dados = ReembolsoPixManualCreate(
        valor_cents=4990,
        referencia_comprovante="PIX-TESTE-123",
    )

    with pytest.raises(HTTPException) as erro:
        registrar_reembolso_pix_manual(
            pagamento_id=10,
            dados=dados,
            db=db,
            admin=SimpleNamespace(is_admin=True),
        )

    assert erro.value.status_code == 409
    db.add.assert_not_called()
    db.commit.assert_not_called()

def test_pix_manual_registra_operacao_pendente():
    from app.main import registrar_reembolso_pix_manual
    from app.schemas import ReembolsoPixManualCreate
    from app.models import ReembolsoFinanceiro

    pagamento = SimpleNamespace(
        id=10,
        status="REFUND_IN_PROCESS",
        valor_cents=4990,
    )

    db = MagicMock()

    consulta_pagamento = MagicMock()
    consulta_pagamento.filter.return_value.with_for_update.return_value.first.return_value = pagamento

    consulta_reembolso = MagicMock()
    consulta_reembolso.filter.return_value.first.return_value = None

    db.query.side_effect = [
        consulta_pagamento,
        consulta_reembolso,
    ]

    dados = ReembolsoPixManualCreate(
        valor_cents=4990,
        referencia_comprovante="PIX-TESTE-123",
    )

    resultado = registrar_reembolso_pix_manual(
        pagamento_id=10,
        dados=dados,
        db=db,
        admin=SimpleNamespace(is_admin=True),
    )

    assert resultado["ok"] is True
    assert resultado["status"] == "PENDENTE"

    db.add.assert_called_once()
    reembolso = db.add.call_args.args[0]

    assert isinstance(reembolso, ReembolsoFinanceiro)
    assert reembolso.pagamento_id == 10
    assert reembolso.metodo == "PIX_MANUAL"
    assert reembolso.valor_cents == 4990
    assert reembolso.status == "PENDENTE"
    assert reembolso.referencia_comprovante == "PIX-TESTE-123"

    assert pagamento.status == "REFUND_IN_PROCESS"
    db.commit.assert_called_once()
    db.delete.assert_not_called()

def test_pix_manual_trata_duplicidade_no_banco():
    from sqlalchemy.exc import IntegrityError

    from app.main import registrar_reembolso_pix_manual
    from app.schemas import ReembolsoPixManualCreate

    pagamento = SimpleNamespace(
        id=10,
        status="REFUND_IN_PROCESS",
        valor_cents=4990,
    )

    db = MagicMock()

    consulta_pagamento = MagicMock()
    consulta_pagamento.filter.return_value.with_for_update.return_value.first.return_value = pagamento

    consulta_reembolso = MagicMock()
    consulta_reembolso.filter.return_value.first.return_value = None

    db.query.side_effect = [
        consulta_pagamento,
        consulta_reembolso,
    ]

    db.commit.side_effect = IntegrityError(
        statement="INSERT INTO reembolsos_financeiros",
        params={},
        orig=Exception("Registro duplicado"),
    )

    dados = ReembolsoPixManualCreate(
        valor_cents=4990,
        referencia_comprovante="PIX-TESTE-123",
    )

    with pytest.raises(HTTPException) as erro:
        registrar_reembolso_pix_manual(
            pagamento_id=10,
            dados=dados,
            db=db,
            admin=SimpleNamespace(is_admin=True),
        )

    assert erro.value.status_code == 409
    db.rollback.assert_called_once()
    assert pagamento.status == "REFUND_IN_PROCESS"

def test_pix_manual_exige_confirmacao_do_extrato():
    from app.main import confirmar_reembolso_pix_manual

    db = MagicMock()

    with pytest.raises(HTTPException) as erro:
        confirmar_reembolso_pix_manual(
            reembolso_id=10,
            confirmacao_extrato=False,
            db=db,
            admin=SimpleNamespace(is_admin=True),
        )

    assert erro.value.status_code == 400
    assert "extrato bancário" in erro.value.detail

    db.query.assert_not_called()
    db.commit.assert_not_called()

def test_usuario_comum_nao_pode_confirmar_pix_manual():
    from app.main import confirmar_reembolso_pix_manual

    db = MagicMock()

    with pytest.raises(HTTPException) as erro:
        confirmar_reembolso_pix_manual(
            reembolso_id=10,
            confirmacao_extrato=True,
            db=db,
            admin=SimpleNamespace(is_admin=False),
        )

    assert erro.value.status_code == 403

    db.query.assert_not_called()
    db.commit.assert_not_called()

def test_pix_manual_impede_confirmacao_duplicada():
    from app.main import confirmar_reembolso_pix_manual

    reembolso = SimpleNamespace(
        id=10,
        metodo="PIX_MANUAL",
        status="CONFIRMADO",
        pagamento_id=20,
    )

    db = MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = reembolso

    with pytest.raises(HTTPException) as erro:
        confirmar_reembolso_pix_manual(
            reembolso_id=10,
            confirmacao_extrato=True,
            db=db,
            admin=SimpleNamespace(is_admin=True),
        )

    assert erro.value.status_code == 400
    assert db.query.call_count == 1
    db.commit.assert_not_called()
    db.delete.assert_not_called()

def test_pix_manual_confirmacao_financeira_preserva_acesso():
    from app.main import confirmar_reembolso_pix_manual

    reembolso = SimpleNamespace(
        id=10,
        metodo="PIX_MANUAL",
        status="PENDENTE",
        pagamento_id=20,
        valor_cents=4990,
        confirmado_em=None,
    )

    pagamento = SimpleNamespace(
        id=20,
        usuario_id=2,
        curso_id=1,
        status="REFUND_IN_PROCESS",
        valor_cents=4990,
        atualizado_em=None,
    )

    db = MagicMock()

    consulta_reembolso = MagicMock()
    consulta_reembolso.filter.return_value.with_for_update.return_value.first.return_value = reembolso

    consulta_pagamento = MagicMock()
    consulta_pagamento.filter.return_value.with_for_update.return_value.first.return_value = pagamento

    db.query.side_effect = [
        consulta_reembolso,
        consulta_pagamento,
    ]

    with patch(
        "app.main.recalcular_acesso_apos_reembolso",
        return_value={
            "situacao": "CONFERENCIA_NECESSARIA",
            "pagamentos_sem_historico": [1],
        },
    ) as recalcular:
        resultado = confirmar_reembolso_pix_manual(
            reembolso_id=10,
            confirmacao_extrato=True,
            db=db,
            admin=SimpleNamespace(is_admin=True),
        )

    recalcular.assert_called_once_with(
        db=db,
        usuario_id=2,
        curso_id=1,
        pagamento_reembolsado_id=20,
    )

    assert resultado["ok"] is True
    assert resultado["status"] == "CONFIRMADO"
    assert resultado["pagamento_status"] == "REFUNDED"

    assert reembolso.status == "CONFIRMADO"
    assert isinstance(reembolso.confirmado_em, datetime)

    assert pagamento.status == "REFUNDED"
    assert isinstance(pagamento.atualizado_em, datetime)

    # A confirmação financeira não altera o acesso do aluno.
    assert db.query.call_count == 2
    db.commit.assert_called_once()
    db.delete.assert_not_called()
    db.execute.assert_not_called()

def test_falha_commit_reembolso_executa_rollback():
    from app.main import confirmar_reembolso_pix_manual

    reembolso = SimpleNamespace(
        id=10,
        metodo="PIX_MANUAL",
        status="PENDENTE",
        pagamento_id=20,
        valor_cents=4990,
        confirmado_em=None,
    )

    pagamento = SimpleNamespace(
        id=20,
        usuario_id=2,
        curso_id=1,
        status="REFUND_IN_PROCESS",
        valor_cents=4990,
        atualizado_em=None,
    )

    db = MagicMock()

    consulta_reembolso = MagicMock()
    consulta_reembolso.filter.return_value.with_for_update.return_value.first.return_value = reembolso

    consulta_pagamento = MagicMock()
    consulta_pagamento.filter.return_value.with_for_update.return_value.first.return_value = pagamento

    db.query.side_effect = [
        consulta_reembolso,
        consulta_pagamento,
    ]

    db.commit.side_effect = RuntimeError("Falha simulada no commit")

    with patch(
        "app.main.recalcular_acesso_apos_reembolso",
        return_value={"situacao": "SEM_DIREITOS_VIGENTES"},
    ):
        with pytest.raises(RuntimeError, match="Falha simulada no commit"):
            confirmar_reembolso_pix_manual(
                reembolso_id=10,
                confirmacao_extrato=True,
                db=db,
                admin=SimpleNamespace(is_admin=True),
            )

    db.commit.assert_called_once()
    db.rollback.assert_called_once()