"""Concorrência em PostgreSQL descartável, com pagamentos simulados."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app import models as m, schemas
from app.importacao_cursos import importar
from test_cursos_comerciais_concorrencia_pg import pg, disputar, ADMIN, ALUNO
from test_importacao_cursos import documento


def paralelo(factory, funcoes):
    barreira = Barrier(len(funcoes))
    def executar(fn):
        with factory() as db:
            barreira.wait(timeout=10)
            try:
                return fn(db)
            except HTTPException as exc:
                db.rollback()
                return exc.status_code
    with ThreadPoolExecutor(max_workers=len(funcoes)) as executor:
        return list(executor.map(executar, funcoes))


@pytest.mark.parametrize('outro', ['manual', 'duplicacao'])
def test_importacao_disputa_nome_com_manual_ou_duplicacao(pg, documento, outro):
    main, factory, _, _ = pg
    with factory() as db:
        for tabela in ('cursos', 'tempo_acesso_curso'):
            db.execute(text(f"SELECT setval(pg_get_serial_sequence('{tabela}', 'id'), (SELECT max(id) FROM {tabela}))"))
        db.commit()
    nome = documento['curso']['nome']
    def importacao(db):
        return importar(db, 2, 'teste-concorrencia-1234', documento, documento)
    def criacao(db):
        if outro == 'manual':
            dados = schemas.CursoCreate(nome=nome, banca='Banca', cargo='Cargo', orgao='Órgão', ano=2026, uf='SP')
            return main.criar_curso(dados, db, ADMIN)
        return main.duplicar_curso_inteiro(1, schemas.DuplicarCursoRequest(novo_nome=nome), db, ADMIN)
    resultados = paralelo(factory, [importacao, criacao])
    assert sum(not isinstance(x, int) for x in resultados) == 1, resultados
    assert any(x in (400, 409) for x in resultados if isinstance(x, int)), resultados
    with factory() as db:
        cursos = db.query(m.Curso).filter(m.Curso.nome == nome).all()
        assert len(cursos) == 1
        registros = db.query(m.ImportacaoCurso).all()
        disciplinas = db.query(m.CursoDisciplinaPropria).filter_by(curso_id=cursos[0].id).count()
        assert (len(registros), disciplinas) in ((1, 1), (0, 0))
        if registros:
            assert registros[0].curso_id == cursos[0].id
            assert db.query(m.TempoAcessoCurso).filter_by(curso_id=cursos[0].id).count() == 3


@pytest.mark.parametrize('confirmar_primeiro', [False, True])
def test_confirmacao_de_precos_e_publicacao_serializadas(pg, confirmar_primeiro):
    _, factory, _, _ = pg
    with factory() as db:
        curso = db.get(m.Curso, 1); curso.precos_provisorios = True; curso.publicado = False
        tempo = db.get(m.TempoAcessoCurso, 1); tempo.valor_cents = 4; tempo.valor_provisorio_original_cents = 4
        db.execute(text("SELECT setval(pg_get_serial_sequence('tempo_acesso_curso', 'id'), (SELECT max(id) FROM tempo_acesso_curso))"))
        db.add_all([m.TempoAcessoCurso(curso_id=1, meses=n, valor_cents=n, valor_provisorio_original_cents=n, ativo=True) for n in (8, 12)])
        db.commit()
    payload = {'confirmar_precos_definitivos': True, 'tempos_acesso': [{'meses': n, 'valor_cents': n*100} for n in (4,8,12)]}
    def confirmar(main, db): return main.salvar_config_publica_curso(1, payload, db, ADMIN)
    def publicar(main, db): return main.publicar_curso(1, db, ADMIN)
    primeiro, segundo = (confirmar, publicar) if confirmar_primeiro else (publicar, confirmar)
    a, b = disputar(pg, primeiro, segundo)
    assert isinstance(a, dict) if confirmar_primeiro else a == 409
    assert isinstance(b, dict)
    with factory() as db:
        curso=db.get(m.Curso,1)
        assert curso.precos_provisorios is False
        assert curso.publicado is confirmar_primeiro
        assert [t.valor_cents for t in db.query(m.TempoAcessoCurso).filter_by(curso_id=1).order_by(m.TempoAcessoCurso.meses)] == [400,800,1200]


@pytest.mark.parametrize('retirada_primeiro', [False, True])
def test_renovacao_comercial_e_retirada_serializadas(pg, retirada_primeiro):
    _, factory, _, post = pg
    with factory() as db:
        contrato=m.ContratacaoCurso(usuario_id=1, curso_id=1, origem='ADMIN', data_inicio=datetime.utcnow()-timedelta(days=5), data_fim=datetime.utcnow()+timedelta(days=10))
        db.add(contrato);db.commit();cid=contrato.id
    def retirar(main, db): return main.retirar_curso_venda(1, db, ADMIN)
    def renovar(main, db): return main.criar_checkout_mp({'tempo_acesso_id':1,'tipo_compra':'RENOVACAO','contratacao_id':cid},db,ALUNO)
    a,b=disputar(pg, retirar if retirada_primeiro else renovar, renovar if retirada_primeiro else retirar)
    assert isinstance(a,dict)
    assert b==409 if retirada_primeiro else isinstance(b,dict)
    assert post.call_count == (0 if retirada_primeiro else 1)
    with factory() as db:
        assert not db.get(m.Curso,1).publicado
        assert db.query(m.Pagamento).count()==(0 if retirada_primeiro else 1)
        assert db.get(m.ContratacaoCurso,cid).data_fim is not None


def test_concessoes_admin_simultaneas_preservam_isolamento(pg):
    main, factory, _, post = pg
    with factory() as db:
        db.add(m.Usuario(id=3,nome='Aluno 2',email='outro@teste.local',senha_hash='teste',cpf='3',telefone='0'))
        db.commit()
    fim=datetime.utcnow()+timedelta(days=30)
    def conceder(uid):
        return lambda db: main.admin_criar_acesso(schemas.AcessoCursoCreate(usuario_id=uid,curso_id=1,data_fim=fim),db,ADMIN)
    resultados=paralelo(factory,[conceder(1),conceder(3)])
    assert all(isinstance(x,dict) for x in resultados),resultados
    with factory() as db:
        assert {x.usuario_id for x in db.query(m.ContratacaoCurso).all()}=={1,3}
        assert {x.usuario_id for x in db.query(m.ConcessaoAcessoAdmin).all()}=={1,3}
        assert {x.usuario_id for x in db.query(m.AcessoCurso).all()}=={1,3}
        assert db.query(m.Pagamento).count()==0
    post.assert_not_called()


def test_concessao_simultanea_rejeita_usuario_sem_autorizacao(pg):
    main, factory, _, _ = pg
    payload=schemas.AcessoCursoCreate(usuario_id=1,curso_id=1,data_fim=datetime.utcnow()+timedelta(days=30))
    def conceder(ator): return lambda db: main.admin_criar_acesso(payload,db,ator)
    resultados=paralelo(factory,[conceder(ADMIN),conceder(ALUNO)])
    assert sum(isinstance(x,dict) for x in resultados)==1 and 403 in resultados
    with factory() as db:
        assert db.query(m.ConcessaoAcessoAdmin).count()==1
        assert db.query(m.ContratacaoCurso).count()==1
        assert db.query(m.AcessoCurso).one().usuario_id==1


def test_renovacao_admin_simultanea_mesmo_contrato_nao_cria_contrato_extra(pg):
    main, factory, _, _ = pg
    with factory() as db:
        c=m.ContratacaoCurso(usuario_id=1,curso_id=1,origem='ADMIN',
            data_inicio=datetime.utcnow()-timedelta(days=5),data_fim=datetime.utcnow()+timedelta(days=10))
        db.add(c);db.commit();cid=c.id
    fim=datetime.utcnow()+timedelta(days=60)
    def renovar(db):
        return main.admin_criar_acesso(schemas.AcessoCursoCreate(usuario_id=1,curso_id=1,data_fim=fim,
            contratacao_id=cid,chave_idempotencia='renovacao-admin-teste-0001'),db,ADMIN)
    resultados=paralelo(factory,[renovar,renovar])
    assert all(isinstance(x,dict) for x in resultados),resultados
    assert resultados[0] == resultados[1]
    with factory() as db:
        assert db.get(m.ContratacaoCurso,cid).data_fim==fim
        assert db.query(m.ContratacaoCurso).filter_by(usuario_id=1,curso_id=1,origem='ADMIN').count()==1
        assert db.query(m.OperacaoAcessoAdmin).count()==1
