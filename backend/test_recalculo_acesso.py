from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from unittest.mock import patch
from app.main import recalcular_acesso_apos_reembolso

from app.main import consultar_direitos_acesso_apos_reembolso


def test_compra_antiga_sem_historico_exige_conferencia():
    db = MagicMock()

    pagamento_antigo = SimpleNamespace(id=1)

    # Consultas, na ordem:
    # pagamentos, períodos, concessões e demonstrações.
    db.query.return_value.filter.return_value.all.side_effect = [
        [pagamento_antigo],
        [],
        [],
        [],
    ]

    resultado = consultar_direitos_acesso_apos_reembolso(
        db=db,
        usuario_id=2,
        curso_id=1,
        pagamento_reembolsado_id=2,
    )

    assert resultado["pagamentos_sem_historico"] == [1]
    assert resultado["requer_conferencia"] is True
    assert resultado["possui_acesso_sem_prazo"] is False
    assert resultado["maior_data_fim"] is None

from datetime import timedelta


def test_outra_compra_vigente_preserva_acesso():
    db = MagicMock()

    agora = datetime.utcnow()
    data_inicio = agora - timedelta(days=10)
    data_fim = agora + timedelta(days=110)

    outra_compra = SimpleNamespace(id=3)

    periodo = SimpleNamespace(
        pagamento_id=3,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )

    # Consultas: pagamentos, períodos, concessões e demonstrações.
    db.query.return_value.filter.return_value.all.side_effect = [
        [outra_compra],
        [periodo],
        [],
        [],
    ]

    resultado = consultar_direitos_acesso_apos_reembolso(
        db=db,
        usuario_id=2,
        curso_id=1,
        pagamento_reembolsado_id=2,
    )

    assert resultado["pagamentos_sem_historico"] == []
    assert resultado["requer_conferencia"] is False
    assert resultado["possui_acesso_sem_prazo"] is False
    assert resultado["maior_data_fim"] == data_fim

def test_concessao_administrativa_preserva_acesso():
    db = MagicMock()

    agora = datetime.utcnow()
    data_fim = agora + timedelta(days=90)

    concessao = SimpleNamespace(
        data_inicio=agora - timedelta(days=5),
        data_fim=data_fim,
        ativo=True,
    )

    # Consultas: pagamentos, concessões e demonstrações.
    # Sem outros pagamentos, a consulta aos períodos é ignorada.
    db.query.return_value.filter.return_value.all.side_effect = [
        [],
        [concessao],
        [],
    ]

    resultado = consultar_direitos_acesso_apos_reembolso(
        db=db,
        usuario_id=2,
        curso_id=1,
        pagamento_reembolsado_id=2,
    )

    assert resultado["pagamentos_sem_historico"] == []
    assert resultado["requer_conferencia"] is False
    assert resultado["possui_acesso_sem_prazo"] is False
    assert resultado["maior_data_fim"] == data_fim

def test_demonstracao_vigente_preserva_acesso():
    db = MagicMock()

    agora = datetime.utcnow()
    data_fim = agora + timedelta(days=7)

    demonstracao = SimpleNamespace(
        data_inicio=agora - timedelta(days=1),
        data_fim=data_fim,
        ativo=True,
    )

    # Sem outras compras: consultas a pagamentos,
    # concessões administrativas e demonstrações.
    db.query.return_value.filter.return_value.all.side_effect = [
        [],
        [],
        [demonstracao],
    ]

    resultado = consultar_direitos_acesso_apos_reembolso(
        db=db,
        usuario_id=2,
        curso_id=1,
        pagamento_reembolsado_id=2,
    )

    assert resultado["pagamentos_sem_historico"] == []
    assert resultado["requer_conferencia"] is False
    assert resultado["possui_acesso_sem_prazo"] is False
    assert resultado["maior_data_fim"] == data_fim

def test_concessao_sem_prazo_preserva_acesso():
    db = MagicMock()

    agora = datetime.utcnow()

    concessao = SimpleNamespace(
        data_inicio=agora - timedelta(days=5),
        data_fim=None,
        ativo=True,
    )

    db.query.return_value.filter.return_value.all.side_effect = [
        [],           # Outras compras
        [concessao],  # Concessões administrativas
        [],           # Demonstrações
    ]

    resultado = consultar_direitos_acesso_apos_reembolso(
        db=db,
        usuario_id=2,
        curso_id=1,
        pagamento_reembolsado_id=2,
    )

    assert resultado["pagamentos_sem_historico"] == []
    assert resultado["requer_conferencia"] is False
    assert resultado["possui_acesso_sem_prazo"] is True
    assert resultado["maior_data_fim"] is None

def test_reembolso_sem_outros_direitos_desativa_acesso():
    db = MagicMock()

    acesso = SimpleNamespace(
        ativo=True,
        data_fim=datetime.utcnow() + timedelta(days=90),
    )

    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = acesso

    direitos = {
        "pagamentos_sem_historico": [],
        "requer_conferencia": False,
        "possui_acesso_sem_prazo": False,
        "maior_data_fim": None,
    }

    with patch(
        "app.main.consultar_direitos_acesso_apos_reembolso",
        return_value=direitos,
    ):
        resultado = recalcular_acesso_apos_reembolso(
            db=db,
            usuario_id=2,
            curso_id=1,
            pagamento_reembolsado_id=2,
        )

    assert resultado["situacao"] == "SEM_DIREITOS_VIGENTES"
    assert acesso.ativo is False
    db.commit.assert_not_called()

def test_compra_sem_historico_impede_alteracao_do_acesso():
    db = MagicMock()

    direitos = {
        "pagamentos_sem_historico": [1],
        "requer_conferencia": True,
        "possui_acesso_sem_prazo": False,
        "maior_data_fim": None,
    }

    with patch(
        "app.main.consultar_direitos_acesso_apos_reembolso",
        return_value=direitos,
    ):
        resultado = recalcular_acesso_apos_reembolso(
            db=db,
            usuario_id=2,
            curso_id=1,
            pagamento_reembolsado_id=2,
        )

    assert resultado["situacao"] == "CONFERENCIA_NECESSARIA"
    assert resultado["pagamentos_sem_historico"] == [1]

    # Nenhuma consulta para alterar o acesso deve ocorrer.
    db.query.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()

def test_recalculo_preserva_prazo_de_outra_compra():
    db = MagicMock()

    data_fim = datetime.utcnow() + timedelta(days=120)

    acesso = SimpleNamespace(
        ativo=True,
        data_fim=datetime.utcnow() + timedelta(days=240),
    )

    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = acesso

    direitos = {
        "pagamentos_sem_historico": [],
        "requer_conferencia": False,
        "possui_acesso_sem_prazo": False,
        "maior_data_fim": data_fim,
    }

    with patch(
        "app.main.consultar_direitos_acesso_apos_reembolso",
        return_value=direitos,
    ):
        resultado = recalcular_acesso_apos_reembolso(
            db=db,
            usuario_id=2,
            curso_id=1,
            pagamento_reembolsado_id=2,
        )

    assert resultado["situacao"] == "ACESSO_PRESERVADO"
    assert acesso.ativo is True
    assert acesso.data_fim == data_fim
    db.commit.assert_not_called()

def test_recalculo_preserva_acesso_sem_prazo():
    db = MagicMock()

    acesso = SimpleNamespace(
        ativo=True,
        data_fim=datetime.utcnow() + timedelta(days=90),
    )

    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = acesso

    direitos = {
        "pagamentos_sem_historico": [],
        "requer_conferencia": False,
        "possui_acesso_sem_prazo": True,
        "maior_data_fim": None,
    }

    with patch(
        "app.main.consultar_direitos_acesso_apos_reembolso",
        return_value=direitos,
    ):
        resultado = recalcular_acesso_apos_reembolso(
            db=db,
            usuario_id=2,
            curso_id=1,
            pagamento_reembolsado_id=2,
        )

    assert resultado["situacao"] == "ACESSO_PRESERVADO"
    assert acesso.ativo is True
    assert acesso.data_fim is None
    db.commit.assert_not_called()