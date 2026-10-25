"""Locks, integridade e migration em PostgreSQL local descartável."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import psycopg
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from app import models as m
from test_compras_concorrencia_pg import motor
from test_compras_fluxo import ambiente_compra
from test_transacoes_mp import preparar, webhook

MIGRATION = Path(__file__).parent / 'migrations/014_pagamentos_multiplas_transacoes.sql'


def aplicar(engine):
    with engine.connect() as c:
        c.connection.driver_connection.execute(MIGRATION.read_text())


@pytest.mark.parametrize('mesmo_id', [False, True])
@pytest.mark.parametrize('caminhos', ['misto', 'webhooks'])
def test_tres_caminhos_concorrentes(ambiente_compra, motor, mesmo_id, caminhos):
    main, _, f, post, _ = ambiente_compra
    pid, dados, transacoes, _ = preparar(ambiente_compra)
    aplicar(motor)
    transacoes.update({str(tx): dados(tx, 'approved') for tx in (101, 102, 103)})
    barreira = Barrier(3)
    def executar(i):
        tx = 101 if mesmo_id else 101 + i
        with f() as db:
            barreira.wait(timeout=10)
            try:
                if caminhos == 'webhooks':
                    return asyncio.run(webhook(main, db, tx))
                if i == 0:
                    return main.confirmar_pagamento({'payment_id': str(tx), 'curso_id': 1}, db, SimpleNamespace(id=1))
                if i == 1:
                    return asyncio.run(webhook(main, db, tx))
                return main.admin_revalidar_pagamento({'mp_payment_id': str(tx)}, db, SimpleNamespace(is_admin=True, tipo_admin="admin_geral"))
            except Exception:
                db.rollback()
                raise
    with patch.object(main, 'validar_assinatura_mercadopago', return_value=True):
        with ThreadPoolExecutor(max_workers=3) as executor:
            resultados = list(executor.map(executar, range(3)))
        with f() as db:
            for _ in range(2): asyncio.run(webhook(main, db, 101))
    assert sum(r.get('liberou_acesso', False) for r in resultados) <= 1
    with f() as db:
        assert db.query(m.Pagamento).count() == (1 if mesmo_id else 3)
        assert db.query(m.ContratacaoCurso).count() == 1
        assert db.query(m.PeriodoAcessoPagamento).count() == 1
        assert db.query(m.Pagamento).filter_by(ocorrencia_financeira='COBRANCA_DUPLICADA').count() == (0 if mesmo_id else 2)
        assert db.get(m.Pagamento, pid).mp_payment_id in ('101', '102', '103')
    post.assert_called_once()


def test_migration_antiga_idempotente_preserva_dados(ambiente_compra, motor):
    main, _, f, _, _ = ambiente_compra
    pid, _, _, _ = preparar(ambiente_compra)
    with ambiente_compra[2].begin() as c:
        # A fixture definitiva aplica 014; retirar o trigger ao simular o esquema anterior.
        c.execute(text('DROP TRIGGER IF EXISTS validar_origem_transacao_pagamento ON pagamentos'))
        c.execute(text('ALTER TABLE pagamentos DROP COLUMN pagamento_origem_id CASCADE'))
        c.execute(text('DROP INDEX uq_pagamentos_mp_payment_id'))
        antes = list(c.execute(text('SELECT * FROM pagamentos')).mappings())
    aplicar(motor)
    aplicar(motor)
    with motor.connect() as c:
        depois = list(c.execute(text('SELECT * FROM pagamentos')).mappings())
        assert [{k: v for k, v in row.items() if k != 'pagamento_origem_id'} for row in depois] == antes
        assert all(row['pagamento_origem_id'] is None for row in depois)


def test_migration_duplicados_interrompe_sem_escrita(ambiente_compra, motor):
    preparar(ambiente_compra)
    with ambiente_compra[2].begin() as c:
        c.execute(text('DROP TRIGGER IF EXISTS proteger_checkout_identidade ON pagamentos'))
        c.execute(text('DROP TRIGGER IF EXISTS validar_origem_transacao_pagamento ON pagamentos'))
        c.execute(text('ALTER TABLE pagamentos DROP COLUMN pagamento_origem_id CASCADE'))
        c.execute(text('DROP INDEX uq_pagamentos_mp_payment_id'))
        c.execute(text("UPDATE pagamentos SET mp_payment_id='historico'"))
        c.execute(text("INSERT INTO pagamentos(usuario_id,curso_id,status,valor_cents,mp_payment_id,tipo_compra) VALUES(1,1,'PENDING',4990,'historico','NOVA')"))
    with pytest.raises(psycopg.Error, match='duplicado'): aplicar(motor)
    with motor.connect() as c:
        assert c.execute(text("SELECT count(*) FROM information_schema.columns WHERE table_name='pagamentos' AND column_name='pagamento_origem_id'")).scalar() == 0
        assert c.execute(text('SELECT count(*) FROM pagamentos')).scalar() == 2


@pytest.mark.parametrize('erro', ['cadeia', 'usuario', 'pref', 'valor', 'id', 'origem_mutavel'])
def test_integridade_direta_no_banco(ambiente_compra, motor, erro):
    _, client, f, _, _ = ambiente_compra
    pid, _, _, _ = preparar(ambiente_compra)
    aplicar(motor)
    for tx in (101, 102):
        assert client.post('/pagamentos/confirmar', json={'payment_id': tx, 'curso_id': 1}).status_code == 200
    with f() as db:
        filho = db.query(m.Pagamento).filter_by(mp_payment_id='102').one()
        fid = filho.id
    with pytest.raises(DBAPIError):
        with ambiente_compra[2].begin() as c:
            if erro == 'id':
                c.execute(text("UPDATE pagamentos SET mp_payment_id='999' WHERE id=:id"), {'id': pid})
            elif erro == 'origem_mutavel':
                c.execute(text('UPDATE pagamentos SET pagamento_origem_id=:f WHERE id=:p'), {'f': fid, 'p': pid})
            else:
                origem, uid, pref, valor = (fid if erro == 'cadeia' else pid), (2 if erro == 'usuario' else 1), ('outra' if erro == 'pref' else 'pref_teste'), (1 if erro == 'valor' else 4990)
                c.execute(text('INSERT INTO pagamentos(usuario_id,curso_id,tempo_acesso_id,oportunidade_id,pagamento_origem_id,mp_preference_id,status,valor_cents,tipo_compra) SELECT :u,curso_id,tempo_acesso_id,oportunidade_id,:o,:pref,\'PENDING\',:v,tipo_compra FROM pagamentos WHERE id=:p'), {'u': uid, 'o': origem, 'pref': pref, 'v': valor, 'p': pid})


def test_indice_unico_impede_transacao_duplicada(ambiente_compra, motor):
    preparar(ambiente_compra)
    aplicar(motor)
    with pytest.raises(IntegrityError):
        with ambiente_compra[2].begin() as c:
            c.execute(text("UPDATE pagamentos SET mp_payment_id='101'"))
            c.execute(text("INSERT INTO pagamentos(usuario_id,curso_id,status,valor_cents,mp_payment_id,tipo_compra) VALUES(1,1,'PENDING',4990,'101','NOVA')"))


def test_reembolso_e_contestacao_preservam_transacao_especifica(ambiente_compra, motor):
    main, client, f, _, _ = ambiente_compra
    _, dados, transacoes, _ = preparar(ambiente_compra)
    aplicar(motor)
    m.Base.metadata.create_all(motor, tables=[m.ReembolsoFinanceiro.__table__, m.ContestacaoPagamento.__table__])
    for tx in (101, 102):
        transacoes[str(tx)] = dados(tx, 'approved')
        assert client.post('/pagamentos/confirmar', json={'payment_id': tx, 'curso_id': 1}).status_code == 200
    with f() as db:
        pago = db.query(m.Pagamento).filter_by(mp_payment_id='101').one()
        duplicado = db.query(m.Pagamento).filter_by(mp_payment_id='102').one()
        dup_id = duplicado.id
        assert duplicado.contratacao_id is None
        r = main.consultar_direitos_acesso_apos_reembolso(db, 1, 1, pago.id)
        assert r['pagamentos_sem_historico'] == []  # Duplicidade não é compra histórica desconhecida.
        assert db.query(m.ReembolsoFinanceiro).count() == 0
        assert db.query(m.ContestacaoPagamento).count() == 0
        duplicado.status = 'REFUND_IN_PROCESS'
        reembolso = m.ReembolsoFinanceiro(pagamento_id=dup_id, metodo='PIX_MANUAL', valor_cents=duplicado.valor_cents, status='PENDENTE')
        contestacao = m.ContestacaoPagamento(pagamento_id=dup_id, mp_dispute_id='disputa-simulada', valor_cents=duplicado.valor_cents)
        db.add_all([reembolso, contestacao]);db.commit()
        assert db.query(m.PeriodoAcessoPagamento).one().pagamento_id == pago.id
        assert db.query(m.ReembolsoFinanceiro).one().pagamento_id == dup_id
        assert db.query(m.ContestacaoPagamento).one().pagamento_id == dup_id
        historico = main.historico_compras_usuario(db, SimpleNamespace(id=1))
        assert {p['mp_payment_id'] for p in historico} == {'101', '102'}
        listagem = main.admin_listar_pagamentos(None, db, SimpleNamespace(is_admin=True, tipo_admin="admin_geral"))
        linha = next(p for p in listagem if p['id'] == dup_id)
        assert linha['mp_payment_id'] == '102' and linha['ocorrencia_financeira'] == 'COBRANCA_DUPLICADA'


@pytest.mark.parametrize('estrutura', ['tipo', 'indice', 'tabela', 'oportunidade'])
def test_migration_incompativel_rollback(ambiente_compra, motor, estrutura):
    preparar(ambiente_compra)
    with ambiente_compra[2].begin() as c:
        c.execute(text('ALTER TABLE pagamentos DROP COLUMN pagamento_origem_id CASCADE'))
        if estrutura == 'tipo': c.execute(text('ALTER TABLE pagamentos ADD COLUMN pagamento_origem_id text'))
        elif estrutura == 'indice':
            c.execute(text('DROP INDEX uq_pagamentos_mp_payment_id'))
            c.execute(text('CREATE INDEX uq_pagamentos_mp_payment_id ON pagamentos(status)'))
        elif estrutura == 'tabela': c.execute(text('DROP TABLE oportunidades_compra CASCADE'))
        else: c.execute(text('ALTER TABLE oportunidades_compra DROP COLUMN usuario_id CASCADE'))
    with pytest.raises(psycopg.Error): aplicar(motor)
    with motor.connect() as c:
        assert c.execute(text('SELECT count(*) FROM pagamentos')).scalar() == 1
        tipo = c.execute(text("SELECT data_type FROM information_schema.columns WHERE table_schema='public' AND table_name='pagamentos' AND column_name='pagamento_origem_id'")).scalar()
        assert tipo == ('text' if estrutura == 'tipo' else None)


@pytest.mark.parametrize('mesmo_id', [False, True])
def test_novas_tentativas_pendentes_concorrentes(ambiente_compra, motor, mesmo_id):
    main, client, f, _, _ = ambiente_compra
    pid, _, _, _ = preparar(ambiente_compra)
    aplicar(motor)
    assert client.post('/pagamentos/confirmar', json={'payment_id': 101, 'curso_id': 1}).status_code == 200
    from test_compras_concorrencia_pg import paralelo
    with patch.object(main, 'validar_assinatura_mercadopago', return_value=True):
        def processar(db, i):
            tx = 102 if mesmo_id else 102 + i
            if i == 0:
                return main.confirmar_pagamento({'payment_id': tx, 'curso_id': 1}, db, SimpleNamespace(id=1))
            return asyncio.run(webhook(main, db, tx))
        respostas = paralelo(f, processar)
    assert all(r['status'] == 'PENDING' for r in respostas)
    with f() as db:
        assert db.query(m.Pagamento).count() == (2 if mesmo_id else 3)
        assert db.get(m.Pagamento, pid).mp_payment_id == '101'
        assert db.query(m.ContratacaoCurso).count() == 0


def test_pg_rollback_contratacao(ambiente_compra, motor):
    aplicar(motor)
    from test_transacoes_mp import test_falha_contratacao_rollback_integral
    test_falha_contratacao_rollback_integral(ambiente_compra)
