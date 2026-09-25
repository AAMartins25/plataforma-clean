from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.main import solicitar_reembolso


def test_solicitar_reembolso_preserva_acesso():
    pagamento = SimpleNamespace(
        id=10,
        usuario_id=2,
        curso_id=1,
        status="APPROVED",
        aprovado_em=datetime.utcnow() - timedelta(days=1),
        criado_em=datetime.utcnow() - timedelta(days=2),
        atualizado_em=None,
    )

    usuario = SimpleNamespace(id=2)

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = pagamento

    resultado = solicitar_reembolso(
        pagamento_id=10,
        db=db,
        usuario=usuario,
    )

    assert resultado["ok"] is True
    assert resultado["status"] == "REFUND_REQUESTED"
    assert pagamento.status == "REFUND_REQUESTED"

    # A solicitação não deve consultar nem alterar o acesso.
    db.query.assert_called_once()
    db.commit.assert_called_once()
    db.delete.assert_not_called()
    db.execute.assert_not_called()