from datetime import datetime, timedelta


def renovacao_disponivel(
    vencimento: datetime | None,
    agora: datetime | None = None,
) -> bool:
    if vencimento is None:
        return False

    if agora is None:
        agora = datetime.utcnow()

    prazo_restante = vencimento - agora

    return (
        timedelta(0) < prazo_restante
        <= timedelta(days=15)
    )
