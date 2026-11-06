"""Teoria formatada em SQLite descartável, sem acesso ao banco configurado."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from test_aulas_admin import infraestrutura, MODELOS, texto
from app import models as m
from app.copias import copiar_assunto_conteudo
from app.teoria_html import preparar_conteudo


@pytest.fixture
def ambiente(infraestrutura):
    """Chama as rotas diretamente: TestClient trava no AnyIO deste Python local."""
    main, engine, factory = infraestrutura
    tabelas = [modelo.__table__ for modelo in MODELOS +
               [m.QuestaoPraticaAssunto, m.QuestaoPraticaAlternativa]]
    m.Base.metadata.drop_all(engine, tables=tabelas)
    m.Base.metadata.create_all(engine, tables=tabelas)
    with factory() as db:
        db.add(m.Usuario(id=1, nome='Admin', email='admin@teste.local', senha_hash='teste', cpf='1', telefone='0'))
        db.add(m.Curso(id=1, nome='Curso'))
        db.flush()
        db.add(m.CursoDisciplinaPropria(id=1, curso_id=1, nome='Disciplina'))
        db.flush()
        db.add(m.CursoAssuntoProprio(id=1, curso_disciplina_propria_id=1, nome='Assunto'))
        db.flush()
        db.add(m.Pasta(id=1, curso_assunto_proprio_id=1, tipo='TEORIA', nome='Teoria'))
        db.flush()
        db.add(m.Aula(id=1, pasta_id=1, titulo='Aula'))
        db.flush()
        db.add(m.Material(id=1, aula_id=1, titulo='Texto', tipo='TEXTO', conteudo='Conteúdo', ordem=1))
        db.commit()
    class Resposta:
        def __init__(self, status_code, dados):
            self.status_code = status_code
            self.dados = dados
            self.text = str(dados)

        def json(self):
            return self.dados

    class Cliente:
        usuario = SimpleNamespace(id=1, is_admin=True, tipo_admin='admin_geral')

        def request(self, metodo, caminho, json=None):
            try:
                if self.usuario is None:
                    raise HTTPException(401, 'Não autenticado')
                with factory() as db:
                    if metodo == 'get' and caminho == '/aulas/1/materiais':
                        dados = main.listar_materiais_da_aula(1, db=db, usuario=self.usuario)
                    else:
                        admin = main.exigir_admin_aulas(self.usuario)
                        entrada = main.MaterialCreate(**json)
                        if metodo == 'post' and caminho == '/materiais':
                            dados = main.criar_material(entrada, db=db, usuario=admin)
                        elif metodo == 'put' and caminho.startswith('/materiais/'):
                            dados = main.editar_material(int(caminho.rsplit('/', 1)[1]), entrada, db=db, usuario=admin)
                        else:
                            raise AssertionError(caminho)
                    return Resposta(200, dados)
            except HTTPException as exc:
                return Resposta(exc.status_code, {'detail': exc.detail})

        def get(self, caminho):
            return self.request('get', caminho)

        def post(self, caminho, json):
            return self.request('post', caminho, json)

        def put(self, caminho, json):
            return self.request('put', caminho, json)

    cliente = Cliente()
    def perfil(admin):
        cliente.usuario = SimpleNamespace(id=1, is_admin=admin,
                                          tipo_admin='admin_geral' if admin else None)
    yield main, cliente, factory, perfil


def test_criar_editar_reabrir_e_preservar_legado(ambiente):
    _, cliente, factory, _ = ambiente
    legado = cliente.get('/aulas/1/materiais').json()[0]
    assert legado['conteudo_formato'] == 'texto_puro'
    assert legado['conteudo'] == 'Conteúdo'

    html = '<h2>Título</h2><p><strong>Negrito</strong> <em>itálico</em> <u>sublinhado</u></p>'
    html += '<ul><li>Item</li></ul><figure class="table"><table><tbody><tr><td>A</td></tr></tbody></table></figure>'
    criado = cliente.post('/materiais', json=texto(titulo='Rico', conteudo=html, conteudo_formato='html_v1'))
    assert criado.status_code == 200, criado.text
    identificador = criado.json()['id']
    assert criado.json()['conteudo_formato'] == 'html_v1'
    for trecho in ('<h2>', '<strong>', '<em>', '<u>', '<ul>', '<table>', '<td>'):
        assert trecho in criado.json()['conteudo']

    editado = cliente.put(f'/materiais/{identificador}', json=texto(titulo='Rico editado',
                          conteudo='<p style="text-align:center">Editado<br>em duas linhas</p>',
                          conteudo_formato='html_v1'))
    assert editado.status_code == 200, editado.text
    assert 'text-align:center' in editado.json()['conteudo']
    assert '<br>' in editado.json()['conteudo']
    reaberto = next(m for m in cliente.get('/aulas/1/materiais').json() if m['id'] == identificador)
    assert reaberto['conteudo'] == editado.json()['conteudo']
    assert reaberto['conteudo_formato'] == 'html_v1'
    with factory() as db:
        assert db.get(m.Material, 1).conteudo == 'Conteúdo'
        assert db.get(m.Material, 1).conteudo_formato is None


def test_edicao_legada_nao_converte_sem_pedido_explicito(ambiente):
    _, cliente, _, _ = ambiente
    assert cliente.put('/materiais/1', json={
        'aula_id': 1, 'tipo': 'TEXTO', 'titulo': 'Novo', 'conteudo_formato': 'html_v1'
    }).status_code == 422
    resposta = cliente.put('/materiais/1', json=texto(conteudo='<b>Literal</b>\nLinha'))
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()['conteudo'] == '<b>Literal</b>\nLinha'
    assert resposta.json()['conteudo_formato'] == 'texto_puro'
    convertido = cliente.put('/materiais/1', json=texto(
        conteudo='<p><b>Literal</b><br>Linha</p>', conteudo_formato='html_v1'))
    assert convertido.status_code == 200, convertido.text
    assert convertido.json()['conteudo_formato'] == 'html_v1'
    assert cliente.put('/materiais/1', json=texto(conteudo='apagaria o formato',
                       conteudo_formato='texto_puro')).status_code == 422


def test_sanitizacao_na_criacao_e_na_edicao(ambiente):
    _, cliente, _, _ = ambiente
    sujo = ('<p onclick="x()" style="text-align:expression(x)">Seguro</p>'
             '<script>alert(1)</script><img src="https://exemplo.local/a.png">'
             '<a href="javascript:alert(1)">ruim</a>'
             '<a href="https://exemplo.local/ok">bom</a>'
             '<a href="//exemplo.local/evil">protocolo relativo</a>')
    for metodo, caminho in (('post', '/materiais'), ('put', '/materiais/1')):
        resposta = cliente.request(metodo, caminho, json=texto(conteudo=sujo, conteudo_formato='html_v1'))
        assert resposta.status_code == 200, resposta.text
        limpo = resposta.json()['conteudo']
        for proibido in ('<script', '<img', 'onclick', 'javascript:', 'expression(', 'href="//'):
            assert proibido not in limpo
        assert 'href="https://exemplo.local/ok"' in limpo


def test_html_requer_permissao_administrativa(ambiente):
    main, cliente, factory, perfil = ambiente
    with factory() as db:
        antes = db.query(m.Material).count()
    perfil(False)
    resposta = cliente.post('/materiais', json=texto(conteudo='<p>Privado</p>', conteudo_formato='html_v1'))
    assert resposta.status_code == 403
    with factory() as db:
        assert db.query(m.Material).count() == antes
    cliente.usuario = None
    assert cliente.post('/materiais', json=texto(conteudo='<p>Privado</p>', conteudo_formato='html_v1')).status_code == 401


def test_chave_cloud_exige_permissao_e_nao_usa_gpl(ambiente, monkeypatch):
    main, _, _, perfil = ambiente
    monkeypatch.setenv('CKEDITOR_LICENSE_KEY', 'chave-comercial-de-teste')
    assert main.obter_chave_ckeditor(usuario=main.exigir_admin_aulas(
        SimpleNamespace(id=1, is_admin=True, tipo_admin='admin_geral'))) == {
            'licenseKey': 'chave-comercial-de-teste'
        }
    with pytest.raises(HTTPException) as erro:
        main.exigir_admin_aulas(SimpleNamespace(id=1, is_admin=False, tipo_admin=None))
    assert erro.value.status_code == 403


def test_formato_invalido_e_somente_imagem_rejeitados(ambiente):
    _, cliente, _, _ = ambiente
    assert cliente.post('/materiais', json=texto(conteudo='x', conteudo_formato='inventado')).status_code == 422
    assert cliente.post('/materiais', json=texto(conteudo='<img src="https://exemplo.local/a">',
                        conteudo_formato='html_v1')).status_code == 422


def test_urls_inseguras_nao_passam_pela_sanitizacao():
    for url in ('javascript:alert(1)', '//exemplo.local/a', 'data:text/html,abc',
                'https://usuario:senha@exemplo.local/a', 'https://exemplo.local\\@outro.local'):
        limpo = preparar_conteudo(f'<p><a href="{url}">link</a></p>', 'html_v1')
        assert 'href=' not in limpo


def test_copia_de_assunto_preserva_html_e_formato(ambiente):
    _, cliente, factory, _ = ambiente
    origem = cliente.put('/materiais/1', json=texto(
        conteudo='<p><strong>Rico</strong></p>', conteudo_formato='html_v1'))
    assert origem.status_code == 200, origem.text
    with factory() as db:
        novo_assunto = copiar_assunto_conteudo(db, db.get(m.CursoAssuntoProprio, 1), 1)
        db.flush()
        pasta = db.query(m.Pasta).filter_by(curso_assunto_proprio_id=novo_assunto.id).one()
        aula = db.query(m.Aula).filter_by(pasta_id=pasta.id).one()
        copiado = db.query(m.Material).filter_by(aula_id=aula.id).one()
        assert copiado.conteudo == origem.json()['conteudo']
        assert copiado.conteudo_formato == 'html_v1'


def test_marcas_internas_listas_e_tabela_persistem_apos_reabrir(ambiente):
    """Distingue perda nos dados de perda visual (coberta pelo Chromium)."""
    _, cliente, factory, _ = ambiente
    # Saída semântica do CKEditor: itálico usa <i>, negrito usa <strong>.
    html = ('<h2>Título</h2><h3>Subtítulo</h3>'
            '<p>Texto com <strong>negrito interno</strong>, <i>itálico interno</i> '
            'e <i><strong>ambos</strong></i>, com <u>sublinhado interno</u>.</p>'
            '<ul><li data-list-item-id="interno">Primeiro</li><li>Segundo</li></ul>'
            '<p>Outro parágrafo.</p><figure class="table"><table><thead><tr>'
            '<th>Elemento</th><th>Característica</th><th>Exemplo</th></tr></thead>'
            '<tbody><tr><td>A</td><td>B</td><td>C</td></tr></tbody></table></figure>')
    esperado = html.replace(' data-list-item-id="interno"', '')
    criado = cliente.post('/materiais', json=texto(conteudo=html, conteudo_formato='html_v1'))
    assert criado.status_code == 200, criado.text
    identificador = criado.json()['id']
    assert criado.json()['conteudo'] == esperado
    for _ in range(2):
        reaberto = next(item for item in cliente.get('/aulas/1/materiais').json()
                        if item['id'] == identificador)
        assert reaberto['conteudo'] == esperado
        assert reaberto['conteudo_formato'] == 'html_v1'
        with factory() as db:
            assert db.get(m.Material, identificador).conteudo == esperado
        salvo = cliente.put(f'/materiais/{identificador}', json=texto(
            conteudo=reaberto['conteudo'], conteudo_formato='html_v1'))
        assert salvo.status_code == 200, salvo.text
        assert salvo.json()['conteudo'] == esperado


def test_sanitizador_nao_libera_css_ou_classes_para_preservar_destaques():
    html = ('<p><strong onclick="alert(1)" class="font-bold">Seguro</strong>'
            '<i style="background:url(javascript:alert(1))">Itálico</i>'
            '<span class="italic" style="position:fixed;color:red" onmouseover="x()">Sem CSS</span></p>')
    assert preparar_conteudo(html, 'html_v1') == (
        '<p><strong>Seguro</strong><i>Itálico</i>Sem CSS</p>')
