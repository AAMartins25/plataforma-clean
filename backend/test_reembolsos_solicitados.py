"""Interface administrativa: regressões com SQLite em memória e provedor simulado."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from app import models as m
from test_compras_fluxo import ambiente_compra, motor
from test_reembolso_manual_fluxo import duplicata, admin, registrar


def pendente(ambiente):
    pid = duplicata(ambiente)
    client = ambiente[1]
    assert client.post(f"/me/reembolso/{pid}", json={}).status_code == 200
    admin(ambiente)
    assert client.post(f"/admin/reembolsos/{pid}/aprovar", json={}).status_code == 200
    return pid, registrar(client, pid).json()["reembolso_id"]


def test_listagem_e_confirmacao_exigem_admin(ambiente_compra):
    main, client, factory, _, _ = ambiente_compra
    pid, rid = pendente(ambiente_compra)
    main.app.dependency_overrides[main.get_usuario_atual] = lambda: SimpleNamespace(id=1, is_admin=False)
    assert client.get("/admin/reembolsos").status_code == 403
    assert client.post(f"/admin/reembolsos/{rid}/pix-manual/confirmar?confirmacao_extrato=true", json={}).status_code == 403
    with factory() as db:
        assert db.get(m.ReembolsoFinanceiro, rid).status == "PENDENTE"
    admin(ambiente_compra)
    assert client.post(f"/admin/reembolsos/{rid}/pix-manual/confirmar?confirmacao_extrato=false", json={}).status_code == 400
    assert client.post(f"/admin/reembolsos/{rid}/pix-manual/confirmar", json={}).status_code == 422
    lista = client.get("/admin/reembolsos").json()
    row = next(r for r in lista if r["pagamento_id"] == pid)
    assert row["reembolso_id"] == rid and row["valor_cents"] == 4990


@pytest.mark.parametrize("direito", ["compra", "concessao", "demonstracao", "antiga", "nenhum"])
def test_confirmacao_preserva_direitos_e_impede_repeticao(ambiente_compra, direito):
    main, client, factory, _, _ = ambiente_compra
    duplicata(ambiente_compra)
    agora = datetime.utcnow()
    with factory() as db:
        pagamento = db.query(m.Pagamento).filter_by(mp_payment_id="101").one()
        pid = pagamento.id
        for demo in db.query(m.DemonstracaoCurso).all():
            demo.ativo = False
        if direito in ("compra", "antiga"):
            outro = m.Pagamento(usuario_id=1, curso_id=1, status="APPROVED", valor_cents=4990, aprovado_em=agora)
            db.add(outro); db.flush()
            if direito == "compra":
                db.add(m.PeriodoAcessoPagamento(pagamento_id=outro.id, usuario_id=1, curso_id=1,
                    data_inicio=agora-timedelta(days=1), data_fim=agora+timedelta(days=180)))
        elif direito == "concessao":
            db.add(m.ConcessaoAcessoAdmin(usuario_id=1, curso_id=1, ativo=True,
                data_inicio=agora-timedelta(days=1), data_fim=None))
        elif direito == "demonstracao":
            db.query(m.DemonstracaoCurso).first().ativo = True
        db.commit()
        antes = (db.query(m.ContratacaoCurso).count(), db.query(m.PeriodoAcessoPagamento).count())
    main.app.dependency_overrides[main.get_usuario_atual] = lambda: SimpleNamespace(id=1, is_admin=False)
    assert client.post(f"/me/reembolso/{pid}", json={}).status_code == 200
    admin(ambiente_compra)
    assert client.post(f"/admin/reembolsos/{pid}/aprovar", json={}).status_code == 200
    rid = registrar(client, pid).json()["reembolso_id"]
    assert registrar(client, pid).status_code == 409
    url = f"/admin/reembolsos/{rid}/pix-manual/confirmar?confirmacao_extrato=true"
    resposta = client.post(url, json={})
    assert resposta.status_code == 200, resposta.text
    assert client.post(url, json={}).status_code == 400
    with factory() as db:
        assert db.query(m.AcessoCurso).one().ativo == (direito != "nenhum")
        assert db.get(m.ReembolsoFinanceiro, rid).confirmado_por == 2
        assert db.get(m.Pagamento, pid).status == "REFUNDED"
        assert antes == (db.query(m.ContratacaoCurso).count(), db.query(m.PeriodoAcessoPagamento).count())
