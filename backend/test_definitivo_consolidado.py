"""Provas da consolidação M2 -> definitivo; somente fixtures SQLite e API simulada."""
from pathlib import Path
import subprocess

from fastapi import FastAPI
from sqlalchemy import event, inspect, select

from app.pausa_financeira import controle, inbox, instalar
from test_compras_fluxo import ambiente_compra, motor
from test_pausa_financeira import modo, enviar, admin


def test_identidade_definitiva(ambiente_compra):
    main, client = ambiente_compra[:2]
    admin(ambiente_compra)
    assert main.app.state.protecao_financeira.definitivo is True
    resposta = client.get('/admin/financeiro/manutencao')
    assert resposta.status_code == 200
    estado = resposta.json()
    assert estado['backend_definitivo'] is True
    assert estado['versao_protecao'] == 'pausa-financeira-v2-transacional'


def test_reinstalar_preserva_pausa_geracao_sem_dml(ambiente_compra):
    main, client, factory = ambiente_compra[:3]
    assert modo(ambiente_compra, 'PAUSADO').status_code == 200
    engine = factory.kw['bind']
    app = FastAPI()

    @app.post('/webhooks/mercadopago')
    def original():
        return {}

    def somente_leitura(c, cursor, sql, params, context, many):
        assert sql.lstrip().split()[0].upper() not in {'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP'}

    event.listen(engine, 'before_cursor_execute', somente_leitura)
    try:
        protecao = instalar(app, engine, factory, main.get_db, main.get_usuario_atual,
            main.validar_assinatura_mercadopago, main.processar_pagamento_mp, main.mp_headers)
        estado = protecao.estado()
        assert estado['modo'] == 'PAUSADO' and estado['geracao'] == 1
        assert estado['backend_definitivo'] is True
    finally:
        event.remove(engine, 'before_cursor_execute', somente_leitura)


def test_webhook_pausado_preserva_inbox_sem_processar(ambiente_compra):
    assert modo(ambiente_compra, 'PAUSADO').status_code == 200
    for _ in range(2):
        r = enviar(ambiente_compra)
        assert r.status_code == 200 and r.json()['armazenado'] is True
        assert r.json()['processado'] is False
    with ambiente_compra[2].kw['bind'].connect() as c:
        rows = c.execute(select(inbox)).mappings().all()
        assert len(rows) == 1 and rows[0]['estado'] == 'PENDENTE'
    ambiente_compra[3].assert_not_called()
    ambiente_compra[4].assert_not_called()


def test_recuperacao_exige_acao_explicita_e_mantem_checkout_bloqueado(ambiente_compra):
    assert modo(ambiente_compra, 'PAUSADO').status_code == 200
    client = ambiente_compra[1]
    r = client.post('/admin/financeiro/manutencao', json={
        'modo': 'RECUPERACAO', 'geracao': 1, 'motivo': 'fixture isolada'})
    assert r.status_code == 200, r.text
    assert r.json()['modo'] == 'RECUPERACAO' and r.json()['geracao'] == 2
    assert client.post('/checkout/mercadopago', json={}).status_code == 503
    ambiente_compra[3].assert_not_called()


def test_nao_reabre_com_inbox_pendente(ambiente_compra):
    assert modo(ambiente_compra, 'PAUSADO').status_code == 200
    main, client = ambiente_compra[:2]
    main.app.state.protecao_financeira.armazenar('101', 'teste:pendente', 'WEBHOOK')
    r = client.post('/admin/financeiro/manutencao', json={
        'modo': 'NORMAL', 'geracao': 1, 'motivo': 'fixture isolada',
        'conferencia_provedor': True})
    assert r.status_code == 409
    with ambiente_compra[2].kw['bind'].connect() as c:
        assert c.execute(select(controle.c.modo, controle.c.geracao)).one() == ('PAUSADO', 1)


def test_campos_014015_e_protecao_m2_preservados(ambiente_compra):
    engine = ambiente_compra[2].kw['bind']
    cols = {c['name']: c for c in inspect(engine).get_columns('pagamentos')}
    assert cols['pagamento_origem_id']['nullable'] is True
    assert cols['mp_status']['nullable'] is True and cols['mp_status']['type'].length == 30
    assert next(c for c in inspect(engine).get_columns('reembolsos_financeiros')
                if c['name'] == 'confirmado_por')['nullable'] is True
    root = Path(__file__).resolve().parents[1]
    for name in ('backend/app/pausa_financeira.py', 'backend/app/financeiro_transacional.py',
                 'backend/app/database.py', 'backend/manutencao_temporaria.py',
                 'backend/manutencao_temporaria.md'):
        original = subprocess.check_output(['git', 'show',
            'f36e2a1c8008a8f9cc0445397d292cb6d5460d43:' + name], cwd=root)
        assert (root / name).read_bytes() == original, name
