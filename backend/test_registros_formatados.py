"""Regressões HTTP em SQLite descartável; nenhum banco externo é utilizado."""
import pytest
from pydantic import ValidationError
from app import models as m, schemas
from app.registros_html import preparar_registro, texto_visivel
from test_revisoes_assunto import env
from test_anotacoes_tentativa import api as anotacao_api, criar
from test_mensagens_prof import api as conversa_api, iniciar, _dados_reformulacao

HTML = '<p><strong>Nota</strong> <i>itálica</i> <u>sublinhada</u></p><ul><li>Item</li></ul><figure class="table"><table><tr><td>A</td><td>B</td></tr></table></figure><p><span class="ro-math-inline">p \\land q \\Rightarrow r</span></p>'


def test_formato_limites_e_xss():
    for cls in (schemas.AnotacaoTexto, schemas.MensagemProfessorTexto):
        value = cls(texto=HTML+'<script>alert(1)</script><img src="x" onerror="alert(1)"><iframe src="x"></iframe>',texto_formato='html_v1')
        assert '<strong>' in value.texto and '<table>' in value.texto and 'ro-math-inline' in value.texto
        assert all(x not in value.texto for x in ('<script','<img','onerror','<iframe'))
        assert '<a>link</a>' in cls(texto='<p><a href="javascript:alert(1)">link</a></p>',texto_formato='html_v1').texto
        assert len(texto_visivel(cls(texto='<p>palavra</p>'*300,texto_formato='html_v1').texto,'html_v1').split()) == 300
        with pytest.raises(ValidationError): cls(texto='<p>palavra</p>'*301,texto_formato='html_v1')
        with pytest.raises(ValidationError): cls(texto='<p><br></p>',texto_formato='html_v1')
        with pytest.raises(ValidationError): cls(texto='teste',texto_formato='outro')
        assert cls(texto='<b>legado literal</b>').texto == '<b>legado literal</b>'
    assert preparar_registro(preparar_registro(HTML,'html_v1'),'html_v1') == preparar_registro(HTML,'html_v1')


def test_anotacao_gravar_reabrir_editar_e_legado(anotacao_api):
    db,c = anotacao_api
    raw = criar(c,texto='<b>antigo literal</b>').json()
    aid = raw['id']
    assert db.get(m.AnotacaoAlunoQuestao,aid).texto == '<b>antigo literal</b>'
    rows = c.get('/me/minhas-anotacoes?demonstracao_id=1').json()
    assert rows[0]['anotacao'] == '<b>antigo literal</b>' and rows[0]['texto_formato'] == 'texto_puro'
    url = f'/me/anotacoes-questoes/{aid}?demonstracao_id=1'
    saved = c.put(url,json={'texto':HTML,'texto_formato':'html_v1'})
    assert saved.status_code == 200, saved.text
    expected = saved.json()['texto']
    assert c.put(url,json={'texto':'Cliente antigo sem formato'}).status_code == 409
    assert c.get('/me/minhas-anotacoes?demonstracao_id=1').json()[0]['anotacao'] == expected
    again = c.put(url,json={'texto':expected,'texto_formato':'html_v1'})
    assert again.json()['texto'] == expected
    row = db.get(m.AnotacaoAlunoQuestao,aid)
    assert (row.usuario_id,row.questao_id,row.bateria_id,row.tentativa_id,row.demonstracao_id) == (1,1,1,1,1)
    assert c.put(url.replace('=1','=2'),json={'texto':HTML,'texto_formato':'html_v1'}).status_code == 404
    assert db.get(m.AnotacaoAlunoQuestao,aid).texto == expected


def test_mensagem_formatada_permissoes_e_reformulacao(conversa_api):
    db,c,actor = conversa_api
    response = iniciar(c,texto=HTML,texto_formato='html_v1')
    assert response.status_code == 200, response.text
    conv = response.json(); cid = conv['conversa_id']
    assert conv['mensagens'][0]['texto_formato'] == 'html_v1'
    assert '<table>' in c.get('/me/mensagens-prof?demonstracao_id=1').json()[0]['mensagens'][0]['texto']
    assert c.post(f'/me/mensagens-prof/{cid}/responder?demonstracao_id=1',json={'texto':HTML,'texto_formato':'html_v1'}).status_code == 409
    assert c.put(f'/me/mensagens-prof/{cid}',json={'texto':'indevida'}).status_code in {404,405}
    actor.id = 2
    assert c.get('/me/mensagens-prof?demonstracao_id=1').status_code == 403
    assert c.post(f'/me/mensagens-prof/{cid}/responder?demonstracao_id=1',json={'texto':HTML,'texto_formato':'html_v1'}).status_code == 404
    actor.id = 1
    # A reformulação autorizada continua substituindo a conversa e é idempotente.
    body = _dados_reformulacao(c,cid,texto=HTML,texto_formato='html_v1')
    url = f'/me/mensagens-prof/{cid}/reformular?demonstracao_id=1'
    first = c.post(url,json=body)
    assert first.status_code == 200, first.text
    assert c.post(url,json=body).json() == first.json()
    assert c.post(url,json={**body,'texto_formato':'texto_puro'}).status_code == 409


def test_respostas_invalidas_nao_gravam_tentativa(conversa_api):
    db,c,_ = conversa_api
    body = {'bateria_id':1,'demonstracao_id':1,'respostas':[{'questao_id':i,'resposta_marcada':'C'} for i in range(1,11)]}
    before = db.query(m.TentativaBateria).count()
    for respostas in (body['respostas'][:9], body['respostas']+[body['respostas'][0]],
                      [{**x,'resposta_marcada':''} for x in body['respostas']],
                      [{**x,'resposta_marcada':'Z'} for x in body['respostas']]):
        res = c.post('/baterias/concluir',json={**body,'respostas':respostas})
        assert res.status_code == 400, res.text
    assert db.query(m.TentativaBateria).count() == before
    assert c.post('/baterias/concluir',json=body).status_code == 200


def test_dificuldade_nao_sei_pontuacao_e_revisao(conversa_api):
    db,c,_ = conversa_api
    questao = db.get(m.Questao,1)
    questao.tipo = 'MULTIPLA'
    questao.tipo_questao = 'MULTIPLA_5'
    # This scenario starts a fresh scheduled resolution, without the fixture's prior answer.
    db.query(m.RespostaAlunoQuestao).filter_by(tentativa_id=2).delete()
    db.delete(db.get(m.TentativaBateria,2))
    for letra in 'ABCDE':
        db.add(m.Alternativa(questao_id=1,letra=letra,texto='Alternativa'))
    db.commit()
    respostas = [{'questao_id':i,'resposta_marcada':'C'} for i in range(1,11)]
    body = {'bateria_id':1,'demonstracao_id':1,'respostas':respostas}
    before = db.query(m.TentativaBateria).count()
    assert c.post('/baterias/concluir',json=body).status_code == 400
    revision = '/me/revisoes/1/baterias/1/respostas?demonstracao_id=1'
    assert c.post(revision,json={'respostas':respostas}).status_code == 400
    assert db.query(m.TentativaBateria).count() == before
    respostas[0]['dificuldade'] = 'FACIL'
    respostas[-1]['resposta_marcada'] = 'NAO_SEI'
    normal = c.post('/baterias/concluir',json=body)
    assert normal.status_code == 200, normal.text
    assert normal.json()['percentual_acerto'] == 90
    row = db.query(m.RespostaAlunoQuestao).filter_by(tentativa_id=normal.json()['id'],questao_id=10).one()
    assert row.respondida and row.pulou and not row.acertou
    scheduled = c.post(revision,json={'respostas':respostas})
    assert scheduled.status_code == 200, scheduled.text
    assert db.get(m.TentativaBateria,scheduled.json()['id']).percentual_acerto == 90


def test_leitura_sanitiza_sem_reescrever_anotacao(anotacao_api):
    db,c = anotacao_api
    aid = criar(c,texto=HTML,texto_formato='html_v1').json()['id']
    row = db.get(m.AnotacaoAlunoQuestao,aid)
    original = row.texto + '<script>alert(1)</script><img src=x onerror=alert(1)>'
    row.texto = original
    db.commit()
    read = c.get('/me/minhas-anotacoes?demonstracao_id=1').json()[0]
    assert '<script' not in read['anotacao'] and '<img' not in read['anotacao']
    assert db.get(m.AnotacaoAlunoQuestao,aid).texto == original


def test_chave_editor_exige_autenticacao(conversa_api):
    db,c,actor = conversa_api
    main = c.app.state.main_module
    assert c.get('/me/ckeditor-chave').status_code == 200
    override = main.app.dependency_overrides.pop(main.get_usuario_atual)
    try:
        assert c.get('/me/ckeditor-chave').status_code == 401
    finally:
        main.app.dependency_overrides[main.get_usuario_atual] = override
