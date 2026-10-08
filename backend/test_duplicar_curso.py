"""Duplicação em banco descartável, com rollback e relações reais."""
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from app import models as m, schemas
from test_revisoes_assunto import env
from test_questoes_pratica_patch import carregar_main_isolado
from sqlalchemy import event

@pytest.fixture
def copia(env):
    db,_=env
    for table in [m.TempoAcessoCurso.__table__,m.Video.__table__,m.Material.__table__,m.Comentario.__table__,m.QuestaoPraticaAssunto.__table__,m.QuestaoPraticaAlternativa.__table__]:table.create(db.bind)
    db.add(m.TempoAcessoCurso(curso_id=1,meses=3,valor_cents=1000))
    db.add(m.Video(aula_id=1,titulo='Vídeo',url='https://example.com/video',provedor='CLOUDFLARE',cloudflare_uid='uid'))
    db.add(m.Material(aula_id=1,tipo='TEXTO',titulo='Texto',conteudo='Conteúdo'))
    alt=m.Alternativa(questao_id=1,letra='A',texto='Alternativa');db.add(alt);db.flush()
    db.add(m.Comentario(questao_id=1,alternativa_id=alt.id,texto='Comentário'))
    q=m.QuestaoPraticaAssunto(curso_assunto_proprio_id=1,tipo='MULTIPLA',enunciado='Prática',gabarito='A');db.add(q);db.flush()
    db.add(m.QuestaoPraticaAlternativa(questao_pratica_id=q.id,letra='A',texto='A',correta=True));db.commit()
    with carregar_main_isolado(lambda:db,db.bind) as main:
        yield db,main


def executar(main,db,nome='Cópia',admin=True):
    return main.duplicar_curso_inteiro(1,schemas.DuplicarCursoRequest(novo_nome=nome),db,SimpleNamespace(id=1,is_admin=admin))


def snapshot(db):
    return {t.name:db.execute(t.select().order_by(t.c.id)).all() for t in db.bind_tables} if hasattr(db,'bind_tables') else {table.name:db.execute(table.select()).all() for table in m.Base.metadata.sorted_tables if table.name in __import__('sqlalchemy').inspect(db.bind).get_table_names()}


def test_copia_completa_relacoes_original_dados_aluno(copia):
    db,main=copia;before=snapshot(db)
    result=executar(main,db);cid=result['novo_curso_id']
    c=db.get(m.Curso,cid);assert not c.publicado and c.nome=='Cópia'
    d=db.query(m.CursoDisciplinaPropria).filter_by(curso_id=cid).one()
    a=db.query(m.CursoAssuntoProprio).filter_by(curso_disciplina_propria_id=d.id).one()
    p=db.query(m.Pasta).filter_by(curso_assunto_proprio_id=a.id).one()
    aula=db.query(m.Aula).filter_by(pasta_id=p.id).one()
    assert aula.id!=1 and p.id!=1 and a.id!=1 and d.id!=1
    assert db.query(m.Video).filter_by(aula_id=aula.id).one().cloudflare_uid=='uid'
    assert db.query(m.Material).filter_by(aula_id=aula.id).one().conteudo=='Conteúdo'
    assert db.query(m.TempoAcessoCurso).filter_by(curso_id=cid).one().valor_cents==1000
    bs=db.query(m.Bateria).filter_by(aula_id=aula.id).all();assert len(bs)==3
    qs=db.query(m.Questao).filter(m.Questao.bateria_id.in_([b.id for b in bs])).all();assert len(qs)==10
    com=db.query(m.Comentario).filter(m.Comentario.questao_id.in_([q.id for q in qs])).one()
    assert db.get(m.Alternativa,com.alternativa_id).questao_id==com.questao_id
    pratica=db.query(m.QuestaoPraticaAssunto).filter_by(curso_assunto_proprio_id=a.id).one()
    assert db.query(m.QuestaoPraticaAlternativa).filter_by(questao_pratica_id=pratica.id).one().correta
    after=snapshot(db)
    for table,rows in before.items():
        assert all(row in after[table] for row in rows),table
    for table in ['demonstracoes_curso','contratacoes_curso','respostas_aluno_questoes','tentativas_bateria','revisoes_aluno','progresso_aulas']:
        assert before[table]==after[table]


@pytest.mark.parametrize('nome,admin,code',[('x',False,403),('',True,400),('x'*256,True,400),('curso',True,400)])
def test_validacoes(copia,nome,admin,code):
    db,main=copia
    with pytest.raises(HTTPException) as e:executar(main,db,nome,admin)
    assert e.value.status_code==code
    assert db.query(m.Curso).count()==1


def test_rollback_integral(copia):
    db,main=copia;before=snapshot(db)
    def fail(mapper,connection,target):raise RuntimeError('Falha controlada após criar parte da estrutura')
    event.listen(m.Video,'before_insert',fail)
    try:
        with pytest.raises(HTTPException) as e:executar(main,db)
        assert e.value.status_code==500
    finally:event.remove(m.Video,'before_insert',fail)
    assert snapshot(db)==before


def test_origem_inexistente_e_estrutura_incompativel(copia):
    db,main=copia
    with pytest.raises(HTTPException) as e:main.duplicar_curso_inteiro(999,schemas.DuplicarCursoRequest(novo_nome='Cópia'),db,SimpleNamespace(is_admin=True))
    assert e.value.status_code==404
    db.add(m.Pasta(curso_assunto_proprio_id=1,tipo='INTERATIVIDADE',nome='Legado'));db.commit()
    with pytest.raises(HTTPException) as e:executar(main,db)
    assert e.value.status_code==409 and db.query(m.Curso).count()==1
