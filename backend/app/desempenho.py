"""Consultas de desempenho sem escrita e independentes da retomada da Sprint."""
from datetime import datetime
from fastapi import Depends, HTTPException
from app import models as m
from app.revisoes import disponiveis


def ultima_concluida(db, usuario_id, bateria_id, cid, did, exigidas):
    candidatas = db.query(m.TentativaBateria).filter_by(
        usuario_id=usuario_id, bateria_id=bateria_id, contratacao_id=cid,
        demonstracao_id=did, status='FEITA').all()
    validas = []
    for t in candidatas:
        data = t.concluida_em if t.revisao_id is not None else t.revisao_concluida_em
        if data is None or t.percentual_acerto is None:
            continue
        respostas = db.query(m.RespostaAlunoQuestao).filter_by(
            tentativa_id=t.id, usuario_id=usuario_id, bateria_id=bateria_id,
            contratacao_id=cid, demonstracao_id=did, respondida=True).all()
        if not exigidas or not exigidas.issubset({r.questao_id for r in respostas if r.resposta_marcada}):
            continue
        validas.append((data, t.id, t))
    return max(validas, key=lambda x: (x[0], x[1]))[2] if validas else None


def consultar(db, usuario_id, curso_id, cid, did):
    curso = db.get(m.Curso, curso_id)
    if not curso:
        raise HTTPException(404, 'Curso não encontrado')
    disciplinas = db.query(m.CursoDisciplinaPropria).filter_by(curso_id=curso_id, ativo=True).order_by(m.CursoDisciplinaPropria.ordem, m.CursoDisciplinaPropria.id).all()
    resultado = []
    for d in disciplinas:
        if did is not None and not d.disponivel_demonstracao:
            continue
        assuntos = []
        for a in db.query(m.CursoAssuntoProprio).filter_by(curso_disciplina_propria_id=d.id, ativo=True).order_by(m.CursoAssuntoProprio.ordem, m.CursoAssuntoProprio.id):
            baterias = []
            pasta = db.query(m.Pasta).filter_by(curso_assunto_proprio_id=a.id, tipo='TEORIA').first()
            if pasta:
                for aula in db.query(m.Aula).filter_by(pasta_id=pasta.id):
                    for b, questoes in disponiveis(db, aula.id):
                        t = ultima_concluida(db, usuario_id, b.id, cid, did, {q.id for q in questoes})
                        baterias.append({'id': b.id, 'status_aluno': 'FEITA' if t else None,
                                         'percentual_acerto': t.percentual_acerto if t else None,
                                         'tentativa_id': t.id if t else None})
            assuntos.append({'id': a.id, 'nome': a.nome, 'baterias': baterias})
        resultado.append({'id': d.id, 'nome': d.nome, 'assuntos': assuntos})
    return {'curso_id': curso_id, 'nome_curso': curso.nome, 'disciplinas': resultado}


def registrar_rotas(app, get_db, get_usuario, validar):
    @app.get('/me/desempenho/contextos-expirados')
    def contextos(db=Depends(get_db), usuario=Depends(get_usuario)):
        agora = datetime.utcnow()
        rows = []
        for modelo, campo in [(m.ContratacaoCurso, 'contratacao_id'), (m.DemonstracaoCurso, 'demonstracao_id')]:
            for acesso in db.query(modelo).filter(modelo.usuario_id == usuario.id, modelo.data_fim <= agora, modelo.data_inicio <= agora):
                if campo == 'contratacao_id' and acesso.origem not in ('ADMIN', 'PAGAMENTO'):
                    continue
                curso = db.get(m.Curso, acesso.curso_id)
                if curso:
                    rows.append({'curso_id': curso.id, 'nome_curso': curso.nome, 'ativo': False,
                                 campo: acesso.id, 'data_inicio': acesso.data_inicio, 'data_fim': acesso.data_fim})
        return sorted(rows, key=lambda x: x['data_inicio'], reverse=True)

    @app.get('/me/cursos/{curso_id}/desempenho')
    def vigente(curso_id: int, contratacao_id: int | None = None, demonstracao_id: int | None = None,
                db=Depends(get_db), usuario=Depends(get_usuario)):
        validar(db=db, usuario=usuario, curso_id=curso_id, contratacao_id=contratacao_id, demonstracao_id=demonstracao_id)
        return consultar(db, usuario.id, curso_id, contratacao_id, demonstracao_id)

    @app.get('/me/cursos-expirados/{curso_id}/desempenho')
    def expirado(curso_id: int, contratacao_id: int | None = None, demonstracao_id: int | None = None,
                 db=Depends(get_db), usuario=Depends(get_usuario)):
        if (contratacao_id is None) == (demonstracao_id is None):
            raise HTTPException(400, 'Informe exatamente um contexto de acesso ao curso.')
        modelo, rid = (m.ContratacaoCurso, contratacao_id) if contratacao_id is not None else (m.DemonstracaoCurso, demonstracao_id)
        acesso = db.query(modelo).filter_by(id=rid, usuario_id=usuario.id, curso_id=curso_id).first()
        agora = datetime.utcnow()
        if not acesso or acesso.data_fim is None or acesso.data_fim > agora or acesso.data_inicio > agora:
            raise HTTPException(403, 'Contexto histórico expirado não encontrado')
        if contratacao_id is not None and acesso.origem not in ('ADMIN', 'PAGAMENTO'):
            raise HTTPException(403, 'Contratação inválida')
        return consultar(db, usuario.id, curso_id, contratacao_id, demonstracao_id)
