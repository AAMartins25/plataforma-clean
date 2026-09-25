import ast
import hashlib
import hmac
from pathlib import Path
from types import SimpleNamespace

# Extrai a função real do main.py sem iniciar o backend.
codigo = Path(__file__).with_name("app").joinpath("main.py").read_text(
    encoding="utf-8"
)
arvore = ast.parse(codigo)

funcao = next(
    no for no in arvore.body
    if isinstance(no, ast.FunctionDef)
    and no.name == "validar_assinatura_mercadopago"
)

ambiente = {
    "Request": object,
    "MP_WEBHOOK_SECRET": "chave-ficticia-de-teste",
    "hmac": hmac,
    "hashlib": hashlib,
}

exec(compile(ast.Module(body=[funcao], type_ignores=[]), "teste", "exec"), ambiente)

validar = ambiente["validar_assinatura_mercadopago"]

payment_id = "123456"
request_id = "teste-001"
ts = "1234567890"

mensagem = f"id:{payment_id};request-id:{request_id};ts:{ts};"
assinatura = hmac.new(
    ambiente["MP_WEBHOOK_SECRET"].encode(),
    mensagem.encode(),
    hashlib.sha256
).hexdigest()

request = SimpleNamespace(headers={
    "x-request-id": request_id,
    "x-signature": f"ts={ts},v1={assinatura}",
})

def test_assinatura_valida():
    request.headers["x-signature"] = f"ts={ts},v1={assinatura}"
    assert validar(request, payment_id) is True


def test_assinatura_invalida():
    request.headers["x-signature"] = f"ts={ts},v1={'0' * 64}"
    assert validar(request, payment_id) is False