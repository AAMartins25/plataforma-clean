from sqlalchemy.orm import Session
from app.models import OportunidadeCompra


def obter_oportunidade(
    db: Session,
    usuario_id: int,
    curso_id: int,
    tipo_compra: str,
    contratacao_id=None,
    demonstracao_id=None,
    vencimento_original=None,
):
    consulta = db.query(OportunidadeCompra).filter(
        OportunidadeCompra.usuario_id == usuario_id,
        OportunidadeCompra.curso_id == curso_id,
        OportunidadeCompra.tipo_compra == tipo_compra,
    )

    if tipo_compra == "RENOVACAO":
        consulta = consulta.filter(
            OportunidadeCompra.contratacao_id == contratacao_id,
            OportunidadeCompra.vencimento_original == vencimento_original,
        )
    else:
        consulta = consulta.filter(
            OportunidadeCompra.demonstracao_id == demonstracao_id,
        )
        if demonstracao_id is None:
            consulta = consulta.filter(
                OportunidadeCompra.concluida_em.is_(None)
            )

    oportunidade = consulta.order_by(
        OportunidadeCompra.id.desc()
    ).first()

    if oportunidade is None:
        oportunidade = OportunidadeCompra(
            usuario_id=usuario_id,
            curso_id=curso_id,
            tipo_compra=tipo_compra,
            contratacao_id=contratacao_id,
            demonstracao_id=demonstracao_id,
            vencimento_original=vencimento_original,
        )
        db.add(oportunidade)
        db.flush()

    return oportunidade


def bloquear_oportunidade_pagamento(db: Session, pagamento):
    """Bloqueia a oportunidade durante o processamento do pagamento."""
    if pagamento.oportunidade_id is None:
        return None

    oportunidade = (
        db.query(OportunidadeCompra)
        .filter(
            OportunidadeCompra.id == pagamento.oportunidade_id,
            OportunidadeCompra.usuario_id == pagamento.usuario_id,
            OportunidadeCompra.curso_id == pagamento.curso_id,
        )
        .with_for_update()
        .first()
    )

    if oportunidade is None:
        raise ValueError("Oportunidade do pagamento não encontrada.")

    return oportunidade


def concluir_oportunidade(db: Session, oportunidade):
    """Encerra a oportunidade na mesma transação da contratação."""
    if oportunidade is None:
        return

    if oportunidade.concluida_em is not None:
        raise ValueError("Esta oportunidade já foi concluída.")

    from datetime import datetime

    oportunidade.concluida_em = datetime.utcnow()
    db.flush()
