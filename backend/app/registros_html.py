"""Conteúdo textual de aluno/professor: formato explícito, sem imagens."""
from html.parser import HTMLParser

import nh3
from fastapi import HTTPException
from app.teoria_html import TAGS, _atributo, preparar_conteudo, validar_formato


class TextoVisivel(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes = []

    def handle_data(self, data):
        self.partes.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in {'p', 'br', 'li', 'tr', 'td', 'th', 'h2', 'h3', 'h4', 'figure'}:
            self.partes.append(' ')

    def handle_endtag(self, tag):
        self.handle_starttag(tag, [])


def texto_visivel(texto, formato):
    if formato != 'html_v1':
        return texto
    parser = TextoVisivel()
    parser.feed(texto)
    parser.close()
    return ''.join(parser.partes)


def preparar_registro(texto, formato=None):
    try:
        formato = validar_formato(formato)
    except HTTPException as exc:
        raise ValueError(str(exc.detail)) from exc
    texto = texto.strip()
    if formato == 'html_v1':
        if len(texto) > 100_000:
            raise ValueError('O texto formatado excede 100.000 caracteres')
        # Retirar imagens inclusive de colagens; só as ferramentas textuais
        # compartilham a allowlist, os limites e a validação de fórmulas da teoria.
        texto = nh3.clean(texto, tags=set(TAGS) - {'img'},
            attributes={'a': {'href'}, 'figure': {'class'}, 'span': {'class'},
                        **{t: {'style'} for t in ('p', 'h2', 'h3', 'h4')},
                        **{t: {'style', 'colspan', 'rowspan'} for t in ('td', 'th')}},
            attribute_filter=_atributo, url_schemes={'https'}, link_rel=None)
        try:
            texto = preparar_conteudo(texto, formato)
        except HTTPException as exc:
            raise ValueError(str(exc.detail)) from exc
    visivel = texto_visivel(texto, formato)
    if not visivel.strip() or len(visivel.split()) > 300:
        raise ValueError('Informe texto entre 1 e 300 palavras')
    return texto


def para_leitura(registro):
    formato = registro.texto_formato or 'texto_puro'
    if formato != 'html_v1':
        return registro.texto
    return preparar_registro(registro.texto, formato)
