"""Somente SQLite isolado e provedor simulado; textos abaixo são fixtures, não minutas."""
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import pytest
from app import models as m
from test_compras_fluxo import ambiente_compra, motor, contrato

TABELAS = [m.DocumentoJuridicoVersao.__table__, m.PoliticaAceiteJuridico.__table__,
    m.AceiteJuridico.__table__, m.AceiteJuridicoDocumento.__table__, m.AceiteJuridicoPagamento.__table__]

@pytest.fixture
def juridico(ambiente_compra, monkeypatch):
    main, client, factory, post, get = ambiente_compra
    with factory() as db:
        m.Base.metadata.create_all(db.get_bind(), tables=TABELAS)
        for i, tipo in enumerate(('TERMOS', 'PRIVACIDADE'), 1):
            conteudo = f'FIXTURE SEM VALIDADE JURÍDICA {tipo}\n<texto>& fim\n'
            db.add(m.DocumentoJuridicoVersao(id=i, tipo=tipo, versao='teste', titulo=tipo,
                conteudo=conteudo, sha256=sha256(conteudo.encode()).hexdigest(), publicado_em=datetime.now(timezone.utc)))
        db.flush()
        db.add(m.PoliticaAceiteJuridico(id=1, habilitada=True, termos_id=1, privacidade_id=2))
        db.commit()
    return ambiente_compra


def payload(tempo=1, **extra):
    return {'tempo_acesso_id': tempo, 'aceite_juridico': {'aceito': True, 'termos_id': 1, 'privacidade_id': 2}, **extra}

@pytest.mark.parametrize('aceite', [None, {}, {'aceito': False}, {'aceito': 'true'}, {'aceito': 1}])
def test_sem_aceite_nao_cria_nada(juridico, aceite):
    _, c, factory, post, get = juridico
    r = c.post('/checkout/mercadopago', json={'tempo_acesso_id': 1, 'aceite_juridico': aceite})
    assert r.status_code == 400, r.text
    post.assert_not_called(); get.assert_not_called()
    with factory() as db:
        assert db.query(m.Pagamento).count() == db.query(m.OportunidadeCompra).count() == 0

@pytest.mark.parametrize('campo,valor', [('termos_id', 2), ('termos_id', '1'), ('privacidade_id', 99)])
def test_versoes_invalidas(juridico, campo, valor):
    _, c, _, post, get = juridico
    p = payload(); p['aceite_juridico'][campo] = valor
    assert c.post('/checkout/mercadopago', json=p).status_code == 409
    post.assert_not_called(); get.assert_not_called()


def test_compra_registra_e_reabre(juridico):
    _, c, factory, post, get = juridico
    for _ in range(2):
        r = c.post('/checkout/mercadopago', json=payload())
        assert r.status_code == 200, r.text
    assert post.call_count == get.call_count == 1
    with factory() as db:
        assert db.query(m.Pagamento).count() == 1
        assert db.query(m.AceiteJuridico).count() == 2
        a = db.query(m.AceiteJuridico).first()
        assert (a.usuario_id, a.curso_id, a.meses, a.valor_cents, a.modalidade) == (1, 1, 4, 4990, 'NOVA')
        assert a.aceito_em is not None
        assert db.query(m.AceiteJuridicoDocumento).count() == 4
        assert db.query(m.AceiteJuridicoPagamento).count() == 2
        assert db.query(m.PeriodoAcessoPagamento).count() == 0
        assert db.query(m.ContratacaoCurso).count() == 0
    post.reset_mock(); get.reset_mock()
    assert c.post('/checkout/mercadopago', json={'tempo_acesso_id': 1}).status_code == 400
    post.assert_not_called(); get.assert_not_called()


def test_prazo_e_valor_servidor(juridico):
    _, c, factory, _, _ = juridico
    assert c.post('/checkout/mercadopago', json=payload(2, valor_cents=1, usuario_id=2)).status_code == 200
    with factory() as db:
        a = db.query(m.AceiteJuridico).one()
        assert (a.usuario_id, a.meses, a.valor_cents) == (1, 8, 9980)


def test_renovacao_sem_alterar_contrato(juridico):
    _, c, factory, _, _ = juridico
    with factory() as db:
        cid = contrato(db, dias=10)
        fim = db.get(m.ContratacaoCurso, cid).data_fim
    assert c.post('/checkout/mercadopago', json=payload(tipo_compra='RENOVACAO', contratacao_id=cid)).status_code == 200
    with factory() as db:
        assert db.get(m.ContratacaoCurso, cid).data_fim == fim
        assert db.query(m.AceiteJuridico).one().modalidade == 'RENOVACAO'


def test_documento_recuperavel_e_versao_antiga(juridico):
    _, c, factory, _, _ = juridico
    r = c.get('/public/juridico/vigente')
    assert r.json()['obrigatorio'] is True
    assert c.get('/public/juridico/documentos/1').status_code == 200
    assert '&lt;texto&gt;&amp; fim' in c.get('/public/juridico/documentos/1').text
    with factory() as db:
        conteudo = 'FIXTURE NOVA'
        db.add(m.DocumentoJuridicoVersao(id=3, tipo='TERMOS', versao='teste2', titulo='Novo', conteudo=conteudo,
            sha256=sha256(conteudo.encode()).hexdigest(), publicado_em=datetime.now(timezone.utc)))
        db.flush(); db.get(m.PoliticaAceiteJuridico, 1).termos_id = 3; db.commit()
    assert c.post('/checkout/mercadopago', json=payload()).status_code == 409
    assert c.get('/public/juridico/documentos/1').status_code == 200


def test_demo_independe_de_aceite(juridico):
    _, c, factory, post, _ = juridico
    assert c.post('/cursos/1/demonstracao').status_code == 200
    post.assert_not_called()
    with factory() as db: assert db.query(m.AceiteJuridico).count() == 0


def test_pre_ativacao_compativel(juridico):
    _, c, factory, _, _ = juridico
    with factory() as db:
        db.get(m.PoliticaAceiteJuridico, 1).habilitada = False; db.commit()
    assert c.get('/public/juridico/vigente').json()['obrigatorio'] is False
    assert c.post('/checkout/mercadopago', json={'tempo_acesso_id': 1}).status_code == 200
    with factory() as db: assert db.query(m.AceiteJuridico).count() == 0


def test_concessao_administrativa_sem_aceite(juridico):
    from types import SimpleNamespace
    from app.schemas import AcessoCursoCreate
    main, _, factory, _, _ = juridico
    with factory() as db:
        r = main.admin_criar_acesso(payload=AcessoCursoCreate(usuario_id=1, curso_id=2, ativo=True, data_fim=datetime.utcnow()+timedelta(days=30)),
            db=db, usuario=SimpleNamespace(is_admin=True, tipo_admin="admin_geral"))
        assert r['ok']
        assert db.query(m.ConcessaoAcessoAdmin).count() == 1
        assert db.query(m.AceiteJuridico).count() == 0


def test_pagamento_anterior_confirma_sem_tabelas_juridicas(ambiente_compra, monkeypatch):
    from apoio_testes_juridicos import preparar, confirmar
    _, dados, tx, _ = preparar(ambiente_compra)
    # Não existem tabelas jurídicas neste banco: confirmar não deve sequer consultá-las.
    tx['101'] = dados(101, 'approved')
    assert confirmar(ambiente_compra, 101).json()['liberou_acesso']


def test_gerador_preserva_bytes_aprovados():
    from preparar_documentos_juridicos import gerar
    original = "Fixture 'não minuta'\r\nlinha\\fim\n".encode()
    sql = gerar(original, original)
    import base64, re
    cargas = re.findall(r"pg_catalog.decode\((.*?), 'base64'\)", sql, re.S)
    assert len(cargas) == 2
    for carga in cargas:
        assert base64.b64decode(''.join(re.findall(r"'([A-Za-z0-9+/=]+)'", carga)), validate=True) == original
    assert sha256(original).hexdigest() in sql
    assert 'UPDATE politica' not in sql
    with pytest.raises(ValueError): gerar(b'', original)
