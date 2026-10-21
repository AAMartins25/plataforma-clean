"""Comunicações pós-commit: não escreve em tabelas financeiras nem cria cobranças."""
import base64
import hashlib
import html
import json
import logging
import os
import re
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from email.utils import parseaddr
from threading import Event, Thread, Lock
from urllib.parse import urlsplit, parse_qsl

import requests
from sqlalchemy import (MetaData, Table, Column, Integer, String, DateTime, JSON,
                        ForeignKey, select, update, and_, or_, func)
from sqlalchemy.orm import aliased
from app import models as m
from app.checkout_seguro import validar_identidade

log = logging.getLogger(__name__)
metadata = MetaData()
fila = Table('emails_pagamentos', metadata,
    Column('pagamento_id', Integer, ForeignKey(m.Pagamento.__table__.c.id), primary_key=True),
    Column('tipo', String(10), primary_key=True),
    Column('estado', String(20), nullable=False),
    Column('criado_em', DateTime(timezone=True), nullable=False),
    Column('proxima_consulta_em', DateTime(timezone=True), nullable=False),
    Column('lease_ate', DateTime(timezone=True)), Column('lease_token', String(64)),
    Column('tentativas', Integer, nullable=False),
    Column('primeiro_envio_em', DateTime(timezone=True)),
    Column('payload', JSON), Column('payload_hash', String(64)),
    Column('aceito_em', DateTime(timezone=True)), Column('provedor_id', String(100)),
    Column('erro_codigo', String(40)))


def agora():
    return datetime.now(timezone.utc)


def tz(d):
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


def data_iso(valor):
    if not isinstance(valor, str):
        raise ValueError('data_invalida')
    d = datetime.fromisoformat(valor.replace('Z', '+00:00'))
    if d.tzinfo is None:
        raise ValueError('data_sem_fuso')
    return tz(d)


def hash_payload(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                         separators=(',', ':')).encode()).hexdigest()


def reais(cents):
    return 'R$ ' + f'{Decimal(cents)/100:.2f}'.replace('.', ',')


@dataclass(frozen=True)
class Config:
    ativa: bool = False
    desde: datetime | None = None
    remetente: str = ''
    resend_key: str = field(default='', repr=False)
    intervalo: int = 30
    lote: int = 3

    @classmethod
    def ambiente(cls):
        if os.getenv('EMAILS_PAGAMENTOS_ATIVOS', '').lower() != 'true':
            return cls()
        try:
            desde = data_iso(os.getenv('EMAILS_PAGAMENTOS_DESDE', ''))
            remetente = os.getenv('RESEND_FROM_EMAIL', '')
            email = parseaddr(remetente)[1]
            if ('\r' in remetente or '\n' in remetente or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', email)
                or not os.getenv('RESEND_API_KEY')):
                raise ValueError()
            intervalo = int(os.getenv('EMAILS_PAGAMENTOS_INTERVALO_S', '30'))
            lote = int(os.getenv('EMAILS_PAGAMENTOS_LOTE', '3'))
            if not 15 <= intervalo <= 300 or not 1 <= lote <= 5:
                raise ValueError()
            return cls(True, desde, remetente, os.getenv('RESEND_API_KEY'), intervalo, lote)
        except Exception:
            log.warning('etapa=email_pagamento categoria=configuracao_invalida')
            return cls()


class Invalido(Exception):
    pass


def exigir(valor):
    if not valor:
        raise Invalido()


def metodo(d):
    ident, tipo = d.get('payment_method_id'), d.get('payment_type_id')
    if ident == 'pix':
        return 'Pix'
    if tipo == 'ticket':
        return 'Boleto'
    nomes = {'credit_card': 'Cartão de crédito', 'debit_card': 'Cartão de débito',
             'account_money': 'Saldo Mercado Pago', 'bank_transfer': 'Transferência bancária'}
    if tipo in nomes:
        return nomes[tipo]
    exigir(isinstance(ident, str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,40}', ident))
    return 'Outra modalidade (' + ident + ')'


def dv10(s):
    soma = sum(sum(divmod(int(v) * (2 if i % 2 == 0 else 1), 10))
               for i, v in enumerate(reversed(s)))
    return str((10 - soma % 10) % 10)


def boleto_linha(valor, cents):
    exigir(isinstance(valor, str) and len(valor) <= 100 and re.fullmatch(r'[0-9.\s]+', valor))
    s = re.sub(r'[^0-9]', '', valor)
    if len(s) == 47:
        exigir(s[9] == dv10(s[:9]) and s[20] == dv10(s[10:20]) and s[31] == dv10(s[21:31]))
        b = s[:4] + s[32] + s[33:47] + s[4:9] + s[10:20] + s[21:31]
    else:
        exigir(len(s) == 44)
        b = s
    sem_dv = b[:4] + b[5:]
    soma = sum(int(v) * (2 + i % 8) for i, v in enumerate(reversed(sem_dv)))
    dv = 11 - soma % 11
    exigir(b[4] == str(1 if dv in (0, 10, 11) else dv) and b[3] == '9' and int(b[9:19]) == cents)
    c1, c2, c3 = b[:4] + b[19:24], b[24:34], b[34:44]
    return c1 + dv10(c1) + c2 + dv10(c2) + c3 + dv10(c3) + b[4] + b[5:19]


def instrucoes(d, cents, clock):
    exigir(d.get('status') == 'pending')
    # Sem vencimento confiável, não afirmar que a cobrança ainda está válida.
    vencimento = data_iso(d.get('date_of_expiration'))
    exigir(vencimento > clock())
    modo = metodo(d)
    if modo == 'Pix':
        td = (d.get('point_of_interaction') or {}).get('transaction_data') or {}
        codigo, imagem = td.get('qr_code'), td.get('qr_code_base64')
        exigir(isinstance(codigo, str) and 20 <= len(codigo) <= 2048 and codigo.startswith('000201')
               and re.fullmatch(r'[0-9A-Fa-f]{4}', codigo[-4:]) and codigo[-8:-4] == '6304')
        crc = 0xFFFF
        for byte in codigo[:-4].encode():
            crc ^= byte << 8
            for _ in range(8):
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
        exigir(f'{crc:04X}' == codigo[-4:].upper())
        campos, pos = {}, 0
        while pos < len(codigo):
            exigir(pos+4 <= len(codigo) and codigo[pos:pos+4].isdigit())
            tag, tamanho = codigo[pos:pos+2], int(codigo[pos+2:pos+4])
            pos += 4
            exigir(pos+tamanho <= len(codigo) and tag not in campos)
            campos[tag] = codigo[pos:pos+tamanho]
            pos += tamanho
        exigir(campos.get('53') == '986')
        if '54' in campos:
            exigir(Decimal(campos['54'])*100 == cents)

        exigir(isinstance(imagem, str) and len(imagem) <= 2_000_000)
        png = base64.b64decode(imagem, validate=True)
        exigir(len(png) >= 33 and png[:8] == b'\x89PNG\r\n\x1a\n' and png[12:16] == b'IHDR')
        largura, altura = int.from_bytes(png[16:20], 'big'), int.from_bytes(png[20:24], 'big')
        exigir(0 < largura <= 4096 and 0 < altura <= 4096)
        pos, chunks = 8, []
        while pos < len(png):
            exigir(pos+12 <= len(png))
            tamanho = int.from_bytes(png[pos:pos+4], 'big')
            fim = pos+8+tamanho
            exigir(fim+4 <= len(png))
            tag = png[pos+4:pos+8]
            exigir(zlib.crc32(png[pos+4:fim]) == int.from_bytes(png[fim:fim+4], 'big'))
            chunks.append(tag)
            pos = fim+4
            if tag == b'IEND':
                exigir(tamanho == 0 and pos == len(png))
                break
        exigir(chunks[0] == b'IHDR' and chunks[-1] == b'IEND' and b'IDAT' in chunks)

        return {'modo': modo, 'vencimento': vencimento.isoformat(), 'codigo': codigo, 'imagem': imagem}
    exigir(modo == 'Boleto')
    td = d.get('transaction_details') or {}
    linha = boleto_linha((d.get('barcode') or {}).get('content'), cents)
    link = td.get('external_resource_url')
    exigir(isinstance(link, str) and len(link) <= 2048)
    u = urlsplit(link)
    exigir(u.scheme == 'https' and u.hostname in {'mercadopago.com', 'www.mercadopago.com',
           'mercadopago.com.br', 'www.mercadopago.com.br'} and not u.username and not u.password
           and u.port in (None, 443) and not u.fragment
           and not any(k.lower() in {'access_token', 'authorization', 'password', 'api_key'}
                       for k, v in parse_qsl(u.query)))
    return {'modo': modo, 'vencimento': vencimento.isoformat(), 'codigo': linha, 'link': link}


class EmailsPagamentos:
    def __init__(self, engine, factory, headers_mp, config=None, clock=agora):
        self.engine, self.factory, self.headers_mp = engine, factory, headers_mp
        self.config, self.clock = config or Config.ambiente(), clock
        self.parar = Event()
        self.thread = None
        self.local = Lock()

    def normal(self):
        with self.engine.connect() as c:
            from app.pausa_financeira import controle
            return c.execute(select(controle.c.modo).where(controle.c.id == 1)).scalar() == 'NORMAL'

    def descobrir(self):
        if not self.config.ativa or not self.normal():
            return
        raiz = aliased(m.Pagamento)
        for tipo, estados in (('PENDENTE', ('PENDING', 'PENDENTE', 'IN_PROCESS')),
                              ('APROVADO', ('APPROVED',))):
            with self.factory() as db:
                ids = list(db.query(m.Pagamento.id).join(raiz,
                    raiz.id == func.coalesce(m.Pagamento.pagamento_origem_id, m.Pagamento.id))
                    .filter(raiz.checkout_identidade.isnot(None), raiz.mp_preference_id.isnot(None),
                            raiz.criado_em >= self.config.desde.replace(tzinfo=None),
                            m.Pagamento.mp_payment_id.isnot(None), m.Pagamento.status.in_(estados),
                            m.Pagamento.ocorrencia_financeira.is_(None),
                            ~select(fila.c.pagamento_id).where(fila.c.pagamento_id == m.Pagamento.id,
                                fila.c.tipo == tipo).exists())
                    .order_by(m.Pagamento.id).limit(self.config.lote).all())
                ids = [row[0] for row in ids]
            for pid in ids:
                from sqlalchemy.dialects.postgresql import insert as pg_insert
                from sqlalchemy.dialects.sqlite import insert as sqlite_insert
                insert = pg_insert if self.engine.dialect.name == 'postgresql' else sqlite_insert
                with self.engine.begin() as c:
                    c.execute(insert(fila).values(pagamento_id=pid, tipo=tipo, estado='DADOS_PENDENTES',
                        criado_em=self.clock(), proxima_consulta_em=self.clock(), tentativas=0)
                        .on_conflict_do_nothing(index_elements=['pagamento_id', 'tipo']))

    def contexto(self, pid):
        with self.factory() as db:
            p = db.get(m.Pagamento, pid)
            exigir(p is not None and p.mp_payment_id and p.ocorrencia_financeira is None)
            exigir(db.query(m.ContestacaoPagamento.id).filter_by(pagamento_id=pid).first() is None)
            exigir(db.query(m.ReembolsoFinanceiro.id).filter(
                m.ReembolsoFinanceiro.pagamento_id==pid,
                m.ReembolsoFinanceiro.status.in_(['PENDENTE','EM_PROCESSAMENTO','CONFIRMADO','VERIFICACAO_NECESSARIA']))
                .first() is None)
            raiz = db.get(m.Pagamento, p.pagamento_origem_id or p.id)
            exigir(raiz is not None and raiz.checkout_identidade and raiz.mp_preference_id
                   and raiz.criado_em is not None and raiz.criado_em >= self.config.desde.replace(tzinfo=None))
            campos = ('usuario_id','curso_id','tempo_acesso_id','oportunidade_id','valor_cents',
                      'mp_preference_id','tipo_compra','codigo_cupom','vendedor_id','qr_code_id',
                      'vencimento_original','moeda','provedor')
            exigir(all(getattr(p,k) == getattr(raiz,k) for k in campos))
            usuario, curso = db.get(m.Usuario,p.usuario_id), db.get(m.Curso,p.curso_id)
            op = db.get(m.OportunidadeCompra,p.oportunidade_id)
            exigir(usuario and curso and op and (op.usuario_id,op.curso_id,op.tipo_compra) ==
                   (p.usuario_id,p.curso_id,p.tipo_compra))
            exigir(isinstance(usuario.email,str) and re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',usuario.email))
            periodo = db.query(m.PeriodoAcessoPagamento).filter_by(pagamento_id=p.id).first()
            contrato = db.get(m.ContratacaoCurso,p.contratacao_id) if p.contratacao_id else None
            acesso = db.query(m.AcessoCurso).filter_by(usuario_id=p.usuario_id,curso_id=p.curso_id,ativo=True).first()
            instante = self.clock().replace(tzinfo=None)
            disponivel = bool(periodo and contrato and acesso and
                (periodo.usuario_id,periodo.curso_id,periodo.contratacao_id) == (p.usuario_id,p.curso_id,contrato.id)
                and (contrato.usuario_id,contrato.curso_id) == (p.usuario_id,p.curso_id)
                and periodo.data_fim > instante and contrato.data_fim and contrato.data_fim >= periodo.data_fim
                and acesso.data_inicio <= instante and (acesso.data_fim is None or acesso.data_fim >= periodo.data_fim))
            dados = {k:getattr(raiz,k) for k in ('checkout_identidade','checkout_recebedor_id','checkout_meses',
                     'mp_preference_id','oportunidade_id','moeda','provedor')}
            from types import SimpleNamespace
            return {'pid':pid, 'mp_id':str(p.mp_payment_id), 'email':usuario.email,'curso':curso.nome,
                'valor':p.valor_cents,'status':p.status,'mp_status':p.mp_status,'raiz':SimpleNamespace(**dados),
                'aprovado':p.aprovado_em is not None,'acesso':disponivel,'op_concluida':op.concluida_em is not None}

    def consultar_mp(self, ident):
        exigir(bool(re.fullmatch(r'[0-9]{1,64}',ident)))
        r = requests.get('https://api.mercadopago.com/v1/payments/'+ident,
                         headers=self.headers_mp(),timeout=(3,10),allow_redirects=False)
        if r.status_code != 200:
            raise RuntimeError('mp_http')
        d = r.json()
        exigir(isinstance(d,dict) and type(d.get('id')) in (int,str) and str(d['id']) == ident)
        return d

    def validar_mp(self, ctx, d):
        validar_identidade(ctx['raiz'],d)
        valor = Decimal(str(d.get('transaction_amount'))) * 100
        exigir(valor.is_finite() and valor == valor.to_integral_value() and int(valor) == ctx['valor']
               and d.get('currency_id') == 'BRL')

    def montar(self, ctx, tipo, d):
        esc = html.escape
        valor = reais(ctx['valor'])
        prefixo = f"<p>Curso: {esc(ctx['curso'])}</p><p>Cobrança: #{ctx['pid']}</p><p>Valor: {valor}</p>"
        payload = {'from':self.config.remetente,'to':[ctx['email']]}
        if tipo == 'PENDENTE':
            exigir(ctx['status'] in {'PENDING','PENDENTE','IN_PROCESS'} and not ctx['aprovado']
                   and not ctx['op_concluida'] and ctx['mp_status'] not in {'REFUNDED','CHARGED_BACK'})
            inst = instrucoes(d,ctx['valor'],self.clock)
            aviso = 'Estas instruções correspondem somente a esta cobrança. Se você já concluiu a compra, não efetue outro pagamento.'
            validade = esc(data_iso(inst['vencimento']).strftime('%d/%m/%Y %H:%M UTC'))
            payload['subject'] = 'Compra processada - pagamento pendente'
            payload['text'] = (f"Olá!\n{aviso}\nCurso: {ctx['curso']}\nValor: {valor}\n"
                f"Cobrança: #{ctx['pid']}\nValidade/vencimento: {validade}\n" +
                (f"Pix Copia e Cola: {inst['codigo']}\nQR Code anexado." if inst['modo']=='Pix'
                 else f"Linha digitável: {inst['codigo']}\nBoleto: {inst['link']}"))
            payload['html'] = f'<p>Olá!</p><p>{aviso}</p>'+prefixo+f'<p>Validade/vencimento: {validade}</p>'
            if inst['modo']=='Pix':
                payload['html'] += f'<p>Pix Copia e Cola:</p><pre>{esc(inst["codigo"])}</pre><img src="cid:pix-qrcode" alt="QR Code Pix">'
                payload['attachments'] = [{'filename':'pix.png','content':inst['imagem'],
                    'content_type':'image/png','content_id':'pix-qrcode'}]
            else:
                payload['html'] += f'<p>Linha digitável: {esc(inst["codigo"])}</p><p><a href="{esc(inst["link"],quote=True)}">Visualizar boleto</a></p>'
        else:
            exigir(d.get('status')=='approved' and ctx['status']=='APPROVED' and ctx['aprovado']
                   and ctx['acesso'] and ctx['op_concluida'] and ctx['mp_status']=='APPROVED')
            forma = metodo(d)
            meses = ctx['raiz'].checkout_meses
            payload['subject'] = 'Compra concluída - pagamento confirmado'
            payload['text'] = ("Olá!\n\nObrigado por comprar no Resumão Online! 🎉\n\n"
                "Seu pagamento foi confirmado com sucesso e seu curso já está disponível na plataforma na área 'Meus Cursos'.\n\n"
                "Acessar: https://resumaoonline.com.br\n\nDados da sua compra:\n"
                f"Curso: {ctx['curso']}\nPeríodo de acesso: {meses} meses\nValor pago: {valor}\nForma de pagamento: {forma}\n\n"
                "Bons estudos e sucesso na sua preparação!\n\nEquipe Resumão Online")
            payload['html'] = ("<p>Olá!</p><p><strong>Obrigado por comprar no Resumão Online!</strong> 🎉</p>"
                "<p>Seu pagamento foi confirmado com sucesso e seu curso já está disponível na plataforma na área <strong>'Meus Cursos'</strong>.</p>"
                '<p>Acessar: <a href="https://resumaoonline.com.br">https://resumaoonline.com.br</a></p>'
                f'<p><strong>Dados da sua compra:</strong></p><ul><li><strong>Curso:</strong> {esc(ctx["curso"])}</li>'
                f'<li><strong>Período de acesso:</strong> {meses} meses</li><li><strong>Valor pago:</strong> {valor}</li>'
                f'<li><strong>Forma de pagamento:</strong> {esc(forma)}</li></ul>'
                '<p>Bons estudos e sucesso na sua preparação!</p><p><strong>Equipe Resumão Online</strong></p>')
        return payload

    def finalizar(self, job, **valores):
        with self.engine.begin() as c:
            c.execute(update(fila).where(fila.c.pagamento_id==job['pagamento_id'],fila.c.tipo==job['tipo'],
                fila.c.lease_token==job['lease_token']).values(lease_ate=None,lease_token=None,**valores))

    def processar_um(self):
        if not self.config.ativa or not self.normal():
            return False
        import secrets
        with self.engine.begin() as c:
            job = c.execute(select(fila).where(
                or_(fila.c.estado.in_(['DADOS_PENDENTES','PENDENTE']),
                    and_(fila.c.estado=='EM_ENVIO',fila.c.lease_ate<self.clock())),
                fila.c.proxima_consulta_em<=self.clock())
                .order_by(fila.c.criado_em,fila.c.pagamento_id,fila.c.tipo)
                .with_for_update(skip_locked=True).limit(1)).mappings().first()
            if job is None:
                return False
            job = dict(job)
            job['lease_token'] = secrets.token_hex(16)
            c.execute(update(fila).where(fila.c.pagamento_id==job['pagamento_id'],fila.c.tipo==job['tipo'])
                .values(estado='EM_ENVIO',lease_ate=self.clock()+timedelta(seconds=120),lease_token=job['lease_token']))
        try:
            if job['tentativas'] >= 3:
                self.finalizar(job,estado='INCERTO',erro_codigo='limite_tentativas')
                return True
            ctx = self.contexto(job['pagamento_id'])
            d = self.consultar_mp(ctx['mp_id'])
            self.validar_mp(ctx,d)
            esperado = 'pending' if job['tipo']=='PENDENTE' else 'approved'
            vencido = False
            if job['tipo']=='PENDENTE' and isinstance(d.get('date_of_expiration'),str):
                vencido = data_iso(d['date_of_expiration']) <= self.clock()
            if d.get('status') != esperado or vencido or (job['tipo']=='PENDENTE' and ctx['op_concluida']):
                self.finalizar(job,estado='SUSPENSO',erro_codigo='pagamento_nao_elegivel')
                return True
            payload = self.montar(ctx,job['tipo'],d)
            # Releitura local depois da consulta externa: nunca escrever no domínio financeiro.
            ctx = self.contexto(job['pagamento_id'])
            self.validar_mp(ctx,d)
            payload = self.montar(ctx,job['tipo'],d)
            digest = hash_payload(payload)
            if job['payload_hash'] and job['payload_hash'] != digest:
                self.finalizar(job,estado='SUSPENSO',erro_codigo='dados_alterados')
                return True
            if job['primeiro_envio_em'] and tz(job['primeiro_envio_em'])+timedelta(hours=23)<=self.clock():
                self.finalizar(job,estado='INCERTO',erro_codigo='janela_idempotencia_expirada')
                return True
            if not self.normal():
                self.finalizar(job,estado='PENDENTE',proxima_consulta_em=self.clock()+timedelta(seconds=60))
                return True
            with self.engine.begin() as c:
                alteradas = c.execute(update(fila).where(fila.c.pagamento_id==job['pagamento_id'],fila.c.tipo==job['tipo'],
                    fila.c.lease_token==job['lease_token'],fila.c.lease_ate>self.clock()).values(payload=job['payload'] or payload,
                    payload_hash=digest,primeiro_envio_em=job['primeiro_envio_em'] or self.clock(),
                    tentativas=fila.c.tentativas+1)).rowcount
            if alteradas != 1:
                return True
            key = f'resumao-pagamento-v1-{job["pagamento_id"]}-{job["tipo"].lower()}'
            r = requests.post('https://api.resend.com/emails',json=job['payload'] or payload,
                headers={'Authorization':'Bearer '+self.config.resend_key,'Idempotency-Key':key},
                timeout=(3,10),allow_redirects=False)
            if not 200<=r.status_code<300:
                self.finalizar(job,estado='ERRO',erro_codigo='resend_http')
            else:
                try:
                    resposta = r.json()
                except Exception:
                    raise RuntimeError('resend_json') from None
                receipt = resposta.get('id') if isinstance(resposta,dict) else None
                if not isinstance(receipt,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',receipt):
                    self.finalizar(job,estado='INCERTO',erro_codigo='resposta_resend_invalida')
                else:
                    self.finalizar(job,estado='ACEITO',aceito_em=self.clock(),provedor_id=receipt,erro_codigo=None)
        except (Invalido,ValueError,TypeError):
            # Dados ausentes/inválidos podem aparecer em uma atualização posterior do MP.
            self.finalizar(job,estado='DADOS_PENDENTES',erro_codigo='dados_nao_confirmados',
                           proxima_consulta_em=self.clock()+timedelta(minutes=5))
        except Exception:
            # Nenhum texto bruto de exceção/payload/credencial é registrado.
            try:
                self.finalizar(job,estado='INCERTO',erro_codigo='consulta_ou_envio_nao_confirmado')
            except Exception:
                pass  # Lease expirável + mesmo payload/key preservam retomada segura.
            log.warning('etapa=email_pagamento categoria=operacao_nao_confirmada')
        return True

    def reenviar(self, pid, tipo):
        exigir(self.config.ativa and self.normal())
        exigir(tipo in {'PENDENTE','APROVADO'})
        with self.engine.begin() as c:
            job = c.execute(select(fila).where(fila.c.pagamento_id==pid,fila.c.tipo==tipo)
                            .with_for_update()).mappings().first()
            exigir(job and job['estado'] in {'ERRO','INCERTO'} and job['tentativas']<3)
            exigir(not job['primeiro_envio_em'] or tz(job['primeiro_envio_em'])+timedelta(hours=23)>self.clock())
            c.execute(update(fila).where(fila.c.pagamento_id==pid,fila.c.tipo==tipo)
                .values(estado='PENDENTE',proxima_consulta_em=self.clock(),erro_codigo=None))

    def aceito(self, pid, dados):
        if not self.config.ativa:
            return False
        try:
            ctx = self.contexto(pid)
            self.validar_mp(ctx,dados)
            digest = hash_payload(self.montar(ctx,'PENDENTE',dados))
            with self.engine.connect() as c:
                return c.execute(select(fila.c.pagamento_id).where(fila.c.pagamento_id==pid,
                    fila.c.tipo=='PENDENTE',fila.c.estado=='ACEITO',fila.c.aceito_em.isnot(None),
                    fila.c.payload_hash==digest)).first() is not None
        except Exception:
            return False

    def rodada(self):
        if not self.config.ativa or not self.local.acquire(blocking=False):
            return
        try:
            self.descobrir()
            for _ in range(self.config.lote):
                if not self.processar_um():break
        except Exception:
            log.warning('etapa=email_pagamento categoria=fila_indisponivel')
        finally:self.local.release()

    def iniciar(self):
        if not self.config.ativa:return
        def loop():
            from app.financeiro_transacional import ATUAL
            ATUAL.set(None)
            while not self.parar.is_set():
                self.rodada()
                self.parar.wait(self.config.intervalo)
        self.thread = Thread(target=loop,daemon=True,name='emails-pagamentos')
        self.thread.start()

    def encerrar(self):
        self.parar.set()
        if self.thread:self.thread.join(timeout=1)
