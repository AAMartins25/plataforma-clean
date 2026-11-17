from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from app.descricao_publica import preparar_descricao, descricao_para_visitante, MARCADOR
from app import models as m
from test_cursos_comerciais import comercial, ator, ADMIN
from test_compras_fluxo import ambiente_compra, motor

@pytest.mark.parametrize('texto', ['', '  Curso\n\n Professor & prova\r\n', '<b>texto literal</b> 2 < 3', '<script>alert(1)</script>'])
def test_legado_literal(texto):
    assert preparar_descricao({'descricao_publica': texto}, None) == texto
    assert preparar_descricao({'descricao_publica': texto}, texto) == texto
    assert descricao_para_visitante(texto) == {'descricao_publica': texto, 'descricao_publica_html': None}
    assert preparar_descricao({}, texto) == texto


def test_allowlist():
    html = '<h2 onclick="evil()">Curso</h2><p><strong>A</strong> <em>B</em><br>C</p><ol><li>Um</li></ol><script>alert(1)</script><img src=x onerror=evil()><a href="javascript:evil()">link</a><svg onload=evil()></svg><p style="color:red" data-x="1">Fim</p>'
    valor = preparar_descricao({'descricao_publica': html, 'descricao_publica_formato': 'html_v1'}, None)
    assert valor.startswith(MARCADOR)
    publico = descricao_para_visitante(valor)
    assert '<strong>A</strong>' in publico['descricao_publica_html']
    for mal in ['script', 'onclick', 'onerror', 'javascript', '<img', '<svg', 'style=', 'data-x=']:
        assert mal not in publico['descricao_publica_html']
    assert publico['descricao_publica'].startswith('Curso\nA B\nC\nUm\n')

def test_separador_e_tamanho_com_sanitizacao():
    html = '<p>Antes <span style="font-size:19px">maior</span></p><hr><p><span style="font-size:19px;color:red">inseguro</span><span style="font-size:99px">grande</span><span style="font-size:expression(alert(1))">ataque</span></p>'
    salvo = preparar_descricao({'descricao_publica': html, 'descricao_publica_formato': 'html_v1'}, None)
    publico = descricao_para_visitante(salvo)['descricao_publica_html']
    assert '<hr>' in publico
    assert '<span style="font-size:19px">maior</span>' in publico
    assert publico.count('style=') == 1
    assert 'expression' not in publico and 'color:red' not in publico

@pytest.mark.parametrize('payload', [{'descricao_publica': []}, {'descricao_publica': 'x', 'descricao_publica_formato': 'ruim'}, {'descricao_publica': 'x'*1000001, 'descricao_publica_formato': 'html_v1'}])
def test_rejeita_invalido(payload):
    with pytest.raises(HTTPException) as e:
        preparar_descricao(payload, None)
    assert e.value.status_code == 422


def test_rotas_gravacao_releitura_precos_permissoes(comercial):
    a = comercial
    main, client, factory, post, get = a
    # Tabelas da estrutura pública, criadas somente no SQLite descartável.
    with factory() as db:
        m.Base.metadata.create_all(db.bind, tables=[m.CursoDisciplinaPropria.__table__, m.CursoAssuntoProprio.__table__])
        curso = db.get(m.Curso, 1)
        curso.descricao_publica = '  Original\n\n<b>literal</b>  '
        db.commit()
        original = curso.descricao_publica
        tempos = [tuple(x) for x in db.execute(m.TempoAcessoCurso.__table__.select())]
    payload = {'descricao_publica': original}
    assert client.put('/admin/cursos/1/config-publica', json=payload).status_code == 403
    ator(a, ADMIN)
    assert client.put('/admin/cursos/1/config-publica', json=payload).status_code == 200
    assert client.get('/admin/cursos/1/config-publica').json()['descricao_publica'] == original
    html = '<h2>Curso</h2><p style="text-align:center"><strong>Professor</strong> e <em>prova</em> <span style="font-size:14px">Texto</span></p><ul><li>Uma aula</li></ul>'
    payload = {'descricao_publica': html, 'descricao_publica_formato': 'html_v1'}
    assert client.put('/admin/cursos/1/config-publica', json=payload).status_code == 200
    with factory() as db:
        assert db.get(m.Curso, 1).descricao_publica == MARCADOR + html
        assert tempos == [tuple(x) for x in db.execute(m.TempoAcessoCurso.__table__.select())]
    admin = client.get('/admin/cursos/1/config-publica').json()
    assert admin['descricao_publica'] == MARCADOR + html
    publico = client.get('/public/cursos/1/checkout')
    assert publico.status_code == 200, publico.text
    assert publico.json()['descricao_publica_html'] == html
    assert publico.json()['descricao_publica'] == 'Curso\nProfessor e prova Texto\nUma aula'
    assert not post.called and not get.called

@pytest.mark.parametrize('tamanho', [14, 16, 20])
def test_tamanho_personalizado_sobrevive_ao_salvar_e_exibir(tamanho):
    html = f'<p><span style="font-size:{tamanho}px;">Texto</span></p>'
    salvo = preparar_descricao({'descricao_publica': html, 'descricao_publica_formato': 'html_v1'}, None)
    assert f'font-size:{tamanho}px' in salvo
    assert f'font-size:{tamanho}px' in descricao_para_visitante(salvo)['descricao_publica_html']

@pytest.mark.parametrize('alinhamento', ['left', 'center', 'right', 'justify'])
def test_alinhamento_sobrevive_ao_salvar_e_exibir(alinhamento):
    html = f'<p style="text-align:{alinhamento};">Texto</p>'
    salvo = preparar_descricao({'descricao_publica': html, 'descricao_publica_formato': 'html_v1'}, None)
    assert f'text-align:{alinhamento}' in salvo
    assert f'text-align:{alinhamento}' in descricao_para_visitante(salvo)['descricao_publica_html']

def test_alinhamento_rejeita_estilos_e_elementos_nao_permitidos():
    html = '<p style="text-align:center;color:red">x</p><span style="text-align:right">y</span><p style="text-align:expression(alert(1))">z</p>'
    salvo = preparar_descricao({'descricao_publica': html, 'descricao_publica_formato': 'html_v1'}, None)
    assert 'style=' not in salvo
