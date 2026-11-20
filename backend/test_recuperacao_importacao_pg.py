"""Barreira de recuperação no PostgreSQL descartável usado pelas regressões comerciais."""
from fastapi.testclient import TestClient
from sqlalchemy import select
from app import models as m
from app.pausa_financeira import controle, inbox
from test_cursos_comerciais_concorrencia_pg import pg
import pytest


@pytest.fixture
def modo_recuperacao(monkeypatch):
    monkeypatch.setenv('RESUMAO_RECUPERACAO_IMPORTACAO', '1')


def test_barreira_e_notificacao_duravel(modo_recuperacao, pg, monkeypatch):
    main, factory, engine, provedor = pg
    monkeypatch.setattr(main, 'validar_assinatura_mercadopago', lambda request, pid: True)
    with engine.begin() as c:
        c.execute(controle.update().where(controle.c.id==1).values(modo='PAUSADO',geracao=1))
    # O schema de teste é isolado por search_path; o verificador de inicialização
    # de produção exige objetos em public, portanto não é executado nesta fixture.
    client = TestClient(main.app)
    try:
        for metodo, rota in [('POST','/checkout/mercadopago'),('POST','/admin/acessos'),
                             ('POST','/admin/importacoes/cursos'),('PUT','/admin/cursos/1/publicar')]:
            assert client.request(metodo,rota,json={}).status_code==503
        for _ in range(2):
            resposta=client.post('/webhooks/mercadopago?type=payment&data.id=101',
                headers={'x-request-id':'evento-teste'},
                json={'id':'evento-teste','type':'payment','data':{'id':'101'}})
            assert resposta.status_code==200 and resposta.json()['armazenado']
    finally:
        client.close()
    with engine.connect() as c:
        assert c.execute(select(inbox.c.estado)).scalars().all()==['PENDENTE']
    with factory() as db:
        assert db.query(m.Pagamento).count()==0
        assert db.query(m.ContratacaoCurso).count()==0
        assert db.query(m.AcessoCurso).count()==0
    provedor.assert_not_called()
