"""Direitos por compra: decisões de contestação não alteram períodos históricos."""
from datetime import datetime
from fastapi import HTTPException
from app import models as m


def bloqueios(db, usuario_id, curso_id):
    return db.query(m.ContestacaoPagamento).join(m.Pagamento).filter(
        m.Pagamento.usuario_id == usuario_id, m.Pagamento.curso_id == curso_id,
        m.ContestacaoPagamento.devolucao_confirmada_em.isnot(None),
        m.ContestacaoPagamento.devolucao_confirmada_por.isnot(None),
        m.ContestacaoPagamento.referencia_devolucao.isnot(None),
        m.ContestacaoPagamento.bloqueio_executado_em.isnot(None),
        m.ContestacaoPagamento.bloqueio_executado_por.isnot(None)).all()


def vigente(inicio, fim, agora):
    return inicio is not None and inicio <= agora and (fim is None or fim > agora)


def contrato_vigente(db, contrato, agora=None):
    agora = agora or datetime.utcnow()
    if not vigente(contrato.data_inicio, contrato.data_fim, agora):
        return False
    if contrato.origem == 'ADMIN':
        return True
    if contrato.origem != 'PAGAMENTO':
        return False
    ids = {c.pagamento_id for c in bloqueios(db, contrato.usuario_id, contrato.curso_id)}
    if not ids:
        return True  # Preserva autorização legada quando não há bloqueio manual.
    afetado = db.query(m.Pagamento.id).filter(
        m.Pagamento.contratacao_id == contrato.id,
        m.Pagamento.id.in_(ids)).first()
    if not afetado:
        return True  # Outra contratação é um direito independente.
    periodos = db.query(m.PeriodoAcessoPagamento).join(m.Pagamento).filter(
        m.PeriodoAcessoPagamento.contratacao_id == contrato.id,
        m.PeriodoAcessoPagamento.usuario_id == contrato.usuario_id,
        m.PeriodoAcessoPagamento.curso_id == contrato.curso_id,
        m.Pagamento.contratacao_id == contrato.id,
        m.Pagamento.usuario_id == contrato.usuario_id,
        m.Pagamento.curso_id == contrato.curso_id,
        m.Pagamento.aprovado_em.isnot(None),
        m.Pagamento.status != 'REFUNDED',
        m.Pagamento.ocorrencia_financeira.is_(None)).all()
    return any(p.pagamento_id not in ids and vigente(p.data_inicio, p.data_fim, agora)
               for p in periodos)


def curso_vigente(db, usuario_id, curso_id, agora=None):
    agora = agora or datetime.utcnow()
    contratos = db.query(m.ContratacaoCurso).filter_by(
        usuario_id=usuario_id, curso_id=curso_id).all()
    if any(contrato_vigente(db, c, agora) for c in contratos):
        return True
    concessoes = db.query(m.ConcessaoAcessoAdmin).filter_by(
        usuario_id=usuario_id, curso_id=curso_id, ativo=True).all()
    if any(vigente(c.data_inicio, c.data_fim, agora) for c in concessoes):
        return True
    demos = db.query(m.DemonstracaoCurso).filter_by(
        usuario_id=usuario_id, curso_id=curso_id, ativo=True).all()
    if any(vigente(d.data_inicio, d.data_fim, agora) for d in demos):
        return True
    # AcessoCurso é cache agregado; não pode reintroduzir compra bloqueada.
    if bloqueios(db, usuario_id, curso_id):
        return False
    acesso = db.query(m.AcessoCurso).filter_by(
        usuario_id=usuario_id, curso_id=curso_id, ativo=True).first()
    return bool(acesso and vigente(acesso.data_inicio, acesso.data_fim, agora))


def conferir_historico(db, pagamento):
    """Falha conservadora antes de registrar qualquer bloqueio."""
    def conferir(condicao):
        if not condicao:
            raise HTTPException(409, {'codigo': 'CONFERENCIA_NECESSARIA',
                'mensagem': 'Períodos e vínculos históricos exigem conferência administrativa; nenhum bloqueio executado.'})
    conferir(pagamento.aprovado_em is not None and pagamento.contratacao_id is not None
             and pagamento.ocorrencia_financeira is None)
    contrato = db.get(m.ContratacaoCurso, pagamento.contratacao_id)
    conferir(contrato is not None and contrato.origem == 'PAGAMENTO'
        and (contrato.usuario_id, contrato.curso_id) == (pagamento.usuario_id, pagamento.curso_id)
        and contrato.data_inicio is not None and contrato.data_fim is not None)
    pagamentos = db.query(m.Pagamento).filter_by(contratacao_id=contrato.id).filter(
        m.Pagamento.aprovado_em.isnot(None), m.Pagamento.ocorrencia_financeira.is_(None)).all()
    periodos = db.query(m.PeriodoAcessoPagamento).filter_by(contratacao_id=contrato.id).order_by(
        m.PeriodoAcessoPagamento.data_inicio, m.PeriodoAcessoPagamento.id).all()
    conferir(bool(periodos) and {p.id for p in pagamentos} == {p.pagamento_id for p in periodos}
             and len(pagamentos) == len(periodos))
    por_id = {p.id: p for p in pagamentos}
    cursor = contrato.data_inicio
    for periodo in periodos:
        p = por_id[periodo.pagamento_id]
        conferir((p.usuario_id, p.curso_id) == (contrato.usuario_id, contrato.curso_id)
            and (periodo.usuario_id, periodo.curso_id) == (contrato.usuario_id, contrato.curso_id)
            and periodo.data_inicio == cursor and periodo.data_fim > periodo.data_inicio)
        if p.tipo_compra == 'RENOVACAO':
            conferir(p.vencimento_original == periodo.data_inicio)
        cursor = periodo.data_fim
    conferir(cursor == contrato.data_fim and pagamento.id in por_id)
    # Pagamentos históricos sem contratação não podem ser presumidos como
    # integrantes ou independentes do mesmo acesso agregado.
    conferir(db.query(m.Pagamento.id).filter_by(usuario_id=pagamento.usuario_id,
        curso_id=pagamento.curso_id, contratacao_id=None).filter(
        m.Pagamento.aprovado_em.isnot(None), m.Pagamento.ocorrencia_financeira.is_(None)).first() is None)
    acesso = db.query(m.AcessoCurso).filter_by(usuario_id=pagamento.usuario_id,
        curso_id=pagamento.curso_id, ativo=True).first()
    if acesso:
        direitos = db.query(m.ContratacaoCurso).filter_by(usuario_id=pagamento.usuario_id,
            curso_id=pagamento.curso_id).all()
        direitos += db.query(m.ConcessaoAcessoAdmin).filter_by(usuario_id=pagamento.usuario_id,
            curso_id=pagamento.curso_id, ativo=True).all()
        direitos += db.query(m.DemonstracaoCurso).filter_by(usuario_id=pagamento.usuario_id,
            curso_id=pagamento.curso_id, ativo=True).all()
        # Cache mais amplo que todos os direitos conhecidos pode ser concessão legada.
        conferir(acesso.data_inicio is not None)
        cursor_acesso = acesso.data_inicio
        coberto = False
        for d in sorted((d for d in direitos if d.data_inicio is not None), key=lambda d: d.data_inicio):
            if d.data_inicio > cursor_acesso:
                break
            if d.data_fim is None:
                coberto = True
                break
            cursor_acesso = max(cursor_acesso, d.data_fim)
            if acesso.data_fim is not None and cursor_acesso >= acesso.data_fim:
                coberto = True
                break
        conferir(coberto)
    return contrato
