"""Adaptador restrito ao bucket privado configurado no servidor."""
import os
import base64
import json
import re
from urllib.parse import quote, urlsplit
import requests
from fastapi import HTTPException


class SupabaseImagens:
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.chave = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        self.bucket = os.getenv("SUPABASE_IMAGENS_BUCKET", "teoria-imagens")
        partes = urlsplit(self.url)
        if (partes.scheme != "https" or not partes.hostname or partes.username or partes.password
                or partes.path or partes.query or partes.fragment or not self.chave
                or not self.bucket.replace("-", "").isalnum()):
            raise HTTPException(503, "Armazenamento de imagens ainda não configurado.")
        self.base = self.url + "/storage/v1"
        self.cabecalhos = {"apikey": self.chave}
        if not re.fullmatch(r"sb_secret_[A-Za-z0-9_-]{16,}", self.chave):
            try:
                # Classificação apenas; a assinatura é validada pelo Supabase.
                partes = self.chave.split(".")
                if len(partes) != 3:
                    raise ValueError()
                claims = json.loads(base64.urlsafe_b64decode(partes[1] + "=" * (-len(partes[1]) % 4)))
                if claims.get("role") != "service_role":
                    raise ValueError()
            except (ValueError, TypeError, AttributeError, UnicodeError):
                raise HTTPException(503, "Configure uma chave secreta ou service_role válida somente no backend.") from None
            self.cabecalhos["Authorization"] = "Bearer " + self.chave

    def _request(self, metodo, path, **kwargs):
        try:
            with requests.Session() as sessao:
                sessao.trust_env = False
                r = sessao.request(metodo, self.base + path, timeout=(5, 15), allow_redirects=False,
                                   headers={**kwargs.pop("headers", {}), **self.cabecalhos}, **kwargs)
                if r.status_code not in {200, 201, 204}:
                    raise HTTPException(502, "O armazenamento de imagens não concluiu a operação.")
                return r
        except requests.RequestException:
            raise HTTPException(502, "Armazenamento de imagens indisponível.") from None

    def enviar(self, chave, dados, mime):
        self._request("POST", "/object/" + self.bucket + "/" + quote(chave, safe="/"),
                      data=dados, headers={"Content-Type": mime, "x-upsert": "false", "Cache-Control": "max-age=3600"})

    def excluir(self, chave):
        self._request("DELETE", "/object/" + self.bucket, json={"prefixes": [chave]})

    def listar(self, offset=0, limite=100):
        try:
            resultado = self._request("POST", "/object/list/" + self.bucket,
                json={"prefix": "", "limit": limite, "offset": offset,
                      "sortBy": {"column": "name", "order": "asc"}}).json()
            if not isinstance(resultado, list) or len(resultado) > limite:
                raise ValueError()
            return resultado
        except (ValueError, TypeError):
            raise HTTPException(502, "Não foi possível listar os objetos para manutenção.") from None

    def assinar(self, chave):
        try:
            r = self._request("POST", "/object/sign/" + self.bucket + "/" + quote(chave, safe="/"),
                              json={"expiresIn": 900}).json()
            relativo = r["signedURL"]
            if not relativo.startswith("/object/sign/" + self.bucket + "/"):
                raise ValueError()
            return self.base + relativo
        except (ValueError, KeyError, TypeError):
            raise HTTPException(502, "O armazenamento retornou um endereço inválido.") from None


def obter_storage_imagens():
    return SupabaseImagens()
