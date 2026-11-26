"""Percentuais das listas do aluno, calculados em lote sem carregar questões."""
from sqlalchemy import case, func, select

from app.models import Aula, Bateria, CursoAssuntoProprio, Pasta, TentativaBateria


def contagens_por_assunto(db, assuntos, usuario_id, contratacao_id, demonstracao_id):
    """Retorna (baterias elegíveis, feitas) para os assuntos solicitados."""
    ids = [assunto.id for assunto in assuntos]
    resultado = {ident: [0, 0] for ident in ids}
    if not ids:
        return resultado

    # Equivale à pasta TEORIA obtida pela rota atual. A pasta é única no
    # esquema vigente; min(id) torna a escolha determinística em dados legados.
    primeira_pasta = (
        select(func.min(Pasta.id))
        .where(Pasta.curso_assunto_proprio_id == CursoAssuntoProprio.id,
               Pasta.tipo == "TEORIA")
        .correlate(CursoAssuntoProprio)
        .scalar_subquery()
    )
    elegiveis = (
        select(Bateria.id.label("bateria_id"),
               CursoAssuntoProprio.id.label("assunto_id"))
        .select_from(CursoAssuntoProprio)
        .join(Pasta, Pasta.curso_assunto_proprio_id == CursoAssuntoProprio.id)
        .join(Aula, Aula.pasta_id == Pasta.id)
        .join(Bateria, Bateria.aula_id == Aula.id)
        .where(CursoAssuntoProprio.id.in_(ids), Pasta.id == primeira_pasta,
               Aula.ativo.is_(True), Bateria.ativo.is_(True),
               Bateria.status == "CONCLUIDA")
        .cte("baterias_elegiveis")
    )

    # O histórico de conclusão pertence ao contexto de estudo, independente
    # do estado da tentativa usada para retomar ou refazer a Sprint. Uma linha
    # por bateria impede que várias conclusões sejam contadas mais de uma vez.
    concluidas = (
        select(TentativaBateria.bateria_id.label("bateria_id"))
        .join(elegiveis, elegiveis.c.bateria_id == TentativaBateria.bateria_id)
        .where(TentativaBateria.usuario_id == usuario_id,
               TentativaBateria.status == "FEITA",
               TentativaBateria.revisao_id.is_(None),
               TentativaBateria.contratacao_id == contratacao_id,
               TentativaBateria.demonstracao_id == demonstracao_id)
        .distinct()
        .subquery()
    )
    totais = (
        select(
            elegiveis.c.assunto_id,
            func.count(elegiveis.c.bateria_id),
            func.sum(case((concluidas.c.bateria_id.is_not(None), 1), else_=0)),
        )
        .select_from(elegiveis)
        .outerjoin(concluidas, concluidas.c.bateria_id == elegiveis.c.bateria_id)
        .group_by(elegiveis.c.assunto_id)
    )
    for assunto_id, total, feitas in db.execute(totais):
        resultado[assunto_id] = [total, feitas]
    return resultado


def percentual(total, feitas):
    # Math.round() do JavaScript, para valores sempre não negativos.
    return (2 * feitas * 100 + total) // (2 * total) if total else 0
