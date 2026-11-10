"""Editor das baterias: HTTP real, SQLite descartável e Storage em memória."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from app import models as m
from test_aulas_admin import questao, inserir_historico
from test_imagens_teoria import ambiente_imagens, aulas, infraestrutura, enviar
from app.imagens_manutencao import limpar_pendentes


HTML = '<h2>Título</h2><p style="text-align:center"><strong>Negrito</strong> <i>itálico</i> <u>sublinhado</u><br>linha</p><ul><li>Item</li></ul><ol><li>Um</li></ol><p><a href="https://exemplo.org">Link</a><span class="ro-math-inline">x^2</span></p><figure class="table"><table><tbody><tr><td colspan="2">Célula</td></tr></tbody></table><figcaption>Legenda</figcaption></figure>'


def rica(tipo='MULTIPLA_4', **extra):
    letras = 'ABCDE' if tipo == 'MULTIPLA_5' else 'ABCD'
    return questao(tipo, enunciado=HTML, enunciado_formato='html_v1',
                   comentario=HTML, comentario_formato='html_v1',
                   alternativas=[] if tipo=='CERTO_ERRADO' else [dict(letra=l, texto='<p><strong>'+l+'</strong></p>', texto_formato='html_v1') for l in letras], **extra)


@pytest.mark.parametrize('tipo',['MULTIPLA_4','MULTIPLA_5','CERTO_ERRADO'])
def test_criar_editar_reabrir_todos_campos(ambiente_imagens,tipo):
    _,c,factory,_,_=ambiente_imagens
    payload=rica(tipo)
    r=c.post('/questoes',json=payload); assert r.status_code==200,r.text
    id=r.json()['id']
    atual=next(q for q in c.get('/baterias/1/questoes').json() if q['id']==id)
    for campo in ['enunciado','comentario']:
        assert atual[campo+'_formato']=='html_v1'
        for tag in ['<h2>','<strong>','<i>','<u>','<ul>','<ol>','<table>','ro-math-inline','text-align:center']:
            assert tag in atual[campo]
    assert all(a['texto_formato']=='html_v1' and '<strong>' in a['texto'] for a in atual['alternativas'])
    ids=[a['id'] for a in atual['alternativas']]
    payload['enunciado']='<p><strong>Editado</strong></p>'
    r=c.put(f'/questoes/{id}',json=payload); assert r.status_code==200,r.text
    reaberta=next(q for q in c.get('/baterias/1/questoes').json() if q['id']==id)
    assert reaberta['enunciado']==payload['enunciado']
    assert [a['id'] for a in reaberta['alternativas']]==ids


def test_legado_nao_reescrito_e_edicao_cliente_antigo(ambiente_imagens):
    _,c,factory,_,_=ambiente_imagens
    texto='Antiga <b>literal</b> & x < y\nSegunda linha'
    payload=questao(enunciado=texto,comentario=texto)
    r=c.post('/questoes',json=payload); assert r.status_code==200,r.text
    id=r.json()['id']
    with factory() as db:
        assert db.get(m.Questao,id).enunciado==texto
        assert db.get(m.Questao,1).enunciado=='Concluída'
    payload=rica();assert c.put(f'/questoes/{id}',json=payload).status_code==200
    payload.pop('enunciado_formato');payload.pop('comentario_formato')
    for a in payload['alternativas']:a.pop('texto_formato')
    assert c.put(f'/questoes/{id}',json=payload).status_code==200
    q=next(q for q in c.get('/baterias/1/questoes').json() if q['id']==id)
    assert q['enunciado_formato']=='html_v1' and q['alternativas'][0]['texto_formato']=='html_v1'


@pytest.mark.parametrize('campo',['enunciado','comentario','alternativa'])
@pytest.mark.parametrize('conteudo',['<p><br></p>','<script>alert(1)</script>','<p>\u200b &nbsp;</p>'])
def test_html_vazio_recusado_sem_gravar(ambiente_imagens,campo,conteudo):
    _,c,factory,_,_=ambiente_imagens
    p=rica()
    if campo=='alternativa':p['alternativas'][0]['texto']=conteudo
    else:p[campo]=conteudo
    with factory() as db:antes=db.query(m.Questao).count()
    r=c.post('/questoes',json=p);assert r.status_code==422,r.text
    with factory() as db:assert db.query(m.Questao).count()==antes


@pytest.mark.parametrize('campo',['enunciado','comentario','alternativa'])
def test_xss_e_urls_ativas_removidos(ambiente_imagens,campo):
    _,c,_,_,_=ambiente_imagens
    p=rica();ataque='<p onclick="alert(1)" style="color:red;position:fixed">Seguro<script>alert(1)</script><a href="javascript:alert(1)">link</a><iframe src="https://exemplo.org"></iframe><svg onload="alert(1)"></svg></p>'
    if campo=='alternativa':p['alternativas'][0]['texto']=ataque
    else:p[campo]=ataque
    r=c.post('/questoes',json=p);assert r.status_code==200,r.text
    q=next(q for q in c.get('/baterias/1/questoes').json() if q['id']==r.json()['id'])
    html=q['alternativas'][0]['texto'] if campo=='alternativa' else q[campo]
    assert 'Seguro' in html
    assert not any(t in html for t in ['onclick','javascript:','<script','<iframe','<svg','position:','color:'])


@pytest.mark.parametrize('campo',['enunciado_formato','comentario_formato','alternativa'])
def test_formato_invalido_recusado(ambiente_imagens,campo):
    _,c,_,_,_=ambiente_imagens;p=rica()
    if campo=='alternativa':p['alternativas'][0]['texto_formato']='html_livre'
    else:p[campo]='html_livre'
    assert c.post('/questoes',json=p).status_code==422


def test_edicao_formatacao_preserva_historico_e_identidades(ambiente_imagens):
    _,c,factory,_,_=ambiente_imagens
    with factory() as db:
        inserir_historico(db,'tentativa');inserir_historico(db,'resposta');inserir_historico(db,'anotacao');inserir_historico(db,'mensagem');inserir_historico(db,'revisao')
        modelos=[m.TentativaBateria,m.RespostaAlunoQuestao,m.AnotacaoAlunoQuestao,m.ConversaQuestaoProfessor,m.RevisaoAluno]
        antes={t.__tablename__:list(db.execute(select(t.__table__))) for t in modelos}
    p=rica('CERTO_ERRADO');p['bateria_id']=2
    r=c.put('/questoes/1',json=p);assert r.status_code==200,r.text
    with factory() as db:assert antes=={t.__tablename__:list(db.execute(select(t.__table__))) for t in modelos}
    p=rica();p['bateria_id']=2
    assert c.put('/questoes/1',json=p).status_code==409
    assert c.delete('/questoes/1').status_code==409


def test_imagens_em_todos_campos_copia_permissoes_e_limpeza(ambiente_imagens):
    main,c,factory,perfil,storage=ambiente_imagens
    imgs=enviar(c)
    img=imgs[0];html=f'<figure class="image"><img src="{img["src"]}" alt="Figura"><figcaption>Legenda</figcaption></figure>'
    p=rica();p['enunciado']=html;p['comentario']=html;p['alternativas'][0]['texto']=html
    r=c.post('/questoes',json=p);assert r.status_code==200,r.text
    id=r.json()['id']
    # Other nine questions allow the same production rules to conclude the battery.
    for i in range(9):assert c.post('/questoes',json=questao('CERTO_ERRADO')).status_code==200
    assert c.put('/baterias/1/concluir',json={}).status_code==200
    with factory() as db:
        assert db.query(m.ImagemQuestao).filter_by(questao_id=id).count()==1
        db.get(m.ImagemTeoria,img['id']).ultima_atividade=datetime.utcnow()-timedelta(days=3);db.commit()
    perfil(False)
    url='/baterias/1/imagens/assinaturas?contratacao_id=1'
    assert c.post(url,json={'ids':[img['id']]}).status_code==200
    assert c.post('/baterias/1/imagens/assinaturas?contratacao_id=2',json={'ids':[img['id']]}).status_code==403
    assert c.post('/baterias/2/imagens/assinaturas?contratacao_id=1',json={'ids':[img['id']]}).status_code==403
    perfil(True)
    with factory() as db:
        m.TempoAcessoCurso.__table__.create(db.bind,checkfirst=True)
        resultado=main.duplicar_curso_inteiro(1,main.schemas.DuplicarCursoRequest(novo_nome='Cópia rica'),db,SimpleNamespace(id=1,is_admin=True,tipo_admin='admin_geral'))
        curso=resultado['novo_curso_id']
        copia=(db.query(m.Questao).join(m.Bateria).join(m.Aula).join(m.Pasta).join(m.CursoAssuntoProprio,m.Pasta.curso_assunto_proprio_id==m.CursoAssuntoProprio.id).join(m.CursoDisciplinaPropria).filter(m.CursoDisciplinaPropria.curso_id==curso,m.Questao.enunciado==html).one())
        assert copia.enunciado_formato=='html_v1' and copia.comentario==html
        assert copia.alternativas[0].texto==html and copia.alternativas[0].texto_formato=='html_v1'
        assert db.query(m.ImagemQuestao).filter_by(questao_id=copia.id).count()==1
        assert limpar_pendentes(db,storage)==0
    assert storage.objetos
    # Edit only one field: the other references must retain the shared image.
    p['enunciado']='<p>Sem imagem aqui</p>'
    assert c.put(f'/questoes/{id}',json=p).status_code==200
    with factory() as db:assert db.query(m.ImagemQuestao).filter_by(questao_id=id).count()==1


def test_imagem_pendente_de_outro_admin_recusada(ambiente_imagens):
    _,c,factory,_,_=ambiente_imagens
    img=enviar(c)[0]
    with factory() as db:db.get(m.ImagemTeoria,img['id']).autor_id=2;db.commit()
    p=rica();p['enunciado']=f'<p><img src="{img["src"]}"></p>'
    assert c.post('/questoes',json=p).status_code==422
    with factory() as db:assert db.query(m.Questao).count()==1


def test_revisao_programada_retorna_formatos_e_preserva_respostas(ambiente_imagens):
    _,c,factory,perfil,_=ambiente_imagens
    for i in range(10):
        r=c.post('/questoes',json=rica('CERTO_ERRADO'));assert r.status_code==200,r.text
    assert c.put('/baterias/1/concluir',json={}).status_code==200
    with factory() as db:
        db.add(m.RevisaoAluno(id=1,usuario_id=1,pasta_id=1,aula_id=1,contratacao_id=1,etapa=1,status='PENDENTE',data_prevista=datetime.utcnow()-timedelta(days=1)));db.commit()
    perfil(False)
    url='/me/revisoes/1/baterias/1'
    r=c.get(url+'/questoes?contratacao_id=1');assert r.status_code==200,r.text
    questoes=r.json()
    assert len(questoes)==10
    assert all(q['enunciado_formato']=='html_v1' and '<strong>' in q['comentario'] and q['comentario_formato']=='html_v1' for q in questoes)
    respostas={'respostas':[{'questao_id':q['id'],'resposta_marcada':'C','dificuldade':'FACIL','rever':False} for q in questoes]}
    r=c.post(url+'/respostas?contratacao_id=1',json=respostas);assert r.status_code==200,r.text
    assert c.post(url+'/respostas?contratacao_id=1',json=respostas).status_code==200
    with factory() as db:
        assert db.query(m.RespostaAlunoQuestao).count()==10
        assert db.query(m.TentativaBateria).count()==1


def test_limite_bateria_e_gabarito_nao_mudam(ambiente_imagens):
    _,c,factory,_,_=ambiente_imagens
    p=rica();p['gabarito']='E'
    assert c.post('/questoes',json=p).status_code==400
    p=rica('CERTO_ERRADO');p['alternativas']=[{'letra':'C','texto':'Certo'}]
    assert c.post('/questoes',json=p).status_code==400
    for i in range(10):assert c.post('/questoes',json=rica('CERTO_ERRADO')).status_code==200
    assert c.post('/questoes',json=rica('CERTO_ERRADO')).status_code==400
