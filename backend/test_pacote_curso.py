from io import BytesIO
import json
import stat
import zipfile

from fastapi import HTTPException
from PIL import Image
import pytest

from app.pacote_curso import ler_pacote, mapa_pacote, importar_pacote, validar_referencias_texto
from app import models as m
from test_importacao_cursos import contexto, documento


def curso():
    return {'versao': 1, 'curso': {'nome': 'Curso', 'banca': 'Banca', 'cargo': 'Cargo',
            'orgao': 'Órgão', 'ano': 2026, 'uf': 'SP',
            'descricao_publica_markdown': 'Descrição'}, 'disciplinas': []}


def imagem():
    saida = BytesIO()
    Image.new('RGB', (10, 10), 'red').save(saida, 'PNG')
    return saida.getvalue()


def zipar(itens):
    saida = BytesIO()
    with zipfile.ZipFile(saida, 'w', zipfile.ZIP_DEFLATED) as pacote:
        for nome, dados in itens:
            pacote.writestr(nome, dados)
    return saida.getvalue()


def test_ler_curso_e_mais_de_vinte_imagens():
    itens = [('curso.json', json.dumps(curso()))]
    itens += [(f'imagens/{n}.png', imagem()) for n in range(21)]
    pacote = ler_pacote(zipar(itens))
    assert pacote.documento == curso()
    assert len(pacote.imagens) == 21
    assert all(i.mime == 'image/png' for i in pacote.imagens.values())


def test_exemplo_documentado_e_valido():
    from pathlib import Path
    from app.importacao_cursos import preparar
    exemplo = Path(__file__).resolve().parent.parent / 'docs/importacao-cursos/exemplo-zip'
    bruto = zipar([('curso.json', (exemplo / 'curso.json').read_bytes()),
                   ('imagens/quadro.png', (exemplo / 'imagens/quadro.png').read_bytes())])
    pacote = ler_pacote(bruto)
    mapa = mapa_pacote(pacote, bruto)
    def converter(valor):
        if isinstance(valor, dict): return {k: converter(v) for k, v in valor.items()}
        if isinstance(valor, list): return [converter(v) for v in valor]
        if isinstance(valor, str):
            return valor.replace('![Quadro ilustrativo](imagens/quadro.png)',
                                 f'<img src="/midias/imagens/{mapa["imagens/quadro.png"]}" alt="Quadro ilustrativo">')
        return valor
    preparar(pacote.documento, converter(pacote.documento), mapa)


@pytest.mark.parametrize('itens', [
    [('curso.json', '{}')],
    [('imagens/a.png', b'invalido')],
    [('curso.json', '{"versao":1,"versao":1}')],
    [('curso.json', json.dumps(curso())), ('../a.png', b'x')],
    [('curso.json', json.dumps(curso())), ('imagens/a.png', b'nao e imagem')],
    [('curso.json', json.dumps(curso())), ('imagens/a.png', imagem()), ('imagens/A.png', imagem())],
    [('curso.json', json.dumps(curso())), ('imagens/a.svg', b'<svg/>')],
    [('curso.json', json.dumps(curso())), ('outro.txt', b'x')],
])
def test_recusa_pacotes_invalidos(itens):
    with pytest.raises(HTTPException):
        ler_pacote(zipar(itens))


def test_recusa_link_simbolico():
    link = zipfile.ZipInfo('imagens/link.png')
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(HTTPException):
        ler_pacote(zipar([('curso.json', json.dumps(curso())), (link, 'destino')]))


def test_recusa_taxa_excessiva_de_descompactacao():
    pacote = zipar([('curso.json', json.dumps(curso())), ('imagens/bomba.png', b'A' * 1_000_000)])
    with pytest.raises(HTTPException) as erro:
        ler_pacote(pacote)
    assert 'descompactação' in str(erro.value.detail)


def test_recusa_mais_de_cem_imagens():
    pacote = zipar([('curso.json', json.dumps(curso()))] + [(f'imagens/{i}.png', imagem()) for i in range(101)])
    with pytest.raises(HTTPException):
        ler_pacote(pacote)


@pytest.mark.parametrize('original,html', [
    ('![x](imagens/ausente.png)', '<p>Texto</p>'),
    ('![x](https://exemplo.com/a.png)', '<p>Texto</p>'),
    ('<img src="x">', '<p>Texto</p>'),
    ('![x](imagens/a.png)', '<p>Texto</p>'),
    ('Texto', '<img src="/midias/imagens/12345678-1234-4234-8234-123456789abc" alt="x">'),
    ('![x](imagens/a.png)', '<img src="/midias/imagens/12345678-1234-4234-8234-123456789abc" alt="">'),
])
def test_referencias_invalidas_sao_rejeitadas(original, html):
    with pytest.raises(HTTPException):
        validar_referencias_texto(original, html, {'imagens/a.png':'12345678-1234-4234-8234-123456789abc'}, 'resumo')


def test_ordem_das_imagens_nao_pode_mudar():
    a, b = '12345678-1234-4234-8234-123456789abc', '22345678-1234-4234-8234-123456789abc'
    original = '![a](imagens/a.png) ![b](imagens/b.png)'
    html = f'<img src="/midias/imagens/{b}" alt="b"><img src="/midias/imagens/{a}" alt="a">'
    with pytest.raises(HTTPException):
        validar_referencias_texto(original, html, {'imagens/a.png':a, 'imagens/b.png':b}, 'resumo')


class Storage:
    def __init__(self, falhar=False):
        self.objetos = {}
        self.falhar = falhar
    def enviar(self, chave, dados, mime):
        self.objetos[chave] = dados
        if self.falhar:
            raise RuntimeError('falha após upload')
    def excluir(self, chave):
        self.objetos.pop(chave, None)
    def assinar(self, chave):
        assert chave in self.objetos
        return 'https://imagens.example/' + chave


def preparar_fluxo(documento):
    import copy
    d = copy.deepcopy(documento)
    a = d['disciplinas'][0]['assuntos'][0]
    a['resumos'][0]['texto_markdown'] = 'Texto ![figura](imagens/a.png)'
    a['baterias'][0]['questoes'][0]['enunciado_markdown'] = 'Enunciado ![figura](imagens/a.png)'
    a['baterias'][0]['questoes'][0]['alternativas']['A'] = 'Alternativa ![figura](imagens/a.png)'
    a['baterias'][0]['questoes'][0]['comentario_markdown'] = 'Comentário ![figura](imagens/a.png)'
    bruto = zipar([('curso.json', json.dumps(d)), ('imagens/a.png', imagem())])
    mapa = mapa_pacote(ler_pacote(bruto), bruto)
    convertido = copy.deepcopy(d)
    def converter(valor):
        if isinstance(valor, dict):
            return {k: converter(v) for k, v in valor.items()}
        if isinstance(valor, list):
            return [converter(v) for v in valor]
        if isinstance(valor, str):
            return valor.replace('![figura](imagens/a.png)', f'<img src="/midias/imagens/{mapa["imagens/a.png"]}" alt="figura">')
        return valor
    return bruto, converter(convertido)


def criar_tabelas_imagens(db):
    for tabela in (m.ImagemTeoria, m.ImagemTeoriaMaterial, m.ImagemQuestao):
        tabela.__table__.create(db.bind, checkfirst=True)


def test_importa_vinculos_e_repeticao(contexto, documento):
    db = contexto
    criar_tabelas_imagens(db)
    bruto, convertido = preparar_fluxo(documento)
    storage = Storage()
    r = importar_pacote(db, 1, '1234567890abcdef', bruto, convertido, storage)
    assert not r['repetida'] and len(storage.objetos) == 1
    assert db.query(m.ImagemTeoriaMaterial).count() == 1
    assert db.query(m.ImagemQuestao).count() == 1
    assert importar_pacote(db, 1, '1234567890abcdef', bruto, convertido, storage)['repetida']
    assert len(storage.objetos) == 1


def test_falha_upload_desfaz_importacao(contexto, documento):
    db = contexto
    criar_tabelas_imagens(db)
    bruto, convertido = preparar_fluxo(documento)
    storage = Storage(falhar=True)
    with pytest.raises(RuntimeError):
        importar_pacote(db, 1, '1234567890abcdef', bruto, convertido, storage)
    assert not storage.objetos
    assert db.query(m.ImagemTeoria).count() == 0
    assert db.query(m.Curso).count() == 1


def test_imagem_alterada_na_conversao_e_recusada(contexto, documento):
    db = contexto
    criar_tabelas_imagens(db)
    bruto, convertido = preparar_fluxo(documento)
    convertido['disciplinas'][0]['assuntos'][0]['resumos'][0]['texto_markdown'] = 'Texto sem imagem'
    storage = Storage()
    with pytest.raises(HTTPException):
        importar_pacote(db, 1, '1234567890abcdef', bruto, convertido, storage)
    assert not storage.objetos


def test_resposta_perdida_apos_commit_preserva_e_recupera(contexto, documento, monkeypatch):
    db = contexto
    criar_tabelas_imagens(db)
    bruto, convertido = preparar_fluxo(documento)
    storage = Storage()
    commit = db.commit
    def perder_resposta():
        commit()
        raise RuntimeError('resposta perdida')
    monkeypatch.setattr(db, 'commit', perder_resposta)
    with pytest.raises(RuntimeError):
        importar_pacote(db, 1, '1234567890abcdef', bruto, convertido, storage)
    assert len(storage.objetos) == 1
    monkeypatch.setattr(db, 'commit', commit)
    # A serialização do editor pode diferir entre tentativas; a identidade é o ZIP.
    convertido['disciplinas'][0]['assuntos'][0]['resumos'][0]['texto_markdown'] += '<p>nova serialização</p>'
    assert importar_pacote(db, 1, '1234567890abcdef', bruto, convertido, storage)['repetida']
    assert len(storage.objetos) == 1


def test_copiar_assunto_importado_preserva_vinculos(contexto, documento):
    from app.copias import copiar_assunto_conteudo
    db = contexto
    criar_tabelas_imagens(db)
    for tabela in (m.Video, m.Comentario, m.QuestaoPraticaAssunto, m.QuestaoPraticaAlternativa):
        tabela.__table__.create(db.bind, checkfirst=True)
    bruto, convertido = preparar_fluxo(documento)
    storage = Storage()
    importar_pacote(db, 1, '1234567890abcdef', bruto, convertido, storage)
    origem = db.query(m.CursoAssuntoProprio).one()
    db.add(m.Curso(id=55, nome='Destino'))
    destino = m.CursoDisciplinaPropria(curso_id=55, nome='Disciplina destino')
    db.add(destino); db.flush()
    copiar_assunto_conteudo(db, origem, destino.id)
    db.flush()
    assert db.query(m.ImagemTeoria).count() == 1
    assert db.query(m.ImagemTeoriaMaterial).count() == 2
    assert db.query(m.ImagemQuestao).count() == 2
    assert len(storage.objetos) == 1


def test_falha_tardia_preserva_objeto_quando_rollback_nao_confirmado(contexto, documento):
    from sqlalchemy import event
    db = contexto
    criar_tabelas_imagens(db)
    bruto, convertido = preparar_fluxo(documento)
    storage = Storage()
    def falhar(mapper, connection, target):
        raise RuntimeError('falha ao gravar alternativa')
    event.listen(m.Alternativa, 'before_insert', falhar)
    try:
        with pytest.raises(RuntimeError):
            importar_pacote(db, 1, '1234567890abcdef', bruto, convertido, storage)
    finally:
        event.remove(m.Alternativa, 'before_insert', falhar)
    # A falha do flush pode encerrar a transação antes de ser possível
    # comprovar o rollback; neste caso a reconciliação remove o órfão.
    assert len(storage.objetos) == 1
    assert db.query(m.Curso).count() == 1
    assert db.query(m.ImagemTeoria).count() == 0


def test_cem_imagens_distribuidas_pelo_curso(contexto):
    import copy
    import time
    db = contexto
    criar_tabelas_imagens(db)
    d = curso()
    d['curso']['nome'] = 'Curso com cem imagens'
    d['disciplinas'] = [{'nome': 'Disciplina', 'assuntos': []}]
    itens = []
    for grupo in range(5):
        resumos = []
        for numero in range(grupo * 20, grupo * 20 + 20):
            saida = BytesIO()
            Image.new('RGB', (32, 32), (numero, 20, 40)).save(saida, 'PNG')
            nome = f'imagens/f{numero}.png'
            itens.append((nome, saida.getvalue()))
            resumos.append({'titulo': f'Resumo {numero}', 'texto_markdown': f'Texto ![figura]({nome})'})
        d['disciplinas'][0]['assuntos'].append({'nome': f'Assunto {grupo}', 'aula_titulo': 'Aula', 'resumos': resumos, 'baterias': []})
    bruto = zipar([('curso.json', json.dumps(d))] + itens)
    mapa = mapa_pacote(ler_pacote(bruto), bruto)
    convertido = copy.deepcopy(d)
    for assunto in convertido['disciplinas'][0]['assuntos']:
        for resumo in assunto['resumos']:
            for nome, id in mapa.items():
                resumo['texto_markdown'] = resumo['texto_markdown'].replace(f'![figura]({nome})', f'<img src="/midias/imagens/{id}" alt="figura">')
    storage = Storage()
    inicio = time.monotonic()
    resultado = importar_pacote(db, 1, '1234567890abcdef', bruto, convertido, storage)
    duracao = time.monotonic() - inicio
    assert not resultado['repetida']
    assert len(storage.objetos) == 100
    assert db.query(m.ImagemTeoriaMaterial).count() == 100
    print(f'importação de 100 imagens com Storage em memória: {duracao:.2f}s')


def test_carga_imagens_fotograficas(contexto):
    import copy
    import random
    import time
    db = contexto
    criar_tabelas_imagens(db)
    d = curso()
    d['curso']['nome'] = 'Curso de carga'
    d['disciplinas'] = [{'nome': 'Disciplina', 'assuntos': []}]
    arquivos = []
    gerador = random.Random(47)
    for grupo in range(2):
        resumos = []
        for numero in range(grupo * 15, grupo * 15 + 15):
            foto = Image.frombytes('RGB', (800, 600), gerador.randbytes(800 * 600 * 3))
            buffer = BytesIO()
            foto.save(buffer, 'JPEG', quality=75)
            nome = f'imagens/f{numero}.jpg'
            arquivos.append((nome, buffer.getvalue()))
            resumos.append({'titulo': f'Resumo {numero}', 'texto_markdown': f'Texto ![figura]({nome})'})
        d['disciplinas'][0]['assuntos'].append({'nome': f'Assunto {grupo}', 'aula_titulo': 'Aula', 'resumos': resumos, 'baterias': []})
    bruto = zipar([('curso.json', json.dumps(d))] + arquivos)
    inicio = time.monotonic()
    mapa = mapa_pacote(ler_pacote(bruto), bruto)
    convertido = copy.deepcopy(d)
    for assunto in convertido['disciplinas'][0]['assuntos']:
        for resumo in assunto['resumos']:
            for nome, id in mapa.items():
                resumo['texto_markdown'] = resumo['texto_markdown'].replace(f'![figura]({nome})', f'<img src="/midias/imagens/{id}" alt="figura">')
    storage = Storage()
    importar_pacote(db, 1, 'cargarepresentativa1234', bruto, convertido, storage)
    duracao = time.monotonic() - inicio
    assert len(storage.objetos) == 30
    assert db.query(m.ImagemTeoriaMaterial).count() == 30
    print(f'ZIP {len(bruto)/1024/1024:.1f} MiB, 30 JPEG 800x600, validação e importação em memória: {duracao:.2f}s')


def test_zip_com_uf_nacional_mantem_contrato_v1():
    dados = curso()
    dados['curso']['uf'] = 'NACIONAL'
    pacote = ler_pacote(zipar([('curso.json', json.dumps(dados))]))
    from app.importacao_cursos import preparar
    assert preparar(pacote.documento, pacote.documento, mapa={})['curso']['uf'] == 'NACIONAL'


def test_importacao_zip_nacional_com_imagem_persiste(contexto, documento):
    dados = dict(documento, curso=dict(documento['curso'], uf='NACIONAL'))
    criar_tabelas_imagens(contexto)
    bruto, convertido = preparar_fluxo(dados)
    resultado = importar_pacote(contexto, 1, 'nacionalzip123456', bruto, convertido, Storage())
    contexto.expire_all()
    assert contexto.get(m.Curso, resultado['curso_id']).uf == 'NACIONAL'
    assert contexto.query(m.ImagemTeoriaMaterial).count() == 1
    assert contexto.query(m.ImagemQuestao).count() == 1
