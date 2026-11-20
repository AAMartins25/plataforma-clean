"""Recuperação local: nenhuma conexão ou provedor de produção."""
import pytest
from sqlalchemy import select
from app import models as m
from app.pausa_financeira import inbox
from app.recuperacao_importacao import instalar
from test_compras_fluxo import ambiente_compra, motor
from test_pausa_financeira import enviar, modo
from test_transacoes_mp import preparar


@pytest.fixture
def recuperacao(monkeypatch):
    monkeypatch.setenv('RESUMAO_RECUPERACAO_IMPORTACAO', '1')


@pytest.mark.parametrize('metodo,rota', [
    ('post','/admin/importacoes/cursos'), ('post','/admin/importacoes/cursos/validar'),
    ('post','/checkout/mercadopago'), ('post','/admin/acessos'),
    ('put','/admin/cursos/1/publicar'), ('put','/admin/cursos/1/config-publica'),
    ('post','/admin/cursos/1/duplicar'),
])
def test_operacoes_novas_bloqueadas(recuperacao, ambiente_compra, metodo, rota):
    main, client, factory, post, get = ambiente_compra
    r = client.request(metodo.upper(), rota, json={}, headers={'Origin':'https://resumaoonline.com.br'})
    assert r.status_code == 503
    assert r.headers['retry-after'] == '60'
    assert r.headers['cache-control'] == 'no-store'
    assert r.headers['access-control-allow-origin'] == 'https://resumaoonline.com.br'
    post.assert_not_called(); get.assert_not_called()
    with factory() as db:
        assert db.query(m.Pagamento).count() == 0
        assert db.query(m.ContratacaoCurso).count() == 0


def test_notificacao_legitima_e_pagamento_previo_preservados(recuperacao, ambiente_compra):
    a=ambiente_compra
    pid, dados, transacoes, _ = preparar(a, legado=True)
    transacoes['101']=dados(101,'approved')
    for _ in range(2):
        resposta=enviar(a,101,'evento-recuperacao')
        assert resposta.status_code==200 and resposta.json()['armazenado']
    with a[2]() as db:
        assert db.query(m.ContratacaoCurso).count()==1
        assert db.query(m.PeriodoAcessoPagamento).count()==1
        assert db.query(m.AcessoCurso).filter_by(usuario_id=1,curso_id=1,ativo=True).count()==1
    with a[2].kw['bind'].connect() as c:
        assert len(c.execute(select(inbox)).all())==1
    assert a[1].post('/checkout/mercadopago',json={'tempo_acesso_id':1}).status_code==503


def test_pausa_financeira_armazenamento_e_recuperacao(recuperacao, ambiente_compra):
    a=ambiente_compra
    _, dados, transacoes, _=preparar(a, legado=True)
    transacoes['101']=dados(101,'approved')
    assert modo(a,'PAUSADO').status_code==200
    assert enviar(a,101,'evento-pausado').json()['armazenado']
    with a[2].kw['bind'].connect() as c:
        assert c.execute(select(inbox.c.estado)).scalar_one()=='PENDENTE'
    assert modo(a,'RECUPERACAO').status_code==200
    r=a[1].post('/admin/financeiro/notificacoes/recuperar',json={'limite':1})
    assert r.status_code==200 and r.json()['resultados'][0]['processado']
    with a[2]() as db:
        assert db.query(m.PeriodoAcessoPagamento).count()==1
    assert modo(a,'NORMAL').status_code==200
    assert a[1].post('/checkout/mercadopago',json={}).status_code==503


def test_configuracao_invalida_falha_fechada(monkeypatch):
    monkeypatch.setenv('RESUMAO_RECUPERACAO_IMPORTACAO','sim')
    with pytest.raises(RuntimeError): instalar(object())
