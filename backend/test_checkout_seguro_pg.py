"""PostgreSQL descartável localhost; nenhuma conexão de produção."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch
import pytest
import psycopg
from contextlib import contextmanager
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from app import models as m
from test_compras_concorrencia_pg import motor
from test_compras_fluxo import ambiente_compra
from test_transacoes_mp import preparar, webhook
from test_checkout_seguro import test_identidade_persistida_antes_do_envio
from test_financeiro_transacional_pg import independente

SQL=Path(__file__).parent/'migrations/017_checkout_identidade_segura.sql'

@contextmanager
def protegido(ambiente,engine):
    with ambiente[0].app.state.protecao_financeira.lease():
        with engine.begin() as c:yield c


def aplicar(engine):
    with engine.connect() as c:c.connection.driver_connection.execute(SQL.read_text())


def test_migration_legado_idempotente(ambiente_compra,motor):
    with protegido(ambiente_compra,motor) as c:
        c.execute(text('DROP TRIGGER proteger_checkout_identidade ON pagamentos'))
        c.execute(text('DROP FUNCTION proteger_checkout_identidade()'))
        c.execute(text('ALTER TABLE pagamentos DROP COLUMN checkout_identidade CASCADE'))
        c.execute(text('ALTER TABLE pagamentos DROP COLUMN checkout_recebedor_id CASCADE'))
        c.execute(text('ALTER TABLE pagamentos DROP COLUMN checkout_meses'))
        c.execute(text("INSERT INTO pagamentos(id,usuario_id,curso_id,tempo_acesso_id,status,valor_cents,tipo_compra) VALUES(99,1,1,1,'APPROVED',4990,'NOVA')"))
        before=c.execute(text('SELECT row_to_json(p) FROM pagamentos p WHERE id=99')).scalar_one()
    aplicar(motor);aplicar(motor)
    with motor.connect() as c:
        after=c.execute(text('SELECT row_to_json(p) FROM pagamentos p WHERE id=99')).scalar_one()
        assert after.pop('checkout_identidade') is None
        assert after.pop('checkout_recebedor_id') is None
        assert after.pop('checkout_meses') is None
        assert before==after
        assert c.execute(text("SELECT tgenabled FROM pg_trigger WHERE tgname='proteger_checkout_identidade'")).scalar_one()=='O'


@pytest.mark.parametrize('campo', ['checkout_identidade','checkout_recebedor_id','checkout_meses','usuario_id',
 'curso_id','tempo_acesso_id','valor_cents','moeda','provedor','oportunidade_id','mp_preference_id'])
def test_vinculo_imutavel(ambiente_compra,motor,campo):
    pid,_,_,_=preparar(ambiente_compra)
    valor={'checkout_identidade':'X'*43,'checkout_recebedor_id':'999','checkout_meses':8,'usuario_id':2,'curso_id':2,
      'tempo_acesso_id':2,'valor_cents':1,'moeda':'USD','provedor':'OUTRO','oportunidade_id':None,
      'mp_preference_id':'outra'}[campo]
    with pytest.raises(psycopg.Error):
        with independente(motor) as c:c.execute(f'UPDATE pagamentos SET {campo}=%s WHERE id=%s',(valor,pid))
    with motor.connect() as c:assert c.execute(text('SELECT checkout_identidade IS NOT NULL FROM pagamentos WHERE id=:id'),{'id':pid}).scalar()


def test_unicidade_e_nao_exclusao(ambiente_compra,motor):
    pid,_,_,_=preparar(ambiente_compra)
    with pytest.raises(psycopg.Error):
        with independente(motor) as c:c.execute('DELETE FROM pagamentos WHERE id=%s',(pid,))
    with pytest.raises(psycopg.Error):
        with independente(motor) as c:c.execute('''INSERT INTO pagamentos(usuario_id,curso_id,tempo_acesso_id,status,valor_cents,
        tipo_compra,oportunidade_id,checkout_identidade,checkout_recebedor_id,checkout_meses,moeda,provedor)
        SELECT usuario_id,curso_id,tempo_acesso_id,status,valor_cents,tipo_compra,oportunidade_id,
        checkout_identidade,checkout_recebedor_id,checkout_meses,moeda,provedor FROM pagamentos WHERE id=%s''',(pid,))
    with motor.connect() as c:assert c.execute(text('SELECT count(*) FROM pagamentos')).scalar()==1


@pytest.mark.parametrize('mesmo_id',[True,False])
def test_aprovacoes_concorrentes_conexoes_independentes(ambiente_compra,motor,mesmo_id):
    main,_,f,post,get=ambiente_compra
    _,dados,tx,_=preparar(ambiente_compra)
    tx.update({str(i):dados(i,'approved') for i in (101,102)})
    api=get.side_effect
    def provedor(url,**kw):
        assert '/merchant_orders/' not in url
        return api(url,**kw)
    get.side_effect=provedor
    barreira=Barrier(2); conexoes=[]
    def executar(i):
        with f() as db:
            # Conexões físicas independentes, antes de disputar os locks financeiros.
            conexoes.append(db.execute(text('SELECT pg_backend_pid()')).scalar_one())
            barreira.wait(timeout=10)
            db.rollback()
            ident=101 if mesmo_id else 101+i
            return main.confirmar_pagamento({'payment_id':str(ident),'curso_id':1},db,SimpleNamespace(id=1))
    with ThreadPoolExecutor(max_workers=2) as e: resultados=list(e.map(executar,(0,1)))
    assert len(set(conexoes))==2
    assert sum(r.get('liberou_acesso',False) for r in resultados)==1
    with f() as db:
        assert db.query(m.PeriodoAcessoPagamento).count()==1
        assert db.query(m.ContratacaoCurso).count()==1
        assert db.query(m.Pagamento).count()==(1 if mesmo_id else 2)
    post.assert_called_once()


def test_migration_incompativel_rollback(ambiente_compra,motor):
    with protegido(ambiente_compra,motor) as c:
        c.execute(text('DROP TRIGGER proteger_checkout_identidade ON pagamentos'))
        c.execute(text('DROP INDEX uq_pagamentos_checkout_identidade'))
        c.execute(text('ALTER TABLE pagamentos DROP COLUMN checkout_identidade'))
        c.execute(text('ALTER TABLE pagamentos ADD COLUMN checkout_identidade integer'))
    with pytest.raises((DBAPIError,psycopg.Error)):aplicar(motor)
    with motor.connect() as c:
        assert c.execute(text("SELECT data_type FROM information_schema.columns WHERE table_schema='public' AND table_name='pagamentos' AND column_name='checkout_identidade'")).scalar_one()=='integer'
