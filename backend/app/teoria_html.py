"""Formato e sanitização dos materiais de teoria em HTML."""

import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlsplit

import nh3
from fastapi import HTTPException
from app.imagens import PADRAO_SRC, referencias


FORMATO_HTML = "html_v1"
FORMATO_TEXTO = "texto_puro"
LIMITE_HTML = 1_000_000
LIMITE_TAGS = 15_000
LIMITE_PROFUNDIDADE = 128
LIMITE_FONTE_FORMULA = 4096
LIMITE_FORMULAS = 200

TAGS = frozenset({
    "p", "br", "h2", "h3", "h4", "strong", "b", "em", "i", "u",
    "ul", "ol", "li", "blockquote", "a", "figure", "figcaption",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "span", "img",
})


def _url_segura(valor: str) -> bool:
    if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in valor) or "\\" in valor:
        return False
    if valor.startswith("/") and not valor.startswith("//") and "\\" not in valor:
        return True
    try:
        partes = urlsplit(valor)
        # Consultar port também valida portas não numéricas ou fora do intervalo.
        _ = partes.port
        return (partes.scheme == "https" and bool(partes.hostname)
                and not partes.username and not partes.password)
    except (ValueError, UnicodeError):
        return False


def _atributo(tag: str, nome: str, valor: str) -> str | None:
    if tag == "img":
        if nome == "src":
            return valor if PADRAO_SRC.fullmatch(valor) else None
        if nome == "alt":
            return valor[:2000]
        if nome in {"width", "height"}:
            return valor if valor.isascii() and valor.isdigit() and 1 <= int(valor) <= 8192 else None
        return None
    if nome == "style" and tag in {"p", "h2", "h3", "h4", "th", "td"}:
        # Reconstruir uma declaração conhecida, sem transportar CSS da origem.
        alinhamentos = [m.group(1).lower() for parte in valor.split(";")
                        if (m := re.fullmatch(r"\s*text-align\s*:\s*(left|right|center|justify)\s*",
                                             parte, re.IGNORECASE | re.ASCII))]
        return f"text-align:{alinhamentos[-1]}" if alinhamentos else None
    if tag == "a" and nome == "href":
        return valor if _url_segura(valor) else None
    if tag == "figure" and nome == "class":
        return valor if valor in {"table", "ro-math-display", "image"} else None
    if tag == "span" and nome == "class":
        return valor if valor == "ro-math-inline" else None
    if tag in {"td", "th"} and nome in {"colspan", "rowspan"}:
        return valor if re.fullmatch(r"[1-9][0-9]?", valor) and int(valor) <= 20 else None
    return None


class _Formulas(HTMLParser):
    """A fonte de uma fórmula é texto puro, com tamanho e quantidade limitados."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ativa = None
        self.partes = []
        self.quantidade = 0
        self.comprimento = 0

    def handle_starttag(self, tag, attrs):
        if self.ativa:
            raise HTTPException(422, "A fonte da fórmula deve conter somente texto LaTeX.")
        classes = [v for k, v in attrs if k == "class"]
        if ((tag == "span" and classes == ["ro-math-inline"])
                or (tag == "figure" and classes == ["ro-math-display"])):
            self.quantidade += 1
            if self.quantidade > LIMITE_FORMULAS:
                raise HTTPException(422, "Cada teoria pode ter até 200 fórmulas.")
            self.ativa, self.partes, self.comprimento = tag, [], 0

    def handle_data(self, data):
        if self.ativa:
            self.partes.append(data)
            self.comprimento += len(data)
            if self.comprimento > LIMITE_FONTE_FORMULA:
                raise HTTPException(422, "Cada fórmula pode ter até 4.096 caracteres.")

    def handle_endtag(self, tag):
        if self.ativa:
            if tag != self.ativa:
                raise HTTPException(422, "Estrutura de fórmula inválida.")
            fonte = "".join(self.partes)
            if (not fonte.strip() or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ufffd]", fonte)):
                raise HTTPException(422, "A fórmula está vazia ou contém caracteres inválidos.")
            self.ativa = None

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_comment(self, data):
        if self.ativa:
            raise HTTPException(422, "A fonte da fórmula deve conter somente texto LaTeX.")

    handle_decl = handle_comment
    handle_pi = handle_comment

    def close(self):
        super().close()
        if self.ativa:
            raise HTTPException(422, "Fórmula sem fechamento.")


class _SpansCanonicos(HTMLParser):
    """Preserva o comportamento anterior: spans comuns continuam desembrulhados.

    Executado somente depois do nh3, não substitui o sanitizador de segurança.
    Mantém entidades e a serialização sanitizada dos demais elementos.
    """
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.saida = []
        self.spans = []

    def handle_starttag(self, tag, attrs):
        if tag == "span":
            manter = attrs == [("class", "ro-math-inline")]
            self.spans.append(manter)
            if not manter:
                return
        self.saida.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if tag == "span" and self.spans and not self.spans.pop():
            return
        self.saida.append(f"</{tag}>")

    def handle_data(self, data):
        self.saida.append(data)

    def handle_entityref(self, name):
        self.saida.append(f"&{name};")

    def handle_charref(self, name):
        self.saida.append(f"&#{name};")


class _Estrutura(HTMLParser):
    """Limites anteriores ao parser nativo; não é o sanitizador de segurança."""

    VAZIAS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
              "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.tags = 0
        self.pilha = []

    def handle_starttag(self, tag, attrs):
        self.tags += 1
        if self.tags > LIMITE_TAGS:
            raise HTTPException(422, "O texto formatado tem muitos elementos. Divida-o em teorias menores.")
        if tag not in self.VAZIAS:
            self.pilha.append(tag)
            if len(self.pilha) > LIMITE_PROFUNDIDADE:
                raise HTTPException(422, "O texto formatado tem aninhamento excessivo.")

    def handle_endtag(self, tag):
        if tag in self.pilha:
            del self.pilha[len(self.pilha) - 1 - self.pilha[::-1].index(tag):]

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)


def validar_formato(formato: str | None) -> str:
    if formato in (None, FORMATO_TEXTO):
        return FORMATO_TEXTO
    if formato != FORMATO_HTML:
        raise HTTPException(status_code=422, detail="Formato de conteúdo inválido")
    return formato


def preparar_conteudo(conteudo: str | None, formato: str | None) -> str | None:
    if conteudo is None:
        return None
    if validar_formato(formato) == FORMATO_TEXTO:
        return conteudo
    if len(conteudo) > LIMITE_HTML:
        raise HTTPException(422, "O texto formatado excede 1.000.000 de caracteres. Divida-o em teorias menores.")
    try:
        conteudo.encode("utf-8", errors="strict")
        referencias(conteudo)
        estrutura = _Estrutura()
        estrutura.feed(conteudo)
        estrutura.close()
        formulas = _Formulas()
        formulas.feed(conteudo)
        formulas.close()
        # O estado do parser pertence exclusivamente a esta chamada, nunca a um
        # objeto global compartilhado entre as threads das rotas síncronas.
        limpo = nh3.clean(
            conteudo, tags=set(TAGS),
            attributes={"a": {"href"}, "figure": {"class"}, "span": {"class"},
                        "img": {"src", "alt", "width", "height"},
                        **{t: {"style"} for t in ("p", "h2", "h3", "h4")},
                        **{t: {"style", "colspan", "rowspan"} for t in ("td", "th")}},
            attribute_filter=_atributo, url_schemes={"https"}, link_rel=None,
            strip_comments=True,
        ).strip()
        if "<span" in limpo:
            spans = _SpansCanonicos()
            spans.feed(limpo)
            spans.close()
            limpo = "".join(spans.saida)
        formulas = _Formulas()
        formulas.feed(limpo)
        formulas.close()
        if len(limpo) > LIMITE_HTML:
            raise HTTPException(422, "O HTML convertido excede 1.000.000 de caracteres. Divida-o em teorias menores.")
        texto = unescape(nh3.clean(limpo, tags=set(), attributes={}, link_rel=None))
    except (ValueError, UnicodeError, AssertionError) as erro:
        raise HTTPException(422, "O texto formatado contém HTML inválido.") from erro
    if not re.sub(r"[\s\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]", "", texto) and not referencias(limpo):
        raise HTTPException(status_code=422, detail="O texto formatado está vazio")
    return limpo
