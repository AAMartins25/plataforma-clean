"""Registro de casos MP e decisões manuais independentes. Nunca movimenta dinheiro."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
import requests
from fastapi import Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update, text, or_
from app import models as m
from app.direitos_acesso import conferir_historico
from app.financeiro_transacional import protegido, timeout_financeiro
from app.transacoes_mp import consultar_pagamento, resolver_transacao


class Confirmacao(BaseModel):
    referencia_devolucao: str = Field(min_length=1, max_length=255)
    confirmacao_devolucao: bool

    @field_validator('referencia_devolucao')
    @classmethod
    def referencia(cls, valor):
        valor = valor.strip()
        if not valor:
            raise ValueError('Informe uma referência de comprovante ou extrato.')
        return valor


def registrar_observacao(db, pagamento, caso=None):
    """Chamador mantém lock de usuário/raiz/transação e commita atomicamente."""
    existente = db.query(m.ContestacaoPagamento).filter_by(pagamento_id=pagamento.id).with_for_update().first()
    cid = str(caso['id']) if caso else None
    if existente:
        if cid and existente.mp_dispute_id not in (None, cid):
            raise HTTPException(409, 'Outro caso já vinculado à compra; conferência necessária.')
        if cid:
            existente.mp_dispute_id = cid
        # Atualizações do provedor não reescrevem decisões/auditoria administrativa.
        return existente
    if cid and db.query(m.ContestacaoPagamento.id).filter_by(mp_dispute_id=cid).first():
        raise HTTPException(409, 'Contestação já vinculada a outra transação.')
    registro = m.ContestacaoPagamento(pagamento_id=pagamento.id, mp_dispute_id=cid,
        status='ABERTA', motivo=('Mercado Pago: ' + str((caso or {}).get('reason') or 'CHARGED_BACK'))[:1000],
        valor_cents=pagamento.valor_cents)
    db.add(registro)
    db.flush()
    return registro


def travar_escopo(db, caso_id):
    """Serializa a entrada de eventos com a decisão manual no PostgreSQL."""
    bind = db.get_bind() if hasattr(db, 'get_bind') else db
    if bind.dialect.name == 'postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:chave, 0))'),
                   {'chave': 'contestacao:' + str(caso_id)})


def conferir_escopo(db, c, p):
    from app.pausa_financeira import inbox
    if not c.mp_dispute_id:
        raise HTTPException(409, {'codigo': 'CONFERENCIA_NECESSARIA',
            'mensagem': 'CHARGED_BACK não comprova o escopo integral da contestação.'})
    eventos = db.execute(select(inbox).where(inbox.c.chave.like('c:%'),
        or_(inbox.c.payment_id == c.mp_dispute_id, inbox.c.estado != 'CONCLUIDO'))).mappings().all()
    comprovado = False
    for evento in eventos:
        resultado = evento['resultado'] or {}
        mesmo_caso = evento['payment_id'] == c.mp_dispute_id
        mesma_compra = str(p.mp_payment_id) in resultado.get('pagamentos_mp', [])
        if not (mesmo_caso or mesma_compra):
            continue
        if evento['estado'] != 'CONCLUIDO' or resultado.get('escopo') != 'INTEGRAL_VERIFICADO':
            raise HTTPException(409, {'codigo': 'CONFERENCIA_NECESSARIA',
                'mensagem': 'Há evento de contestação pendente ou com escopo ambíguo.'})
        if mesmo_caso and resultado.get('pagamentos_mp') == [str(p.mp_payment_id)] \
                and resultado.get('valor_cents') == p.valor_cents and resultado.get('moeda') == 'BRL':
            comprovado = True
    if not comprovado:
        raise HTTPException(409, {'codigo': 'CONFERENCIA_NECESSARIA',
            'mensagem': 'Não há comprovação independente do escopo integral desta compra.'})


def conferir_caso(db, c, p):
    conferir_escopo(db, c, p)
    if c.valor_cents != p.valor_cents or p.valor_cents <= 0 or p.moeda != 'BRL':
        raise HTTPException(409, {'codigo': 'CONFERENCIA_NECESSARIA',
            'mensagem': 'Valor integral ou moeda não comprovados; nenhum bloqueio executado.'})
    return conferir_historico(db, p)


def travar(db, ident):
    inicial = db.get(m.ContestacaoPagamento, ident)
    if inicial is None:
        raise HTTPException(404, 'Contestação não encontrada.')
    p = db.get(m.Pagamento, inicial.pagamento_id)
    if p is None:
        raise HTTPException(409, 'Pagamento não encontrado; conferência necessária.')
    # Mesma ordem do checkout/resolver_transacao e de ambos os POSTs.
    db.query(m.Usuario).filter_by(id=p.usuario_id).with_for_update().one()
    db.query(m.Pagamento).filter_by(id=p.pagamento_origem_id or p.id).with_for_update().populate_existing().one()
    p = db.query(m.Pagamento).filter_by(id=p.id).with_for_update().populate_existing().one()
    c = db.query(m.ContestacaoPagamento).filter_by(id=ident).with_for_update().populate_existing().one()
    return c, p


def instalar(app, get_db, get_usuario_atual, headers):
    def admin(usuario=Depends(get_usuario_atual)):
        if not usuario.is_admin:
            raise HTTPException(403, 'Acesso restrito ao administrador.')
        return usuario

    @app.get('/admin/contestacoes')
    def listar(db=Depends(get_db), usuario=Depends(admin), pagina: int = Query(1, ge=1)):
        linhas = db.query(m.ContestacaoPagamento, m.Pagamento, m.Usuario, m.Curso).join(
            m.Pagamento, m.Pagamento.id == m.ContestacaoPagamento.pagamento_id).join(
            m.Usuario, m.Usuario.id == m.Pagamento.usuario_id).join(
            m.Curso, m.Curso.id == m.Pagamento.curso_id).order_by(
            m.ContestacaoPagamento.id.desc()).offset((pagina-1)*50).limit(51).all()
        itens = []
        for c, p, u, curso in linhas[:50]:
            situacao = 'BLOQUEADO' if c.bloqueio_executado_em else 'AGUARDANDO_DEVOLUCAO'
            if not c.bloqueio_executado_em:
                try:
                    conferir_caso(db, c, p)
                    if c.devolucao_confirmada_em:
                        situacao = 'BLOQUEIO_DISPONIVEL'
                except HTTPException as exc:
                    if exc.status_code != 409:
                        raise
                    situacao = 'CONFERENCIA_NECESSARIA'
            itens.append({'id': c.id, 'aluno': u.nome, 'email': u.email, 'curso': curso.nome,
                'pagamento_id': p.id, 'mp_payment_id': p.mp_payment_id,
                'mp_dispute_id': c.mp_dispute_id, 'valor_cents': c.valor_cents,
                'status': c.status, 'mp_status': p.mp_status, 'status_pagamento': p.status,
                'motivo': c.motivo, 'criada_em': c.criada_em, 'aprovado_em': p.aprovado_em,
                'devolucao_confirmada_em': c.devolucao_confirmada_em,
                'devolucao_confirmada_por': c.devolucao_confirmada_por,
                'referencia_devolucao': c.referencia_devolucao,
                'bloqueio_executado_em': c.bloqueio_executado_em,
                'bloqueio_executado_por': c.bloqueio_executado_por,
                'situacao_acesso': situacao})
        from app.pausa_financeira import inbox
        pendentes = db.execute(select(inbox).where(inbox.c.chave.like('c:%'),
            inbox.c.estado != 'CONCLUIDO').order_by(inbox.c.id.desc()).offset((pagina-1)*50).limit(51)).mappings().all()
        pendencias = [{'notificacao_id': r['id'], 'caso_mp': r['payment_id'],
            'recebida_em': r['recebida_em'], 'tentativas': r['tentativas'],
            'situacao': 'CONFERENCIA_NECESSARIA', 'motivo': r['erro'] or 'Evento aguardando processamento.',
            'pagamentos_mp': (r['resultado'] or {}).get('pagamentos_mp', [])} for r in pendentes[:50]]
        return {'contestacoes': itens, 'pendencias': pendencias, 'pagina': pagina,
            'tem_proxima': len(linhas) > 50 or len(pendentes) > 50}

    @app.post('/admin/contestacoes/{ident}/confirmar-devolucao')
    @protegido
    def confirmar(ident: int, dados: Confirmacao, db=Depends(get_db), usuario=Depends(admin)):
        if dados.confirmacao_devolucao is not True:
            raise HTTPException(400, 'Confirme expressamente a devolução efetiva no extrato do cartão.')
        c, p = travar(db, ident)
        if c.devolucao_confirmada_em:
            if c.referencia_devolucao != dados.referencia_devolucao:
                raise HTTPException(409, 'Devolução já confirmada com outra referência.')
        else:
            c.referencia_devolucao = dados.referencia_devolucao
            c.devolucao_confirmada_em = datetime.utcnow()
            c.devolucao_confirmada_por = usuario.id
        db.commit()
        return {'message': 'Devolução registrada. Nenhum bloqueio de acesso foi executado.'}

    @app.post('/admin/contestacoes/{ident}/bloquear-acesso')
    @protegido
    def bloquear(ident: int, confirmacao_bloqueio: bool = False,
                 db=Depends(get_db), usuario=Depends(admin)):
        if confirmacao_bloqueio is not True:
            raise HTTPException(400, 'Confirmação explícita do bloqueio é obrigatória.')
        c, p = travar(db, ident)
        if not (c.devolucao_confirmada_em and c.devolucao_confirmada_por and c.referencia_devolucao):
            raise HTTPException(409, 'Confirme a devolução efetiva antes do bloqueio manual.')
        if not c.bloqueio_executado_em:
            travar_escopo(db, c.mp_dispute_id)
            conferir_caso(db, c, p)
            c.bloqueio_executado_em = datetime.utcnow()
            c.bloqueio_executado_por = usuario.id
        db.commit()
        return {'message': 'Bloqueio manual registrado somente para os direitos desta compra.'}


@protegido
def receber_caso(db, caso, dados_pagamento, payment_id, headers):
    p = resolver_transacao(db, payment_id, dados_pagamento, headers)
    # O endpoint de caso registra o evento sem conceder/revogar acesso,
    # sem alterar status de reembolso e sem executar o processador de aprovação.
    c = registrar_observacao(db, p, caso)
    db.commit()
    return {'ok': True, 'contestacao_id': c.id}


class Conferencia(HTTPException):
    def __init__(self, motivo):
        super().__init__(409, motivo)


def consultar_escopo(ident, headers, resumo):
    try:
        r = requests.get(f'https://api.mercadopago.com/v1/chargebacks/{ident}',
                         headers=headers, timeout=timeout_financeiro())
        if r.status_code != 200:
            raise HTTPException(502, 'Consulta canônica da contestação indisponível.')
        caso = r.json()
    except (requests.RequestException, ValueError):
        raise HTTPException(502, 'Consulta canônica da contestação indisponível.') from None
    if not isinstance(caso, dict) or str(caso.get('id')) != ident:
        raise Conferencia('Identidade canônica da contestação incompatível.')
    pagamentos = caso.get('payments')
    if not isinstance(pagamentos, list) or not pagamentos or any(
            not re.fullmatch(r'[0-9]{1,64}', str(p)) for p in pagamentos):
        raise Conferencia('Identificação dos pagamentos não comprovada.')
    resumo['pagamentos_mp'] = [str(p) for p in pagamentos]
    if len(pagamentos) != 1:
        raise Conferencia('Contestação com múltiplos pagamentos; conferir administrativamente.')
    pid = str(pagamentos[0])
    resposta = consultar_pagamento(pid, headers)
    if resposta.status_code != 200:
        raise HTTPException(502, 'Consulta do pagamento indisponível.')
    try:
        dados = resposta.json()
        valor = Decimal(str(caso['amount'])) * 100
        valor_pagamento = Decimal(str(dados['transaction_amount'])) * 100
        if any(not v.is_finite() or v != v.to_integral_value() or v <= 0
               for v in (valor, valor_pagamento)):
            raise ValueError()
    except (ValueError, KeyError, InvalidOperation, TypeError):
        raise Conferencia('Valor canônico ausente ou inválido.') from None
    resumo.update(valor_cents=int(valor), moeda=caso.get('currency'))
    if caso.get('currency') != 'BRL' or dados.get('currency_id') != 'BRL' or valor != valor_pagamento:
        raise Conferencia('Contestação parcial ou moeda divergente; conferir administrativamente.')
    return caso, dados, pid


def processar_pendente(ident, protecao, op):
    """Usa inbox existente: recurso c:* é caso, nunca enviado ao processador payment.

    O recebimento já foi commitado antes da consulta externa. O efeito de domínio
    e a comprovação têm commit único. Reprocessamentos preservam tentativas anteriores.
    """
    from app.pausa_financeira import inbox, agora
    with protecao.engine.connect() as conn:
        evento = conn.execute(select(inbox).where(inbox.c.id == ident)).mappings().one()
    if evento['estado'] == 'CONCLUIDO':
        return {'id': ident, 'processado': False}
    anterior = evento['resultado'] or {}
    resumo = {'tipo': 'CONTESTACAO', 'envelope_valido': anterior.get('envelope_valido') is True,
              'escopo': 'CONFERENCIA_NECESSARIA', 'pagamentos_mp': [],
              'verificado_em': agora().isoformat()}
    erro = None
    try:
        if not resumo['envelope_valido']:
            raise Conferencia('Envelope ou identidade do evento não comprovados.')
        caso, dados, pid = consultar_escopo(evento['payment_id'], protecao.headers_contestacoes(), resumo)
        op.verificar()
        with protecao.factory() as db:
            db.info['finance_op'] = op
            row = db.execute(select(inbox).where(inbox.c.id == ident).with_for_update()).mappings().one()
            if row['estado'] == 'CONCLUIDO':
                return {'id': ident, 'processado': False}
            real_commit = db.commit
            db.commit = db.flush
            receber_caso(db, caso, dados, pid, protecao.headers_contestacoes())
            resumo['escopo'] = 'INTEGRAL_VERIFICADO'
            resumo['historico'] = historico_resultado(row['resultado'])
            db.execute(update(inbox).where(inbox.c.id == ident).values(estado='CONCLUIDO',
                resultado=resumo, erro=None, tentativas=row['tentativas']+1, concluida_em=agora()))
            op.verificar()
            real_commit()
        return {'id': ident, 'processado': True}
    except HTTPException as exc:
        erro = str(exc.detail)[:200]
    except Exception:
        erro = 'Falha de processamento; evento preservado para conferência e recuperação.'
    resumo['escopo'] = 'CONFERENCIA_NECESSARIA'
    # Outra sessão, sem a geração interrompida; não grava no domínio financeiro.
    from app.financeiro_transacional import ATUAL
    token = ATUAL.set(None)
    try:
        with protecao.engine.begin() as conn:
            row = conn.execute(select(inbox).where(inbox.c.id == ident).with_for_update()).mappings().one()
            if row['estado'] != 'CONCLUIDO':
                resumo['historico'] = historico_resultado(row['resultado'])
                conn.execute(update(inbox).where(inbox.c.id == ident).values(estado='ERRO',
                    erro=erro, resultado=resumo, tentativas=row['tentativas']+1))
    finally:
        ATUAL.reset(token)
    return {'id': ident, 'processado': False, 'conferencia_necessaria': True}


def historico_resultado(resultado):
    if not resultado:
        return []
    anterior = {k: v for k, v in resultado.items() if k != 'historico'}
    return list(resultado.get('historico', [])) + [anterior]
