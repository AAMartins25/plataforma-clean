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
    html = '<h2>Curso</h2><p><strong>Professor</strong> e <em>prova</em></p><ul><li>Uma aula</li></ul>'
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
    assert publico.json()['descricao_publica'] == 'Curso\nProfessor e prova\nUma aula'
    assert not post.called and not get.called
