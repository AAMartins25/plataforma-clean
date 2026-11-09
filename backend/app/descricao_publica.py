"""HTML público identificado na coluna Text existente; legado permanece literal."""
import nh3
from fastapi import HTTPException

MARCADOR = '<!--resumao:descricao-publica:html:v1-->'
TAGS = {'p', 'br', 'h2', 'h3', 'h4', 'strong', 'b', 'em', 'i', 'ul', 'ol', 'li'}


def preparar_descricao(payload, anterior):
    # Uma alteração apenas nos valores não deve reescrever a descrição.
    if 'descricao_publica' not in payload:
        return anterior
    valor = payload['descricao_publica']
    if valor is None:
        valor = ''
    if not isinstance(valor, str):
        raise HTTPException(422, 'Descrição pública inválida.')
    formato = payload.get('descricao_publica_formato', 'texto_puro')
    if formato not in {'texto_puro', 'html_v1'}:
        raise HTTPException(422, 'Formato da descrição inválido.')
    if valor == anterior and formato == 'texto_puro':
        return anterior
    if formato == 'texto_puro' and not valor.startswith(MARCADOR):
        return valor
    html = valor.removeprefix(MARCADOR)
    if len(html) > 1_000_000:
        raise HTTPException(422, 'A descrição formatada excede 1.000.000 de caracteres.')
    try:
        html.encode('utf-8', errors='strict')
        limpo = nh3.clean(html, tags=TAGS, attributes={}, link_rel=None, strip_comments=True)
    except (ValueError, UnicodeError) as erro:
        raise HTTPException(422, 'HTML da descrição inválido.') from erro
    return MARCADOR + limpo


def descricao_para_visitante(valor):
    """Mantém a resposta textual usada pelo checkout; HTML vai em campo adicional."""
    if not valor or not valor.startswith(MARCADOR):
        return {"descricao_publica": valor, "descricao_publica_html": None}
    from html.parser import HTMLParser
    class Texto(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.partes = []
        def handle_data(self, data):
            self.partes.append(data)
        def handle_starttag(self, tag, attrs):
            if tag == 'br':
                self.partes.append('\n')
        def handle_endtag(self, tag):
            if tag in {'p', 'h2', 'h3', 'h4', 'li'}:
                self.partes.append('\n')
    html = preparar_descricao({'descricao_publica': valor}, None)[len(MARCADOR):]
    texto = Texto()
    texto.feed(html)
    return {"descricao_publica": ''.join(texto.partes).rstrip('\n'), "descricao_publica_html": html}
