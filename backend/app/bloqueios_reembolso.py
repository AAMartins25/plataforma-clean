"""Decisões de acesso separadas da devolução; nunca cria esquema na inicialização."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, MetaData, Table, inspect, select
from sqlalchemy.orm import Session
from app import models as m

metadata = MetaData()
bloqueios_reembolso = Table(
    'bloqueios_acesso_reembolso', metadata,
    Column('pagamento_id', Integer, ForeignKey(m.Pagamento.id), primary_key=True),
    Column('reembolso_id', Integer, ForeignKey(m.ReembolsoFinanceiro.id), nullable=False, unique=True),
    Column('executado_em', DateTime, nullable=False),
    Column('executado_por', Integer, ForeignKey(m.Usuario.id), nullable=False),
)


def esquema_disponivel(db):
    # Ausência do esquema aditivo não interrompe leituras/fluxos já existentes.
    if not isinstance(db, Session):
        return False
    if 'esquema_bloqueios_reembolso' not in db.info:
        db.info['esquema_bloqueios_reembolso'] = inspect(db.connection()).has_table(
            bloqueios_reembolso.name)
    return db.info['esquema_bloqueios_reembolso']


def decisoes(db, usuario_id=None, curso_id=None):
    if not esquema_disponivel(db):
        return []
    b = bloqueios_reembolso.c
    query = select(bloqueios_reembolso).join(m.Pagamento, m.Pagamento.id == b.pagamento_id).join(
        m.ReembolsoFinanceiro, m.ReembolsoFinanceiro.id == b.reembolso_id).where(
        m.ReembolsoFinanceiro.pagamento_id == b.pagamento_id,
        m.ReembolsoFinanceiro.status == 'CONFIRMADO',
        m.ReembolsoFinanceiro.confirmado_em.isnot(None),
        m.ReembolsoFinanceiro.confirmado_por.isnot(None),
        m.ReembolsoFinanceiro.referencia_comprovante.isnot(None),
        m.ReembolsoFinanceiro.valor_cents == m.Pagamento.valor_cents)
    if usuario_id is not None:
        query = query.where(m.Pagamento.usuario_id == usuario_id)
    if curso_id is not None:
        query = query.where(m.Pagamento.curso_id == curso_id)
    return db.execute(query).all()
