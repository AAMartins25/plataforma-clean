"""Testes em SQLite de memória; nenhum acesso ao banco de implantação."""
import copy
import pytest
from fastapi import HTTPException
from sqlalchemy import event
from app import models as m
from app.importacao_cursos import importar, preparar
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

@pytest.fixture
def contexto():
    engine = create_engine('sqlite://')
    tabelas = [m.Curso, m.CursoDisciplinaPropria, m.CursoAssuntoProprio, m.Pasta,
               m.Aula, m.Bateria, m.Questao, m.Alternativa, m.TempoAcessoCurso,
               m.Material, m.ImportacaoCurso, m.TentativaBateria,
               m.RespostaAlunoQuestao]
    m.Base.metadata.create_all(engine, tables=[x.__table__ for x in tabelas])
    db = sessionmaker(bind=engine, autoflush=False)()
    db.add(m.Curso(id=1, nome='Existente')); db.commit()
    yield db
    db.close(); engine.dispose()

@pytest.fixture
def documento():
    q = {'tipo':'MULTIPLA_4','enunciado_markdown':'Pergunta','alternativas':dict.fromkeys('ABCD','Alternativa'),'gabarito':'A','comentario_markdown':'Comentário'}
    q5 = dict(q, tipo='MULTIPLA_5', alternativas=dict.fromkeys('ABCDE','Alternativa'))
    ce = dict(q, tipo='CERTO_ERRADO', alternativas={}, gabarito='C')
    return {'versao':1,'curso':{'nome':'Importado','banca':'Banca','cargo':'Cargo','orgao':'Órgão','ano':2026,'uf':'SP','descricao_publica_markdown':'Descrição'},'disciplinas':[{'nome':'Disciplina','assuntos':[{'nome':'Assunto','aula_titulo':'Aula','resumos':[{'titulo':'Resumo','texto_markdown':'Teoria'}],'baterias':[{'titulo':'Múltipla','tipo':'MULTIPLA','questoes':[q5]+[q]*9},{'titulo':'Certo errado','tipo':'CERTO_ERRADO','questoes':[ce]*10}]}]}]}

def test_arvore_e_idempotencia(contexto, documento):
    db=contexto; key='0123456789abcdef'
    resultado=importar(db,1,key,documento,documento)
    curso=db.get(m.Curso,resultado['curso_id'])
    assert curso.precos_provisorios and curso.demonstracao_por_ordem and not curso.publicado
    assert [(x.meses,x.valor_cents,x.valor_provisorio_original_cents) for x in db.query(m.TempoAcessoCurso).filter_by(curso_id=curso.id).order_by(m.TempoAcessoCurso.meses)] == [(4,4,4),(8,8,8),(12,12,12)]
    d=db.query(m.CursoDisciplinaPropria).filter_by(curso_id=curso.id).one()
    a=db.query(m.CursoAssuntoProprio).filter_by(curso_disciplina_propria_id=d.id).one()
    pasta=db.query(m.Pasta).filter_by(curso_assunto_proprio_id=a.id).one()
    assert pasta.tipo=='TEORIA'
    aula=db.query(m.Aula).filter_by(pasta_id=pasta.id).one()
    assert db.query(m.Material).filter_by(aula_id=aula.id).one().conteudo_formato=='html_v1'
    assert [b.status for b in db.query(m.Bateria).filter_by(aula_id=aula.id).order_by(m.Bateria.ordem)]==['CONCLUIDA','CONCLUIDA']
    assert importar(db,1,key,documento,documento)=={'curso_id':curso.id,'repetida':True}
    alterado=copy.deepcopy(documento);alterado['curso']['nome']='Outro'
    with pytest.raises(HTTPException) as e: importar(db,1,key,alterado,alterado)
    assert e.value.status_code==409

def test_importacao_preserva_estilos_em_todos_os_campos(contexto, documento):
    original = copy.deepcopy(documento)
    convertido = copy.deepcopy(documento)
    assunto = convertido['disciplinas'][0]['assuntos'][0]
    html = '<p><strong><i><u>Três estilos</u></i></strong> <u>Simples</u></p>'
    assunto['resumos'][0]['texto_markdown'] = html
    for questao in assunto['baterias'][0]['questoes']:
        questao['enunciado_markdown'] = html
        questao['comentario_markdown'] = html
        questao['alternativas'] = {k: html for k in questao['alternativas']}
    importar(contexto, 1, 'estilos123456789', original, convertido)
    contexto.expire_all()
    material = contexto.query(m.Material).one()
    questao = contexto.query(m.Questao).filter_by(tipo_questao='MULTIPLA_5').one()
    for valor in [material.conteudo, questao.enunciado, questao.comentario, *(a.texto for a in questao.alternativas)]:
        assert '<strong><i><u>Três estilos</u></i></strong>' in valor
        assert '<u>Simples</u>' in valor
    assert material.conteudo_formato == questao.enunciado_formato == questao.comentario_formato == 'html_v1'
    assert all(a.texto_formato == 'html_v1' for a in questao.alternativas)

def test_importacao_libera_somente_duas_primeiras(contexto, documento):
    d=copy.deepcopy(documento)
    segunda=copy.deepcopy(d['disciplinas'][0]);segunda['nome']='Segunda'
    terceira=copy.deepcopy(d['disciplinas'][0]);terceira['nome']='Terceira'
    d['disciplinas'] += [segunda, terceira]
    cid=importar(contexto,1,'fedcba9876543210',d,d)['curso_id']
    disciplinas=contexto.query(m.CursoDisciplinaPropria).filter_by(curso_id=cid).order_by(m.CursoDisciplinaPropria.ordem).all()
    assert [x.disponivel_demonstracao for x in disciplinas] == [True, True, False]
    from app.desempenho import consultar
    desempenho=consultar(contexto,1,cid,None,1)
    assert [x['nome'] for x in desempenho['disciplinas']] == ['Disciplina','Segunda']


def test_duplicacao_define_disponibilidade_pela_posicao_no_destino(contexto):
    from app.copias import copiar_disciplina_conteudo
    db=contexto
    origem=m.Curso(id=10,nome='Origem');destino=m.Curso(id=11,nome='Destino',demonstracao_por_ordem=True)
    db.add_all([origem,destino]);db.flush()
    fontes=[m.CursoDisciplinaPropria(curso_id=10,nome=f'Disciplina {i}',ordem=i,
                                     disponivel_demonstracao=i <= 2) for i in range(1,4)]
    db.add_all(fontes);db.flush()
    for item in fontes:
        copiar_disciplina_conteudo(db,item,destino.id)
    copiadas=db.query(m.CursoDisciplinaPropria).filter_by(curso_id=destino.id).order_by(m.CursoDisciplinaPropria.id).all()
    assert [x.disponivel_demonstracao for x in copiadas] == [True,True,False]


def test_disponibilidade_importada_recalcula_ordem_e_ativacao(contexto):
    from app.disponibilidade_demonstracao import sincronizar
    db=contexto
    db.get(m.Curso,1).demonstracao_por_ordem=True
    disciplinas=[m.CursoDisciplinaPropria(curso_id=1,nome=f'Manual {i}',ordem=i,
                                           disponivel_demonstracao=False) for i in range(1,4)]
    db.add_all(disciplinas);db.flush()
    sincronizar(db,1)
    assert [x.disponivel_demonstracao for x in sorted(disciplinas,key=lambda x:x.ordem)] == [True,True,False]
    disciplinas[0].ativo=False;db.flush();sincronizar(db,1)
    assert [x.disponivel_demonstracao for x in sorted(disciplinas,key=lambda x:x.ordem)] == [False,True,True]

@pytest.mark.parametrize('tipo', ['quantidade','mistura','imagem','extra'])
def test_invalidos(contexto, documento, tipo):
    d=copy.deepcopy(documento); a=d['disciplinas'][0]['assuntos'][0]
    if tipo=='quantidade': a['baterias'][0]['questoes'].pop()
    if tipo=='mistura': a['baterias'][0]['questoes'][0]=a['baterias'][1]['questoes'][0]
    if tipo=='imagem': a['resumos'][0]['texto_markdown']='![imagem](https://exemplo.org/a.png)'
    if tipo=='extra': a['videos']=[]
    with pytest.raises(HTTPException): importar(contexto,1,'0123456789abcdef',d,d)
    assert contexto.query(m.Curso).count()==1

def test_rollback_em_falha_de_gravacao(contexto, documento):
    def falhar(mapper, connection, target): raise RuntimeError('falha simulada')
    event.listen(m.Alternativa,'before_insert',falhar)
    try:
        with pytest.raises(RuntimeError): importar(contexto,1,'0123456789abcdef',documento,documento)
        contexto.rollback()
    finally: event.remove(m.Alternativa,'before_insert',falhar)
    assert contexto.query(m.Curso).count()==1
    assert contexto.query(m.ImportacaoCurso).count()==0

def test_bloqueio_e_confirmacao_preco(contexto, documento):
    from types import SimpleNamespace
    from test_questoes_pratica_patch import carregar_main_isolado
    from app.cursos_comerciais import bloquear_curso
    db=contexto
    cid=importar(db,1,'0123456789abcdef',documento,documento)['curso_id']
    admin=SimpleNamespace(id=1,is_admin=True,tipo_admin='admin_geral')
    novos=[{'meses':4,'valor_cents':100},{'meses':8,'valor_cents':200},{'meses':12,'valor_cents':300}]
    with carregar_main_isolado(lambda: db, db.bind) as main:
        with pytest.raises(HTTPException) as e: main.publicar_curso(cid, db, admin)
        assert e.value.status_code==409
        with pytest.raises(HTTPException) as e: bloquear_curso(db,cid,aquisicao=True)
        assert e.value.status_code==409
        # Preços novos podem ser salvos sem confirmar; o marcador e a referência permanecem.
        main.salvar_config_publica_curso(cid, {'confirmar_precos_definitivos':False,'tempos_acesso':novos}, db, admin)
        assert db.get(m.Curso,cid).precos_provisorios
        config=main.obter_config_publica_curso(cid,db,admin)
        assert [(t['valor_cents'],t['valor_provisorio_original_cents']) for t in config['tempos_acesso']] == [(100,4),(200,8),(300,12)]
        # Contorno do frontend: repetir um preço provisório deve continuar sendo rejeitado.
        com_original=[{'meses':4,'valor_cents':4},{'meses':8,'valor_cents':200},{'meses':12,'valor_cents':300}]
        with pytest.raises(HTTPException) as e:
            main.salvar_config_publica_curso(cid, {'confirmar_precos_definitivos':True,'tempos_acesso':com_original}, db, admin)
        assert e.value.status_code==422
        db.rollback()
        assert db.get(m.Curso,cid).precos_provisorios
        with pytest.raises(HTTPException): main.publicar_curso(cid,db,admin)
        with pytest.raises(HTTPException): bloquear_curso(db,cid,aquisicao=True)
        # Após reload, confirmar os mesmos valores já salvos é permitido.
        main.salvar_config_publica_curso(cid, {'confirmar_precos_definitivos':True,'tempos_acesso':novos}, db, admin)
        assert not db.get(m.Curso,cid).precos_provisorios
        assert db.get(m.Curso,cid).demonstracao_por_ordem
        main.publicar_curso(cid,db,admin)
        assert db.get(m.Curso,cid).publicado


def test_confirmacao_no_mesmo_salvamento(contexto, documento):
    from types import SimpleNamespace
    from test_questoes_pratica_patch import carregar_main_isolado
    d=copy.deepcopy(documento); d['curso']['nome']='Importado confirmação imediata'
    db=contexto
    cid=importar(db,1,'abcdef0123456789',d,d)['curso_id']
    admin=SimpleNamespace(id=1,is_admin=True,tipo_admin='admin_geral')
    with carregar_main_isolado(lambda: db, db.bind) as main:
        main.salvar_config_publica_curso(cid, {'confirmar_precos_definitivos':True,'tempos_acesso':[{'meses':4,'valor_cents':40},{'meses':8,'valor_cents':80},{'meses':12,'valor_cents':120}]}, db, admin)
        assert db.get(m.Curso,cid).precos_provisorios is False


def test_versao_e_conteudo_hostil(contexto, documento):
    d=copy.deepcopy(documento); d['versao']=True
    with pytest.raises(HTTPException): preparar(d,d)
    d=copy.deepcopy(documento)
    d['disciplinas'][0]['assuntos'][0]['resumos'][0]['texto_markdown']='<script>alert(1)</script>'
    with pytest.raises(HTTPException) as e: preparar(d,d)
    assert 'resumos[0].texto_markdown' in str(e.value.detail)


def test_alteracao_dos_metadados_convertidos_rejeitada(documento):
    convertido=copy.deepcopy(documento); convertido['curso']['nome']='Outro nome'
    with pytest.raises(HTTPException): preparar(documento,convertido)

from test_cursos_comerciais import comercial, ator, ADMIN, ALUNO
from test_compras_fluxo import ambiente_compra, motor

def test_api_checkout_publicacao_e_curso_antigo(comercial):
    _, client, factory, post, _ = comercial
    with factory() as db:
        curso=db.get(m.Curso,1)
        curso.precos_provisorios=True
        curso.publicado=True
        db.commit()
    ator(comercial,ALUNO)
    r=client.post('/checkout/mercadopago',json={'tempo_acesso_id':1})
    assert r.status_code==409 and 'provisórios' in r.json()['detail']
    post.assert_not_called()
    ator(comercial,ADMIN)
    assert client.put('/admin/cursos/1/publicar',json={}).status_code==409
    with factory() as db:
        db.get(m.Curso,1).precos_provisorios=False
        db.commit()
    assert client.put('/admin/cursos/1/publicar',json={}).status_code==200

@pytest.mark.parametrize('ponto', ['questoes', 'commit'])
def test_rollback_em_pontos_tardios(contexto, documento, ponto):
    db=contexto
    contador={'n':0}
    def falhar_questao(mapper, connection, target):
        contador['n']+=1
        if contador['n']==5: raise RuntimeError('falha após questões anteriores')
    def falhar_commit(session): raise RuntimeError('falha antes do commit')
    alvo,evento,fn = (m.Questao,'before_insert',falhar_questao) if ponto=='questoes' else (db,'before_commit',falhar_commit)
    event.listen(alvo,evento,fn)
    try:
        with pytest.raises(RuntimeError): importar(db,1,'1234567890abcdef',documento,documento)
        db.rollback()
    finally: event.remove(alvo,evento,fn)
    assert db.query(m.Curso).count()==1
    assert db.query(m.ImportacaoCurso).count()==0
    assert db.query(m.CursoDisciplinaPropria).count()==0
    assert db.query(m.Questao).count()==0

@pytest.mark.parametrize('zip_com_imagens', [False, True])
def test_alinhamento_importado_persiste_e_permanece_editavel(contexto, documento, zip_com_imagens):
    from app.teoria_html import preparar_conteudo
    original = copy.deepcopy(documento)
    convertido = copy.deepcopy(documento)
    assunto = convertido['disciplinas'][0]['assuntos'][0]
    html = ('<p>Texto <strong>forte</strong> e <u>sublinhado</u></p>'
            '<p style="text-align:center">Centralizado</p>'
            '<ul><li>Item</li></ul><table><tbody><tr>'
            '<td style="text-align:right"><p>Célula</p></td></tr></tbody></table>')
    assunto['resumos'][0]['texto_markdown'] = html
    q = assunto['baterias'][0]['questoes'][0]
    q['enunciado_markdown'] = q['comentario_markdown'] = html
    q['alternativas'] = {k: html for k in q['alternativas']}
    importar(contexto, 1, 'alinhamento123456', original, convertido,
             mapa={} if zip_com_imagens else None)
    contexto.expire_all()
    material = contexto.query(m.Material).one()
    questao = contexto.query(m.Questao).filter_by(tipo_questao='MULTIPLA_5').one()
    for valor in [material.conteudo, questao.enunciado, questao.comentario, *(a.texto for a in questao.alternativas)]:
        assert '<p style="text-align:justify">Texto <strong>forte</strong> e <u>sublinhado</u></p>' in valor
        assert '<p style="text-align:center">Centralizado</p>' in valor
        assert '<li style="text-align:justify">Item</li>' in valor
        assert '<td style="text-align:right"><p>Célula</p></td>' in valor
        assert preparar_conteudo(valor, 'html_v1') == valor
        editado = valor.replace('text-align:justify', 'text-align:left')
        assert 'text-align:left' in preparar_conteudo(editado, 'html_v1')
    assert 'text-align:justify' not in contexto.query(m.Curso).filter_by(nome='Importado').one().descricao_publica


@pytest.mark.parametrize('zip_sem_imagens', [False, True])
def test_importacao_uf_nacional_v1(contexto, documento, zip_sem_imagens):
    dados = copy.deepcopy(documento)
    dados['curso']['uf'] = 'NACIONAL'
    resultado = importar(contexto, 1, 'ufnacional123456', dados, dados,
                         mapa={} if zip_sem_imagens else None)
    contexto.expire_all()
    assert contexto.get(m.Curso, resultado['curso_id']).uf == 'NACIONAL'
