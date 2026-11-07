"""Validação de arquivos/ZIP e obtenção HTTPS com destino fixado após DNS."""
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
import hashlib
import http.client
import ipaddress
import os
import socket
import ssl
import stat
import time
from urllib.parse import urlsplit
import warnings
import zipfile

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_ARQUIVO = 5 * 1024 * 1024
MAX_LOTE = 25 * 1024 * 1024
MAX_IMAGENS = 20
MAX_PIXELS = 16_000_000
EXTENSOES = {".png", ".jpg", ".jpeg", ".webp"}


def recusar(mensagem):
    raise HTTPException(422, mensagem)


@dataclass(frozen=True)
class ImagemValidada:
    dados: bytes
    mime: str
    extensao: str
    largura: int
    altura: int
    sha256: str


def validar_imagem(dados: bytes) -> ImagemValidada:
    if not dados or len(dados) > MAX_ARQUIVO:
        recusar("Cada imagem deve ter entre 1 byte e 5 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(dados)) as teste:
                formato = teste.format
                if formato not in {"PNG", "JPEG", "WEBP"}:
                    recusar("Use somente imagens PNG, JPEG ou WebP.")
                if (teste.width * teste.height > MAX_PIXELS or max(teste.size) > 8192
                        or getattr(teste, "n_frames", 1) != 1):
                    recusar("A imagem excede 16 megapixels/8192 pixels por lado ou é animada.")
                teste.verify()
            with Image.open(BytesIO(dados)) as original:
                imagem = ImageOps.exif_transpose(original)
                imagem.thumbnail((2560, 2560))
                # Reconstruir os pixels, sem EXIF, comentários, perfis ou anexos.
                modo = "RGBA" if "A" in imagem.getbands() or "transparency" in imagem.info else "RGB"
                limpa = Image.new(modo, imagem.size)
                limpa.paste(imagem.convert(modo))
                saida = BytesIO()
                if formato == "JPEG":
                    limpa.convert("RGB").save(saida, format="JPEG", quality=88)
                    mime, ext = "image/jpeg", "jpg"
                elif formato == "WEBP":
                    limpa.save(saida, format="WEBP", quality=88)
                    mime, ext = "image/webp", "webp"
                else:
                    limpa.save(saida, format="PNG")
                    mime, ext = "image/png", "png"
                resultado = saida.getvalue()
                if len(resultado) > MAX_ARQUIVO:
                    recusar("A imagem normalizada excede 5 MB.")
                return ImagemValidada(resultado, mime, ext, limpa.width, limpa.height,
                                      hashlib.sha256(resultado).hexdigest())
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError,
            Image.DecompressionBombError, Image.DecompressionBombWarning):
        recusar("Arquivo de imagem inválido ou danificado.")


def caminho_pacote(nome: str) -> str:
    if (not nome or len(nome) > 240 or "\\" in nome or ":" in nome or "%" in nome
            or any(ord(c) < 32 or ord(c) == 127 for c in nome)):
        recusar("O pacote contém um caminho inválido.")
    partes = nome.split("/")
    if any(p in {"", ".", ".."} for p in partes) or PurePosixPath(nome).is_absolute():
        recusar("O pacote contém um caminho fora da pasta permitida.")
    return nome


def ler_zip(dados: bytes):
    if not dados or len(dados) > MAX_LOTE:
        recusar("O ZIP deve ter até 25 MB.")
    try:
        with zipfile.ZipFile(BytesIO(dados)) as pacote:
            itens = pacote.infolist()
            if len(itens) > 50:
                recusar("O ZIP contém muitos arquivos/pastas.")
            nomes, imagens, markdown, total = set(), {}, None, 0
            for item in itens:
                if item.orig_filename != item.filename:
                    recusar("O pacote contém um nome truncado ou inválido.")
                nome = caminho_pacote(item.filename.rstrip("/") if item.is_dir() else item.filename)
                if nome.casefold() in nomes:
                    recusar("O ZIP contém nomes repetidos ou ambíguos.")
                nomes.add(nome.casefold())
                tipo = stat.S_IFMT(item.external_attr >> 16)
                if tipo not in {0, stat.S_IFREG, stat.S_IFDIR} or item.flag_bits & 1:
                    recusar("Links, arquivos especiais e ZIPs criptografados não são aceitos.")
                if item.is_dir():
                    if nome != "imagens":
                        recusar("Use apenas conteudo.md e a pasta imagens/.")
                    continue
                total += item.file_size
                if (total > MAX_LOTE or item.file_size > MAX_ARQUIVO
                        or item.file_size > max(1, item.compress_size) * 200):
                    recusar("O ZIP excede os limites de descompactação.")
                if nome == "conteudo.md":
                    if item.file_size > 1_000_000:
                        recusar("O Markdown do pacote é muito grande.")
                    markdown = pacote.read(item).decode("utf-8-sig")
                    if len(markdown) > 250000 or not markdown.strip():
                        recusar("O Markdown deve conter texto e ter até 250.000 caracteres.")
                elif (len(PurePosixPath(nome).parts) == 2 and nome.startswith("imagens/")
                      and PurePosixPath(nome).suffix.lower() in EXTENSOES):
                    if len(imagens) >= MAX_IMAGENS:
                        recusar("Cada pacote pode conter até 20 imagens.")
                    imagens[nome] = validar_imagem(pacote.read(item))
                else:
                    recusar("Use somente conteudo.md e imagens PNG/JPEG/WebP em imagens/.")
            if markdown is None:
                recusar("O ZIP precisa conter conteudo.md na raiz.")
            return markdown, imagens
    except HTTPException:
        raise
    except (zipfile.BadZipFile, UnicodeError, RuntimeError, NotImplementedError, OSError, EOFError):
        recusar("ZIP inválido, danificado ou com codificação não suportada.")


def destino_https(url: str):
    if (len(url) > 4096 or "\\" in url or any(c.isspace() or ord(c) < 32 for c in url)):
        recusar("Endereço de imagem inválido.")
    try:
        partes = urlsplit(url)
        host = (partes.hostname or "").encode("idna").decode().lower()
        permitidos = {h.strip().lower() for h in os.getenv("IMAGENS_HOSTS_PERMITIDOS", "").split(",") if h.strip()}
        if (partes.scheme != "https" or partes.username or partes.password or partes.fragment
                or partes.port not in {None, 443} or host not in permitidos):
            recusar("A origem desta imagem não está autorizada. Use o arquivo ou um ZIP.")
        respostas = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        ips = list(dict.fromkeys(r[4][0] for r in respostas))
        if not ips or any(not ipaddress.ip_address(ip).is_global
                          or getattr(ipaddress.ip_address(ip), "ipv4_mapped", None) is not None for ip in ips):
            recusar("O endereço da imagem não aponta exclusivamente para a Internet pública.")
        return partes, host, ips[0]
    except HTTPException:
        raise
    except (ValueError, UnicodeError, OSError):
        recusar("Não foi possível validar a origem da imagem.")


class _HTTPSFixado(http.client.HTTPSConnection):
    def __init__(self, host, ip, timeout):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self.ip = ip

    def connect(self):
        # Conecta ao IP já verificado; TLS continua validando certificado e SNI
        # do hostname original. Não há segunda resolução DNS nem proxy herdado.
        sock = socket.create_connection((self.ip, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


def baixar_imagem(url: str) -> ImagemValidada:
    partes, host, ip = destino_https(url)
    conexao = _HTTPSFixado(host, ip, 5)
    try:
        conexao.request("GET", (partes.path or "/") + ("?" + partes.query if partes.query else ""),
                        headers={"Accept": "image/png,image/jpeg,image/webp", "Accept-Encoding": "identity"})
        resposta = conexao.getresponse()
        if resposta.status != 200:  # Inclusive redirects: nenhum salto é seguido.
            recusar("A imagem não está disponível para download direto. Use o arquivo ou um ZIP.")
        if resposta.getheader("Content-Encoding", "identity").lower() != "identity":
            recusar("A origem retornou uma codificação de imagem não suportada.")
        comprimento = resposta.getheader("Content-Length")
        if comprimento and (not comprimento.isdigit() or int(comprimento) > MAX_ARQUIVO):
            recusar("A imagem remota excede 5 MB.")
        inicio, blocos, tamanho = time.monotonic(), [], 0
        while True:
            if time.monotonic() - inicio > 15:
                recusar("O download da imagem excedeu o tempo permitido.")
            bloco = resposta.read1(65536)
            if not bloco:
                break
            tamanho += len(bloco)
            if tamanho > MAX_ARQUIVO:
                recusar("A imagem remota excede 5 MB.")
            blocos.append(bloco)
        return validar_imagem(b"".join(blocos))
    except HTTPException:
        raise
    except (OSError, http.client.HTTPException):
        # Não incluir URLs assinadas, tokens, cabeçalhos ou erro da origem.
        recusar("Falha ao obter a imagem. Use o arquivo ou um ZIP.")
    finally:
        conexao.close()
