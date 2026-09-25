from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.main import meus_cursos


def test_meus_cursos_desativa_acesso_expirado():
    db = MagicMock()

    acesso_expirado = SimpleNamespace(
        ativo=True,
        data_fim=datetime.utcnow() - timedelta(days=1),
    )

    # Primeira consulta: acessos vencidos.
    # Segunda consulta: acessos ainda disponíveis.
    db.query.return_value.filter.return_value.all.side_effect = [
        [acesso_expirado],
        [],
    ]

    db.query.return_value.join.return_value.filter.return_value.all.return_value = []

    resultado = meus_cursos(
        db=db,
        usuario=SimpleNamespace(id=87),
    )

    assert acesso_expirado.ativo is False
    assert resultado == []
    db.commit.assert_called_once()
