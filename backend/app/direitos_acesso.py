"""Direitos por compra: decisões de contestação não alteram períodos históricos."""
from datetime import datetime
from fastapi import HTTPException
from app import models as m
from app.bloqueios_reembolso import decisoes


def bloqueios(db, usuario_id, curso_id):
    return db.query(m.ContestacaoPagamento).join(m.Pagamento).filter(
        m.Pagamento.usuario_id == usuario_id, m.Pagamento.curso_id == curso_id,
        m.ContestacaoPagamento.devolucao_confirmada_em.isnot(None),
        m.ContestacaoPagamento.devolucao_confirmada_por.isnot(None),
        m.ContestacaoPagamento.referencia_devolucao.isnot(None),
        m.ContestacaoPagamento.bloqueio_executado_em.isnot(None),
        m.ContestacaoPagamento.bloqueio_executado_por.isnot(None)).all() + decisoes(db, usuario_id, curso_id)


def vigente(inicio, fim, agora):
    return inicio is not None and inicio <= agora and (fim is None or fim > agora)


def conferir(condicao):
    if not condicao:
        raise HTTPException(409, {'codigo': 'CONFERENCIA_NECESSARIA',
            'mensagem': 'Períodos e vínculos históricos exigem conferência administrativa; nenhum bloqueio executado.'})


def concessoes_do_contrato(db, contrato, validar=False):
    """Associa apenas concessões de origem identificável pelo fluxo administrativo.

    Uma concessão inicial tem o mesmo início da contratação. Renovações sem nova
    contratação só são associadas quando há um único contrato ADMIN candidato.
    Históricos sobrepostos ambíguos continuam exigindo conferência antes de bloquear.
    """
    if contrato.origem != 'ADMIN':
        return []
    contratos = db.query(m.ContratacaoCurso).filter_by(
        usuario_id=contrato.usuario_id, curso_id=contrato.curso_id, origem='ADMIN').all()
    concessoes = db.query(m.ConcessaoAcessoAdmin).filter_by(
        usuario_id=contrato.usuario_id, curso_id=contrato.curso_id).all()
    resultado = []
    for c in concessoes:
        if c.data_inicio < contrato.data_inicio or (
                contrato.data_fim is not None and c.data_inicio >= contrato.data_fim):
            continue
        candidatos = [t for t in contratos if t.data_inicio == c.data_inicio]
        if not candidatos:
            candidatos = [t for t in contratos if vigente(t.data_inicio, t.data_fim, c.data_inicio)]
        if len(candidatos) == 1 and candidatos[0].id == contrato.id:
            resultado.append(c)
        elif validar and any(t.id == contrato.id for t in candidatos):
            conferir(False)
    return resultado


def periodos_pagos(db, contrato):
    return db.query(m.PeriodoAcessoPagamento).join(m.Pagamento).filter(
        m.PeriodoAcessoPagamento.contratacao_id == contrato.id,
        m.PeriodoAcessoPagamento.usuario_id == contrato.usuario_id,
        m.PeriodoAcessoPagamento.curso_id == contrato.curso_id,
        m.Pagamento.contratacao_id == contrato.id,
        m.Pagamento.usuario_id == contrato.usuario_id,
        m.Pagamento.curso_id == contrato.curso_id,
        m.Pagamento.aprovado_em.isnot(None),
        m.Pagamento.ocorrencia_financeira.is_(None)).all()


def contrato_tem_bloqueio(db, contrato):
    ids = {c.pagamento_id for c in bloqueios(db, contrato.usuario_id, contrato.curso_id)}
    return bool(ids and db.query(m.Pagamento.id).filter(
        m.Pagamento.contratacao_id == contrato.id, m.Pagamento.id.in_(ids)).first())


def intervalos_contrato(db, contrato):
    if contrato.origem not in ('ADMIN', 'PAGAMENTO'):
        return []
    ids = {c.pagamento_id for c in bloqueios(db, contrato.usuario_id, contrato.curso_id)}
    if not ids or not db.query(m.Pagamento.id).filter(
            m.Pagamento.contratacao_id == contrato.id, m.Pagamento.id.in_(ids)).first():
        # Preserva concessão/renovação/desativação administrativa e contratos legados.
        # Status financeiro REFUNDED, sozinho, nunca cancela um período.
        return [(contrato.data_inicio, contrato.data_fim)]
    intervalos = [(p.data_inicio, p.data_fim) for p in periodos_pagos(db, contrato)
                  if p.pagamento_id not in ids]
    intervalos += [(c.data_inicio, c.data_fim) for c in concessoes_do_contrato(db, contrato) if c.ativo]
    return intervalos


def fim_continuo(intervalos, agora):
    """Fim do direito atual, incluindo extensões contíguas, sem atravessar lacunas."""
    intervalos = [(i, f) for i, f in intervalos if i is not None]
    atuais = [(i, f) for i, f in intervalos if vigente(i, f, agora)]
    if not atuais:
        return False, None
    if any(f is None for _, f in atuais):
        return True, None
    fim = max(f for _, f in atuais)
    for inicio, termino in sorted(intervalos, key=lambda x: x[0]):
        if inicio > fim:
            break
        if termino is None:
            return True, None
        fim = max(fim, termino)
    return True, fim


def vencimento_renovacao(db, contrato, agora=None):
    """Prazo pago: ignora bloqueados e preserva a cobertura futura já adquirida."""
    if not contrato_tem_bloqueio(db, contrato):
        return contrato.data_fim
    agora = agora or datetime.utcnow()
    intervalos = intervalos_contrato(db, contrato)
    atual, fim = fim_continuo(intervalos, agora)
    if not atual or fim is None:
        return None
    futuros = [f for i, f in intervalos if i is not None and i > agora]
    if any(f is None for f in futuros):
        return None
    return max([fim] + futuros)


def oportunidade_consumida(db, oportunidade):
    """Uma compra bloqueada não consome novamente o mesmo prazo de renovação."""
    pagamentos = db.query(m.Pagamento).filter_by(oportunidade_id=oportunidade.id).filter(
        m.Pagamento.aprovado_em.isnot(None), m.Pagamento.ocorrencia_financeira.is_(None)).all()
    if not pagamentos:
        return True  # Histórico inconclusivo: não reabrir automaticamente.
    ids = {b.pagamento_id for b in bloqueios(db, oportunidade.usuario_id, oportunidade.curso_id)}
    return any(p.id not in ids for p in pagamentos)


def contrato_vigente(db, contrato, agora=None):
    agora = agora or datetime.utcnow()
    return vigente(contrato.data_inicio, contrato.data_fim, agora) and any(
        vigente(i, f, agora) for i, f in intervalos_contrato(db, contrato))


def direito_atual_curso(db, usuario_id, curso_id, agora=None):
    agora = agora or datetime.utcnow()
    contratos = db.query(m.ContratacaoCurso).filter_by(usuario_id=usuario_id, curso_id=curso_id).all()
    intervalos = [periodo for c in contratos for periodo in intervalos_contrato(db, c)]
    for modelo in (m.ConcessaoAcessoAdmin, m.DemonstracaoCurso):
        intervalos += [(c.data_inicio, c.data_fim) for c in db.query(modelo).filter_by(
            usuario_id=usuario_id, curso_id=curso_id, ativo=True).all()]
    return fim_continuo(intervalos, agora)


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
    conferir(pagamento.aprovado_em is not None and pagamento.contratacao_id is not None
             and pagamento.ocorrencia_financeira is None)
    contrato = db.get(m.ContratacaoCurso, pagamento.contratacao_id)
    conferir(contrato is not None and contrato.origem in ('PAGAMENTO', 'ADMIN')
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
    bloqueados = {b.pagamento_id for b in bloqueios(db, contrato.usuario_id, contrato.curso_id)}
    pagos_validos = []
    administrativos = concessoes_do_contrato(db, contrato, validar=True)
    for periodo in periodos:
        p = por_id[periodo.pagamento_id]
        conferir((p.usuario_id, p.curso_id) == (contrato.usuario_id, contrato.curso_id)
            and (periodo.usuario_id, periodo.curso_id) == (contrato.usuario_id, contrato.curso_id)
            and periodo.data_fim > periodo.data_inicio
            and periodo.data_inicio >= contrato.data_inicio and periodo.data_fim <= contrato.data_fim)
        if contrato.origem == 'PAGAMENTO':
            conferir(periodo.data_inicio <= cursor if bloqueados else periodo.data_inicio == cursor)
            if periodo.data_inicio < cursor:
                conferir(p.tipo_compra == 'RENOVACAO')
            if p.id not in bloqueados:
                conferir(all(periodo.data_inicio >= fim or periodo.data_fim <= inicio
                    for inicio, fim in pagos_validos))
                pagos_validos.append((periodo.data_inicio, periodo.data_fim))
        else:
            conferir(p.tipo_compra == 'RENOVACAO')
        if p.tipo_compra == 'RENOVACAO':
            conferir(p.vencimento_original == periodo.data_inicio)
        cursor = max(cursor, periodo.data_fim)
    if contrato.origem == 'ADMIN':
        # O trecho administrativo pode anteceder e sobrepor os períodos pagos.
        intervalos = [(c.data_inicio, c.data_fim) for c in administrativos]
        intervalos += [(p.data_inicio, p.data_fim) for p in periodos]
        coberto, fim = fim_continuo(intervalos, contrato.data_inicio)
        conferir(coberto and (fim is None or fim >= contrato.data_fim))
    else:
        conferir(cursor == contrato.data_fim)
    conferir(pagamento.id in por_id)
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
