"""Logs com campos fixos, sem payloads ou texto de exceções."""
import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic

logger = logging.getLogger('resumao.financeiro')
notificacao = ContextVar('diagnostico_notificacao', default=None)
ultima = ContextVar('diagnostico_ultima_falha', default=None)

@contextmanager
def contexto(ident):
    a = notificacao.set(ident)
    b = ultima.set(None)
    try:
        yield
    finally:
        ultima.reset(b)
        notificacao.reset(a)

def falha(etapa, categoria, inicio=None, http=None):
    dados = {'etapa': etapa, 'categoria': categoria}
    if inicio is not None:
        dados['duracao_ms'] = round(max(0, monotonic()-inicio)*1000, 2)
    if isinstance(http, int) and not isinstance(http, bool):
        dados['status_http'] = http
    ident = notificacao.get()
    if isinstance(ident, int) and not isinstance(ident, bool):
        dados['notificacao_id'] = ident
    if isinstance(ident, int) and not isinstance(ident, bool):
        ultima.set(dados)
    emitir(dados)

def emitir(dados):
    try:
        logger.warning('financeiro %s', json.dumps(dados, sort_keys=True))
    except Exception:
        pass  # Instrumentação não pode modificar o resultado financeiro.

def resumo():
    emitir(ultima.get() or {'etapa': 'processamento_notificacao',
        'categoria': 'falha_nao_classificada', 'notificacao_id': notificacao.get()})

def transporte(exc):
    import requests
    if isinstance(exc, requests.exceptions.SSLError): return 'tls'
    if isinstance(exc, requests.exceptions.Timeout): return 'timeout'
    if isinstance(exc, requests.exceptions.ConnectionError): return 'conexao'
    return 'transporte'
