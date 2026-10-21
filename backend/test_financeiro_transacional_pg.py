"""Falhas reais somente em PostgreSQL localhost compras_test_* descartável."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

import psycopg
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import DBAPIError, TimeoutError

from app.pausa_financeira import Protecao, Modo, controle, inbox
from app.financeiro_transacional import ATUAL
from app import models as m
from test_compras_concorrencia_pg import motor
from test_compras_fluxo import ambiente_compra
from test_pausa_financeira import modo, enviar
from test_transacoes_mp import preparar


def independente(engine):
    return psycopg.connect(engine.url.render_as_string(hide_password=False).replace('postgresql+psycopg://','postgresql://'), autocommit=True)


def probe(engine):
    with engine.begin() as c:c.execute(text('CREATE TABLE efeito_guard(id integer PRIMARY KEY)'))


@pytest.mark.parametrize('intermediario',[False,True])
def test_desconexao_impede_commit_e_retomada(ambiente_compra,motor,intermediario):
    p=ambiente_compra[0].app.state.protecao_financeira;probe(motor)
    with p.lease() as op:
        with ambiente_compra[2]() as db:
            if intermediario:
                db.execute(text('INSERT INTO efeito_guard VALUES(1)'));db.commit()
            db.execute(text('INSERT INTO efeito_guard VALUES(2)'))
            pid=db.execute(text('SELECT pg_backend_pid()')).scalar_one()
            with independente(motor) as c:assert c.execute('SELECT pg_terminate_backend(%s)',(pid,)).fetchone()[0]
            with pytest.raises((DBAPIError,HTTPException)):db.commit()
            db.rollback()
            assert op.falhou
            with pytest.raises(HTTPException):
                db.execute(text('INSERT INTO efeito_guard VALUES(3)'));db.commit()
    with motor.connect() as c:
        assert list(c.execute(text('SELECT id FROM efeito_guard ORDER BY id')).scalars())==([1] if intermediario else [])
    # Outra execução pode reconectar e recebe nova autorização.
    with p.lease():
        with ambiente_compra[2]() as db:db.execute(text('INSERT INTO efeito_guard VALUES(4)'));db.commit()
    with motor.connect() as c:assert c.execute(text('SELECT count(*) FROM efeito_guard WHERE id=4')).scalar()==1


def test_reabertura_nao_autoriza_geracao_antiga(ambiente_compra,motor):
    p=ambiente_compra[0].app.state.protecao_financeira;probe(motor)
    with p.lease() as op:
        with ambiente_compra[2]() as db:
            db.execute(text('INSERT INTO efeito_guard VALUES(1)'));db.commit()
            token=ATUAL.set(None)
            try:
                p.mudar(Modo(modo='PAUSADO',geracao=0,motivo='teste'),2)
                p.mudar(Modo(modo='NORMAL',geracao=1,motivo='teste',conferencia_provedor=True),2)
            finally:ATUAL.reset(token)
            with pytest.raises(HTTPException):
                db.execute(text('INSERT INTO efeito_guard VALUES(2)'));db.commit()
            assert op.falhou
    with motor.connect() as c:assert list(c.execute(text('SELECT id FROM efeito_guard')).scalars())==[1]


@pytest.mark.parametrize('commit_concluido',[False,True])
def test_resultado_incerto_reconciliado_sem_duplicar(ambiente_compra,motor,commit_concluido):
    a=ambiente_compra;_,dados,transacoes,_=preparar(a);transacoes['101']=dados(101,'approved')
    modo(a,'PAUSADO');enviar(a);modo(a,'RECUPERACAO')
    p=a[0].app.state.protecao_financeira
    with motor.connect() as c:ident=c.execute(select(inbox.c.id)).scalar_one()
    # Simular perda da resposta do COMMIT antes/depois de o servidor efetivá-lo.
    raw=motor.dialect.do_commit
    disparou=False
    def incerto(c):
        nonlocal disparou
        if not disparou and ATUAL.get() is not None and ATUAL.get().commit_iniciado:
            disparou=True
            if commit_concluido:raw(c)
            raise psycopg.OperationalError('resposta do commit perdida no teste')
        return raw(c)
    with patch.object(motor.dialect,'do_commit',side_effect=incerto):
        r=p.processar(ident,True)
    assert disparou and not r['processado']
    with a[2]() as db:
        assert db.query(m.PeriodoAcessoPagamento).count()==int(commit_concluido)
    # Verificação antes da repetição; se já concluído, não reexecutar concessão.
    with motor.connect() as c:estado=c.execute(select(inbox.c.estado)).scalar_one()
    assert (estado=='CONCLUIDO')==commit_concluido
    p.processar(ident,True)
    with a[2]() as db:
        assert db.query(m.ContratacaoCurso).count()==1
        assert db.query(m.PeriodoAcessoPagamento).count()==1


def test_pool_unico_uma_conexao_processa_sem_reserva_circular(ambiente_compra,motor):
    a=ambiente_compra;_,dados,transacoes,_=preparar(a);transacoes['101']=dados(101,'approved')
    modo(a,'PAUSADO');enviar(a);modo(a,'RECUPERACAO')
    pequeno=create_engine(motor.url,pool_size=1,max_overflow=0,pool_timeout=.2)
    factory=sessionmaker(bind=pequeno,autoflush=False)
    p=Protecao(pequeno,factory,a[0].processar_pagamento_mp,consulta=lambda pid:a[0].consultar_pagamento(pid,a[0].mp_headers()))
    try:
        assert not hasattr(p,'leases')
        with pequeno.connect() as c:ident=c.execute(select(inbox.c.id)).scalar_one()
        ocupada=pequeno.connect()
        with pytest.raises(HTTPException):p.processar(ident,True)
        ocupada.close()
        assert p.processar(ident,True)['processado']
        assert pequeno.pool.checkedout()==0
        with a[2]() as db:assert db.query(m.PeriodoAcessoPagamento).count()==1
    finally:pequeno.dispose()


def test_pausa_durante_consulta_externa_nao_grava(ambiente_compra,motor):
    a=ambiente_compra;_,dados,transacoes,_=preparar(a);transacoes['101']=dados(101,'approved')
    p=a[0].app.state.protecao_financeira
    chegou=Event();liberar=Event();real=p.consulta
    def consulta(pid):
        chegou.set();assert liberar.wait(5);return real(pid)
    ident=p.armazenar('101','w:teste-pausa-api','WEBHOOK')
    with patch.object(p,'consulta',side_effect=consulta):
        with ThreadPoolExecutor(max_workers=1) as pool:
            task=pool.submit(p.processar,ident)
            assert chegou.wait(4)
            assert p.mudar(Modo(modo='PAUSADO',geracao=0,motivo='teste'),2)['modo']=='PAUSADO'
            liberar.set();assert not task.result(timeout=5)['processado']
    with a[2]() as db:assert db.query(m.PeriodoAcessoPagamento).count()==0
    with motor.connect() as c:assert c.execute(select(inbox.c.estado)).scalar_one()!='CONCLUIDO'


def test_chamada_interna_sem_middleware_bloqueada(ambiente_compra,motor):
    a=ambiente_compra;pid,dados,transacoes,_=preparar(a);transacoes['101']=dados(101,'approved')
    modo(a,'PAUSADO')
    with a[2]() as db:
        with pytest.raises(HTTPException):a[0].processar_pagamento_mp('101',db)
    with a[2]() as db:
        assert db.get(m.Pagamento,pid).aprovado_em is None
        assert db.query(m.ContratacaoCurso).count()==0


def test_duas_instancias_pools_independentes_concessao_unica(ambiente_compra,motor):
    a=ambiente_compra;_,dados,transacoes,_=preparar(a)
    for tx in (101,102):transacoes[str(tx)]=dados(tx,'approved')
    modo(a,'PAUSADO');enviar(a,101,'tx1');enviar(a,102,'tx2');modo(a,'RECUPERACAO')
    with motor.connect() as c:ids=list(c.execute(select(inbox.c.id).order_by(inbox.c.id)).scalars())
    engines=[create_engine(motor.url,pool_size=1,max_overflow=0,pool_timeout=.5) for _ in range(2)]
    consumidores=[Protecao(e,sessionmaker(bind=e,autoflush=False),a[0].processar_pagamento_mp,
        consulta=lambda pid:a[0].consultar_pagamento(pid,a[0].mp_headers())) for e in engines]
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            tarefas=[pool.submit(p.processar,ident,True) for p,ident in zip(consumidores,ids)]
            assert all(t.result(timeout=8)['processado'] for t in tarefas)
        with a[2]() as db:
            assert db.query(m.Pagamento).count()==2
            assert db.query(m.ContratacaoCurso).count()==1
            assert db.query(m.PeriodoAcessoPagamento).count()==1
            assert db.query(m.Pagamento).filter_by(ocorrencia_financeira='COBRANCA_DUPLICADA').count()==1
        assert all(e.pool.checkedout()==0 for e in engines)
    finally:
        for e in engines:e.dispose()


def test_recuperacao_http_autenticada_com_pool_um(ambiente_compra,motor):
    from fastapi import FastAPI,Depends
    from fastapi.testclient import TestClient
    from app.pausa_financeira import instalar
    a=ambiente_compra;_,dados,transacoes,_=preparar(a);transacoes['101']=dados(101,'approved')
    modo(a,'PAUSADO');enviar(a);modo(a,'RECUPERACAO')
    engine=create_engine(motor.url,pool_size=1,max_overflow=0,pool_timeout=.2)
    factory=sessionmaker(bind=engine,autoflush=False)
    app=FastAPI()
    @app.post('/webhooks/mercadopago')
    def original():return {}
    def get_db():
        with factory() as db:yield db
    def auth(db=Depends(get_db)):
        return db.get(m.Usuario,2)
    instalar(app,engine,factory,get_db,auth,lambda request,pid:True,
        a[0].processar_pagamento_mp,a[0].mp_headers,
        consulta=lambda pid:a[0].consultar_pagamento(pid,a[0].mp_headers()))
    try:
        with TestClient(app) as c:
            r=c.post('/admin/financeiro/notificacoes/recuperar',json={'limite':1})
            assert r.status_code==200 and r.json()['resultados'][0]['processado'],r.text
        assert engine.pool.checkedout()==0
        with a[2]() as db:assert db.query(m.PeriodoAcessoPagamento).count()==1
    finally:engine.dispose()


def test_prazo_esgotado_nao_grava_e_preserva_notificacao(ambiente_compra,motor):
    from time import monotonic
    a=ambiente_compra;_,dados,transacoes,_=preparar(a);transacoes['101']=dados(101,'approved')
    modo(a,'PAUSADO');enviar(a);modo(a,'RECUPERACAO')
    p=a[0].app.state.protecao_financeira
    with motor.connect() as c:ident=c.execute(select(inbox.c.id)).scalar_one()
    assert not p.processar(ident,True,prazo=monotonic()-1)['processado']
    with a[2]() as db:assert db.query(m.PeriodoAcessoPagamento).count()==0
    with motor.connect() as c:assert c.execute(select(inbox.c.estado)).scalar_one()!='CONCLUIDO'
    assert p.processar(ident,True)['processado']


def test_orm_e_sql_diretos_na_sessao_nao_contornam_pausa(ambiente_compra,motor):
    a=ambiente_compra;pid,_,_,_=preparar(a);modo(a,'PAUSADO')
    with a[2]() as db:
        pagamento=db.get(m.Pagamento,pid)
        pagamento.status='APPROVED'
        with pytest.raises(HTTPException):db.commit()
        db.rollback()
    with a[2]() as db:
        with pytest.raises(HTTPException):
            db.execute(text("UPDATE pagamentos SET status='APPROVED' WHERE id=:id"),{'id':pid})
            db.commit()
    with a[2]() as db:assert db.get(m.Pagamento,pid).status=='PENDENTE'


def test_checkout_externo_incerto_nao_inventa_preferencia(ambiente_compra,motor):
    from unittest.mock import Mock
    from datetime import datetime
    a=ambiente_compra
    post=a[3];post.side_effect=__import__('requests').Timeout('resposta externa incerta simulada')
    r=a[1].post('/checkout/mercadopago',json={'tempo_acesso_id':1})
    assert r.status_code==502
    with a[2]() as db:
        raiz=db.query(m.Pagamento).one();pid=raiz.id;identidade=raiz.checkout_identidade
        assert raiz.status=='CHECKOUT_INDEFINIDO' and raiz.mp_preference_id is None
        assert db.query(m.ContratacaoCurso).count()==0
    assert a[1].post('/checkout/mercadopago',json={'tempo_acesso_id':1}).status_code==409
    assert post.call_count==1
    external='checkout:'+identidade
    def api(url,**kwargs):
        r=Mock(status_code=200)
        if '/merchant_orders/' in url:
            r.json.return_value={'id':'ordem','preference_id':'pref_recuperada',
                'external_reference':external,'payments':[{'id':101}]}
        else:r.json.return_value={'id':'101','status':'approved','payment_method_id':'pix',
            'transaction_amount':49.9,'currency_id':'BRL','order':{'id':'ordem'},
            'external_reference':external,'collector_id':123456,'live_mode':True,'date_approved':datetime.utcnow().isoformat()+'Z'}
        return r
    a[4].side_effect=api
    assert a[1].post('/pagamentos/confirmar',json={'payment_id':'101','curso_id':1}).status_code==409
    with a[2]() as db:
        assert db.query(m.Pagamento).count()==1
        assert db.get(m.Pagamento,pid).mp_preference_id is None
        assert db.get(m.Pagamento,pid).mp_payment_id is None
        assert db.query(m.PeriodoAcessoPagamento).count()==0


def test_limite_http_nao_abandona_gravacao_apos_prazo(ambiente_compra,motor):
    from time import monotonic
    a=ambiente_compra;_,dados,transacoes,_=preparar(a);transacoes['101']=dados(101,'approved')
    modo(a,'PAUSADO');enviar(a);modo(a,'RECUPERACAO')
    p=a[0].app.state.protecao_financeira;p.duracao=.1
    entrou=Event();liberar=Event();terminou=Event();real=p.consulta
    def consulta(pid):
        entrou.set()
        try:
            assert liberar.wait(5)
            return real(pid)
        finally:terminou.set()
    with patch.object(p,'consulta',side_effect=consulta):
        try:
            inicio=monotonic()
            r=a[1].post('/admin/financeiro/notificacoes/recuperar',json={})
            assert entrou.is_set() and r.status_code==503
            assert monotonic()-inicio<2
            assert p.mudar(Modo(modo='PAUSADO',geracao=2,motivo='teste'),2)['modo']=='PAUSADO'
        finally:liberar.set()
        assert terminou.wait(4)
        # Esperar a conclusão do consumidor, não somente o retorno da API externa.
        limite=monotonic()+4
        while monotonic()<limite:
            if p.consumidores.acquire(blocking=False):
                p.consumidores.release();break
        else:pytest.fail('Consumidor não liberou recursos após o prazo')
    with a[2]() as db:assert db.query(m.PeriodoAcessoPagamento).count()==0
    with motor.connect() as c:assert c.execute(select(inbox.c.estado)).scalar_one()!='CONCLUIDO'


def test_intermediario_startup_recusa_falta_016(ambiente_compra,motor):
    from fastapi import FastAPI
    from app.pausa_financeira import instalar
    a=ambiente_compra;app=FastAPI()
    @app.post('/webhooks/mercadopago')
    def original():return {}
    instalar(app,motor,a[2],a[0].get_db,a[0].get_usuario_atual,lambda request,pid:True,
             a[0].processar_pagamento_mp,a[0].mp_headers,definitivo=False)
    with motor.begin() as c:c.execute(text('DROP TABLE controle_financeiro'))
    with pytest.raises(DBAPIError):app.router.on_startup[-1]()
    with a[2]() as db:assert db.query(m.Pagamento).count()==0


def test_autocommit_nao_pode_gravar(ambiente_compra,motor):
    p=ambiente_compra[0].app.state.protecao_financeira;probe(motor)
    with p.lease():
        with motor.connect().execution_options(isolation_level='AUTOCOMMIT') as c:
            with pytest.raises(HTTPException):c.execute(text('INSERT INTO efeito_guard VALUES(1)'))
    with motor.connect() as c:assert c.execute(text('SELECT count(*) FROM efeito_guard')).scalar()==0


def test_rollback_savepoint_nao_reutiliza_bloqueio_liberado(ambiente_compra,motor):
    a=ambiente_compra;pid,_,_,_=preparar(a);p=a[0].app.state.protecao_financeira
    with a[2]() as db:
        nested=db.begin_nested()
        db.execute(text("UPDATE pagamentos SET status='PENDING' WHERE id=:id"),{'id':pid})
        nested.rollback()
        assert p.mudar(Modo(modo='PAUSADO',geracao=0,motivo='teste'),2)['modo']=='PAUSADO'
        with pytest.raises(HTTPException):
            db.execute(text("UPDATE pagamentos SET status='APPROVED' WHERE id=:id"),{'id':pid})
            db.commit()
    with a[2]() as db:
        assert db.get(m.Pagamento,pid).status=='PENDENTE'
        assert db.query(m.PeriodoAcessoPagamento).count()==0
