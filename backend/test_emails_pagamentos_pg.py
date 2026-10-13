"""PostgreSQL 17.6 compras_test_* em localhost; provedores inteiramente simulados."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch
import pytest
import psycopg
from sqlalchemy import select, text, update
from sqlalchemy.exc import SQLAlchemyError
from app.emails_pagamentos import EmailsPagamentos, fila
from test_compras_concorrencia_pg import motor
from test_compras_fluxo import ambiente_compra
from test_emails_pagamentos import emails, job
from test_transacoes_mp import confirmar

SQL=Path(__file__).parent/'migrations/019_emails_pagamentos.sql'

def aplicar(engine):
    with engine.connect() as c:c.connection.driver_connection.execute(SQL.read_text())


def test_migration_idempotente_rls_e_preservacao(emails):
    a,s,pid,tx,_,post=emails
    assert confirmar(a,101).status_code==200
    s.rodada();antes=job(s,pid)
    aplicar(s.engine)
    assert job(s,pid)==antes
    with s.engine.connect() as c:
        assert c.execute(text('SHOW server_version')).scalar().startswith('17.6')
        assert c.execute(text("SELECT relrowsecurity FROM pg_class WHERE oid='emails_pagamentos'::regclass")).scalar()
        assert c.execute(text("SELECT count(*) FROM pg_policy WHERE polrelid='emails_pagamentos'::regclass")).scalar()==0
        assert c.execute(text('SELECT modo,geracao FROM controle_financeiro')).one()==('NORMAL',0)
    assert post.call_count==1


@pytest.mark.parametrize('alteracao',['coluna','check','indice','politica'])
def test_migration_incompatibilidade_rollback(emails,alteracao):
    a,s,*_=emails
    with s.engine.begin() as c:
        if alteracao=='coluna':c.execute(text('ALTER TABLE emails_pagamentos ALTER COLUMN tipo TYPE text'))
        elif alteracao=='check':c.execute(text('ALTER TABLE emails_pagamentos DROP CONSTRAINT ck_email_aceito'))
        elif alteracao=='indice':
            c.execute(text('DROP INDEX ix_emails_pagamentos_fila'))
            c.execute(text('CREATE INDEX ix_emails_pagamentos_fila ON emails_pagamentos(criado_em)'))
        else:c.execute(text('CREATE POLICY indevida ON emails_pagamentos USING(true)'))
    with pytest.raises(psycopg.Error):aplicar(s.engine)
    with s.engine.connect() as c:assert c.execute(text('SELECT modo,geracao FROM controle_financeiro')).one()==('NORMAL',0)


def test_duas_instancias_envio_unico_e_conexao_liberada_durante_http(emails):
    a,s,pid,tx,_,post=emails;assert confirmar(a,101).status_code==200
    outra=EmailsPagamentos(s.engine,a[2],s.headers_mp,s.config)
    enviando=Event();liberar=Event()
    def envio(*args,**kwargs):
        # A operação HTTP não retém conexão SQLAlchemy.
        assert s.engine.pool.checkedout()==0
        enviando.set();assert liberar.wait(8)
        from unittest.mock import Mock
        r=Mock(status_code=200);r.json.return_value={'id':'recibo-concorrente'}
        return r
    s.descobrir();outra.descobrir()
    with patch('app.emails_pagamentos.requests.post',side_effect=envio) as chamadas:
        with ThreadPoolExecutor(max_workers=2) as pool:
            primeira=pool.submit(s.processar_um);assert enviando.wait(5)
            segunda=pool.submit(outra.processar_um)
            assert segunda.result(timeout=5) is False
            liberar.set();assert primeira.result(timeout=5) is True
        assert chamadas.call_count==1
    assert job(s,pid)['estado']=='ACEITO'
    with s.engine.connect() as c:assert len(c.execute(select(fila)).all())==1


def test_aceito_no_provedor_commit_local_falha_retomada_mesma_chave(emails):
    from datetime import timedelta
    a,s,pid,tx,_,post=emails;assert confirmar(a,101).status_code==200
    s.descobrir();original=s.finalizar
    def perder_resposta(job,**valores):
        if valores.get('estado')=='ACEITO':raise RuntimeError('simula falha após aceitação')
        return original(job,**valores)
    with patch.object(s,'finalizar',side_effect=perder_resposta):s.processar_um()
    assert job(s,pid)['estado']=='INCERTO'
    s.reenviar(pid,'PENDENTE');s.processar_um()
    assert job(s,pid)['estado']=='ACEITO'
    assert post.call_args_list[0].kwargs['json']==post.call_args_list[1].kwargs['json']
    assert post.call_args_list[0].kwargs['headers']['Idempotency-Key']==post.call_args_list[1].kwargs['headers']['Idempotency-Key']


def test_lease_expirada_nao_envia_chave_depois_24h(emails):
    from datetime import timedelta
    a,s,pid,tx,_,post=emails;assert confirmar(a,101).status_code==200
    s.descobrir()
    ctx=s.contexto(pid);payload=s.montar(ctx,'PENDENTE',tx['101'])
    from app.emails_pagamentos import hash_payload
    with s.engine.begin() as c:c.execute(update(fila).values(estado='EM_ENVIO',
        lease_token='simulado',lease_ate=s.clock()-timedelta(seconds=1),payload=payload,
        payload_hash=hash_payload(payload),primeiro_envio_em=s.clock()-timedelta(hours=24),tentativas=1))
    assert s.processar_um()
    assert job(s,pid)['estado']=='INCERTO' and job(s,pid)['erro_codigo']=='janela_idempotencia_expirada'
    post.assert_not_called()
