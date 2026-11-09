"""Bloqueio explícito após reembolso integral confirmado; sem movimentação financeira."""
from datetime import datetime
from fastapi import Depends, HTTPException
from sqlalchemy import select
from app import models as m
from app.bloqueios_reembolso import bloqueios_reembolso, esquema_disponivel
from app.direitos_acesso import conferir_historico
from app.financeiro_transacional import protegido
from app.admin_intermediario import pode_administrar


def registrar_rotas(app, get_db, get_usuario, travar_pagamento):
    @app.post('/admin/reembolsos/{reembolso_id}/bloquear-acesso')
    @protegido
    def bloquear(reembolso_id: int, confirmacao_bloqueio: bool = False,
                 db=Depends(get_db), usuario=Depends(get_usuario)):
        if not pode_administrar(usuario, 'geral'):
            raise HTTPException(403, 'Acesso restrito ao administrador.')
        if confirmacao_bloqueio is not True:
            raise HTTPException(400, 'Confirmação explícita do bloqueio é obrigatória.')
        if not esquema_disponivel(db):
            raise HTTPException(503, 'Esquema do bloqueio manual de reembolso ainda não disponível.')
        inicial = db.get(m.ReembolsoFinanceiro, reembolso_id)
        if inicial is None:
            raise HTTPException(404, 'Reembolso não encontrado.')
        pagamento = travar_pagamento(db, inicial.pagamento_id)
        reembolso = db.query(m.ReembolsoFinanceiro).filter_by(id=reembolso_id).with_for_update().populate_existing().one()
        if not (reembolso.status == 'CONFIRMADO' and reembolso.confirmado_em
                and reembolso.confirmado_por and (reembolso.referencia_comprovante or '').strip()
                and reembolso.valor_cents == pagamento.valor_cents):
            raise HTTPException(409, 'Confirme a devolução efetiva integral antes do bloqueio manual.')
        b = bloqueios_reembolso.c
        anterior = db.execute(select(bloqueios_reembolso).where(b.pagamento_id == pagamento.id)).first()
        if anterior is None:
            conferir_historico(db, pagamento)
            db.execute(bloqueios_reembolso.insert().values(pagamento_id=pagamento.id,
                reembolso_id=reembolso.id, executado_em=datetime.utcnow(), executado_por=usuario.id))
        db.commit()
        return {'message': 'Bloqueio manual registrado somente para os direitos deste pagamento.'}
