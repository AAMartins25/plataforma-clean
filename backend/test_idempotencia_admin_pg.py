"""Idempotência administrativa no PostgreSQL descartável."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from sqlalchemy import event
from fastapi import HTTPException
import pytest
from app import models as m, schemas
from test_cursos_comerciais_concorrencia_pg import pg, ADMIN, ALUNO


def dados(cid, fim, chave='operacao-admin-teste-0001'):
    return schemas.AcessoCursoCreate(usuario_id=1, curso_id=1, data_fim=fim,
        contratacao_id=cid, chave_idempotencia=chave)


def contrato(factory):
    with factory() as db:
        c=m.ContratacaoCurso(usuario_id=1,curso_id=1,origem='ADMIN',
            data_inicio=datetime.utcnow()-timedelta(days=5),data_fim=datetime.utcnow()+timedelta(days=10))
        db.add(c);db.commit();return c.id


def test_repeticao_conflito_autorizacao_e_operacao_distinta(pg):
    main,factory,_,_=pg; cid=contrato(factory); fim=datetime.utcnow()+timedelta(days=60)
    payload=dados(cid,fim)
    with factory() as db: primeiro=main.admin_criar_acesso(payload,db,ADMIN)
    with factory() as db: assert main.admin_criar_acesso(payload,db,ADMIN)==primeiro
    with factory() as db:
        with pytest.raises(HTTPException) as e: main.admin_criar_acesso(dados(cid,fim+timedelta(days=1)),db,ADMIN)
        assert e.value.status_code==409
    for alteracao in ({'contratacao_id':cid+1}, {'usuario_id':3}, {'curso_id':2}, {'ativo':False}):
        with factory() as db:
            with pytest.raises(HTTPException) as e: main.admin_criar_acesso(payload.model_copy(update=alteracao),db,ADMIN)
            assert e.value.status_code==409
    with factory() as db:
        with pytest.raises(HTTPException) as e: main.admin_criar_acesso(payload,db,ALUNO)
        assert e.value.status_code==403
    with factory() as db:
        with pytest.raises(HTTPException) as e:
            main.admin_criar_acesso(payload,db,SimpleNamespace(id=3,is_admin=True,tipo_admin='admin_geral'))
        assert e.value.status_code==409
    with factory() as db:
        outra=main.admin_criar_acesso(dados(cid,fim+timedelta(days=5),'operacao-admin-teste-0002'),db,ADMIN)
    assert outra['contratacao_id'] != primeiro['contratacao_id']
    with factory() as db:
        assert db.query(m.OperacaoAcessoAdmin).count()==2
        assert db.query(m.ConcessaoAcessoAdmin).count()==2
        assert db.query(m.ContratacaoCurso).count()==2


def test_falha_antes_commit_reenvio_mesma_chave(pg):
    main,factory,_,_=pg; cid=contrato(factory);fim=datetime.utcnow()+timedelta(days=60);payload=dados(cid,fim)
    with factory() as db:
        def falhar(session): raise RuntimeError('falha simulada antes do commit')
        event.listen(db,'before_commit',falhar)
        try:
            with pytest.raises(RuntimeError): main.admin_criar_acesso(payload,db,ADMIN)
            db.rollback()
        finally: event.remove(db,'before_commit',falhar)
    with factory() as db:
        assert db.query(m.OperacaoAcessoAdmin).count()==0
        assert db.query(m.ConcessaoAcessoAdmin).count()==0
        assert db.get(m.ContratacaoCurso,cid).data_fim < fim
    with factory() as db: resultado=main.admin_criar_acesso(payload,db,ADMIN)
    assert resultado['contratacao_id']==cid
    with factory() as db:
        assert db.query(m.OperacaoAcessoAdmin).count()==1
        assert db.query(m.ConcessaoAcessoAdmin).count()==1


def test_precos_provisorios_bloqueiam_sem_gravar_e_venda_desativada_nao_bloqueia(pg):
    main,factory,_,_=pg;cid=contrato(factory);fim=datetime.utcnow()+timedelta(days=60);payload=dados(cid,fim)
    with factory() as db:
        curso=db.get(m.Curso,1);curso.precos_provisorios=True;curso.publicado=False;db.commit()
    with factory() as db:
        with pytest.raises(HTTPException) as e: main.admin_criar_acesso(payload,db,ADMIN)
        assert e.value.status_code==409
        db.rollback()
    with factory() as db:
        assert db.query(m.OperacaoAcessoAdmin).count()==0
        db.get(m.Curso,1).precos_provisorios=False;db.commit()
    with factory() as db: assert main.admin_criar_acesso(payload,db,ADMIN)['contratacao_id']==cid


def test_renovacao_sem_chave_rejeitada(pg):
    main,factory,_,_=pg;cid=contrato(factory)
    payload=schemas.AcessoCursoCreate(usuario_id=1,curso_id=1,data_fim=datetime.utcnow()+timedelta(days=60))
    with factory() as db:
        with pytest.raises(HTTPException) as e: main.admin_criar_acesso(payload,db,ADMIN)
        assert e.value.status_code==428
        db.rollback()
    with factory() as db:
        assert db.query(m.ContratacaoCurso).count()==1
        assert db.query(m.ConcessaoAcessoAdmin).count()==0
