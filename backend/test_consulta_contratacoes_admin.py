"""Consulta administrativa em SQLite descartável; sem efeitos financeiros."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from app import models as m
from test_compras_fluxo import motor, ambiente_compra


def test_consulta_atualizada_autorizada_e_isolada(ambiente_compra):
    main, client, factory, post, _ = ambiente_compra
    admin=SimpleNamespace(id=2,is_admin=True,tipo_admin='admin_geral')
    main.app.dependency_overrides[main.get_usuario_atual]=lambda:admin
    fim=datetime.utcnow()+timedelta(days=10)
    resposta=client.post('/admin/acessos',json={'usuario_id':1,'curso_id':1,'data_fim':fim.isoformat()+'Z'})
    assert resposta.status_code==200, resposta.text
    cid=resposta.json()['contratacao_id']
    consulta='/admin/alunos/1/contratacoes-admin?curso_id=1'
    dados=client.get(consulta)
    assert dados.status_code==200 and len(dados.json())==1
    assert dados.json()[0]['id']==cid and dados.json()[0]['vigente'] is True
    assert client.get('/admin/alunos/1/contratacoes-admin?curso_id=2').json()==[]
    assert client.get('/admin/alunos/2/contratacoes-admin?curso_id=1').json()==[]
    with factory() as db:
        c=db.get(m.ContratacaoCurso,cid);c.data_fim=fim+timedelta(days=2);db.commit()
    assert client.get(consulta).json()[0]['data_fim'].startswith((fim+timedelta(days=2)).isoformat()[:19])
    main.app.dependency_overrides[main.get_usuario_atual]=lambda:SimpleNamespace(id=1,is_admin=False)
    assert client.get(consulta).status_code==403
    with factory() as db:
        assert db.query(m.ContratacaoCurso).count()==1
        assert db.query(m.ConcessaoAcessoAdmin).count()==1
        assert db.query(m.Pagamento).count()==0
    post.assert_not_called()
