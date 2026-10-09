"""Contrato da listagem usado pela priorização visual, sem banco externo."""
from datetime import datetime,timedelta
import pytest
from app import models as m
from test_compras_fluxo import ambiente_compra,motor,demo,contrato

@pytest.mark.parametrize('cenario',['gratuito','pago','ambos','pago_expirado','pago_futuro','demo_expirada','multiplos','admin','outro_curso'])
def test_contextos_vigentes_e_historicos_preservados(ambiente_compra,cenario):
    _,c,f,_,_=ambiente_compra
    agora=datetime.utcnow()
    with f() as db:
        db.add(m.AcessoCurso(usuario_id=1,curso_id=1,ativo=True,data_inicio=agora-timedelta(days=1),data_fim=agora+timedelta(days=120)))
        db.commit()
        did=None;ids=[]
        if cenario!='pago':did=demo(db,1,-1 if cenario=='demo_expirada' else 1)
        if cenario not in ('gratuito','outro_curso'):
            ids.append(contrato(db,'ADMIN' if cenario=='admin' else 'PAGAMENTO',-1 if cenario=='pago_expirado' else 30))
        if cenario=='pago_futuro':db.get(m.ContratacaoCurso,ids[0]).data_inicio=agora+timedelta(days=1);db.commit()
        if cenario=='multiplos':ids.append(contrato(db,dias=10))
        if cenario=='outro_curso':
            db.add(m.AcessoCurso(usuario_id=1,curso_id=2,ativo=True,data_fim=agora+timedelta(days=120)));db.commit()
            ids.append(contrato(db,curso=2))
        antes={tipo:[{col.name:getattr(row,col.name) for col in tipo.__table__.columns} for row in db.query(tipo).order_by(tipo.id)] for tipo in (m.ContratacaoCurso,m.DemonstracaoCurso,m.Pagamento)}
    r=c.get('/me/cursos');assert r.status_code==200,r.text
    cursos={a['curso_id']:a for a in r.json()};a=cursos[1]
    if cenario in ('gratuito','pago_expirado','pago_futuro','outro_curso'):assert a['contratacoes']==[]
    else:
        assert [x['id'] for x in a['contratacoes']]==(list(reversed(ids)) if cenario=='multiplos' else ids)
        assert all(x['origem']==('ADMIN' if cenario=='admin' else 'PAGAMENTO') for x in a['contratacoes'])
    assert len(a['demonstracoes'])==(0 if cenario in ('pago','demo_expirada') else 1)
    if cenario=='outro_curso':assert cursos[2]['contratacoes'][0]['id']==ids[0]
    with f() as db:
        depois={tipo:[{col.name:getattr(row,col.name) for col in tipo.__table__.columns} for row in db.query(tipo).order_by(tipo.id)] for tipo in antes}
        assert depois==antes
