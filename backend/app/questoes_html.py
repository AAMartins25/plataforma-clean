"""Conteúdo das questões usa exatamente os formatos e o sanitizador da teoria."""
from app.teoria_html import preparar_conteudo, validar_formato, FORMATO_HTML


def preparar_questao(dados, anterior=None):
    for campo in ("enunciado", "comentario"):
        formato = campo + "_formato"
        # Clientes antigos podem atualizar outros dados sem reclassificar HTML.
        if formato not in dados.model_fields_set and anterior is not None:
            setattr(dados, formato, getattr(anterior, formato))
        setattr(dados, formato, validar_formato(getattr(dados, formato)))
        setattr(dados, campo, preparar_conteudo(getattr(dados, campo), getattr(dados, formato)))
    if dados.alternativas is not None:
        antigas = {a.letra: a for a in anterior.alternativas} if anterior is not None else {}
        for alternativa in dados.alternativas:
            antiga = antigas.get(alternativa.letra.strip().upper())
            if "texto_formato" not in alternativa.model_fields_set and antiga is not None:
                alternativa.texto_formato = antiga.texto_formato
            alternativa.texto_formato = validar_formato(alternativa.texto_formato)
            alternativa.texto = preparar_conteudo(alternativa.texto, alternativa.texto_formato)


def formatos(questao):
    return {campo + "_formato": validar_formato(getattr(questao, campo + "_formato"))
            for campo in ("enunciado", "comentario")}


def referencias_questao(questao):
    from app.imagens import referencias
    ids = set()
    for campo in ("enunciado", "comentario"):
        if getattr(questao, campo + "_formato") == FORMATO_HTML:
            ids.update(referencias(getattr(questao, campo)))
    for alternativa in questao.alternativas:
        if alternativa.texto_formato == FORMATO_HTML:
            ids.update(referencias(alternativa.texto))
    return ids
