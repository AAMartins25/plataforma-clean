"""Regra comum de disponibilidade das disciplinas no acesso de demonstração."""
from app import models as m


def disciplinas_liberadas(db, curso_id):
    return (db.query(m.CursoDisciplinaPropria.id)
            .filter_by(curso_id=curso_id, ativo=True)
            .order_by(m.CursoDisciplinaPropria.ordem, m.CursoDisciplinaPropria.id)
            .limit(2).all())


def disponivel(db, disciplina):
    curso = db.get(m.Curso, disciplina.curso_id)
    if not curso or not curso.demonstracao_por_ordem:
        return bool(disciplina.disponivel_demonstracao)
    return disciplina.id in {row.id for row in disciplinas_liberadas(db, disciplina.curso_id)}


def sincronizar(db, curso_id):
    curso = db.get(m.Curso, curso_id)
    if not curso or not curso.demonstracao_por_ordem:
        return
    db.flush()
    liberadas = {row.id for row in disciplinas_liberadas(db, curso_id)}
    disciplinas = db.query(m.CursoDisciplinaPropria).filter_by(curso_id=curso_id).all()
    for disciplina in disciplinas:
        disciplina.disponivel_demonstracao = disciplina.ativo and disciplina.id in liberadas
