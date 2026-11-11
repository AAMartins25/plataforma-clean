"""Validação de respostas completas antes de gravar tentativas ou revisões."""
from fastapi import HTTPException
from app.models import Alternativa


def validar_respostas(db, questoes, respostas):
    enviados = {r.questao_id: r for r in respostas}
    if len(enviados) != len(respostas) or set(enviados) != {q.id for q in questoes}:
        raise HTTPException(400, 'Responda exatamente todas as questões da bateria')
    for q in questoes:
        item = enviados[q.id]
        ce = q.tipo == 'CERTO_ERRADO' or q.tipo_questao == 'CERTO_ERRADO'
        letras = {'C', 'E', 'NAO_SEI', 'PULOU', 'NAO TENHO CERTEZA OU NAO SEI'} if ce else {
            a.letra for a in db.query(Alternativa).filter_by(questao_id=q.id)}
        if item.resposta_marcada.strip().upper() not in letras:
            raise HTTPException(400, 'Alternativa inválida ou questão não respondida')
        if item.dificuldade not in {'FACIL', 'MEDIA', 'DIFICIL'} and not (ce and item.dificuldade is None):
            raise HTTPException(400, 'Informe uma dificuldade válida para cada questão de múltipla escolha')
    return enviados
