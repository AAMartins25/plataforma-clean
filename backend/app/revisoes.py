"""Agenda por assunto. Não utiliza modelos de Questões práticas ou ciclos."""
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException
from sqlalchemy import text
from app import models as m, schemas


def contexto(query, model, usuario_id, contratacao_id, demonstracao_id):
    return query.filter(model.usuario_id == usuario_id,
                        model.contratacao_id == contratacao_id,
                        model.demonstracao_id == demonstracao_id)


def bloquear(db, usuario_id, pasta_id, contratacao_id, demonstracao_id):
    # Inclui o caso sem linha de agenda: SELECT FOR UPDATE sozinho não basta.
    if db.bind.dialect.name == 'postgresql':
        key = f'revisao:{usuario_id}:{pasta_id}:{contratacao_id}:{demonstracao_id}'
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))'), {'key': key})


def estrutura(db, pasta_id):
    pasta = db.get(m.Pasta, pasta_id)
    assunto = db.get(m.CursoAssuntoProprio, pasta.curso_assunto_proprio_id) if pasta else None
    disciplina = db.get(m.CursoDisciplinaPropria, assunto.curso_disciplina_propria_id) if assunto else None
    if not disciplina:
        raise HTTPException(404, 'Assunto da revisão não encontrado')
    pastas = db.query(m.Pasta).filter_by(curso_assunto_proprio_id=assunto.id).all()
    aulas = db.query(m.Aula).filter_by(pasta_id=pasta_id).all()
    if len(pastas) != 1 or len(aulas) != 1 or pastas[0].id != pasta_id or pasta.tipo != 'TEORIA':
        raise HTTPException(409, 'O assunto deve possuir uma pasta TEORIA e uma aula')
    return pasta, assunto, disciplina, aulas[0]


def disponiveis(db, aula_id, escrita=False):
    """Mesma seleção na exibição, programação e conclusão; sem limite novo de quantidade."""
    aula = db.query(m.Aula).filter_by(id=aula_id).with_for_update().first() if escrita else db.get(m.Aula, aula_id)
    if not aula or not aula.ativo:
        return []
    query = db.query(m.Bateria).filter_by(aula_id=aula_id, status='CONCLUIDA', ativo=True).order_by(m.Bateria.ordem, m.Bateria.id)
    baterias = (query.with_for_update() if escrita else query).all()
    conjunto = []
    for b in baterias:
        query = db.query(m.Questao).filter_by(bateria_id=b.id).order_by(m.Questao.ordem, m.Questao.id)
        conjunto.append((b, (query.with_for_update() if escrita else query).all()))
    return conjunto


def respondidas(db, tentativa):
    if not tentativa:
        return set()
    respostas = contexto(db.query(m.RespostaAlunoQuestao), m.RespostaAlunoQuestao,
                         tentativa.usuario_id, tentativa.contratacao_id, tentativa.demonstracao_id).filter_by(tentativa_id=tentativa.id, bateria_id=tentativa.bateria_id, respondida=True).all()
    return {r.questao_id for r in respostas if r.resposta_marcada}


def tentativa_atual(db, revisao, bateria_id):
    return contexto(db.query(m.TentativaBateria), m.TentativaBateria, revisao.usuario_id,
                    revisao.contratacao_id, revisao.demonstracao_id).filter_by(revisao_id=revisao.id, bateria_id=bateria_id, ativo=True).order_by(m.TentativaBateria.id.desc()).first()


def programar_primeira(db, usuario_id, aula, contratacao_id, demonstracao_id):
    bloquear(db, usuario_id, aula.pasta_id, contratacao_id, demonstracao_id)
    db.flush()  # Inclui a tentativa recém-finalizada com autoflush=False.
    conjunto = disponiveis(db, aula.id, escrita=True)
    if not any(qs for _, qs in conjunto):
        return
    datas = []
    for bateria, questoes in conjunto:
        if not questoes:
            continue
        exigidas = {q.id for q in questoes}
        candidatas = contexto(db.query(m.TentativaBateria), m.TentativaBateria, usuario_id, contratacao_id, demonstracao_id).filter_by(bateria_id=bateria.id, revisao_id=None, status='FEITA').order_by(m.TentativaBateria.id.desc()).all()
        # A tentativa concluída anterior permanece válida até outra realmente completa.
        # ativo controla a retomada da Sprint, não apaga comprovação histórica.
        tentativa = next((t for t in candidatas if exigidas.issubset(respondidas(db, t))), None)
        if tentativa is None:
            return
        datas.append(tentativa.concluida_em or tentativa.revisao_concluida_em or tentativa.iniciada_em)
    progresso = contexto(db.query(m.ProgressoAula), m.ProgressoAula, usuario_id, contratacao_id, demonstracao_id).filter_by(aula_id=aula.id).first()
    if not progresso:
        progresso = m.ProgressoAula(usuario_id=usuario_id, aula_id=aula.id, pasta_id=aula.pasta_id,
                                   contratacao_id=contratacao_id, demonstracao_id=demonstracao_id)
        db.add(progresso)
    progresso.concluida = True
    progresso.data_conclusao = max(datas)
    existentes = contexto(db.query(m.RevisaoAluno), m.RevisaoAluno, usuario_id, contratacao_id, demonstracao_id).filter_by(pasta_id=aula.pasta_id).order_by(m.RevisaoAluno.id.desc()).first()
    if existentes and not (existentes.status == "CANCELADA" and existentes.motivo_cancelamento == "PERDA_DE_OBJETO"):
        return
    db.add(m.RevisaoAluno(usuario_id=usuario_id, aula_id=aula.id, pasta_id=aula.pasta_id,
                         contratacao_id=contratacao_id, demonstracao_id=demonstracao_id,
                         etapa=1, status='PENDENTE', concluida=False,
                         data_prevista=max(datas) + timedelta(days=7)))


def registrar_rotas(app, get_db, get_usuario, validar):
    def localizar(db, usuario, rid, cid, did, escrita=False):
        if (cid is None) == (did is None):
            raise HTTPException(400, 'Informe exatamente um contexto de acesso ao curso.')
        query = contexto(db.query(m.RevisaoAluno), m.RevisaoAluno, usuario.id, cid, did).filter_by(id=rid)
        r = query.first()
        if not r:
            raise HTTPException(404, 'Revisão não encontrada')
        if escrita:
            bloquear(db, usuario.id, r.pasta_id, cid, did)
            r = query.populate_existing().with_for_update().first()
        pasta, assunto, disciplina, aula = estrutura(db, r.pasta_id)
        if aula.id != r.aula_id:
            raise HTTPException(409, 'Aula da revisão incompatível')
        validar(db=db, usuario=usuario, curso_id=disciplina.curso_id, contratacao_id=cid, demonstracao_id=did)
        if not assunto.ativo or not disciplina.ativo:
            conjunto = []
        elif did is not None and not disciplina.disponivel_demonstracao:
            raise HTTPException(403, 'Disciplina indisponível na demonstração')
        else:
            conjunto = disponiveis(db, aula.id, escrita=escrita)
        return r, assunto, disciplina, conjunto

    def resultado(db, r, assunto, disciplina, conjunto):
        baterias = []
        for b, qs in conjunto:
            t = tentativa_atual(db, r, b.id)
            feitas = respondidas(db, t)
            baterias.append({'id': b.id, 'titulo': b.titulo, 'ordem': b.ordem,
                             'tentativa_id': t.id if t else None, 'total_questoes': len(qs), 'respondidas': len({q.id for q in qs} & feitas),
                             'concluida': bool(qs) and {q.id for q in qs}.issubset(feitas),
                             'respostas': [{'questao_id': x.questao_id, 'resposta_marcada': x.resposta_marcada,
                                            'dificuldade': x.dificuldade, 'rever': x.rever}
                                           for x in (db.query(m.RespostaAlunoQuestao).filter_by(tentativa_id=t.id).all() if t else [])
                                           if x.questao_id in {q.id for q in qs}]})
        return {'id': r.id, 'status': r.status, 'etapa': r.etapa, 'pasta_id': r.pasta_id,
                'aula_id': r.aula_id, 'assunto_id': assunto.id, 'titulo': assunto.nome,
                'disciplina_id': disciplina.id, 'curso_id': disciplina.curso_id,
                'data_prevista': r.data_prevista, 'concluida_em': r.concluida_em,
                'cancelada_em': r.cancelada_em, 'motivo_cancelamento': r.motivo_cancelamento,
                'contratacao_id': r.contratacao_id, 'demonstracao_id': r.demonstracao_id,
                'perda_de_objeto': not any(qs for _, qs in conjunto), 'baterias': baterias}

    @app.get('/me/revisoes/{revisao_id}')
    def abrir(revisao_id: int, contratacao_id: int | None = None, demonstracao_id: int | None = None,
              db=Depends(get_db), usuario=Depends(get_usuario)):
        r, a, d, bs = localizar(db, usuario, revisao_id, contratacao_id, demonstracao_id)
        return resultado(db, r, a, d, bs)

    @app.post('/me/revisoes/{revisao_id}/reconciliar')
    def reconciliar(revisao_id: int, contratacao_id: int | None = None, demonstracao_id: int | None = None,
                    db=Depends(get_db), usuario=Depends(get_usuario)):
        r, a, d, bs = localizar(db, usuario, revisao_id, contratacao_id, demonstracao_id, True)
        if r.status == 'PENDENTE' and not any(qs for _, qs in bs):
            r.status = 'CANCELADA'
            r.concluida = False
            r.cancelada_em = datetime.utcnow()
            r.motivo_cancelamento = 'PERDA_DE_OBJETO'
        db.commit()
        return resultado(db, r, a, d, bs)

    @app.get('/me/revisoes/{revisao_id}/baterias/{bateria_id}/questoes')
    def questoes(revisao_id: int, bateria_id: int, contratacao_id: int | None = None, demonstracao_id: int | None = None,
                 db=Depends(get_db), usuario=Depends(get_usuario)):
        r, _, _, bs = localizar(db, usuario, revisao_id, contratacao_id, demonstracao_id)
        if r.status != 'PENDENTE' or datetime.utcnow() < r.data_prevista:
            raise HTTPException(409, 'Revisão não disponível para responder')
        qs = next((qs for b, qs in bs if b.id == bateria_id), None)
        if qs is None:
            raise HTTPException(404, 'Bateria indisponível na revisão')
        return [{'id': q.id, 'ordem': q.ordem, 'enunciado': q.enunciado, 'tipo': q.tipo,
                 'tipo_questao': q.tipo_questao, 'quantidade_alternativas': q.quantidade_alternativas,
                 'gabarito': q.gabarito, 'comentario': q.comentario,
                 'alternativas': [{'letra': alt.letra, 'texto': alt.texto} for alt in db.query(m.Alternativa).filter_by(questao_id=q.id).order_by(m.Alternativa.letra)]} for q in qs]

    @app.post('/me/revisoes/{revisao_id}/baterias/{bateria_id}/respostas')
    def respostas(revisao_id: int, bateria_id: int, dados: schemas.RespostasBateriaRevisaoCreate,
                  contratacao_id: int | None = None, demonstracao_id: int | None = None,
                  db=Depends(get_db), usuario=Depends(get_usuario)):
        r, _, _, bs = localizar(db, usuario, revisao_id, contratacao_id, demonstracao_id, True)
        if r.status != 'PENDENTE' or datetime.utcnow() < r.data_prevista:
            raise HTTPException(409, 'Revisão não disponível para responder')
        qs = next((qs for b, qs in bs if b.id == bateria_id), None)
        if not qs:
            raise HTTPException(404, 'Bateria sem questões disponíveis')
        enviados = {x.questao_id: x for x in dados.respostas}
        if len(enviados) != len(dados.respostas) or set(enviados) != {q.id for q in qs}:
            raise HTTPException(400, 'Responda exatamente todas as questões atualmente exigidas')
        t = tentativa_atual(db, r, bateria_id)
        if not t:
            t = m.TentativaBateria(usuario_id=usuario.id, bateria_id=bateria_id, revisao_id=r.id,
                                  contratacao_id=contratacao_id, demonstracao_id=demonstracao_id, ativo=True)
            db.add(t)
            db.flush()
        existentes = {x.questao_id: x for x in db.query(m.RespostaAlunoQuestao).filter_by(tentativa_id=t.id).all()}
        feedback = []
        for q in qs:
            item = enviados[q.id]
            marcada = item.resposta_marcada.strip().upper()
            pulou = marcada in {'NAO_SEI', 'PULOU', 'NAO TENHO CERTEZA OU NAO SEI'}
            letras = {'C', 'E'} if q.tipo == 'CERTO_ERRADO' else {a.letra for a in db.query(m.Alternativa).filter_by(questao_id=q.id)}
            if not pulou and marcada not in letras:
                raise HTTPException(400, 'Alternativa inválida')
            if item.rever and q.tipo != 'CERTO_ERRADO':
                raise HTTPException(400, 'Rever é exclusivo de CERTO/ERRADO neste fluxo')
            if item.dificuldade not in {None, 'FACIL', 'MEDIA', 'DIFICIL'}:
                raise HTTPException(400, 'Dificuldade inválida')
            resposta = existentes.get(q.id)
            if resposta and (resposta.resposta_marcada != marcada or resposta.dificuldade != item.dificuldade or resposta.rever != item.rever):
                raise HTTPException(409, 'Resposta já registrada com outros valores')
            if not resposta:
                resposta = m.RespostaAlunoQuestao(tentativa_id=t.id, usuario_id=usuario.id, questao_id=q.id,
                    bateria_id=bateria_id, contratacao_id=contratacao_id, demonstracao_id=demonstracao_id,
                    resposta_marcada=marcada, gabarito=q.gabarito, dificuldade=item.dificuldade,
                    acertou=not pulou and marcada == str(q.gabarito).strip().upper(), pulou=pulou,
                    rever=item.rever if q.tipo == 'CERTO_ERRADO' else False,
                    respondida=True, finalizada=True, em_revisao=True)
                db.add(resposta)
            feedback.append({'questao_id': q.id, 'acertou': resposta.acertou, 'gabarito': resposta.gabarito, 'comentario': q.comentario})
        t.status = 'FEITA'
        t.concluida_em = t.concluida_em or datetime.utcnow()
        t.percentual_acerto = round(100 * sum(f['acertou'] for f in feedback) / len(feedback))
        db.commit()
        return {'id': t.id, 'status': t.status, 'feedback': feedback}

    @app.put('/me/revisoes/{revisao_id}/concluir')
    def concluir(revisao_id: int, contratacao_id: int | None = None, demonstracao_id: int | None = None,
                 db=Depends(get_db), usuario=Depends(get_usuario)):
        r, a, d, bs = localizar(db, usuario, revisao_id, contratacao_id, demonstracao_id, True)
        if r.status != 'PENDENTE':
            return resultado(db, r, a, d, bs)
        if not any(qs for _, qs in bs):
            r.status = 'CANCELADA'
            r.cancelada_em = datetime.utcnow()
            r.motivo_cancelamento = 'PERDA_DE_OBJETO'
            db.commit()
            return resultado(db, r, a, d, bs)
        if datetime.utcnow() < r.data_prevista:
            raise HTTPException(409, 'A data da revisão ainda não chegou')
        for b, qs in bs:
            if not {q.id for q in qs}.issubset(respondidas(db, tentativa_atual(db, r, b.id))):
                raise HTTPException(409, 'Há questões exigidas sem resposta nesta revisão')
        r.status = 'CONCLUIDA'
        r.concluida = True
        r.concluida_em = datetime.utcnow()
        if r.etapa < 4:
            db.add(m.RevisaoAluno(usuario_id=r.usuario_id, pasta_id=r.pasta_id, aula_id=r.aula_id,
                contratacao_id=r.contratacao_id, demonstracao_id=r.demonstracao_id,
                etapa=r.etapa + 1, status='PENDENTE', concluida=False,
                data_prevista=r.concluida_em + timedelta(days={1: 15, 2: 21, 3: 28}[r.etapa])))
        db.commit()
        return resultado(db, r, a, d, bs)
