import os
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.main import confirmar_reembolso_pix_manual
from app.models import (
    AcessoCurso,
    ConcessaoAcessoAdmin,
    Curso,
    DemonstracaoCurso,
    Pagamento,
    PeriodoAcessoPagamento,
    ReembolsoFinanceiro,
    Usuario,
)


DATABASE_URL_LOCAL = os.environ["DATABASE_URL"]


def test_reembolso_com_compra_antiga_exige_conferencia():
    engine = create_engine(DATABASE_URL_LOCAL)

    with engine.connect() as conexao:
        transacao = conexao.begin()

        try:
            with Session(
                bind=conexao,
                join_transaction_mode="create_savepoint",
            ) as db:
                agora = datetime.utcnow()

                # Pré-condição: compra antiga aprovada,
                # ainda sem histórico individual de acesso.
                compra_antiga = db.get(Pagamento, 1)

                assert compra_antiga is not None
                assert compra_antiga.usuario_id == 2
                assert compra_antiga.curso_id == 1
                assert compra_antiga.aprovado_em is not None

                periodo_antigo = db.scalar(
                    select(PeriodoAcessoPagamento).where(
                        PeriodoAcessoPagamento.pagamento_id == 1
                    )
                )
                assert periodo_antigo is None

                # Criamos uma segunda compra fictícia,
                # que será o objeto do reembolso.
                pagamento = Pagamento(
                    usuario_id=2,
                    curso_id=1,
                    status="REFUND_IN_PROCESS",
                    valor_cents=4990,
                    aprovado_em=agora,
                )
                db.add(pagamento)
                db.flush()

                db.add(
                    PeriodoAcessoPagamento(
                        pagamento_id=pagamento.id,
                        usuario_id=2,
                        curso_id=1,
                        data_inicio=agora,
                        data_fim=agora + timedelta(days=120),
                    )
                )

                reembolso = ReembolsoFinanceiro(
                    pagamento_id=pagamento.id,
                    metodo="PIX_MANUAL",
                    valor_cents=4990,
                    status="PENDENTE",
                )
                db.add(reembolso)
                db.flush()

                acesso_antes = db.scalar(
                    select(AcessoCurso).where(
                        AcessoCurso.usuario_id == 2,
                        AcessoCurso.curso_id == 1,
                    )
                )

                estado_antes = (
                    (acesso_antes.ativo, acesso_antes.data_fim)
                    if acesso_antes is not None
                    else None
                )

                resultado = confirmar_reembolso_pix_manual(
                    reembolso_id=reembolso.id,
                    confirmacao_extrato=True,
                    db=db,
                    admin=SimpleNamespace(is_admin=True),
                )

                db.refresh(pagamento)
                db.refresh(reembolso)

                assert resultado["ok"] is True
                assert pagamento.status == "REFUNDED"
                assert reembolso.status == "CONFIRMADO"

                assert resultado["situacao_acesso"] == "CONFERENCIA_NECESSARIA"
                assert 1 in resultado["pagamentos_sem_historico"]
                assert "conferência" in resultado["message"]

                acesso_depois = db.scalar(
                    select(AcessoCurso).where(
                        AcessoCurso.usuario_id == 2,
                        AcessoCurso.curso_id == 1,
                    )
                )

                estado_depois = (
                    (acesso_depois.ativo, acesso_depois.data_fim)
                    if acesso_depois is not None
                    else None
                )

                # A compra antiga sem histórico impede
                # a alteração automática do acesso.
                assert estado_depois == estado_antes

        finally:
            transacao.rollback()
            engine.dispose()

def test_reembolso_sem_outros_direitos_desativa_acesso():
    engine = create_engine(DATABASE_URL_LOCAL)

    with engine.connect() as conexao:
        transacao = conexao.begin()

        try:
            with Session(
                bind=conexao,
                join_transaction_mode="create_savepoint",
            ) as db:
                agora = datetime.utcnow()
                identificador = uuid4().hex

                aluno = Usuario(
                    nome="Aluno Teste Reembolso",
                    email=f"teste_{identificador}@example.com",
                    senha_hash="hash_ficticio",
                    cpf=f"{uuid4().int % 10**11:011d}",
                    telefone="11999999999",
                    ativo=True,
                    is_admin=False,
                )

                curso = Curso(
                    nome=f"Curso Teste Reembolso {identificador}",
                    ativo=True,
                )

                db.add_all([aluno, curso])
                db.flush()

                pagamento = Pagamento(
                    usuario_id=aluno.id,
                    curso_id=curso.id,
                    status="REFUND_IN_PROCESS",
                    valor_cents=4990,
                    aprovado_em=agora,
                )
                db.add(pagamento)
                db.flush()

                db.add(
                    PeriodoAcessoPagamento(
                        pagamento_id=pagamento.id,
                        usuario_id=aluno.id,
                        curso_id=curso.id,
                        data_inicio=agora,
                        data_fim=agora + timedelta(days=120),
                    )
                )

                acesso = AcessoCurso(
                    usuario_id=aluno.id,
                    curso_id=curso.id,
                    ativo=True,
                    data_inicio=agora,
                    data_fim=agora + timedelta(days=120),
                )
                db.add(acesso)

                reembolso = ReembolsoFinanceiro(
                    pagamento_id=pagamento.id,
                    metodo="PIX_MANUAL",
                    valor_cents=4990,
                    status="PENDENTE",
                )
                db.add(reembolso)
                db.flush()

                resultado = confirmar_reembolso_pix_manual(
                    reembolso_id=reembolso.id,
                    confirmacao_extrato=True,
                    db=db,
                    admin=SimpleNamespace(is_admin=True),
                )

                db.refresh(aluno)
                db.refresh(acesso)
                db.refresh(pagamento)
                db.refresh(reembolso)

                assert resultado["ok"] is True
                assert pagamento.status == "REFUNDED"
                assert reembolso.status == "CONFIRMADO"

                assert resultado["situacao_acesso"] == "SEM_DIREITOS_VIGENTES"
                assert resultado["pagamentos_sem_historico"] == []
                assert "desativado" in resultado["message"]

                # O acesso ao curso é encerrado.
                assert acesso.ativo is False

                # A conta do aluno permanece ativa.
                assert aluno.ativo is True

        finally:
            transacao.rollback()
            engine.dispose()

def test_reembolso_preserva_outra_compra_vigente():
    engine = create_engine(DATABASE_URL_LOCAL)

    with engine.connect() as conexao:
        transacao = conexao.begin()

        try:
            with Session(
                bind=conexao,
                join_transaction_mode="create_savepoint",
            ) as db:
                agora = datetime.utcnow()
                identificador = uuid4().hex

                aluno = Usuario(
                    nome="Aluno Teste Duas Compras",
                    email=f"duas_compras_{identificador}@example.com",
                    senha_hash="hash_ficticio",
                    cpf=f"{uuid4().int % 10**11:011d}",
                    telefone="11999999999",
                    ativo=True,
                    is_admin=False,
                )

                curso = Curso(
                    nome=f"Curso Teste Duas Compras {identificador}",
                    ativo=True,
                )

                db.add_all([aluno, curso])
                db.flush()

                # Compra que será reembolsada.
                pagamento_reembolsado = Pagamento(
                    usuario_id=aluno.id,
                    curso_id=curso.id,
                    status="REFUND_IN_PROCESS",
                    valor_cents=4990,
                    aprovado_em=agora,
                )

                # Outra compra aprovada do mesmo curso.
                outra_compra = Pagamento(
                    usuario_id=aluno.id,
                    curso_id=curso.id,
                    status="APPROVED",
                    valor_cents=4990,
                    aprovado_em=agora,
                )

                db.add_all([
                    pagamento_reembolsado,
                    outra_compra,
                ])
                db.flush()

                prazo_reembolsado = agora + timedelta(days=120)
                prazo_outra_compra = agora + timedelta(days=60)

                db.add_all([
                    PeriodoAcessoPagamento(
                        pagamento_id=pagamento_reembolsado.id,
                        usuario_id=aluno.id,
                        curso_id=curso.id,
                        data_inicio=agora,
                        data_fim=prazo_reembolsado,
                    ),
                    PeriodoAcessoPagamento(
                        pagamento_id=outra_compra.id,
                        usuario_id=aluno.id,
                        curso_id=curso.id,
                        data_inicio=agora,
                        data_fim=prazo_outra_compra,
                    ),
                ])

                acesso = AcessoCurso(
                    usuario_id=aluno.id,
                    curso_id=curso.id,
                    ativo=True,
                    data_inicio=agora,
                    data_fim=prazo_reembolsado,
                )
                db.add(acesso)

                reembolso = ReembolsoFinanceiro(
                    pagamento_id=pagamento_reembolsado.id,
                    metodo="PIX_MANUAL",
                    valor_cents=4990,
                    status="PENDENTE",
                )
                db.add(reembolso)
                db.flush()

                resultado = confirmar_reembolso_pix_manual(
                    reembolso_id=reembolso.id,
                    confirmacao_extrato=True,
                    db=db,
                    admin=SimpleNamespace(is_admin=True),
                )

                db.refresh(aluno)
                db.refresh(acesso)
                db.refresh(pagamento_reembolsado)
                db.refresh(outra_compra)

                assert pagamento_reembolsado.status == "REFUNDED"
                assert outra_compra.status == "APPROVED"

                # O acesso permanece ativo, mas seu prazo
                # passa a ser o da outra compra.
                assert acesso.ativo is True
                assert acesso.data_fim == prazo_outra_compra

                assert aluno.ativo is True
                assert resultado["situacao_acesso"] == "ACESSO_PRESERVADO"
                assert "preservado" in resultado["message"]

        finally:
            transacao.rollback()
            engine.dispose()

def test_reembolso_preserva_concessao_administrativa():
    engine = create_engine(DATABASE_URL_LOCAL)

    with engine.connect() as conexao:
        transacao = conexao.begin()

        try:
            with Session(
                bind=conexao,
                join_transaction_mode="create_savepoint",
            ) as db:
                agora = datetime.utcnow()
                identificador = uuid4().hex

                aluno = Usuario(
                    nome="Aluno Teste Concessao",
                    email=f"concessao_{identificador}@example.com",
                    senha_hash="hash_ficticio",
                    cpf=f"{uuid4().int % 10**11:011d}",
                    telefone="11999999999",
                    ativo=True,
                    is_admin=False,
                )

                curso = Curso(
                    nome=f"Curso Teste Concessao {identificador}",
                    ativo=True,
                )

                db.add_all([aluno, curso])
                db.flush()

                pagamento = Pagamento(
                    usuario_id=aluno.id,
                    curso_id=curso.id,
                    status="REFUND_IN_PROCESS",
                    valor_cents=4990,
                    aprovado_em=agora,
                )
                db.add(pagamento)
                db.flush()

                prazo_compra = agora + timedelta(days=120)
                prazo_concessao = agora + timedelta(days=60)

                db.add(
                    PeriodoAcessoPagamento(
                        pagamento_id=pagamento.id,
                        usuario_id=aluno.id,
                        curso_id=curso.id,
                        data_inicio=agora,
                        data_fim=prazo_compra,
                    )
                )

                db.add(
                    ConcessaoAcessoAdmin(
                        usuario_id=aluno.id,
                        curso_id=curso.id,
                        data_inicio=agora - timedelta(days=1),
                        data_fim=prazo_concessao,
                        ativo=True,
                    )
                )

                acesso = AcessoCurso(
                    usuario_id=aluno.id,
                    curso_id=curso.id,
                    ativo=True,
                    data_inicio=agora,
                    data_fim=prazo_compra,
                )
                db.add(acesso)

                reembolso = ReembolsoFinanceiro(
                    pagamento_id=pagamento.id,
                    metodo="PIX_MANUAL",
                    valor_cents=4990,
                    status="PENDENTE",
                )
                db.add(reembolso)
                db.flush()

                resultado = confirmar_reembolso_pix_manual(
                    reembolso_id=reembolso.id,
                    confirmacao_extrato=True,
                    db=db,
                    admin=SimpleNamespace(is_admin=True),
                )

                db.refresh(aluno)
                db.refresh(acesso)
                db.refresh(pagamento)
                db.refresh(reembolso)

                assert pagamento.status == "REFUNDED"
                assert reembolso.status == "CONFIRMADO"

                # A concessão administrativa mantém o acesso.
                assert acesso.ativo is True
                assert acesso.data_fim == prazo_concessao

                # A conta do aluno continua ativa.
                assert aluno.ativo is True

                # A resposta informa a preservação do acesso.
                assert resultado["situacao_acesso"] == "ACESSO_PRESERVADO"
                assert "preservado" in resultado["message"]

        finally:
            transacao.rollback()
            engine.dispose()

def test_reembolso_preserva_concessao_sem_prazo():
    engine = create_engine(DATABASE_URL_LOCAL)

    with engine.connect() as conexao:
        transacao = conexao.begin()

        try:
            with Session(
                bind=conexao,
                join_transaction_mode="create_savepoint",
            ) as db:
                agora = datetime.utcnow()
                identificador = uuid4().hex

                aluno = Usuario(
                    nome="Aluno Teste Concessao",
                    email=f"concessao_{identificador}@example.com",
                    senha_hash="hash_ficticio",
                    cpf=f"{uuid4().int % 10**11:011d}",
                    telefone="11999999999",
                    ativo=True,
                    is_admin=False,
                )

                curso = Curso(
                    nome=f"Curso Teste Concessao {identificador}",
                    ativo=True,
                )

                db.add_all([aluno, curso])
                db.flush()

                pagamento = Pagamento(
                    usuario_id=aluno.id,
                    curso_id=curso.id,
                    status="REFUND_IN_PROCESS",
                    valor_cents=4990,
                    aprovado_em=agora,
                )
                db.add(pagamento)
                db.flush()

                prazo_compra = agora + timedelta(days=120)
                prazo_concessao = None

                db.add(
                    PeriodoAcessoPagamento(
                        pagamento_id=pagamento.id,
                        usuario_id=aluno.id,
                        curso_id=curso.id,
                        data_inicio=agora,
                        data_fim=prazo_compra,
                    )
                )

                db.add(
                    ConcessaoAcessoAdmin(
                        usuario_id=aluno.id,
                        curso_id=curso.id,
                        data_inicio=agora - timedelta(days=1),
                        data_fim=prazo_concessao,
                        ativo=True,
                    )
                )

                acesso = AcessoCurso(
                    usuario_id=aluno.id,
                    curso_id=curso.id,
                    ativo=True,
                    data_inicio=agora,
                    data_fim=prazo_compra,
                )
                db.add(acesso)

                reembolso = ReembolsoFinanceiro(
                    pagamento_id=pagamento.id,
                    metodo="PIX_MANUAL",
                    valor_cents=4990,
                    status="PENDENTE",
                )
                db.add(reembolso)
                db.flush()

                resultado = confirmar_reembolso_pix_manual(
                    reembolso_id=reembolso.id,
                    confirmacao_extrato=True,
                    db=db,
                    admin=SimpleNamespace(is_admin=True),
                )

                db.refresh(aluno)
                db.refresh(acesso)
                db.refresh(pagamento)
                db.refresh(reembolso)

                assert pagamento.status == "REFUNDED"
                assert reembolso.status == "CONFIRMADO"

                # A concessão administrativa mantém o acesso.
                assert acesso.ativo is True
                assert acesso.data_fim is None

                # A conta do aluno continua ativa.
                assert aluno.ativo is True

                # A resposta informa a preservação do acesso.
                assert resultado["situacao_acesso"] == "ACESSO_PRESERVADO"
                assert "preservado" in resultado["message"]

        finally:
            transacao.rollback()
            engine.dispose()

def test_reembolso_preserva_demonstracao_vigente():
    engine = create_engine(DATABASE_URL_LOCAL)

    with engine.connect() as conexao:
        transacao = conexao.begin()

        try:
            with Session(
                bind=conexao,
                join_transaction_mode="create_savepoint",
            ) as db:
                agora = datetime.utcnow()
                identificador = uuid4().hex

                aluno = Usuario(
                    nome="Aluno Teste Demonstracao",
                    email=f"demo_{identificador}@example.com",
                    senha_hash="hash_ficticio",
                    cpf=f"{uuid4().int % 10**11:011d}",
                    telefone="11999999999",
                    ativo=True,
                    is_admin=False,
                )

                curso = Curso(
                    nome=f"Curso Teste Demonstracao {identificador}",
                    ativo=True,
                )

                db.add_all([aluno, curso])
                db.flush()

                pagamento = Pagamento(
                    usuario_id=aluno.id,
                    curso_id=curso.id,
                    status="REFUND_IN_PROCESS",
                    valor_cents=4990,
                    aprovado_em=agora,
                )
                db.add(pagamento)
                db.flush()

                prazo_compra = agora + timedelta(days=120)
                prazo_demonstracao = agora + timedelta(days=7)

                db.add(
                    PeriodoAcessoPagamento(
                        pagamento_id=pagamento.id,
                        usuario_id=aluno.id,
                        curso_id=curso.id,
                        data_inicio=agora,
                        data_fim=prazo_compra,
                    )
                )

                db.add(
                    DemonstracaoCurso(
                        usuario_id=aluno.id,
                        curso_id=curso.id,
                        data_inicio=agora - timedelta(days=1),
                        data_fim=prazo_demonstracao,
                        liberado_novamente_em=agora + timedelta(days=30),
                        ativo=True,
                    )
                )

                acesso = AcessoCurso(
                    usuario_id=aluno.id,
                    curso_id=curso.id,
                    ativo=True,
                    data_inicio=agora,
                    data_fim=prazo_compra,
                )
                db.add(acesso)

                reembolso = ReembolsoFinanceiro(
                    pagamento_id=pagamento.id,
                    metodo="PIX_MANUAL",
                    valor_cents=4990,
                    status="PENDENTE",
                )
                db.add(reembolso)
                db.flush()

                resultado = confirmar_reembolso_pix_manual(
                    reembolso_id=reembolso.id,
                    confirmacao_extrato=True,
                    db=db,
                    admin=SimpleNamespace(is_admin=True),
                )

                db.refresh(aluno)
                db.refresh(acesso)
                db.refresh(pagamento)
                db.refresh(reembolso)

                assert pagamento.status == "REFUNDED"
                assert reembolso.status == "CONFIRMADO"

                # A demonstração vigente preserva o acesso.
                assert acesso.ativo is True
                assert acesso.data_fim == prazo_demonstracao

                # A conta do aluno permanece ativa.
                assert aluno.ativo is True

                assert resultado["situacao_acesso"] == "ACESSO_PRESERVADO"
                assert "preservado" in resultado["message"]

        finally:
            transacao.rollback()
            engine.dispose()

def test_falha_recalculo_nao_confirma_reembolso():
    engine = create_engine(DATABASE_URL_LOCAL)

    with engine.connect() as conexao:
        transacao = conexao.begin()

        try:
            with Session(
                bind=conexao,
                join_transaction_mode="create_savepoint",
            ) as db:
                agora = datetime.utcnow()
                identificador = uuid4().hex

                aluno = Usuario(
                    nome="Aluno Teste Falha",
                    email=f"falha_{identificador}@example.com",
                    senha_hash="hash_ficticio",
                    cpf=f"{uuid4().int % 10**11:011d}",
                    telefone="11999999999",
                    ativo=True,
                )

                curso = Curso(
                    nome=f"Curso Teste Falha {identificador}",
                    ativo=True,
                )

                db.add_all([aluno, curso])
                db.flush()

                pagamento = Pagamento(
                    usuario_id=aluno.id,
                    curso_id=curso.id,
                    status="REFUND_IN_PROCESS",
                    valor_cents=4990,
                    aprovado_em=agora,
                )
                db.add(pagamento)
                db.flush()

                reembolso = ReembolsoFinanceiro(
                    pagamento_id=pagamento.id,
                    metodo="PIX_MANUAL",
                    valor_cents=4990,
                    status="PENDENTE",
                )
                db.add(reembolso)
                db.commit()

                pagamento_id = pagamento.id
                reembolso_id = reembolso.id

                with patch(
                    "app.main.recalcular_acesso_apos_reembolso",
                    side_effect=RuntimeError("Falha simulada"),
                ):
                    try:
                        confirmar_reembolso_pix_manual(
                            reembolso_id=reembolso_id,
                            confirmacao_extrato=True,
                            db=db,
                            admin=SimpleNamespace(is_admin=True),
                        )
                    except RuntimeError:
                        assert not db.in_transaction()
                    else:
                        raise AssertionError(
                            "A falha simulada deveria interromper a confirmação"
                        )

                db.expire_all()

                assert db.get(Pagamento, pagamento_id).status == (
                    "REFUND_IN_PROCESS"
                )
                assert db.get(ReembolsoFinanceiro, reembolso_id).status == (
                    "PENDENTE"
                )

        finally:
            transacao.rollback()
            engine.dispose()