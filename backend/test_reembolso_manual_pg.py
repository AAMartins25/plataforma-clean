"""Somente PostgreSQL local compras_test_* descartável, conexões independentes."""
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import psycopg
import pytest
from sqlalchemy import text
from app import models as m, schemas
from test_compras_concorrencia_pg import motor, paralelo
from test_compras_fluxo import ambiente_compra
from test_reembolso_manual_fluxo import duplicata, admin, registrar
from test_transacoes_mp import webhook
from test_transacoes_concorrencia_pg import aplicar as aplicar014

SCRIPT=Path(__file__).parent/'migrations/015_reembolsos_manual_auditoria.sql'

def aplicar015(engine):
    with engine.connect() as c:
        c.connection.driver_connection.execute(SCRIPT.read_text())


def test_migration015_incremental_idempotente_preserva_historico(ambiente_compra,motor):
    pid=duplicata(ambiente_compra)
    with ambiente_compra[2].begin() as c:
        c.execute(text("INSERT INTO reembolsos_financeiros(pagamento_id,metodo,valor_cents,status) VALUES(:p,'PIX_MANUAL',4990,'CONFIRMADO')"),{'p':pid})
        c.execute(text('ALTER TABLE pagamentos DROP COLUMN mp_status'))
        c.execute(text('ALTER TABLE reembolsos_financeiros DROP COLUMN confirmado_por CASCADE'))
        antes=c.execute(text('SELECT id,pagamento_id,status,valor_cents FROM reembolsos_financeiros')).all()
    aplicar015(motor);aplicar015(motor)
    with motor.connect() as c:
        assert c.execute(text('SELECT id,pagamento_id,status,valor_cents FROM reembolsos_financeiros')).all()==antes
        assert c.execute(text('SELECT confirmado_por FROM reembolsos_financeiros')).scalar() is None
        assert c.execute(text('SELECT count(*) FROM pagamentos WHERE mp_status IS NULL')).scalar()==2
        constraints=c.execute(text("SELECT conname FROM pg_constraint WHERE conrelid='reembolsos_financeiros'::regclass")).scalars().all()
        assert 'fk_reembolso_confirmado_por' in constraints


@pytest.mark.parametrize('incompatibilidade',['tipo','fk','orfao'])
def test_migration015_interrompe_e_rollback(ambiente_compra,motor,incompatibilidade):
    duplicata(ambiente_compra)
    with ambiente_compra[2].begin() as c:
        c.execute(text('ALTER TABLE pagamentos DROP COLUMN mp_status'))
        c.execute(text('ALTER TABLE reembolsos_financeiros DROP COLUMN confirmado_por CASCADE'))
        if incompatibilidade=='tipo':c.execute(text('ALTER TABLE reembolsos_financeiros ADD COLUMN confirmado_por text'))
        else:
            c.execute(text('ALTER TABLE reembolsos_financeiros ADD COLUMN confirmado_por integer'))
            if incompatibilidade=='fk':c.execute(text('ALTER TABLE reembolsos_financeiros ADD CONSTRAINT fk_reembolso_confirmado_por CHECK(confirmado_por>0)'))
            else:c.execute(text("INSERT INTO reembolsos_financeiros(pagamento_id,metodo,valor_cents,status,confirmado_por) SELECT id,'PIX_MANUAL',4990,'CONFIRMADO',999 FROM pagamentos LIMIT 1"))
    with pytest.raises(psycopg.Error):aplicar015(motor)
    with motor.connect() as c:
        assert c.execute(text("SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='pagamentos' AND column_name='mp_status'")).scalar()==0


def aprovado(ambiente):
    pid=duplicata(ambiente)
    assert ambiente[1].post(f'/me/reembolso/{pid}',json={}).status_code==200
    admin(ambiente)
    assert ambiente[1].post(f'/admin/reembolsos/{pid}/aprovar',json={}).status_code==200
    aplicar014(ambiente[2].kw['bind'])
    return pid


def test_registro_concorrente_nao_duplica(ambiente_compra):
    main,_,factory,_,_=ambiente_compra;pid=aprovado(ambiente_compra)
    def operacao(db,i):
        return main.registrar_reembolso_pix_manual(pid,schemas.ReembolsoPixManualCreate(valor_cents=4990,referencia_comprovante='extrato'),db,SimpleNamespace(id=2,is_admin=True))
    resultados=paralelo(factory,operacao)
    assert sum(isinstance(r,dict) for r in resultados)==1 and 409 in resultados
    with factory() as db:assert db.query(m.ReembolsoFinanceiro).count()==1


@pytest.mark.parametrize('canal',['webhook','retorno','confirmacao_repetida'])
def test_confirmacao_concorrente_preserva_acesso(ambiente_compra,canal):
    main,client,factory,_,_=ambiente_compra;pid=aprovado(ambiente_compra)
    rid=registrar(client,pid).json()['reembolso_id']
    with factory() as db:
        p=db.get(m.Pagamento,pid);raiz=p.pagamento_origem_id
        a=db.query(m.AcessoCurso).one();snapshot=(a.ativo,a.data_fim)
    dados={'id':'102','status':'refunded','transaction_amount':49.90,'currency_id':'BRL',
        'external_reference':f'user:1|curso:1|tempo:1|pagamento:{raiz}'}
    def operacao(db,i):
        if i==0 or canal=='confirmacao_repetida':
            return main.confirmar_reembolso_pix_manual(rid,True,db,SimpleNamespace(id=2,is_admin=True))
        if canal=='retorno':return main.confirmar_pagamento({'payment_id':'102','curso_id':1},db,SimpleNamespace(id=1))
        return asyncio.run(webhook(main,db,102))
    with patch.object(main,'consultar_pagamento') as api,patch.object(main,'validar_assinatura_mercadopago',return_value=True):
        api.return_value.status_code=200;api.return_value.json.return_value=dados
        resultados=paralelo(factory,operacao)
    assert any(isinstance(r,dict) and r.get('status')=='CONFIRMADO' for r in resultados)
    if canal=='confirmacao_repetida':assert 400 in resultados
    with factory() as db:
        rf=db.get(m.ReembolsoFinanceiro,rid);assert rf.status=='CONFIRMADO' and rf.confirmado_por==2
        p=db.get(m.Pagamento,pid);assert p.status=='REFUNDED' and p.mp_payment_id=='102'
        assert p.ocorrencia_financeira=='COBRANCA_DUPLICADA'
        assert db.query(m.PeriodoAcessoPagamento).count()==1
        a=db.query(m.AcessoCurso).one();assert (a.ativo,a.data_fim)==snapshot


def test_decisoes_concorrentes_nao_sobrescrevem(ambiente_compra):
    main,client,factory,_,_=ambiente_compra;pid=duplicata(ambiente_compra)
    assert client.post(f'/me/reembolso/{pid}',json={}).status_code==200
    aplicar014(factory.kw['bind'])
    def operacao(db,i):
        funcao=main.aprovar_reembolso if i==0 else main.recusar_reembolso
        return funcao(pid,db,SimpleNamespace(id=2,is_admin=True))
    resultados=paralelo(factory,operacao)
    assert sum(isinstance(r,dict) for r in resultados)==1 and 400 in resultados
    with factory() as db:assert db.query(m.ReembolsoFinanceiro).count()==0


def test_historico_preserva_duplicata_apos_chargeback(ambiente_compra):
    main,_,factory,_,_=ambiente_compra;pid=duplicata(ambiente_compra)
    with factory() as db:
        p=db.get(m.Pagamento,pid)
        p.mp_status='CHARGED_BACK'
        assert main.reconciliar_sem_conceder_acesso(db,p)
        historico=main.historico_compras_usuario(db,SimpleNamespace(id=1))
        assert {p['mp_payment_id'] for p in historico}=={'101','102'}
        linha=next(p for p in historico if p['pagamento_id']==pid)
        assert linha['mp_status']=='CHARGED_BACK' and linha['ocorrencia_financeira']=='COBRANCA_DUPLICADA'
        assert db.query(m.ReembolsoFinanceiro).count()==0
