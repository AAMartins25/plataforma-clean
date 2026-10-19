"""Registro de casos MP e decisões manuais independentes. Nunca movimenta dinheiro."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
import requests
from fastapi import Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
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


def conferir_caso(db, c, p):
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
        return {'contestacoes': itens, 'pagina': pagina, 'tem_proxima': len(linhas) > 50}

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


def consultar_caso(ident, headers):
    try:
        r = requests.get(f'https://api.mercadopago.com/v1/chargebacks/{ident}',
                         headers=headers, timeout=timeout_financeiro())
        if r.status_code != 200:
            raise HTTPException(502, 'Não foi possível consultar a contestação no Mercado Pago.')
        caso = r.json()
    except (requests.RequestException, ValueError):
        raise HTTPException(502, 'Consulta de contestação indisponível.') from None
    if not isinstance(caso, dict) or str(caso.get('id')) != ident:
        raise HTTPException(409, 'Identidade da contestação incompatível.')
    pagamentos = caso.get('payments')
    # Não inferir repartição financeira de um caso que reúne várias compras.
    if not isinstance(pagamentos, list) or len(pagamentos) != 1 or not re.fullmatch(r'[0-9]{1,64}', str(pagamentos[0])):
        raise HTTPException(409, 'CONFERENCIA_NECESSARIA: caso sem transação única comprovada.')
    return caso, str(pagamentos[0])


def processar_caso(ident, factory, headers):
    caso, pid = consultar_caso(ident, headers)
    resposta = consultar_pagamento(pid, headers)
    if resposta.status_code != 200:
        raise HTTPException(502, 'Consulta do pagamento da contestação indisponível.')
    try:
        dados = resposta.json()
        valor = Decimal(str(caso['amount'])) * 100
        valor_pagamento = Decimal(str(dados['transaction_amount'])) * 100
        if not valor.is_finite() or valor != valor.to_integral_value() or valor <= 0:
            raise ValueError()
    except (ValueError, KeyError, InvalidOperation, TypeError):
        raise HTTPException(409, 'CONFERENCIA_NECESSARIA: valor do caso inválido.') from None
    if caso.get('currency') != 'BRL' or valor != valor_pagamento:
        raise HTTPException(409, 'CONFERENCIA_NECESSARIA: valor/moeda divergente ou contestação parcial.')
    with factory() as db:
        return receber_caso(db, caso, dados, pid, headers)
