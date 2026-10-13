"""Vínculo de novos checkouts; não altera estados ou concede acesso."""
import os
import re
import secrets
from fastapi import HTTPException


def nova_identidade():
    return secrets.token_urlsafe(32)


def recebedor_esperado():
    valor = os.getenv('MP_COLLECTOR_ID', '')
    if not re.fullmatch(r'[1-9][0-9]{0,63}', valor):
        raise HTTPException(503, 'Recebedor Mercado Pago não confirmado na configuração.')
    return valor


def referencia_compra(db, dados):
    from app.models import Pagamento
    ref = dados.get('external_reference')
    if not isinstance(ref, str):
        return ''
    if not ref.startswith('checkout:'):
        return ref  # Apenas o resolver pode aceitar vínculos legados.
    identidade = ref[len('checkout:'):]
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}', identidade):
        raise HTTPException(409, 'Identidade de checkout inválida.')
    raiz = db.query(Pagamento).filter(
        Pagamento.checkout_identidade == identidade,
        Pagamento.pagamento_origem_id.is_(None)).first()
    if raiz is None:
        raise HTTPException(409, 'Identidade de checkout não reconhecida.')
    return (f'user:{raiz.usuario_id}|curso:{raiz.curso_id}|'
            f'tempo:{raiz.tempo_acesso_id}|pagamento:{raiz.id}')


def validar_identidade(raiz, dados):
    identidade = raiz.checkout_identidade
    if identidade is None:
        if str(dados.get('external_reference', '')).startswith('checkout:'):
            raise HTTPException(409, 'Identidade incompatível com compra legada.')
        return False
    if dados.get('external_reference') != 'checkout:' + identidade:
        raise HTTPException(409, 'Identidade não corresponde ao checkout registrado.')
    collector = dados.get('collector_id')
    if type(collector) not in (int, str) or str(collector) != raiz.checkout_recebedor_id:
        raise HTTPException(409, 'Recebedor incompatível com checkout.')
    if raiz.checkout_recebedor_id != recebedor_esperado():
        raise HTTPException(409, 'Recebedor configurado difere do checkout registrado.')
    if dados.get('live_mode') is not True:
        raise HTTPException(409, 'Pagamento fora do ambiente de produção.')
    if (raiz.oportunidade_id is None or raiz.moeda != 'BRL' or raiz.provedor != 'MERCADO_PAGO'
            or type(raiz.checkout_meses) is not int or raiz.checkout_meses <= 0):
        raise HTTPException(409, 'Vínculo financeiro do checkout incompleto.')
    # Uma referência de intenção não comprova uma preferência desconhecida.
    if not raiz.mp_preference_id:
        raise HTTPException(409, 'Checkout sem preferência comprovada; verificar antes de processar.')
    return True


def meses_contratados(db, pagamento, tempo):
    from app.models import Pagamento
    raiz = db.get(Pagamento, pagamento.pagamento_origem_id) if pagamento.pagamento_origem_id else pagamento
    if raiz is not None and raiz.checkout_identidade is not None:
        if type(raiz.checkout_meses) is not int or raiz.checkout_meses <= 0:
            raise HTTPException(409, 'Período contratado sem snapshot válido.')
        return raiz.checkout_meses
    return tempo.meses
