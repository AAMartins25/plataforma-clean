from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy.exc import IntegrityError
import pytest
from fastapi import HTTPException
from app.main import admin_criar_acesso
from app.models import AcessoCurso, ConcessaoAcessoAdmin
from app.schemas import AcessoCursoCreate


def test_concessao_para_aluno_sem_acesso():
    db = MagicMock()

    # Consultas: aluno, curso e acesso existente.
    db.query.return_value.filter.return_value.first.side_effect = [
        SimpleNamespace(id=87),
        SimpleNamespace(id=1),
        None,
    ]

    data_fim = datetime.utcnow() + timedelta(days=30)

    payload = AcessoCursoCreate(
        usuario_id=87,
        curso_id=1,
        ativo=True,
        data_fim=data_fim,
    )

    resultado = admin_criar_acesso(
        payload=payload,
        db=db,
        usuario=SimpleNamespace(is_admin=True),
    )

    registros = [
        chamada.args[0]
        for chamada in db.add.call_args_list
    ]

    acessos = [
        registro
        for registro in registros
        if isinstance(registro, AcessoCurso)
    ]

    concessoes = [
        registro
        for registro in registros
        if isinstance(registro, ConcessaoAcessoAdmin)
    ]

    assert len(acessos) == 1
    assert len(concessoes) == 1

    assert acessos[0].usuario_id == 87
    assert acessos[0].curso_id == 1
    assert acessos[0].ativo is True
    assert acessos[0].data_fim == data_fim

    assert concessoes[0].usuario_id == 87
    assert concessoes[0].curso_id == 1
    assert concessoes[0].data_fim == data_fim

    assert resultado["ok"] is True
    db.commit.assert_called_once()

def test_concessao_nao_reduz_prazo_de_compra_vigente():
    db = MagicMock()

    agora = datetime.utcnow()
    prazo_compra = agora + timedelta(days=180)
    prazo_concessao = agora + timedelta(days=30)

    acesso_existente = AcessoCurso(
        usuario_id=87,
        curso_id=1,
        ativo=True,
        data_inicio=agora - timedelta(days=10),
        data_fim=prazo_compra,
    )
    acesso_existente.id = 123

    db.query.return_value.filter.return_value.first.side_effect = [
        SimpleNamespace(id=87),
        SimpleNamespace(id=1),
        acesso_existente,
    ]

    payload = AcessoCursoCreate(
        usuario_id=87,
        curso_id=1,
        ativo=True,
        data_fim=prazo_concessao,
    )

    resultado = admin_criar_acesso(
        payload=payload,
        db=db,
        usuario=SimpleNamespace(is_admin=True),
    )

    # A concessão não pode encurtar o prazo da compra.
    assert acesso_existente.ativo is True
    assert acesso_existente.data_fim == prazo_compra

    # A concessão deve ficar registrada separadamente.
    db.add.assert_called_once()
    concessao = db.add.call_args.args[0]

    assert isinstance(concessao, ConcessaoAcessoAdmin)
    assert concessao.data_fim == prazo_concessao

    assert resultado["ok"] is True
    db.commit.assert_called_once()

def test_concessao_reativa_acesso_expirado():
    db = MagicMock()

    agora = datetime.utcnow()
    novo_prazo = agora + timedelta(days=30)

    acesso_existente = AcessoCurso(
        usuario_id=87,
        curso_id=1,
        ativo=True,
        data_inicio=agora - timedelta(days=180),
        data_fim=agora - timedelta(days=60),
    )
    acesso_existente.id = 123

    db.query.return_value.filter.return_value.first.side_effect = [
        SimpleNamespace(id=87),
        SimpleNamespace(id=1),
        acesso_existente,
    ]

    payload = AcessoCursoCreate(
        usuario_id=87,
        curso_id=1,
        ativo=True,
        data_fim=novo_prazo,
    )

    resultado = admin_criar_acesso(
        payload=payload,
        db=db,
        usuario=SimpleNamespace(is_admin=True),
    )

    # O acesso expirado deve ser reativado.
    assert acesso_existente.ativo is True
    assert acesso_existente.data_inicio >= agora
    assert acesso_existente.data_fim == novo_prazo

    # O histórico da concessão deve ser registrado.
    db.add.assert_called_once()
    concessao = db.add.call_args.args[0]

    assert isinstance(concessao, ConcessaoAcessoAdmin)
    assert concessao.data_fim == novo_prazo
    assert concessao.ativo is True

    assert resultado["ok"] is True
    db.commit.assert_called_once()

def test_concessao_reativa_acesso_inativo():
    db = MagicMock()

    agora = datetime.utcnow()
    novo_prazo = agora + timedelta(days=30)

    acesso_existente = AcessoCurso(
        usuario_id=87,
        curso_id=1,
        ativo=False,
        data_inicio=agora - timedelta(days=60),
        data_fim=agora + timedelta(days=60),
    )
    acesso_existente.id = 123

    db.query.return_value.filter.return_value.first.side_effect = [
        SimpleNamespace(id=87),
        SimpleNamespace(id=1),
        acesso_existente,
    ]

    payload = AcessoCursoCreate(
        usuario_id=87,
        curso_id=1,
        ativo=True,
        data_fim=novo_prazo,
    )

    resultado = admin_criar_acesso(
        payload=payload,
        db=db,
        usuario=SimpleNamespace(is_admin=True),
    )

    assert acesso_existente.ativo is True
    assert acesso_existente.data_inicio >= agora
    assert acesso_existente.data_fim == novo_prazo

    db.add.assert_called_once()
    concessao = db.add.call_args.args[0]

    assert isinstance(concessao, ConcessaoAcessoAdmin)
    assert concessao.ativo is True
    assert concessao.data_fim == novo_prazo

    assert resultado["ok"] is True
    db.commit.assert_called_once()

def test_concessao_preserva_acesso_sem_vencimento():
    db = MagicMock()

    agora = datetime.utcnow()
    prazo_concessao = agora + timedelta(days=30)

    acesso_existente = AcessoCurso(
        usuario_id=87,
        curso_id=1,
        ativo=True,
        data_inicio=agora - timedelta(days=60),
        data_fim=None,
    )
    acesso_existente.id = 123

    db.query.return_value.filter.return_value.first.side_effect = [
        SimpleNamespace(id=87),
        SimpleNamespace(id=1),
        acesso_existente,
    ]

    payload = AcessoCursoCreate(
        usuario_id=87,
        curso_id=1,
        ativo=True,
        data_fim=prazo_concessao,
    )

    resultado = admin_criar_acesso(
        payload=payload,
        db=db,
        usuario=SimpleNamespace(is_admin=True),
    )

    # A concessão não pode limitar o acesso preexistente.
    assert acesso_existente.ativo is True
    assert acesso_existente.data_fim is None

    # A nova concessão possui seu próprio prazo no histórico.
    db.add.assert_called_once()
    concessao = db.add.call_args.args[0]

    assert isinstance(concessao, ConcessaoAcessoAdmin)
    assert concessao.data_fim == prazo_concessao

    assert resultado["ok"] is True
    db.commit.assert_called_once()

def test_concessao_rejeita_data_vencida():
    db = MagicMock()

    db.query.return_value.filter.return_value.first.side_effect = [
        SimpleNamespace(id=87),
        SimpleNamespace(id=1),
    ]

    payload = AcessoCursoCreate(
        usuario_id=87,
        curso_id=1,
        ativo=True,
        data_fim=datetime.utcnow() - timedelta(days=1),
    )

    with pytest.raises(HTTPException) as erro:
        admin_criar_acesso(
            payload=payload,
            db=db,
            usuario=SimpleNamespace(is_admin=True),
        )

    assert erro.value.status_code == 400
    db.add.assert_not_called()
    db.commit.assert_not_called()

def test_concessao_converte_fuso_horario():
    db = MagicMock()

    db.query.return_value.filter.return_value.first.side_effect = [
        SimpleNamespace(id=87),
        SimpleNamespace(id=1),
        None,
    ]

    # 23h59 no horário de Brasília equivalem
    # a 02h59 do dia seguinte em UTC.
    data_enviada = datetime.fromisoformat(
        "2099-12-31T23:59:59-03:00"
    )

    data_esperada = datetime(
        2100, 1, 1, 2, 59, 59
    )

    payload = AcessoCursoCreate(
        usuario_id=87,
        curso_id=1,
        ativo=True,
        data_fim=data_enviada,
    )

    admin_criar_acesso(
        payload=payload,
        db=db,
        usuario=SimpleNamespace(is_admin=True),
    )

    registros = [
        chamada.args[0]
        for chamada in db.add.call_args_list
    ]

    assert len(registros) == 2

    for registro in registros:
        assert registro.data_fim == data_esperada
        assert registro.data_fim.tzinfo is None

    db.commit.assert_called_once()

def test_concessao_bloqueia_usuario_nao_admin():
    db = MagicMock()

    payload = AcessoCursoCreate(
        usuario_id=87,
        curso_id=1,
        ativo=True,
        data_fim=datetime.utcnow() + timedelta(days=30),
    )

    with pytest.raises(HTTPException) as erro:
        admin_criar_acesso(
            payload=payload,
            db=db,
            usuario=SimpleNamespace(is_admin=False),
        )

    assert erro.value.status_code == 403
    db.query.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()

def test_concessao_rejeita_aluno_inexistente():
    db = MagicMock()

    db.query.return_value.filter.return_value.first.return_value = None

    payload = AcessoCursoCreate(
        usuario_id=999999,
        curso_id=1,
        ativo=True,
        data_fim=datetime.utcnow() + timedelta(days=30),
    )

    with pytest.raises(HTTPException) as erro:
        admin_criar_acesso(
            payload=payload,
            db=db,
            usuario=SimpleNamespace(is_admin=True),
        )

    assert erro.value.status_code == 404
    assert erro.value.detail == "Usuário não encontrado"

    db.add.assert_not_called()
    db.commit.assert_not_called()

def test_concessao_rejeita_curso_inexistente():
    db = MagicMock()

    db.query.return_value.filter.return_value.first.side_effect = [
        SimpleNamespace(id=87),
        None,
    ]

    payload = AcessoCursoCreate(
        usuario_id=87,
        curso_id=999999,
        ativo=True,
        data_fim=datetime.utcnow() + timedelta(days=30),
    )

    with pytest.raises(HTTPException) as erro:
        admin_criar_acesso(
            payload=payload,
            db=db,
            usuario=SimpleNamespace(is_admin=True),
        )

    assert erro.value.status_code == 404
    assert erro.value.detail == "Curso não encontrado"

    db.add.assert_not_called()
    db.commit.assert_not_called()

def test_concessao_trata_conflito_no_banco():
    db = MagicMock()

    db.query.return_value.filter.return_value.first.side_effect = [
        SimpleNamespace(id=87),
        SimpleNamespace(id=1),
        None,
    ]

    db.commit.side_effect = IntegrityError(
        "INSERT",
        {},
        Exception("Conflito simulado"),
    )

    payload = AcessoCursoCreate(
        usuario_id=87,
        curso_id=1,
        ativo=True,
        data_fim=datetime.utcnow() + timedelta(days=30),
    )

    with pytest.raises(HTTPException) as erro:
        admin_criar_acesso(
            payload=payload,
            db=db,
            usuario=SimpleNamespace(is_admin=True),
        )

    assert erro.value.status_code == 409
    db.rollback.assert_called_once()