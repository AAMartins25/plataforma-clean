"""Barreira na conexão que grava; não cria objetos no banco."""
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from inspect import signature
from time import monotonic
from weakref import WeakKeyDictionary, ref

from fastapi import HTTPException
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

ATUAL = ContextVar('operacao_financeira', default=None)
PROTECOES = WeakKeyDictionary()
TABELAS = {'pagamentos', 'oportunidades_compra', 'contratacoes_curso',
           'acessos_curso', 'demonstracoes_curso', 'concessoes_acesso_admin',
           'periodos_acesso_pagamento', 'reembolsos_financeiros', 'contestacoes_pagamento'}


@dataclass
class Operacao:
    protecao: object
    modo: str
    geracao: int
    prazo: float
    falhou: bool = False
    commit_iniciado: bool = False
    commits_confirmados: int = 0

    def verificar(self):
        if self.falhou or monotonic() >= self.prazo:
            raise HTTPException(503, 'Operação financeira interrompida. Verifique o resultado antes de tentar novamente.')


def protegido(func):
    """Também protege chamadas diretas; subfunções reutilizam a mesma geração."""
    sig = signature(func)
    @wraps(func)
    def executar(*args, **kwargs):
        db = sig.bind_partial(*args, **kwargs).arguments.get('db')
        if not isinstance(db, Session):
            return func(*args, **kwargs)  # Dublês unitários não são conexões de produção.
        p = PROTECOES.get(db.get_bind())
        if p is None:
            raise HTTPException(503, 'Proteção financeira não instalada nesta conexão.')
        # Consultas MP de estado não precisam reter a transação da autenticação.
        if (func.__name__ in {'confirmar_pagamento', 'admin_revalidar_pagamento', 'processar_pagamento_mp'}
            and not db.info.get('finance_unidade_atomica') and not (db.new or db.dirty or db.deleted)):
            db.expunge_all()
            db.rollback()
        existente = ATUAL.get() or db.info.get('finance_op')
        if existente is not None:
            existente.verificar()
            token = ATUAL.set(existente)
            try:
                return func(*args, **kwargs)
            finally:
                ATUAL.reset(token)
        with p.lease(db=db) as op:
            db.info['finance_op'] = op
            try:
                return func(*args, **kwargs)
            finally:
                # A geração permanece na sessão até close: commits não criam uma nova autorização.
                db.info['finance_op'] = op
    return executar


def instalar_eventos(p):
    engine = p.engine
    PROTECOES[engine] = p
    if getattr(engine, '_financeiro_eventos', False):
        return
    engine._financeiro_eventos = True

    @event.listens_for(engine, 'before_cursor_execute')
    def antes_sql(c, cursor, sql, params, context, many):
        if c.info.get('_fin_interno') or sql.lstrip().upper().startswith('ROLLBACK TO SAVEPOINT'):
            return
        op = c.info.get('finance_op') or ATUAL.get()
        import re
        escritas = re.finditer(r'\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(?:"?public"?\.)?"?([a-z_]+)', sql, re.I)
        financeira = any(m.group(1).lower() in TABELAS for m in escritas)
        compiled = getattr(context, 'compiled', None)
        stmt = getattr(compiled, 'statement', None)
        if getattr(stmt, 'is_dml', False):
            financeira = financeira or getattr(getattr(stmt, 'table', None), 'name', None) in TABELAS
        if op is None and financeira:
            sessao = c.info.get('_fin_session')
            if not sessao or sessao() is None:
                raise HTTPException(503, 'Gravação financeira exige uma sessão protegida ou operação explícita.')
            op = PROTECOES[engine].nova_operacao(c)
            sessao().info['finance_op'] = op
        if op is not None:
            c.info['finance_op'] = op
            PROTECOES[engine].bloquear(c, op)

    @event.listens_for(engine, 'after_cursor_execute')
    def depois_sql(c, cursor, sql, params, context, many):
        if sql.lstrip().upper().startswith('ROLLBACK TO SAVEPOINT'):
            c.info.pop('_fin_bloqueado', None)

    @event.listens_for(engine, 'commit')
    def antes_commit(c):
        op = c.info.get('finance_op')
        if op:
            op.verificar()
            op.commit_iniciado = True
        c.info.pop('_fin_bloqueado', None)

    @event.listens_for(engine, 'rollback')
    def rollback(c):
        c.info.pop('_fin_bloqueado', None)

    @event.listens_for(engine, 'rollback_savepoint')
    def rollback_savepoint(c, name, context):
        # Locks obtidos depois de um savepoint podem ser liberados pelo rollback.
        # A próxima instrução precisa validar/reobter a barreira.
        c.info.pop('_fin_bloqueado', None)

    @event.listens_for(engine, 'handle_error')
    def erro(ctx):
        c = ctx.connection
        if c is not None and not c.closed and not c.invalidated:
            op = c.info.get('finance_op')
            if op and (ctx.is_disconnect or op.commit_iniciado):
                op.falhou = True
                # Uma falha de COMMIT não pode devolver ao pool uma conexão cujo
                # estado transacional é incerto. Fechar, verificar e reconciliar.
                ctx.is_disconnect = True

    @event.listens_for(engine.pool, 'checkin')
    def limpar(dbapi, record):
        for key in ('finance_op', '_fin_session', '_fin_bloqueado', '_fin_interno'):
            record.info.pop(key, None)


@event.listens_for(Session, 'after_begin')
def sessao_iniciada(db, txn, c):
    if db.get_bind() not in PROTECOES:
        return
    c.info['_fin_session'] = ref(db)
    op = db.info.get('finance_op') or ATUAL.get()
    if op is not None:
        db.info['finance_op'] = op
        c.info['finance_op'] = op
        PROTECOES[db.get_bind()].bloquear(c, op)


@event.listens_for(Session, 'after_commit')
def commit_confirmado(db):
    op = db.info.get('finance_op')
    if op:
        op.commit_iniciado = False
        op.commits_confirmados += 1


def timeout_financeiro():
    """Limites de conexão/leitura; o prazo também é verificado antes de gravar."""
    op = ATUAL.get()
    if op is None:
        return (5, 20)
    op.verificar()
    restante = max(.001, op.prazo-monotonic())
    return (min(5, restante), min(20, restante))


def esperar_checkout(db, pagamento_id):
    """Espera curta sem reservar conexão; não reenvia criação externa incerta."""
    from time import sleep
    op = ATUAL.get() or db.info.get('finance_op')
    limite = min(monotonic()+3, op.prazo)
    while monotonic() < limite:
        op.verificar()
        row = db.execute(text('SELECT mp_preference_id FROM pagamentos WHERE id=:id'),
                         {'id':pagamento_id}).first()
        pronto = row is not None and row.mp_preference_id is not None
        db.expunge_all()
        db.rollback()
        if pronto:
            return True
        sleep(.05)
    return False


def configuracao_pool():
    """Teto local explícito; capacidade de produção precisa de confirmação externa."""
    import os
    size = int(os.getenv('DB_POOL_SIZE', '5'))
    overflow = int(os.getenv('DB_MAX_OVERFLOW', '0'))
    timeout = float(os.getenv('DB_POOL_TIMEOUT_S', '3'))
    if size < 1 or overflow < 0 or not 0 < timeout <= 30:
        raise ValueError('Pool financeiro exige tamanho positivo, overflow limitado e timeout entre 0 e 30s.')
    return dict(pool_size=size, max_overflow=overflow, pool_timeout=timeout, pool_pre_ping=True)
