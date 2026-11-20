"""Barreira opcional para uma versão de recuperação já compatível com 028–031."""
import os
import re

from starlette.middleware import Middleware
from starlette.responses import JSONResponse


def bloqueada(method, path):
    path = path.rstrip('/') or '/'
    return (
        (method == 'POST' and path in {
            '/admin/importacoes/cursos', '/admin/importacoes/cursos/validar',
            '/checkout/mercadopago', '/admin/acessos',
        })
        or (method == 'PUT' and bool(re.fullmatch(
            r'/admin/cursos/[^/]+/(?:publicar|config-publica)', path)))
        or (method == 'POST' and bool(re.fullmatch(r'/admin/cursos/[^/]+/duplicar', path)))
    )


class BarreiraRecuperacao:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http' and bloqueada(scope['method'], scope['path']):
            response = JSONResponse(
                {'detail': 'Operação temporariamente indisponível durante a recuperação.'},
                status_code=503, headers={'Retry-After': '60', 'Cache-Control': 'no-store'})
            return await response(scope, receive, send)
        return await self.app(scope, receive, send)


def instalar(app):
    valor = os.getenv('RESUMAO_RECUPERACAO_IMPORTACAO', '0')
    if valor not in ('0', '1'):
        raise RuntimeError('RESUMAO_RECUPERACAO_IMPORTACAO deve ser 0 ou 1')
    if valor == '1':
        app.user_middleware.append(Middleware(BarreiraRecuperacao))
