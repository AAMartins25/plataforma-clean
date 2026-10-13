"""Conexões independentes em PostgreSQL compras_test_* local descartável."""
import importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from unittest.mock import patch

import psycopg
import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from app import models as m
from app.pausa_financeira import Protecao, Modo, controle, inbox
from test_compras_concorrencia_pg import motor
from test_compras_fluxo import ambiente_compra
from test_pausa_financeira import enviar, modo
from test_transacoes_mp import preparar

SQL=Path(__file__).parent/'migrations/016_pausa_financeira_webhooks.sql'


def aplicar(engine):
    with engine.connect() as c:c.connection.driver_connection.execute(SQL.read_text())


def test_016_independente_antigo_idempotente(motor):
    aplicar(motor)
    with motor.begin() as c:
        c.execute(text("UPDATE controle_financeiro SET modo='PAUSADO',geracao=8"))
        c.execute(text("INSERT INTO notificacoes_mp(chave,payment_id,fonte) VALUES('w:test','100','WEBHOOK')"))
        antes=c.execute(text('SELECT * FROM notificacoes_mp')).all()
    aplicar(motor)
    with motor.connect() as c:
        assert c.execute(text('SELECT modo,geracao FROM controle_financeiro')).one()==('PAUSADO',8)
        assert c.execute(text('SELECT * FROM notificacoes_mp')).all()==antes
        assert c.execute(text("SELECT to_regclass('pagamentos')")).scalar() is None


def test_016_homonimo_incompativel_rollback(motor):
    with motor.begin() as c:c.execute(text('CREATE TABLE controle_financeiro(id text)'))
    with pytest.raises(psycopg.Error):aplicar(motor)
    with motor.connect() as c:
        assert c.execute(text("SELECT to_regclass('notificacoes_mp')")).scalar() is None


@pytest.mark.parametrize('objeto',['constraint','coluna','indice','politica'])
def test_016_reaplicacao_interrompe_incompatibilidade(motor,objeto):
    aplicar(motor)
    with motor.begin() as c:
        if objeto=='constraint':c.execute(text('ALTER TABLE controle_financeiro DROP CONSTRAINT controle_financeiro_modo_check'))
        if objeto=='coluna':c.execute(text('ALTER TABLE notificacoes_mp ALTER COLUMN payment_id TYPE varchar(10)'))
        if objeto=='indice':
            c.execute(text('DROP INDEX ix_notificacoes_mp_pendentes'))
            c.execute(text('CREATE INDEX ix_notificacoes_mp_pendentes ON notificacoes_mp(id)'))
        if objeto=='politica':c.execute(text('CREATE POLICY indevida ON notificacoes_mp FOR SELECT USING(true)'))
    with pytest.raises(psycopg.Error):aplicar(motor)
    with motor.connect() as c:assert c.execute(text('SELECT modo FROM controle_financeiro')).scalar()=='NORMAL'


def test_016_rls_sem_acesso_publico(motor):
    aplicar(motor)
    with motor.begin() as c:
        assert c.execute(text("SELECT count(*) FROM pg_class WHERE relname IN ('controle_financeiro','notificacoes_mp') AND relrowsecurity")).scalar()==2
        c.execute(text('CREATE ROLE cliente_pausa_test NOLOGIN'))
    try:
        with pytest.raises(Exception):
            with motor.begin() as c:
                c.execute(text('SET LOCAL ROLE cliente_pausa_test'))
                c.execute(text("UPDATE controle_financeiro SET modo='NORMAL'"))
    finally:
        with motor.begin() as c:c.execute(text('DROP ROLE cliente_pausa_test'))


def test_pausa_aguarda_commits_intermediarios_duas_instancias(ambiente_compra,motor):
    p=ambiente_compra[0].app.state.protecao_financeira
    outra=Protecao(motor,ambiente_compra[2],p.processor)
    with motor.begin() as c:c.execute(text('CREATE TABLE efeito_pausa(id integer PRIMARY KEY)'))
    gravou=Event();liberar=Event();pausado=Event()
    def operacao():
        with p.lease():
            with ambiente_compra[2]() as db:
                db.execute(text('INSERT INTO efeito_pausa VALUES(1)'))
                gravou.set();assert liberar.wait(4)
                db.commit()
                assert pausado.wait(4)
                with pytest.raises(HTTPException):
                    db.execute(text('INSERT INTO efeito_pausa VALUES(2)'))
                    db.commit()
    def pausar():
        result=outra.mudar(Modo(modo='PAUSADO',geracao=0,motivo='teste'),2)
        pausado.set();return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        op=pool.submit(operacao);assert gravou.wait(4)
        pausa=pool.submit(pausar)
        with motor.connect() as c:
            from time import monotonic
            deadline=monotonic()+3
            while monotonic()<deadline:
                c.execute(text('SELECT pg_stat_clear_snapshot()'))
                if c.execute(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND query LIKE '%controle_financeiro%'")).scalar():break
            else:pytest.fail('Ativação não aguardou a transação financeira')
        assert not pausa.done()
        liberar.set();assert pausa.result(timeout=5)['modo']=='PAUSADO';op.result(timeout=5)
    with motor.connect() as c:assert list(c.execute(text('SELECT id FROM efeito_pausa')).scalars())==[1]


def test_webhooks_concorrentes_e_consumidores_independentes(ambiente_compra,motor):
    a=ambiente_compra;_,dados,transacoes,_=preparar(a)
    modo(a,'PAUSADO')
    for tx in (101,102):transacoes[str(tx)]=dados(tx,'approved')
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda i:enviar(a,101 if i<2 else 102,f'evento-{101 if i<2 else 102}'),range(4)))
    assert all(r.status_code==200 for r in results)
    with motor.connect() as c:
        ids=list(c.execute(select(inbox.c.id)).scalars());assert len(ids)==2
    modo(a,'RECUPERACAO')
    p=a[0].app.state.protecao_financeira
    outra=Protecao(motor,a[2],p.processor)
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            def consumir(i):
                try:return (p if i%2 else outra).processar(ids[i%2],True)
                except HTTPException as exc:
                    assert exc.status_code==503
                    return {'processado':False}
            results=list(pool.map(consumir,range(4)))
        for ident in ids:
            results.append(p.processar(ident,True))
        assert sum(r['processado'] for r in results)==2
        with a[2]() as db:
            assert db.query(m.Pagamento).count()==2
            assert db.query(m.ContratacaoCurso).count()==1
            assert db.query(m.PeriodoAcessoPagamento).count()==1
        with motor.connect() as c:assert set(c.execute(select(inbox.c.estado)).scalars())=={'CONCLUIDO'}
    finally:pass  # Não existe pool adicional de leases.


def test_crash_apos_commit_financeiro_reprocessa_sem_duplo_acesso(ambiente_compra,motor):
    a=ambiente_compra;_,dados,transacoes,_=preparar(a)
    transacoes['101']=dados(101,'approved');modo(a,'PAUSADO');enviar(a)
    modo(a,'RECUPERACAO');p=a[0].app.state.protecao_financeira
    with motor.connect() as c:ident=c.execute(select(inbox.c.id)).scalar_one()
    real=p.processor
    class Crash(BaseException):pass
    def crash(pid,db,**kwargs):
        real(pid,db,**kwargs)
        raise Crash()
    with patch.object(p,'processor',side_effect=crash):
        with pytest.raises(Crash):p.processar(ident,True)
    with motor.connect() as c:assert c.execute(select(inbox.c.estado)).scalar_one()=='PENDENTE'
    with a[2]() as db:assert db.query(m.PeriodoAcessoPagamento).count()==0
    assert p.processar(ident,True)['processado']
    with a[2]() as db:
        assert db.query(m.ContratacaoCurso).count()==1
        assert db.query(m.PeriodoAcessoPagamento).count()==1


def test_startup_definitivo_recusa_esquema_anterior(ambiente_compra,motor):
    a=ambiente_compra
    with motor.begin() as c:
        c.execute(text('ALTER TABLE pagamentos DROP COLUMN mp_status'))
    with pytest.raises(RuntimeError,match='014 e 015'):
        for iniciar in a[0].app.router.on_startup:
            iniciar()


def test_exportacao_bootstrap_usa_modelos_head_e_nao_precisa_014015(tmp_path,motor):
    source=Path(__file__).parent
    spec=importlib.util.spec_from_file_location('exportacao',source/'preparar_backend_pausa.py')
    export=importlib.util.module_from_spec(spec);spec.loader.exec_module(export)
    destino=tmp_path/'intermediario'
    sha=export.preparar(destino)
    models=(destino/'backend/app/models.py').read_text()
    assert 'pagamento_origem_id' not in models and 'mp_status' not in models
    main=(destino/'backend/app/main.py').read_text()
    assert 'definitivo=False' in main and 'def processar_pagamento_mp' in main
    assert (destino/'ORIGEM.txt').read_text().startswith(f'Backend intermediário baseado em {sha}')
    # Executar a versão exportada em processo isolado, com dotenv e DB substituídos.
    import subprocess,sys
    url=motor.url.render_as_string(hide_password=False)
    script='''
import importlib.util, sys, types
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
import dotenv
from app import models
engine=create_engine(sys.argv[1]);models.Base.metadata.create_all(engine)
factory=sessionmaker(bind=engine)
stub=types.ModuleType('app.database');stub.engine=engine;stub.SessionLocal=factory
spec=importlib.util.spec_from_file_location('app.main',sys.argv[2]);main=importlib.util.module_from_spec(spec)
with patch.dict(sys.modules,{'app.database':stub}),patch.object(dotenv,'load_dotenv',return_value=False):spec.loader.exec_module(main)
main.app.dependency_overrides[main.get_usuario_atual]=lambda:types.SimpleNamespace(id=99,is_admin=True)
with TestClient(main.app) as c:
 r=c.get('/admin/financeiro/manutencao');assert r.status_code==200,r.text
 assert r.json()['backend_definitivo'] is False
 r=c.post('/admin/financeiro/manutencao',json={'modo':'PAUSADO','geracao':0,'motivo':'teste'})
 assert r.status_code==200,r.text
 assert c.post('/checkout/mercadopago',json={}).status_code==503
 assert c.post('/admin/financeiro/manutencao',json={'modo':'RECUPERACAO','geracao':1,'motivo':'teste'}).status_code==409
 print('Bootstrap compatível com esquema antigo: OK')
'''
    aplicar(motor)
    import os
    env=dict(os.environ,AMBIENTE_TESTE='1',PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(destino/'backend'))
    result=subprocess.run([sys.executable,'-c',script,url,str(destino/'backend/app/main.py')],env=env,
        cwd=destino,capture_output=True,text=True,timeout=40)
    assert result.returncode==0,result.stderr


def test_selecao_id_concorrente_duas_instancias(ambiente_compra, motor):
    from test_pausa_financeira import preparar_selecao
    a = ambiente_compra
    preparar_selecao(a)
    p = a[0].app.state.protecao_financeira
    outra = Protecao(motor, a[2], p.processor, consulta=p.consulta)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(protecao.recuperar, 5, notificacao_id=5) for protecao in (p, outra)]
        results = [future.result(timeout=10) for future in futures]
    assert sum(r['processado'] for result in results for r in result['resultados']) == 1
    with motor.connect() as c:
        rows = {r['id']: r for r in c.execute(select(inbox)).mappings()}
        assert rows[5]['estado'] == 'CONCLUIDO' and rows[5]['tentativas'] == 1
        assert rows[6]['estado'] == 'PENDENTE' and rows[6]['tentativas'] == 0
        assert rows[1]['estado'] == 'ERRO' and rows[1]['tentativas'] == 2
    with a[2]() as db:
        assert db.query(m.Pagamento).count() == 1
        assert db.query(m.ContratacaoCurso).count() == 0
        assert db.query(m.PeriodoAcessoPagamento).count() == 0
        assert db.query(m.AcessoCurso).count() == 0
