"""Cópias reais por HTTP em SQLite descartável, com FKs e histórico de alunos."""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import event, select, text

from app import models as m
from test_aulas_admin import ambiente, infraestrutura, inserir_historico, MODELOS as MODELOS_AULAS

EXTRAS = [m.QuestaoPraticaAssunto, m.QuestaoPraticaAlternativa,
          m.QuestaoPraticaMarcacaoAluno, m.QuestaoPraticaRotatividadeAluno]
MODELOS = [*MODELOS_AULAS, *EXTRAS]
HISTORICO = [m.Usuario, m.ContratacaoCurso, m.DemonstracaoCurso, m.TentativaBateria,
             m.RespostaAlunoQuestao, m.RevisaoAluno, m.ProgressoAula,
             m.AnotacaoAlunoQuestao, m.ConversaQuestaoProfessor,
             m.MensagemConversaQuestao, m.QuestaoPraticaMarcacaoAluno,
             m.QuestaoPraticaRotatividadeAluno]


def preparar_conteudo(db):
    # IDs explícitos na semente da fixture: atualizar apenas sequências do banco descartável.
    if db.bind.dialect.name == 'postgresql':
        for modelo in MODELOS_AULAS:
            tabela = modelo.__tablename__
            db.execute(text(f"SELECT setval(pg_get_serial_sequence('{tabela}', 'id'), COALESCE((SELECT MAX(id) FROM {tabela}), 0) + 1, false)"))
    db.get(m.CursoDisciplinaPropria, 1).nome = 'Direitos Humanos'
    db.get(m.CursoDisciplinaPropria, 1).disponivel_demonstracao = True
    db.get(m.CursoDisciplinaPropria, 2).ordem = 9
    db.get(m.CursoDisciplinaPropria, 2).ativo = False
    db.get(m.CursoAssuntoProprio, 1).nome = 'O que são Direitos Humanos'
    db.get(m.CursoAssuntoProprio, 1).descricao = 'Descrição original'
    db.get(m.CursoAssuntoProprio, 1).ordem = 5
    db.get(m.CursoAssuntoProprio, 2).ordem = 17
    db.get(m.CursoAssuntoProprio, 2).ativo = False
    db.add(m.CursoDisciplinaPropria(curso_id=1, nome='Outra disciplina', ordem=3))
    segundo = m.CursoAssuntoProprio(curso_disciplina_propria_id=1, nome='Assunto em preparação', ativo=False, ordem=12)
    db.add(segundo); db.flush()
    db.add(m.Pasta(curso_assunto_proprio_id=segundo.id, tipo='TEORIA', nome='Aulas'))
    db.add(m.Material(aula_id=1, tipo='LINK', titulo='Link', url='https://teste.local', ordem=11))
    db.get(m.Video,1).provedor = 'CLOUDFLARE'
    db.get(m.Video,1).url = ''
    db.get(m.Video,1).cloudflare_uid = 'uid-original'
    db.add(m.Video(aula_id=1, titulo='YouTube', provedor='YOUTUBE', url='https://youtu.be/original', ordem=12))
    for ordem in range(2,11):
        db.add(m.Questao(bateria_id=2, enunciado=f'Questão {ordem}', tipo='CERTO_ERRADO',
                        tipo_questao='CERTO_ERRADO', gabarito='E', comentario='Explicação',
                        ordem=ordem, ativo=ordem!=10))
    multipla = m.Questao(bateria_id=1, enunciado='Múltipla em rascunho', tipo='MULTIPLA',
                        tipo_questao='MULTIPLA_5', quantidade_alternativas=5,
                        gabarito='B', comentario='Explicação da questão', ordem=3, ativo=False)
    db.add(multipla); db.flush()
    for letra in 'ABCDE':
        alternativa = m.Alternativa(questao_id=multipla.id, letra=letra, texto='Texto '+letra)
        db.add(alternativa); db.flush()
        db.add(m.Comentario(questao_id=multipla.id, alternativa_id=alternativa.id, texto='Comentário '+letra))
    db.add(m.Comentario(questao_id=1, alternativa_id=None, texto='Comentário geral de conteúdo'))
    pratica = m.QuestaoPraticaAssunto(curso_assunto_proprio_id=1, tipo='MULTIPLA',
                                     enunciado='Questão prática', gabarito='A', comentario='Comentário')
    db.add(pratica); db.flush()
    for letra in 'ABCD':
        db.add(m.QuestaoPraticaAlternativa(questao_pratica_id=pratica.id, letra=letra, texto=letra, correta=letra=='A'))
    db.add(m.QuestaoPraticaAssunto(curso_assunto_proprio_id=1, tipo='CERTO_ERRADO',
                                  enunciado='Prática inativa', gabarito='E', ativo=False))
    db.add(m.QuestaoPraticaMarcacaoAluno(usuario_id=1, questao_id=pratica.id, contratacao_id=1, rever=True))
    db.add(m.QuestaoPraticaRotatividadeAluno(usuario_id=1, curso_assunto_proprio_id=1,
                                            questao_id=pratica.id, contratacao_id=1, ciclo=2))
    db.add(m.ProgressoAula(usuario_id=1, aula_id=1, pasta_id=1, contratacao_id=1, concluida=True))
    db.commit()
    for tipo in ('revisao','tentativa','resposta','anotacao','mensagem'):
        inserir_historico(db,tipo)


@pytest.fixture
def copia(ambiente):
    main,client,factory,perfil = ambiente
    engine = factory.kw['bind']
    m.Base.metadata.create_all(engine,tables=[modelo.__table__ for modelo in EXTRAS])
    with factory() as db: preparar_conteudo(db)
    try:
        yield main,client,factory,perfil
    finally:
        m.Base.metadata.drop_all(engine,tables=[modelo.__table__ for modelo in EXTRAS])


def snapshot(db, modelos=MODELOS):
    return {modelo.__tablename__:list(db.execute(select(modelo.__table__).order_by(modelo.id))) for modelo in modelos}


def equivalentes(origem,copia,pai):
    assert origem.id != copia.id
    for coluna in origem.__table__.columns:
        if coluna.name not in {'id','criado_em','criada_em','atualizado_em',pai}:
            assert getattr(origem,coluna.name)==getattr(copia,coluna.name),coluna.name


def comparar_assunto(db,origem,copia,ordem_externa=None):
    # Ordenação externa é anexada ao destino; os descendentes preservam todos os campos.
    for campo in ('nome','descricao','ativo'):
        assert getattr(origem,campo)==getattr(copia,campo)
    assert origem.id != copia.id
    assert copia.ordem==(origem.ordem if ordem_externa is None else ordem_externa)
    def pares(modelo,campo,oid,cid):
        antigos=db.query(modelo).filter(getattr(modelo,campo)==oid).order_by(modelo.id).all()
        novos=db.query(modelo).filter(getattr(modelo,campo)==cid).order_by(modelo.id).all()
        assert len(antigos)==len(novos)
        for a,b in zip(antigos,novos):
            equivalentes(a,b,campo)
            assert getattr(b,campo)==cid
            yield a,b
    for pa,pb in pares(m.Pasta,'curso_assunto_proprio_id',origem.id,copia.id):
        assert pb.assunto_id is None
        for aa,ab in pares(m.Aula,'pasta_id',pa.id,pb.id):
            list(pares(m.Material,'aula_id',aa.id,ab.id))
            list(pares(m.Video,'aula_id',aa.id,ab.id))
            for ba,bb in pares(m.Bateria,'aula_id',aa.id,ab.id):
                for qa,qb in pares(m.Questao,'bateria_id',ba.id,bb.id):
                    mapa={a.id:b.id for a,b in pares(m.Alternativa,'questao_id',qa.id,qb.id)}
                    antigos=db.query(m.Comentario).filter_by(questao_id=qa.id).order_by(m.Comentario.id).all()
                    novos=db.query(m.Comentario).filter_by(questao_id=qb.id).order_by(m.Comentario.id).all()
                    assert len(antigos)==len(novos)
                    for a,b in zip(antigos,novos):
                        assert a.id!=b.id and a.texto==b.texto
                        assert b.alternativa_id==mapa.get(a.alternativa_id)
    for qa,qb in pares(m.QuestaoPraticaAssunto,'curso_assunto_proprio_id',origem.id,copia.id):
        list(pares(m.QuestaoPraticaAlternativa,'questao_pratica_id',qa.id,qb.id))


@pytest.mark.parametrize('tipo',['disciplina','assunto'])
def test_copia_completa_origem_intacta_novos_ids_sem_historico(copia,tipo):
    _,c,factory,_=copia
    with factory() as db:antes=snapshot(db);historico=snapshot(db,HISTORICO)
    if tipo=='disciplina':
        r=c.post('/admin/disciplinas/1/copiar',json={'curso_destino_id':2})
    else:
        r=c.post('/admin/assuntos/1/copiar',json={'disciplina_destino_id':2})
    assert r.status_code==200,r.text
    resultado=r.json();assert resultado['ok'] and resultado['curso_destino_id']==2
    with factory() as db:
        depois=snapshot(db)
        for tabela,linhas in antes.items():assert all(linha in depois[tabela] for linha in linhas),tabela
        assert historico==snapshot(db,HISTORICO)
        if tipo=='disciplina':
            d=db.get(m.CursoDisciplinaPropria,resultado['nova_disciplina_id'])
            assert d.curso_id==2 and d.ordem==10 and d.nome=='Direitos Humanos' and d.disponivel_demonstracao
            originais=db.query(m.CursoAssuntoProprio).filter_by(curso_disciplina_propria_id=1).order_by(m.CursoAssuntoProprio.id).all()
            novos=db.query(m.CursoAssuntoProprio).filter_by(curso_disciplina_propria_id=d.id).order_by(m.CursoAssuntoProprio.id).all()
            assert len(novos)==len(originais)==2
            for a,b in zip(originais,novos):comparar_assunto(db,a,b)
        else:
            a=db.get(m.CursoAssuntoProprio,resultado['novo_assunto_id'])
            assert a.curso_disciplina_propria_id==2
            comparar_assunto(db,db.get(m.CursoAssuntoProprio,1),a,18)


@pytest.mark.parametrize('tipo',['disciplina','assunto'])
@pytest.mark.parametrize('autenticado,status',[(False,401),(True,403)])
def test_permissoes_sem_escrita(copia,tipo,autenticado,status):
    main,c,factory,perfil=copia
    with factory() as db:antes=snapshot(db)
    if autenticado:perfil(False)
    else:main.app.dependency_overrides.pop(main.get_usuario_atual)
    url,payload=('/admin/disciplinas/1/copiar',{'curso_destino_id':2}) if tipo=='disciplina' else ('/admin/assuntos/1/copiar',{'disciplina_destino_id':2})
    assert c.post(url,json=payload).status_code==status
    with factory() as db:assert snapshot(db)==antes


@pytest.mark.parametrize('url,payload,status',[
    ('/admin/disciplinas/999/copiar',{'curso_destino_id':2},404),
    ('/admin/disciplinas/1/copiar',{'curso_destino_id':999},404),
    ('/admin/disciplinas/1/copiar',{'curso_destino_id':1},400),
    ('/admin/assuntos/999/copiar',{'disciplina_destino_id':2},404),
    ('/admin/assuntos/1/copiar',{'disciplina_destino_id':999},404),
    ('/admin/assuntos/1/copiar',{'disciplina_destino_id':1},400),
    ('/admin/assuntos/1/copiar',{},422),
    ('/admin/disciplinas/1/copiar',{'curso_destino_id':'invalido'},422)])
def test_origem_destino_payload_invalidos(copia,url,payload,status):
    _,c,factory,_=copia
    with factory() as db:antes=snapshot(db)
    r=c.post(url,json=payload);assert r.status_code==status,r.text
    with factory() as db:assert snapshot(db)==antes


def test_assunto_para_outra_disciplina_do_mesmo_curso(copia):
    _,c,_,_=copia
    r=c.post('/admin/assuntos/1/copiar',json={'disciplina_destino_id':3})
    assert r.status_code==200 and r.json()['curso_destino_id']==1


@pytest.mark.parametrize('tipo',['disciplina','assunto'])
def test_copias_repetidas_preservam_nomes_e_anexam_ordem(copia,tipo):
    _,c,factory,_=copia
    url,payload=('/admin/disciplinas/1/copiar',{'curso_destino_id':2}) if tipo=='disciplina' else ('/admin/assuntos/1/copiar',{'disciplina_destino_id':2})
    resultados=[c.post(url,json=payload).json() for _ in range(2)]
    with factory() as db:
        if tipo=='disciplina':registros=[db.get(m.CursoDisciplinaPropria,r['nova_disciplina_id']) for r in resultados];ordens=[10,11]
        else:registros=[db.get(m.CursoAssuntoProprio,r['novo_assunto_id']) for r in resultados];ordens=[18,19]
        assert [r.ordem for r in registros]==ordens
        assert registros[0].nome==registros[1].nome
        assert registros[0].id!=registros[1].id


@pytest.mark.parametrize('tipo',['disciplina','assunto'])
@pytest.mark.parametrize('problema',['pastas','tipo_pasta','duas_aulas','comentario','limite_material','limite_video','limite_bateria','limite_questao','ordem','concluida'])
def test_estrutura_incompativel_rejeitada_sem_copia_parcial(copia,tipo,problema):
    _,c,factory,_=copia
    with factory() as db:
        if problema=='pastas':db.add(m.Pasta(curso_assunto_proprio_id=1,tipo='INTERATIVIDADE',nome='Legado'))
        if problema=='tipo_pasta':db.get(m.Pasta,1).tipo='INTERATIVIDADE'
        if problema=='duas_aulas':db.add(m.Aula(pasta_id=1,titulo='Outra',ordem=2))
        if problema=='comentario':
            alternativa=db.query(m.Alternativa).first()
            db.add(m.Comentario(questao_id=1,alternativa_id=alternativa.id,texto='Vínculo errado'))
        if problema=='limite_material':
            for i in range(21):db.add(m.Material(aula_id=1,tipo='TEXTO',titulo=str(i),conteudo='x',ordem=20+i))
        if problema=='limite_video':
            for i in range(21):db.add(m.Video(aula_id=1,titulo=str(i),url='https://youtu.be/teste',ordem=20+i))
        if problema=='limite_bateria':
            for i in range(21):db.add(m.Bateria(aula_id=1,titulo=str(i),ordem=20+i))
        if problema=='limite_questao':
            for i in range(11):db.add(m.Questao(bateria_id=1,tipo='CERTO_ERRADO',tipo_questao='CERTO_ERRADO',gabarito='C',enunciado='x',ordem=20+i))
        if problema=='ordem':db.get(m.Material,2).ordem=3
        if problema=='concluida':db.get(m.Questao,1).gabarito='Z'
        db.commit();antes=snapshot(db)
    url,payload=('/admin/disciplinas/1/copiar',{'curso_destino_id':2}) if tipo=='disciplina' else ('/admin/assuntos/1/copiar',{'disciplina_destino_id':2})
    r=c.post(url,json=payload);assert r.status_code==409,r.text
    with factory() as db:assert snapshot(db)==antes


@pytest.mark.parametrize('tipo',['disciplina','assunto'])
def test_destino_inativo(copia,tipo):
    _,c,factory,_=copia
    with factory() as db:db.get(m.Curso,2).ativo=False;db.commit();antes=snapshot(db)
    url,payload=('/admin/disciplinas/1/copiar',{'curso_destino_id':2}) if tipo=='disciplina' else ('/admin/assuntos/1/copiar',{'disciplina_destino_id':2})
    assert c.post(url,json=payload).status_code==400
    with factory() as db:assert snapshot(db)==antes


@pytest.mark.parametrize('tipo',['disciplina','assunto'])
@pytest.mark.parametrize('fase',['material','pratica','commit','constraint'])
def test_rollback_integral(copia,tipo,fase):
    _,c,factory,_=copia
    with factory() as db:antes=snapshot(db)
    def falhar(*args):raise RuntimeError('Falha controlada após gravar parte da estrutura')
    if fase in ('material','pratica'):
        modelo=m.Material if fase=='material' else m.QuestaoPraticaAssunto
        event.listen(modelo,'before_insert',falhar)
        remover=lambda:event.remove(modelo,'before_insert',falhar)
    elif fase=='commit':
        event.listen(factory.class_,'before_commit',falhar)
        remover=lambda:event.remove(factory.class_,'before_commit',falhar)
    else:
        def constraint(mapper,conexao,registro):registro.aula_id=999
        event.listen(m.Material,'before_insert',constraint)
        remover=lambda:event.remove(m.Material,'before_insert',constraint)
    url,payload=('/admin/disciplinas/1/copiar',{'curso_destino_id':2}) if tipo=='disciplina' else ('/admin/assuntos/1/copiar',{'disciplina_destino_id':2})
    try:
        r=c.post(url,json=payload);assert r.status_code==(409 if fase=='constraint' else 500),r.text
        assert 'nenhuma cópia' in r.json()['detail']
    finally:remover()
    with factory() as db:assert snapshot(db)==antes


def test_copia_independente_edicao_destino_nao_altera_origem(copia):
    _,c,factory,_=copia
    r=c.post('/admin/assuntos/1/copiar',json={'disciplina_destino_id':2});assert r.status_code==200
    with factory() as db:
        a=db.get(m.CursoAssuntoProprio,r.json()['novo_assunto_id'])
        p=db.query(m.Pasta).filter_by(curso_assunto_proprio_id=a.id).one()
        aula=db.query(m.Aula).filter_by(pasta_id=p.id).one()
        material=db.query(m.Material).filter_by(aula_id=aula.id,tipo='TEXTO').one()
        bateria=db.query(m.Bateria).filter_by(aula_id=aula.id,status='EM_ANDAMENTO').one()
        q=db.query(m.Questao).filter_by(bateria_id=bateria.id).one()
        mid,qid,aula_id,bid=material.id,q.id,aula.id,bateria.id
        alternativas=[{'letra':alt.letra,'texto':'Novo '+alt.letra} for alt in db.query(m.Alternativa).filter_by(questao_id=qid)]
        antes_origem=db.get(m.Material,1).conteudo
    assert c.put(f'/materiais/{mid}',json={'aula_id':aula_id,'titulo':'Editado','tipo':'TEXTO','conteudo':'Cópia editada'}).status_code==200
    assert c.put(f'/questoes/{qid}',json={'bateria_id':bid,'tipo':'MULTIPLA','tipo_questao':'MULTIPLA_5',
                'enunciado':'Cópia editada','gabarito':'A','alternativas':alternativas}).status_code==200
    with factory() as db:
        assert db.get(m.Material,1).conteudo==antes_origem
        assert db.query(m.Questao).filter_by(bateria_id=1).one().enunciado=='Múltipla em rascunho'


def test_copia_compatibilidade_estudo_e_revisoes(copia):
    main,c,factory,perfil=copia
    r=c.post('/admin/assuntos/1/copiar',json={'disciplina_destino_id':2});assert r.status_code==200
    with factory() as db:
        assunto_id=r.json()['novo_assunto_id']
        pasta=db.query(m.Pasta).filter_by(curso_assunto_proprio_id=assunto_id).one()
        aula=db.query(m.Aula).filter_by(pasta_id=pasta.id).one()
        bateria=db.query(m.Bateria).filter_by(aula_id=aula.id,status='CONCLUIDA').one()
        for registro in (db.get(m.CursoDisciplinaPropria,2),aula,bateria):registro.ativo=True
        db.commit();bid,aid,pid=bateria.id,aula.id,pasta.id
    perfil(False)
    assert c.get(f'/aulas/{aid}/materiais?contratacao_id=1').status_code==403
    assert c.get(f'/aulas/{aid}/materiais?contratacao_id=3').status_code==200
    assert len(c.get(f'/baterias/{bid}/questoes?contratacao_id=3').json())==10
    from app.revisoes import estrutura, programar_primeira
    with factory() as db:
        _,assunto,disciplina,_=estrutura(db,pid)
        assert assunto.id==assunto_id and disciplina.curso_id==2
        t=m.TentativaBateria(usuario_id=1,bateria_id=bid,contratacao_id=3,status='FEITA',concluida_em=datetime.utcnow())
        db.add(t);db.flush()
        for q in db.query(m.Questao).filter_by(bateria_id=bid):
            db.add(m.RespostaAlunoQuestao(usuario_id=1,questao_id=q.id,bateria_id=bid,contratacao_id=3,
                                         tentativa_id=t.id,resposta_marcada='C',respondida=True))
        db.commit()
        programar_primeira(db,1,db.get(m.Aula,aid),3,None);db.commit()
        assert db.query(m.RevisaoAluno).filter_by(aula_id=aid,contratacao_id=3).one().etapa==1
        assert db.query(m.RevisaoAluno).filter_by(aula_id=1,contratacao_id=1).count()==1
