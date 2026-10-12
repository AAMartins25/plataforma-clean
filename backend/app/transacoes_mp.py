from app.financeiro_transacional import protegido, timeout_financeiro
"""Identidade financeira de tentativas de uma preferência; não concede acesso."""
from decimal import Decimal, InvalidOperation

import requests
from fastapi import HTTPException
from .models import Pagamento, Usuario
from .oportunidades import bloquear_oportunidade_pagamento


def consultar_pagamento(payment_id, headers):
    try:
        return requests.get(
            f"https://api.mercadopago.com/v1/payments/{payment_id}",
            headers=headers, timeout=timeout_financeiro(),
        )
    except requests.RequestException:
        raise HTTPException(502, "Não foi possível consultar o pagamento no Mercado Pago.")


def atualizar_estado_mp(pagamento, dados):
    status = str(dados.get("status") or "").strip().upper()
    if status not in {"APPROVED", "PENDING", "IN_PROCESS", "AUTHORIZED", "IN_MEDIATION",
                      "REJECTED", "CANCELLED", "REFUNDED", "CHARGED_BACK"}:
        raise HTTPException(502, "Estado financeiro retornado pelo Mercado Pago inválido.")
    # Uma consulta iniciada antes da devolução não pode regredir um estado terminal.
    if pagamento.mp_status in {"REFUNDED", "CHARGED_BACK"} and status not in {"REFUNDED", "CHARGED_BACK"}:
        return
    pagamento.mp_status = status


@protegido
def resolver_transacao(db, payment_id, dados, headers, usuario_id=None, curso_id=None):
    """Chamador confirma/commita tudo junto; exceções deixam a transação sem commit.

    Ordem de locks: usuário, raiz, oportunidade, transação. Uma transação nova
    só é inserida depois da consulta autenticada da merchant order.
    """
    pid = str(payment_id)
    if str(dados.get("id")) != pid:
        raise HTTPException(409, "Identificador retornado pelo Mercado Pago incompatível.")
    referencias = {}
    for parte in str(dados.get("external_reference") or "").split("|"):
        if ":" in parte:
            chave, valor = parte.split(":", 1)
            if chave in referencias:
                raise HTTPException(400, "Referência do pagamento ambígua.")
            referencias[chave] = valor
    try:
        uid, cid, tid = (int(referencias[k]) for k in ("user", "curso", "tempo"))
        raiz_id = int(referencias["pagamento"]) if "pagamento" in referencias else None
    except (KeyError, ValueError):
        raise HTTPException(400, "Referência do pagamento ausente ou inválida.")
    if (usuario_id is not None and uid != usuario_id) or (curso_id is not None and cid != int(curso_id)):
        raise HTTPException(403, "O pagamento não corresponde ao usuário e curso informados.")
    if db.query(Usuario).filter(Usuario.id == uid).with_for_update().first() is None:
        raise HTTPException(404, "Usuário do pagamento não encontrado.")
    existente = db.query(Pagamento).filter(Pagamento.mp_payment_id == pid).first()
    if raiz_id is None:
        # Histórico: nunca inferir novas associações sem referência da raiz.
        if existente is None:
            raise HTTPException(404, "Pagamento histórico não identificado.")
        raiz_id = existente.pagamento_origem_id or existente.id
    raiz = db.query(Pagamento).filter(Pagamento.id == raiz_id).with_for_update().populate_existing().first()
    if raiz is None:
        raise HTTPException(404, "Pagamento não encontrado.")
    if raiz.pagamento_origem_id is not None:
        raise HTTPException(409, "Referência deve identificar o pagamento original.")
    if (uid, cid, tid) != (raiz.usuario_id, raiz.curso_id, raiz.tempo_acesso_id):
        raise HTTPException(409, "Pagamento não corresponde à compra registrada.")
    try:
        valor = Decimal(str(dados["transaction_amount"])) * 100
        if not valor.is_finite() or valor != valor.to_integral_value():
            raise ValueError()
    except (KeyError, InvalidOperation, ValueError, TypeError):
        raise HTTPException(400, "Valor do pagamento ausente ou inválido no Mercado Pago.")
    if dados.get("currency_id") != "BRL" or int(valor) != raiz.valor_cents:
        raise HTTPException(409, "Valor ou moeda não corresponde à compra registrada.")
    try:
        oportunidade = bloquear_oportunidade_pagamento(db, raiz)
    except ValueError:
        raise HTTPException(409, "Oportunidade comercial incompatível com o pagamento.")
    if oportunidade is not None and (
        oportunidade.tipo_compra != raiz.tipo_compra
        or (raiz.tipo_compra == "RENOVACAO" and (
            oportunidade.contratacao_id != raiz.contratacao_id
            or oportunidade.vencimento_original != raiz.vencimento_original
        ))
    ):
        raise HTTPException(409, "Dados comerciais da oportunidade incompatíveis.")
    if existente is not None:
        if (existente.pagamento_origem_id or existente.id) != raiz.id:
            raise HTTPException(409, "Transação já vinculada a outra compra.")
        existente = db.query(Pagamento).filter(Pagamento.id == existente.id).with_for_update().populate_existing().one()
        campos = ("usuario_id", "curso_id", "tempo_acesso_id", "oportunidade_id",
                  "valor_cents", "mp_preference_id", "tipo_compra", "codigo_cupom",
                  "vendedor_id", "qr_code_id", "vencimento_original", "moeda", "provedor")
        if any(getattr(existente, k) != getattr(raiz, k) for k in campos):
            raise HTTPException(409, "Dados comerciais da transação incompatíveis com a origem.")
        atualizar_estado_mp(existente, dados)
        return existente
    if raiz.mp_payment_id is None:
        if raiz.status == 'CHECKOUT_INDEFINIDO' and raiz.mp_preference_id is None:
            # Identidade local persistida antes de envio externo incerto.
            raiz.mp_preference_id = verificar_ordem_mp(dados, pid, headers)
        raiz.mp_payment_id = pid
        atualizar_estado_mp(raiz, dados)
        return raiz
    if oportunidade is None or not raiz.mp_preference_id or "pagamento" not in referencias:
        raise HTTPException(409, "Não foi possível comprovar outra tentativa desta compra.")
    verificar_ordem_mp(dados, pid, headers, raiz.mp_preference_id)
    campos = ("usuario_id", "curso_id", "oportunidade_id", "tempo_acesso_id",
              "valor_cents", "provedor", "moeda", "mp_preference_id", "tipo_compra",
              "vencimento_original", "codigo_cupom", "vendedor_id", "qr_code_id")
    tentativa = Pagamento(**{k: getattr(raiz, k) for k in campos},
        pagamento_origem_id=raiz.id, mp_payment_id=pid, status="PENDENTE",
        contratacao_id=raiz.contratacao_id if raiz.tipo_compra == "RENOVACAO" else None)
    atualizar_estado_mp(tentativa, dados)
    db.add(tentativa)
    db.flush()
    return tentativa


def verificar_ordem_mp(dados, pid, headers, preferencia_id=None):
    order_id = (dados.get("order") or {}).get("id")
    if not order_id:
        raise HTTPException(409, "Mercado Pago não informou a ordem da nova tentativa.")
    try:
        resposta = requests.get(
            f"https://api.mercadopago.com/merchant_orders/{order_id}",
            headers=headers, timeout=timeout_financeiro(),
        )
    except requests.RequestException:
        raise HTTPException(502, "Não foi possível verificar a preferência da nova tentativa.")
    if resposta.status_code >= 400:
        raise HTTPException(502, "Não foi possível verificar a preferência da nova tentativa.")
    ordem = resposta.json()
    if (str(ordem.get("id")) != str(order_id)
            or not ordem.get("preference_id")
            or (preferencia_id is not None and str(ordem.get("preference_id")) != preferencia_id)
            or ordem.get("external_reference") != dados.get("external_reference")
            or pid not in {str(p.get("id")) for p in ordem.get("payments", [])}):
        raise HTTPException(409, "Nova tentativa não corresponde à preferência original.")
    return str(ordem["preference_id"])
