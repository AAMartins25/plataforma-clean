"""Rotas pessoais de vendas com JWT real, SQLite efêmero e sem serviços externos."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models as m, vendedores
from app.auth import criar_token
from test_questoes_pratica_patch import carregar_main_isolado


AGORA = datetime(2026, 10, 25, 12)
ROTAS = ('/me/vendedor', '/me/vendedor/vendas')


class Relogio(datetime):
    @classmethod
    def utcnow(cls):
        return AGORA


def headers(uid=1, **kwargs):
    return {'Authorization': 'Bearer ' + criar_token({'sub': str(uid)}, **kwargs)}


@pytest.fixture
def ambiente(monkeypatch):
    monkeypatch.setattr(vendedores, 'datetime', Relogio)
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False},
                           poolclass=StaticPool)

    @event.listens_for(engine, 'connect')
    def foreign_keys(conn, _):
        conn.execute('PRAGMA foreign_keys=ON')

    tabelas = {cls.__table__ for cls in (
        m.Usuario, m.Curso, m.Vendedor, m.CupomDesconto, m.Pagamento, m.AcessoCurso)}
    while True:
        dependencias = {fk.column.table for tabela in tabelas for fk in tabela.foreign_keys}
        if dependencias <= tabelas:
            break
        tabelas |= dependencias
    m.Base.metadata.create_all(engine, tables=list(tabelas))
    factory = sessionmaker(bind=engine)
    with factory() as db:
        for uid in range(1, 6):
            db.add(m.Usuario(id=uid, nome=f'Usuário {uid}', email=f'u{uid}@example.com',
                             cpf=str(uid), telefone='0', senha_hash='teste', ativo=uid != 5,
                             is_admin=uid == 3, tipo_admin='admin_geral' if uid == 3 else None,
                             perfil_inicial='VENDEDOR' if uid in (1, 2, 5) else 'ALUNO'))
        db.add(m.Curso(id=1, nome='Curso 1'))
        db.add(m.Curso(id=2, nome='Curso 2'))
        db.flush()
        for vid, uid in ((1, 1), (2, 2), (3, 5)):
            db.add(m.Vendedor(id=vid, usuario_id=uid, nome=f'Parceiro {vid}',
                              email=f'p{vid}@example.com', ativo=True))
        db.flush()
        db.add_all([
            m.CupomDesconto(id=1, codigo='AA001', vendedor_id=1, ativo=True),
            m.CupomDesconto(id=2, codigo='AA002', vendedor_id=1, ativo=False),
            m.CupomDesconto(id=3, codigo='BB001', vendedor_id=2, ativo=True),
        ])
        db.commit()
    try:
        with carregar_main_isolado(factory, engine) as main:
            monkeypatch.setattr(main, 'datetime', Relogio)
            with TestClient(main.app) as client:
                yield main, client, factory, engine
    finally:
        engine.dispose()


def pagamento(db, *, vendedor=1, cupom='AA001', valor=4391, dias=8, curso=1,
              status='APPROVED', **campos):
    dados = dict(usuario_id=4, curso_id=curso, vendedor_id=vendedor, codigo_cupom=cupom,
                 valor_cents=valor, status=status, criado_em=AGORA-timedelta(days=20),
                 aprovado_em=AGORA-timedelta(days=dias))
    dados.update(campos)
    p = m.Pagamento(**dados)
    db.add(p)
    db.flush()
    return p.id


@pytest.mark.parametrize('rota', ROTAS)
@pytest.mark.parametrize('caso', ['ausente', 'invalido', 'expirado', 'inativo', 'inexistente'])
def test_autenticacao_real(ambiente, rota, caso):
    _, c, _, _ = ambiente
    h = {'ausente': {}, 'invalido': {'Authorization': 'Bearer invalido'},
         'expirado': headers(1, expires_minutes=-1), 'inativo': headers(5),
         'inexistente': headers(999)}[caso]
    assert c.get(rota, headers=h).status_code == 401


@pytest.mark.parametrize('uid', [3, 4])
def test_sem_vinculo_nao_basta_ser_admin(ambiente, uid):
    _, c, _, _ = ambiente
    assert c.get(ROTAS[0], headers=headers(uid)).status_code == 404
    assert c.get(ROTAS[1], headers=headers(uid)).status_code == 403


@pytest.mark.parametrize('ativo,descredenciado,status', [
    (True, None, 200), (True, AGORA-timedelta(days=40), 200),
    (False, AGORA-timedelta(days=29, hours=23, minutes=59, seconds=59), 200),
    (False, AGORA-timedelta(days=30), 403),
    (False, AGORA-timedelta(days=31), 403), (False, None, 403),
])
def test_janela_descredenciamento_igual_a_me(ambiente, ativo, descredenciado, status):
    _, c, f, _ = ambiente
    with f() as db:
        v = db.get(m.Vendedor, 1)
        v.ativo, v.descredenciado_em = ativo, descredenciado
        pagamento(db)
        db.commit()
    assert c.get('/me', headers=headers()).json()['is_vendedor'] == (status == 200)
    for rota in ROTAS:
        r = c.get(rota, headers=headers())
        assert r.status_code == status, r.text
        if status == 200:
            if rota == ROTAS[0]:
                assert r.json()['ativo'] is ativo
            else:
                assert r.json()['total_vendas'] == 1


def test_contrato_vazio_e_cupons_sem_vendas(ambiente):
    main, c, _, _ = ambiente
    assert all(rota in main.app.openapi()['paths'] for rota in ROTAS)
    assert c.get(ROTAS[0], headers=headers()).json() == {
        'id': 1, 'nome': 'Parceiro 1', 'email': 'p1@example.com', 'ativo': True}
    result = c.get(ROTAS[1], headers=headers()).json()
    assert result == {
        'vendedor': {'id': 1, 'nome': 'Parceiro 1'},
        'total_vendas': 0, 'total_vendas_efetivas': 0, 'total_vendas_a_confirmar': 0,
        'valor_vendas_efetivas_cents': 0, 'valor_vendas_a_confirmar_cents': 0,
        'vendas_efetivas': [], 'vendas_a_confirmar': [],
        'cupons': [dict(codigo_cupom=codigo, ativo=ativo, total_vendas=0,
                       vendas_efetivas=0, vendas_a_confirmar=0,
                       valor_vendas_efetivas_cents=0, valor_vendas_a_confirmar_cents=0,
                       cursos_total=[], cursos_efetivos=[], cursos_a_confirmar=[])
                   for codigo, ativo in [('AA001', True), ('AA002', False)]]}


def test_sem_cupons_e_sem_vendas(ambiente):
    _, c, f, _ = ambiente
    with f() as db:
        db.query(m.CupomDesconto).filter_by(vendedor_id=1).delete()
        db.commit()
    result = c.get(ROTAS[1], headers=headers()).json()
    assert result['cupons'] == [] and result['total_vendas'] == 0


def test_apuracao_historica_valores_e_agrupamento(ambiente):
    _, c, f, _ = ambiente
    with f() as db:
        antigos = [pagamento(db, valor=4391), pagamento(db, valor=4391),
                   pagamento(db, valor=9000, curso=2),
                   pagamento(db, valor=5000, cupom='AA002')]
        recente = pagamento(db, valor=3000, dias=1)
        db.commit()
    result = c.get(ROTAS[1], headers=headers()).json()
    assert result['total_vendas'] == 5
    assert result['total_vendas_efetivas'] == 4
    assert result['total_vendas_a_confirmar'] == 1
    assert result['valor_vendas_efetivas_cents'] == 22782
    assert result['valor_vendas_a_confirmar_cents'] == 3000
    assert {p['pagamento_id'] for p in result['vendas_efetivas']} == set(antigos)
    assert result['vendas_a_confirmar'] == [dict(
        pagamento_id=recente, codigo_cupom='AA001', curso_id=1, nome_curso='Curso 1',
        valor_cents=3000, data_pagamento=(AGORA-timedelta(days=1)).isoformat())]
    cupom = result['cupons'][0]
    assert cupom['total_vendas'] == 4 and cupom['vendas_efetivas'] == 3
    assert cupom['valor_vendas_efetivas_cents'] == 17782
    grupos = {(g['curso_id'], g['valor_cents']): g['quantidade'] for g in cupom['cursos_total']}
    assert grupos == {(1, 4391): 2, (1, 3000): 1, (2, 9000): 1}
    assert result['cupons'][1]['ativo'] is False
    assert result['cupons'][1]['total_vendas'] == 1


@pytest.mark.parametrize('delta,confirmada', [
    (timedelta(days=7, microseconds=-1), False),
    (timedelta(days=7), True), (timedelta(days=7, microseconds=1), True),
])
@pytest.mark.parametrize('legado', [False, True])
def test_limite_sete_dias_e_fallback_legado(ambiente, delta, confirmada, legado):
    _, c, f, _ = ambiente
    with f() as db:
        pagamento(db, aprovado_em=None if legado else AGORA-delta,
                  criado_em=AGORA-delta if legado else AGORA-timedelta(days=90))
        db.commit()
    result = c.get(ROTAS[1], headers=headers()).json()
    assert result['total_vendas_efetivas'] == int(confirmada)
    assert result['total_vendas_a_confirmar'] == int(not confirmada)


@pytest.mark.parametrize('status', [
    'PENDENTE', 'PENDING', 'REJECTED', 'CANCELLED', 'REFUNDED', 'CHARGED_BACK',
    'IN_MEDIATION', 'REFUND_REQUESTED', 'REFUND_IN_PROCESS', 'REFUND_DENIED', 'REFUND_ERROR',
])
def test_preserva_filtro_financeiro_historico(ambiente, status):
    _, c, f, _ = ambiente
    with f() as db:
        pagamento(db, status=status)
        db.commit()
    result = c.get(ROTAS[1], headers=headers()).json()
    assert result['total_vendas'] == 0
    assert result['valor_vendas_efetivas_cents'] == 0


@pytest.mark.parametrize('ocorrencia', ['COBRANCA_DUPLICADA', 'APROVACAO_FORA_PRAZO'])
def test_ocorrencias_approved_nao_sao_vendas(ambiente, ocorrencia):
    _, c, f, _ = ambiente
    with f() as db:
        pagamento(db, ocorrencia_financeira=ocorrencia)
        db.commit()
    assert c.get(ROTAS[1], headers=headers()).json()['total_vendas'] == 0


@pytest.mark.parametrize('novo_dono', [2, None])
def test_atribuicao_historica_cupom_transferido_ou_desvinculado(ambiente, novo_dono):
    _, c, f, _ = ambiente
    with f() as db:
        original = pagamento(db)
        db.get(m.CupomDesconto, 1).vendedor_id = novo_dono
        outro = pagamento(db, vendedor=2)
        sem_dono = pagamento(db, vendedor=None)
        db.commit()
    antigo = c.get(ROTAS[1], headers=headers(1)).json()
    atual = c.get(ROTAS[1], headers=headers(2)).json()
    assert {p['pagamento_id'] for p in antigo['vendas_efetivas']} == {original}
    assert {p['pagamento_id'] for p in atual['vendas_efetivas']} == {outro}
    assert all(p['pagamento_id'] != sem_dono for r in (antigo, atual) for p in r['vendas_efetivas'])
    assert next(x for x in antigo['cupons'] if x['codigo_cupom'] == 'AA001')['ativo'] is False


def test_isolamento_nao_aceita_vendedor_fornecido_pelo_cliente(ambiente):
    _, c, f, _ = ambiente
    with f() as db:
        meu = pagamento(db)
        pagamento(db, vendedor=2, cupom='BB001', valor=99999)
        pagamento(db, vendedor=2, cupom='AA001', valor=99999)
        pagamento(db, vendedor=None, valor=99999)
        pagamento(db, cupom=None)
        pagamento(db, cupom='')
        db.commit()
    for rota in ROTAS:
        result = c.get(rota, params={'vendedor_id': 2, 'usuario_id': 2}, headers=headers()).json()
        if rota == ROTAS[0]:
            assert result['id'] == 1
        else:
            assert result['total_vendas'] == 1
            assert result['valor_vendas_efetivas_cents'] == 4391
            assert result['vendas_efetivas'][0]['pagamento_id'] == meu
            assert {x['codigo_cupom'] for x in result['cupons']} == {'AA001', 'AA002'}


def test_consultas_nao_mutam_dados_nem_chamam_servicos(ambiente, monkeypatch):
    main, c, f, engine = ambiente
    with f() as db:
        pagamento(db)
        db.commit()
    def proibido(*args, **kwargs):
        raise AssertionError('GET pessoal não pode chamar serviço externo')
    monkeypatch.setattr(main.requests, 'get', proibido)
    monkeypatch.setattr(main.requests, 'post', proibido)
    escritas = []
    def registrar(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().split()[0].upper() in {'INSERT', 'UPDATE', 'DELETE'}:
            escritas.append(statement)
    event.listen(engine, 'before_cursor_execute', registrar)
    try:
        for _ in range(2):
            for rota in ROTAS:
                assert c.get(rota, headers=headers()).status_code == 200
        assert escritas == []
    finally:
        event.remove(engine, 'before_cursor_execute', registrar)
