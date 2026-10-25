"""Proteção operacional independente dos modelos financeiros 014/015.

A barreira é validada na mesma conexão que grava, em cada transação.
A caixa de entrada contém somente identidade e metadados, nunca payloads/segredos.
"""
from app.admin_intermediario import pode_administrar
import asyncio
import hashlib
import os
import re
from contextlib import contextmanager
from time import monotonic
from threading import BoundedSemaphore
from app.financeiro_transacional import ATUAL, Operacao, instalar_eventos, timeout_financeiro
from datetime import datetime, timezone

import requests
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import (BigInteger, Column, DateTime, Integer, JSON, MetaData,
                        String, Table, ForeignKey, select, text, update)
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

VERSAO = 'pausa-financeira-v2-transacional'
INDISPONIVEL = 'Operações financeiras temporariamente indisponíveis. Seu pagamento não foi rejeitado ou cancelado. Tente novamente após a manutenção.'
metadata = MetaData()
controle = Table('controle_financeiro', metadata,
    Column('id', Integer, primary_key=True), Column('modo', String(16), nullable=False),
    Column('geracao', Integer, nullable=False, server_default='0'),
    Column('alterado_em', DateTime(timezone=True), nullable=False),
    Column('alterado_por', Integer), Column('motivo', String(300), nullable=False))
inbox = Table('notificacoes_mp', metadata,
    Column('id', BigInteger().with_variant(Integer, 'sqlite'), primary_key=True),
    Column('chave', String(160), nullable=False, unique=True),
    Column('payment_id', String(64), nullable=False), Column('fonte', String(16), nullable=False),
    Column('recebida_em', DateTime(timezone=True), nullable=False),
    Column('estado', String(16), nullable=False), Column('tentativas', Integer, nullable=False),
    Column('erro', String(200)), Column('concluida_em', DateTime(timezone=True)),
    Column('resultado', JSON))


# Auditoria específica dos testes históricos; novos eventos nunca herdam isolamento.
IDS_HISTORICOS = (1, 2, 3, 4, 7, 8, 9, 10)
from app.models import Usuario
isolamentos = Table('notificacoes_mp_isolamentos', metadata,
    Column('notificacao_id', BigInteger().with_variant(Integer, 'sqlite'),
           ForeignKey(inbox.c.id), primary_key=True),
    Column('isolada_por', Integer, ForeignKey(Usuario.__table__.c.id), nullable=False),
    Column('isolada_em', DateTime(timezone=True), nullable=False),
    Column('geracao', Integer, nullable=False), Column('motivo', String(300), nullable=False),
    Column('revogada_em', DateTime(timezone=True)),
    Column('revogada_por', Integer, ForeignKey(Usuario.__table__.c.id)),
    Column('motivo_revogacao', String(300)))


def isolamento_ativo():
    return select(isolamentos.c.notificacao_id).where(
        isolamentos.c.notificacao_id == inbox.c.id,
        isolamentos.c.revogada_em.is_(None)).exists().correlate(inbox)


class Isolamento(BaseModel):
    model_config = ConfigDict(extra='forbid')
    geracao: int = Field(ge=0, strict=True)
    motivo: str = Field(min_length=1, max_length=300)


class Modo(BaseModel):
    modo: str = Field(pattern=r'^(NORMAL|PAUSADO|RECUPERACAO)$')
    geracao: int = Field(ge=0)
    motivo: str = Field(min_length=1, max_length=300)
    conferencia_provedor: bool = False


class Recuperar(BaseModel):
    limite: int = Field(default=1, ge=1, le=5)
    notificacao_id: int | None = Field(default=None, gt=0, strict=True)


class Reconciliar(BaseModel):
    inicio: datetime
    fim: datetime
    pagina: int = Field(default=0, ge=0, le=200)


def agora():
    return datetime.now(timezone.utc)


def indisponivel():
    return HTTPException(503, INDISPONIVEL, headers={'Retry-After': '60'})


def financeiro(method, path):
    if method not in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        return False
    return bool(re.fullmatch(
        r'/(?:checkout/mercadopago|pagamentos/confirmar|admin/pagamentos/revalidar|'
        r'me/reembolso/[^/]+|admin/reembolsos/[^/]+/(?:aprovar|recusar|pix-manual|pix-manual/confirmar)|'
        r'admin/acessos|cursos/[^/]+/demonstracao)', path.rstrip('/')))


class Protecao:
    def __init__(self, engine, factory, processor, definitivo=True, consulta=None):
        self.engine = engine
        self.factory = factory
        self.processor = processor
        self.definitivo = definitivo
        self.consulta = consulta
        self.consumidores = BoundedSemaphore(1)
        self.duracao = int(os.getenv('FINANCEIRO_DURACAO_MAXIMA_S', '60'))
        if not 5 <= self.duracao <= 120:
            raise ValueError('FINANCEIRO_DURACAO_MAXIMA_S deve estar entre 5 e 120.')
        instalar_eventos(self)

    def nova_operacao(self, c, recuperacao=False):
        c.info['_fin_interno'] = True
        try:
            row = c.execute(select(controle).where(controle.c.id == 1)).mappings().one()
            modo = 'RECUPERACAO' if recuperacao else 'NORMAL'
            if row['modo'] != modo or (recuperacao and not self.definitivo):
                raise indisponivel()
            return Operacao(self, modo, row['geracao'], monotonic()+self.duracao)
        finally:
            c.info.pop('_fin_interno', None)

    def bloquear(self, c, op):
        op.verificar()
        if c.dialect.name == 'postgresql' and c.connection.driver_connection.autocommit:
            op.falhou = True
            raise HTTPException(503, 'Gravações financeiras exigem transação; autocommit não é permitido.')
        if c.info.get('_fin_bloqueado'):
            return
        c.info['_fin_interno'] = True
        try:
            if c.dialect.name == 'postgresql':
                # Recuperação: um consumidor por transação, coordenado entre instâncias.
                ms = max(1, min(3000, int((op.prazo-monotonic())*1000)))
                c.execute(text(f"SET LOCAL lock_timeout='{ms}ms'"))
                c.execute(text(f"SET LOCAL statement_timeout='{max(1,int((op.prazo-monotonic())*1000))}ms'"))
            q = select(controle).where(controle.c.id == 1)
            if c.dialect.name == 'postgresql':
                q = q.with_for_update(read=op.modo == 'NORMAL')
            row = c.execute(q).mappings().one()
            if (row['modo'], row['geracao']) != (op.modo, op.geracao):
                op.falhou = True
                raise indisponivel()
            c.info['_fin_bloqueado'] = True
        except SQLAlchemyError:
            op.falhou = True
            raise indisponivel() from None
        finally:
            c.info.pop('_fin_interno', None)

    @contextmanager
    def lease(self, recuperacao=False, db=None):
        # Nome preservado para os chamadores: não existe conexão de lease.
        existente = ATUAL.get()
        if existente:
            existente.verificar()
            yield existente
            return
        try:
            if db is None:
                with self.engine.connect() as c:
                    op = self.nova_operacao(c, recuperacao)
            else:
                c = db.connection()
                op = self.nova_operacao(c, recuperacao)
                c.info['finance_op'] = op
            token = ATUAL.set(op)
            try:
                yield op
            finally:
                ATUAL.reset(token)
        except SQLAlchemyError:
            raise indisponivel() from None

    def estado(self):
        with self.engine.connect() as c:
            row = dict(c.execute(select(controle).where(controle.c.id == 1)).mappings().one())
            row['versao_protecao'] = VERSAO
            row['backend_definitivo'] = self.definitivo
            row['commit_implantado'] = os.getenv('RENDER_GIT_COMMIT', 'não informado')
            row['schema_financeiro_pronto'] = self.schema_pronto(c)
            return row

    @staticmethod
    def schema_pronto(c):
        if c.dialect.name != 'postgresql':
            return True  # Somente testes SQLite; produção usa PostgreSQL.
        colunas = c.execute(text("""SELECT count(*)=3 FROM information_schema.columns
            WHERE table_schema='public' AND
            ((table_name='pagamentos' AND column_name IN ('pagamento_origem_id','mp_status'))
             OR (table_name='reembolsos_financeiros' AND column_name='confirmado_por'))""")).scalar()
        if not colunas:
            return False
        return c.execute(text("""SELECT
            EXISTS (SELECT FROM pg_constraint WHERE conrelid='public.pagamentos'::regclass
                AND conname='fk_pagamentos_origem' AND contype='f' AND convalidated)
            AND EXISTS (SELECT FROM pg_index WHERE indexrelid=to_regclass('public.uq_pagamentos_mp_payment_id')
                AND indisunique AND indisvalid)
            AND EXISTS (SELECT FROM pg_trigger WHERE tgrelid='public.pagamentos'::regclass
                AND tgname='validar_origem_transacao_pagamento' AND tgenabled='O' AND NOT tgisinternal)
            AND EXISTS (SELECT FROM pg_constraint WHERE conrelid='public.reembolsos_financeiros'::regclass
                AND conname='fk_reembolso_confirmado_por' AND contype='f' AND convalidated)""")).scalar()

    def mudar(self, payload, admin_id):
        with self.engine.begin() as c:
            if c.dialect.name == 'postgresql':
                c.execute(text("SET LOCAL lock_timeout='5s'"))
                c.execute(text("SET LOCAL statement_timeout='15s'"))
            row = c.execute(select(controle).where(controle.c.id == 1)
                .with_for_update()).mappings().one()
            if row['geracao'] != payload.geracao:
                raise HTTPException(409, 'O estado mudou. Consulte novamente antes de confirmar.')
            if payload.modo == 'RECUPERACAO' and (not self.definitivo or not self.schema_pronto(c)):
                raise HTTPException(409, 'Aplicar e validar 014/015 antes da recuperação.')
            if payload.modo == 'NORMAL':
                if row['modo'] != 'NORMAL' and not payload.conferencia_provedor:
                    raise HTTPException(409, 'Conferir notificações e transações no provedor antes de reabrir.')
                pendentes = c.execute(select(inbox.c.id).where(inbox.c.estado != 'CONCLUIDO',
                    ~isolamento_ativo() if self.definitivo else text('TRUE')).limit(1)).first()
                if pendentes:
                    raise HTTPException(409, 'Há notificações pendentes ou com erro. Concluir a recuperação antes de reabrir.')
            c.execute(update(controle).where(controle.c.id == 1).values(
                modo=payload.modo, geracao=row['geracao']+1, alterado_em=agora(),
                alterado_por=admin_id, motivo=payload.motivo))
        return self.estado()

    def auditar_isolamento(self, payload, admin_id, revogar_id=None):
        # Mesma ordem da recuperação: barreira financeira, depois notificações.
        if not self.definitivo or not payload.motivo.strip():
            raise HTTPException(409, 'Backend definitivo e motivo explícito são obrigatórios.')
        if revogar_id is not None and revogar_id not in IDS_HISTORICOS:
            raise HTTPException(422, 'ID fora do isolamento histórico autorizado.')
        with self.engine.begin() as c:
            op = self.nova_operacao(c, True)
            c.info['finance_op'] = op
            self.bloquear(c, op)
            if op.geracao != payload.geracao:
                raise HTTPException(409, 'Geração financeira divergente.')
            ids = [revogar_id] if revogar_id is not None else list(IDS_HISTORICOS)
            rows = c.execute(select(inbox).where(inbox.c.id.in_(ids))
                .order_by(inbox.c.id).with_for_update()).mappings().all()
            if len(rows) != len(ids):
                raise HTTPException(409, 'Conjunto histórico incompleto; nenhum isolamento aplicado.')
            if revogar_id is not None:
                audit = c.execute(select(isolamentos).where(
                    isolamentos.c.notificacao_id == revogar_id)).mappings().first()
                if audit is None:
                    raise HTTPException(404, 'Isolamento não encontrado.')
                if audit['revogada_em'] is None:
                    c.execute(update(isolamentos).where(isolamentos.c.notificacao_id == revogar_id)
                        .values(revogada_em=agora(), revogada_por=admin_id,
                                motivo_revogacao=payload.motivo.strip()))
            else:
                if any(r['estado'] not in ('PENDENTE', 'ERRO') for r in rows):
                    raise HTTPException(409, 'Só pendências históricas podem ser isoladas.')
                for ident in ids:
                    audit = c.execute(select(isolamentos).where(
                        isolamentos.c.notificacao_id == ident)).mappings().first()
                    if audit is not None:
                        if audit['revogada_em'] is not None:
                            raise HTTPException(409, 'Isolamento revogado; não será reaplicado.')
                        continue  # Repetição preserva administrador, data e motivo originais.
                    c.execute(isolamentos.insert().values(notificacao_id=ident,
                        isolada_por=admin_id, isolada_em=agora(), geracao=op.geracao,
                        motivo=payload.motivo.strip()))
            op.verificar()
        return {'ids': ids, 'revogado': revogar_id is not None, 'geracao': payload.geracao}

    def armazenar(self, payment_id, chave, fonte, metadados=None):
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        insert = pg_insert if self.engine.dialect.name == 'postgresql' else sqlite_insert
        with self.engine.begin() as c:
            if chave.startswith('c:'):
                from app.contestacoes import travar_escopo
                travar_escopo(c, payment_id)
            c.execute(insert(inbox).values(chave=chave, payment_id=payment_id, fonte=fonte,
                recebida_em=agora(), estado='PENDENTE', tentativas=0, resultado=metadados)
                .on_conflict_do_nothing(index_elements=['chave']))
            row = c.execute(select(inbox.c.id, inbox.c.payment_id).where(inbox.c.chave == chave)).one()
            if row.payment_id != payment_id:
                raise HTTPException(409, 'Identidade da notificação incompatível.')
            return row.id

    def processar(self, ident, recuperacao=False, prazo=None):
        if not self.consumidores.acquire(blocking=False):
            raise indisponivel()
        try:
            return self._processar(ident, recuperacao, prazo)
        finally:
            self.consumidores.release()

    def _processar(self, ident, recuperacao, prazo):
        from app.diagnostico_financeiro import contexto
        with contexto(ident):
            return self._processar_notificacao(ident, recuperacao, prazo)

    def _processar_notificacao(self, ident, recuperacao, prazo):
        with self.lease(recuperacao) as op:
            if prazo is not None:
                op.prazo = min(op.prazo, prazo)
            try:
                with self.engine.connect() as conn:
                    chave = conn.execute(select(inbox.c.chave).where(inbox.c.id == ident)).scalar()
                if chave and chave.startswith('c:'):
                    from app.contestacoes import processar_pendente
                    return processar_pendente(ident, self, op)
                # Consulta externa antes de qualquer lock da transação financeira.
                resposta = None
                if self.consulta is not None:
                    with self.engine.connect() as c:
                        row = c.execute(select(inbox.c.payment_id).where(inbox.c.id == ident,
                            ~isolamento_ativo() if self.definitivo else text('TRUE'))).first()
                    if row is None:
                        return {'id':ident, 'processado':False}
                    resposta = self.consulta(row.payment_id)
                op.verificar()
                with self.factory() as db:
                    db.info['finance_op'] = op
                    db.info['finance_unidade_atomica'] = True
                    # A própria transação financeira reivindica a notificação.
                    row = db.execute(select(inbox).where(inbox.c.id == ident,
                        ~isolamento_ativo() if self.definitivo else text('TRUE'))
                        .with_for_update(skip_locked=True)).mappings().first()
                    if row is None or row['estado'] == 'CONCLUIDO':
                        db.rollback()
                        return {'id': ident, 'processado': False}
                    tentativas = row['tentativas']+1
                    real_commit = db.commit
                    # Os commits do processador tornam-se flush nesta unidade atômica.
                    # A conclusão da fila e o efeito financeiro têm um único commit.
                    db.commit = db.flush
                    resultado = (self.processor(row['payment_id'], db, resposta_mp=resposta)
                        if resposta is not None else self.processor(row['payment_id'], db))
                    if resultado.get('ok') is not True:
                        raise HTTPException(409, 'Processamento financeiro não confirmado.')
                    if resultado.get('ignored') and resultado.get('msg') != 'Notificação pendente recebida após aprovação':
                        raise HTTPException(409, 'Transação exige análise; processamento não confirmado.')
                    resumo = {k: resultado[k] for k in ('status','mp_status','liberou_acesso',
                        'ocorrencia_financeira','ignored') if k in resultado}
                    db.execute(update(inbox).where(inbox.c.id == ident).values(
                        estado='CONCLUIDO', tentativas=tentativas, erro=None,
                        concluida_em=agora(), resultado=resumo))
                    op.verificar()
                    real_commit()
                    return {'id':ident, 'processado':True, **resumo}
            except Exception as exc:
                from app.diagnostico_financeiro import resumo
                resumo()
                # Nunca retomar o domínio nesta execução, inclusive após rollback.
                # Resultado incerto de commit continua elegível para reconciliação.
                codigo = exc.status_code if isinstance(exc, HTTPException) else 500
                token = ATUAL.set(None)
                try:
                    with self.engine.begin() as c:
                        c.execute(select(inbox.c.id).where(inbox.c.id == ident).with_for_update()).first()
                        c.execute(update(inbox).where(inbox.c.id == ident, inbox.c.estado != 'CONCLUIDO',
                            ~isolamento_ativo() if self.definitivo else text('TRUE'))
                            .values(estado='ERRO', tentativas=inbox.c.tentativas+1,
                                erro=f'Falha de processamento ({codigo}); verificar e reconciliar antes de repetir.'))
                except SQLAlchemyError:
                    pass  # Sem confirmação: a linha original permanece recuperável.
                finally:
                    ATUAL.reset(token)
                return {'id':ident, 'processado':False, 'erro_codigo':codigo}

    def recuperar(self, limite, prazo=None, notificacao_id=None):
        if not self.definitivo:
            raise HTTPException(409, 'Recuperação exige o backend definitivo após 014/015.')
        if not 1 <= limite <= 5:
            raise HTTPException(422, 'Utilize lotes de um a cinco eventos.')
        if notificacao_id is not None and (type(notificacao_id) is not int or notificacao_id <= 0):
            raise HTTPException(422, 'Informe um ID de notificação positivo.')
        consulta = select(inbox.c.id).where(inbox.c.estado != 'CONCLUIDO',
            ~isolamento_ativo())
        if notificacao_id is not None:
            consulta = consulta.where(inbox.c.id == notificacao_id)
        with self.engine.connect() as c:
            ids = list(c.execute(consulta.order_by(inbox.c.id).limit(limite)).scalars())
        prazo = min(prazo, monotonic()+self.duracao) if prazo is not None else monotonic()+self.duracao
        resultados = []
        for ident in ids:
            if monotonic() >= prazo:
                break
            resultados.append(self.processar(ident, True, prazo))
        return {'resultados':resultados, 'interrompido_por_prazo':len(resultados)<len(ids)}

    def reconciliar(self, payload, headers):
        # Pesquisa independente da existência de um pagamento local individual.
        # Uma página por chamada: progresso e cobertura permanecem verificáveis.
        if payload.inicio.tzinfo is None or payload.fim.tzinfo is None:
            raise HTTPException(400, 'Informe início e fim com fuso horário.')
        if payload.inicio >= payload.fim or (payload.fim-payload.inicio).total_seconds() > 7*86400:
            raise HTTPException(400, 'Janela inválida; limite de sete dias por pesquisa.')
        with self.lease(True):
            if not self.definitivo:
                raise HTTPException(409, 'Reconciliação exige o backend definitivo.')
            offset = payload.pagina*50
            try:
                r = requests.get('https://api.mercadopago.com/v1/payments/search', headers=headers,
                    params={'range':'date_last_updated','begin_date':payload.inicio.isoformat(timespec='milliseconds'),
                        'end_date':payload.fim.isoformat(timespec='milliseconds'),'sort':'date_last_updated','criteria':'asc',
                        'offset':offset,'limit':50}, timeout=timeout_financeiro())
                if r.status_code != 200:
                    raise HTTPException(502, 'Não foi possível pesquisar transações no provedor.')
                data = r.json()
                items, paging = data['results'], data['paging']
                total = int(paging['total'])
                if (not isinstance(items, list) or len(items)>50 or int(paging['offset']) != offset
                    or int(paging['limit']) != 50 or total < 0 or (not items and offset<total)):
                    raise ValueError()
                ids = [str(p['id']) for p in items]
                if any(not re.fullmatch(r'[0-9]{1,64}', pid) for pid in ids):
                    raise ValueError()
                if total>10050:
                    raise HTTPException(409, 'Pesquisa excede a paginação do provedor. Divida a janela e recomece.')
            except (requests.RequestException, ValueError, KeyError, TypeError):
                raise HTTPException(502, 'Resposta de pesquisa inválida ou indisponível.') from None
            janela = f'{payload.inicio.isoformat()}|{payload.fim.isoformat()}'
            prefixo = hashlib.sha256(janela.encode()).hexdigest()
            recebidos = [self.armazenar(pid, f'r:{prefixo}:{pid}', 'RECONCILIACAO') for pid in ids]
            return {'pagina':payload.pagina, 'total_provedor':total, 'armazenadas':len(recebidos),
                'proxima_pagina':payload.pagina+1 if offset+len(ids)<total else None,
                'conferencia_provedor_obrigatoria':True}


class GateMiddleware:
    def __init__(self, app, protecao):
        self.app, self.protecao = app, protecao

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not financeiro(scope['method'], scope['path']):
            return await self.app(scope, receive, send)
        def capturar():
            with self.protecao.engine.connect() as c:
                return self.protecao.nova_operacao(c)
        try:
            op = await run_in_threadpool(capturar)
        except (HTTPException, SQLAlchemyError) as exc:
            erro = exc if isinstance(exc, HTTPException) else indisponivel()
            return await JSONResponse({'detail':erro.detail}, status_code=erro.status_code,
                headers=erro.headers)(scope, receive, send)
        token = ATUAL.set(op)
        try:
            await self.app(scope, receive, send)
        finally:
            ATUAL.reset(token)


def instalar(app, engine, factory, get_db, get_usuario_atual, assinatura, processor, headers, definitivo=True, consulta=None):
    from fastapi import Request
    protecao = Protecao(engine, factory, processor, definitivo, consulta)
    app.state.protecao_financeira = protecao
    protecao.headers_contestacoes = headers
    # Colocar dentro do CORS: respostas 503 mantêm os mesmos headers de origem.
    from starlette.middleware import Middleware
    app.user_middleware.append(Middleware(GateMiddleware, protecao=protecao))

    if engine.dialect.name == 'postgresql':
        def validar_inicio():
            with engine.connect() as c:
                if definitivo and not protecao.schema_pronto(c):
                    raise RuntimeError('Backend definitivo exige migrations 014 e 015 validadas antes da publicação.')
                c.execute(select(controle.c.id).where(controle.c.id == 1)).one()
                permissoes = c.execute(text("""SELECT
                    has_table_privilege(current_user,'public.controle_financeiro','SELECT')
                    AND has_table_privilege(current_user,'public.controle_financeiro','UPDATE')
                    AND has_table_privilege(current_user,'public.notificacoes_mp','SELECT')
                    AND has_table_privilege(current_user,'public.notificacoes_mp','INSERT')
                    AND has_table_privilege(current_user,'public.notificacoes_mp','UPDATE')""")).scalar()
                if definitivo:
                    c.execute(select(isolamentos.c.notificacao_id).limit(0))
                    permissoes = permissoes and c.execute(text("SELECT has_table_privilege(current_user,'public.notificacoes_mp_isolamentos','SELECT') AND has_table_privilege(current_user,'public.notificacoes_mp_isolamentos','INSERT') AND has_table_privilege(current_user,'public.notificacoes_mp_isolamentos','UPDATE')")).scalar()
                if not permissoes:
                    raise RuntimeError('Backend exige permissões operacionais das migrations 016/018.')
        app.router.add_event_handler('startup', validar_inicio)

    def admin(usuario=Depends(get_usuario_atual), db=Depends(get_db)):
        if not pode_administrar(usuario, "geral"):
            raise HTTPException(403, 'Apenas administrador.')
        if hasattr(db, 'expunge') and hasattr(usuario, '_sa_instance_state'):
            db.expunge(usuario)
        db.rollback()
        return usuario

    @app.get('/admin/financeiro/manutencao')
    def estado(usuario=Depends(admin)):
        try:
            return protecao.estado()
        except SQLAlchemyError:
            raise indisponivel() from None

    @app.post('/admin/financeiro/manutencao')
    def mudar(payload: Modo, usuario=Depends(admin)):
        try:
            return protecao.mudar(payload, usuario.id)
        except SQLAlchemyError:
            raise HTTPException(503, 'Não foi possível concluir a drenagem ou consultar o controle; a pausa não foi confirmada.') from None

    @app.get('/admin/financeiro/notificacoes')
    def listar(usuario=Depends(admin)):
        with engine.connect() as c:
            rows = c.execute(select(inbox.c.estado, text('count(*) AS quantidade'))
                .group_by(inbox.c.estado)).mappings().all()
            pendencias = c.execute(select(inbox.c.id, inbox.c.payment_id, inbox.c.fonte,
                inbox.c.estado, inbox.c.tentativas, inbox.c.erro, inbox.c.recebida_em,
                isolamento_ativo().label('isolada'))
                .where(inbox.c.estado != 'CONCLUIDO').order_by(inbox.c.id).limit(100)).mappings().all()
        with engine.connect() as c:
            auditoria = c.execute(select(isolamentos).order_by(isolamentos.c.notificacao_id)).mappings().all()
        return {'isolamentos':[dict(r) for r in auditoria], 'contagens':[dict(r) for r in rows], 'pendencias':[dict(r) for r in pendencias],
            'cobertura_provedor_confirmada':False}

    @app.post('/admin/financeiro/notificacoes/isolamento')
    def isolar(payload: Isolamento, usuario=Depends(admin)):
        return protecao.auditar_isolamento(payload, usuario.id)

    @app.post('/admin/financeiro/notificacoes/{notificacao_id}/isolamento/revogar')
    def revogar(notificacao_id: int, payload: Isolamento, usuario=Depends(admin)):
        return protecao.auditar_isolamento(payload, usuario.id, notificacao_id)

    @app.post('/admin/financeiro/notificacoes/recuperar')
    async def recuperar(payload: Recuperar, usuario=Depends(admin)):
        prazo = monotonic()+protecao.duracao
        tarefa = asyncio.create_task(asyncio.to_thread(protecao.recuperar, payload.limite, prazo, payload.notificacao_id))
        # O thread pode terminar uma consulta externa, mas o prazo compartilhado
        # impede novas gravações/commits. Não cancelar e abandonar uma transação.
        tarefa.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
        try:
            return await asyncio.wait_for(asyncio.shield(tarefa), timeout=protecao.duracao)
        except TimeoutError:
            raise HTTPException(503, 'Prazo da recuperação atingido. Consulte a fila antes de repetir.') from None

    @app.post('/admin/financeiro/notificacoes/reconciliar')
    def reconciliar(payload: Reconciliar, usuario=Depends(admin)):
        return protecao.reconciliar(payload, headers())

    # Substituir somente o handler HTTP; o processador financeiro original é
    # reutilizado pelos consumidores e testes de domínio.
    async def receber(request: Request):
        pid = request.query_params.get('data.id', '')
        if not re.fullmatch(r'[0-9]{1,64}', pid) or not assinatura(request, pid):
            raise HTTPException(401, 'Assinatura do Mercado Pago inválida.')
        try:
            tipo_query = request.query_params.get('type')
            try:
                data = await request.json()
            except ValueError:
                if tipo_query not in ('topic_chargebacks_wh', 'chargebacks'):
                    raise
                data = {'type':tipo_query, 'data':None}
            tipo = (data.get('type') or tipo_query) if isinstance(data, dict) else tipo_query
            if tipo in ('topic_chargebacks_wh', 'chargebacks') and not isinstance(data, dict):
                data = {'type':tipo, 'data':None}
            if tipo in ('topic_chargebacks_wh', 'chargebacks'):
                evento = str(data.get('id') or request.headers.get('x-request-id') or '')
                # Mesmo envelope inconclusivo é persistido: chave baseada em
                # identificadores, sem armazenar payloads, tokens ou assinatura.
                identidade_valida = bool(evento) and len(evento) <= 200
                if not identidade_valida:
                    # Não fundir recebimentos sem identidade com um evento
                    # concluído anteriormente, nem usá-los como comprovação.
                    from uuid import uuid4
                    evento = uuid4().hex
                valido = identidade_valida and isinstance(data.get('data'), dict) and str(data['data'].get('id')) == pid
                digest = hashlib.sha256(f'{pid}|{evento}'.encode()).hexdigest()
                ident = await run_in_threadpool(protecao.armazenar, pid, f'c:{digest}', 'WEBHOOK',
                    {'tipo':'CONTESTACAO', 'envelope_valido':valido,
                     'escopo':'CONFERENCIA_NECESSARIA'})
                try:
                    resultado = await run_in_threadpool(protecao.processar, ident)
                except HTTPException as exc:
                    if exc.status_code != 503:
                        raise
                    resultado = {'processado':False}
                return {'ok':True, 'armazenado':True, **resultado}
            if not isinstance(data, dict) or tipo != 'payment':
                raise HTTPException(400, 'Tipo de notificação inválido.')
            if str((data.get('data') or {}).get('id')) != pid:
                raise HTTPException(400, 'Identificador da notificação incompatível.')
            evento = str(data.get('id') or request.headers.get('x-request-id') or '')
            if not evento or len(evento) > 200:
                raise HTTPException(400, 'Identidade do evento ausente ou inválida.')
            # Identidade do evento, não só do pagamento: atualizações distintas
            # continuam aptas a atualizar o estado financeiro.
            digest = hashlib.sha256(f'{pid}|{evento}'.encode()).hexdigest()
            ident = await run_in_threadpool(protecao.armazenar, pid, f'w:{digest}', 'WEBHOOK')
        except SQLAlchemyError:
            raise HTTPException(503, 'Notificação não armazenada; tentar novamente.') from None
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(400, 'Notificação inválida.') from None
        resultado = {'processado':False}
        try:
            resultado = await run_in_threadpool(protecao.processar, ident)
        except HTTPException as exc:
            if exc.status_code != 503:
                raise
        return {'ok':True, 'armazenado':True, **resultado}

    route = next(r for r in app.routes if getattr(r, 'path', None) == '/webhooks/mercadopago')
    from fastapi.routing import APIRoute
    replacement = APIRoute('/webhooks/mercadopago', receber, methods=['POST'])
    app.routes[app.routes.index(route)] = replacement
    return protecao
