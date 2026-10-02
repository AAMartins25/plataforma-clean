from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import ContratacaoCurso


def registrar_contratacao(
    db: Session,
    pagamento,
    data_inicio: datetime,
    data_fim: datetime,
) -> ContratacaoCurso:
    if pagamento.tipo_compra == "RENOVACAO":
        contratacao = (
            db.query(ContratacaoCurso)
            .filter(
                ContratacaoCurso.id == pagamento.contratacao_id,
                ContratacaoCurso.usuario_id == pagamento.usuario_id,
                ContratacaoCurso.curso_id == pagamento.curso_id,
            )
            .with_for_update()
            .first()
        )

        if not contratacao:
            raise HTTPException(
                status_code=409,
                detail="Contratação da renovação não encontrada."
            )

        if contratacao.data_fim != pagamento.vencimento_original:
            raise HTTPException(
                status_code=409,
                detail="O contrato já teve seu vencimento alterado.",
            )

        if data_fim <= contratacao.data_fim:
            raise HTTPException(
                status_code=409,
                detail="O novo vencimento deve ser posterior ao atual.",
            )

        contratacao.data_fim = data_fim
    else:
        contratacao = ContratacaoCurso(
            usuario_id=pagamento.usuario_id,
            curso_id=pagamento.curso_id,
            data_inicio=data_inicio,
            data_fim=data_fim,
            origem="PAGAMENTO",
        )
        db.add(contratacao)

    db.flush()
    pagamento.contratacao_id = contratacao.id
    return contratacao


def obter_data_aprovacao_mp(dados_mp):
    """Converte a data efetiva de aprovação do Mercado Pago para UTC."""
    from datetime import timezone

    valor = dados_mp.get("date_approved")
    if not isinstance(valor, str) or not valor:
        raise HTTPException(
            status_code=502,
            detail="Mercado Pago não informou a data de aprovação.",
        )

    try:
        data = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=502,
            detail="Data de aprovação inválida no Mercado Pago.",
        )

    if data.tzinfo is None:
        raise HTTPException(
            status_code=502,
            detail="Data de aprovação sem fuso horário.",
        )

    return data.astimezone(timezone.utc).replace(tzinfo=None)


def validar_data_aprovacao_mp(pagamento, dados_mp):
    """Obtém a aprovação efetiva e valida o prazo da renovação."""
    data = obter_data_aprovacao_mp(dados_mp)

    if pagamento.tipo_compra == "RENOVACAO":
        if pagamento.vencimento_original is None:
            raise HTTPException(
                status_code=409,
                detail="Renovação sem vencimento original.",
            )
        if data > pagamento.vencimento_original:
            raise HTTPException(
                status_code=409,
                detail="Pagamento aprovado após o prazo da renovação.",
            )

    return data


def registrar_ocorrencia_financeira(db, pagamento, tipo, dados_mp):
    """Registra pagamento recebido sem conceder acesso ao curso."""
    if tipo not in ("COBRANCA_DUPLICADA", "APROVACAO_FORA_PRAZO"):
        raise ValueError("Tipo de ocorrência financeira inválido.")

    data = obter_data_aprovacao_mp(dados_mp)

    pagamento.status = "APPROVED"
    pagamento.aprovado_em = data
    pagamento.mp_payment_id = str(dados_mp["id"])
    pagamento.ocorrencia_financeira = tipo
    pagamento.ocorrencia_registrada_em = datetime.utcnow()
    pagamento.atualizado_em = datetime.utcnow()

    db.flush()
