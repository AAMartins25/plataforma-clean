"""Leitura defensiva de pacotes de curso. Não grava dados nem envia imagens."""
from dataclasses import dataclass
from io import BytesIO
import json
import hashlib
import re
from uuid import UUID
from pathlib import PurePosixPath
import stat
import zipfile
import logging
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from app.imagens_arquivos import EXTENSOES, MAX_ARQUIVO, caminho_pacote, validar_imagem
from app.importacao_esquemas import ImportacaoCursoV1

# Limites iniciais conservadores; sujeitos a homologação de carga antes de uso.
MAX_ZIP = 64 * 1024 * 1024
MAX_DESCOMPACTADO = 128 * 1024 * 1024
MAX_JSON = 40 * 1024 * 1024
MAX_IMAGENS_PACOTE = 100
MAX_ENTRADAS = MAX_IMAGENS_PACOTE + 2


@dataclass(frozen=True)
class PacoteCurso:
    documento: dict
    imagens: dict


# Sintaxe deliberadamente restrita, sem URL codificada ou título opcional.
REFERENCIA = re.compile(r'!\[([^\]\n]+)\]\((imagens/[A-Za-z0-9_-]+\.(?:png|jpg|jpeg|webp))\)', re.I)
IMAGEM_BRUTA = re.compile(r'!\s*\[|<\s*img\b|&(?:lt|#0*60|#x0*3c);\s*img\b', re.I)


def mapa_pacote(pacote, bytes_zip):
    digest = hashlib.sha256(bytes_zip).hexdigest()
    # IDs temporários são apenas marcadores de conversão; não são armazenados.
    return {nome: str(UUID(bytes=hashlib.sha256((digest + ':' + img.sha256).encode()).digest()[:16], version=4))
            for nome, img in pacote.imagens.items()}


def validar_referencias_texto(original, convertido, mapa, caminho):
    from app.imagens import referencias
    from html.parser import HTMLParser

    refs = list(REFERENCIA.finditer(original))
    resto = REFERENCIA.sub('', original)
    if IMAGEM_BRUTA.search(resto):
        _recusar(f'{caminho}: use imagens locais na sintaxe ![descrição](imagens/arquivo.png).')
    esperadas = []
    for ref in refs:
        if not ref.group(1).strip() or ref.group(2) not in mapa:
            _recusar(f'{caminho}: imagem ausente ou descrição vazia: {ref.group(2)}')
        esperadas.append(mapa[ref.group(2)])
    class Imagens(HTMLParser):
        def __init__(self):
            super().__init__()
            self.ids = []
        def handle_starttag(self, tag, attrs):
            if tag == 'img':
                from app.imagens import PADRAO_SRC
                atributos = dict(attrs)
                match = PADRAO_SRC.fullmatch(atributos.get('src', ''))
                if not match or not atributos.get('alt', '').strip():
                    _recusar(f'{caminho}: referência convertida inválida.')
                self.ids.append(match.group(1))
    parser = Imagens()
    parser.feed(convertido)
    referencias(convertido)  # impõe também o limite por campo
    if parser.ids != esperadas:
        _recusar(f'{caminho}: imagens divergentes após conversão.')
    return {r.group(2) for r in refs}


def _recusar(mensagem):
    raise HTTPException(422, mensagem)


def _objeto_unico(pares):
    resultado = {}
    for chave, valor in pares:
        if chave in resultado:
            _recusar('O JSON contém chaves repetidas.')
        resultado[chave] = valor
    return resultado


def _ler_limitado(pacote, item, limite):
    # Não confiar somente no tamanho declarado na tabela central do ZIP.
    with pacote.open(item) as arquivo:
        dados = arquivo.read(limite + 1)
        if len(dados) > limite or arquivo.read(1):
            _recusar('Uma entrada excede o limite de descompactação.')
        return dados


def ler_pacote(dados: bytes) -> PacoteCurso:
    if not dados or len(dados) > MAX_ZIP:
        _recusar('O ZIP está vazio ou excede o limite permitido.')
    try:
        with zipfile.ZipFile(BytesIO(dados)) as pacote:
            itens = pacote.infolist()
            if len(itens) > MAX_ENTRADAS:
                _recusar('O ZIP contém entradas demais.')
            nomes, imagens, documento = set(), {}, None
            total = 0
            total_normalizado = 0
            for item in itens:
                if item.orig_filename != item.filename:
                    _recusar('O ZIP contém nome truncado ou inválido.')
                nome = caminho_pacote(item.filename.rstrip('/') if item.is_dir() else item.filename)
                if nome.casefold() in nomes:
                    _recusar('O ZIP contém nomes repetidos ou ambíguos.')
                nomes.add(nome.casefold())
                tipo = stat.S_IFMT(item.external_attr >> 16)
                if tipo not in {0, stat.S_IFREG, stat.S_IFDIR} or item.flag_bits & 1:
                    _recusar('Links, entradas especiais e arquivos criptografados não são aceitos.')
                if item.is_dir():
                    if nome != 'imagens':
                        _recusar('Use somente a pasta imagens/.')
                    continue
                total += item.file_size
                if (total > MAX_DESCOMPACTADO or
                        item.file_size > max(1, item.compress_size) * 200):
                    _recusar('O ZIP excede os limites de descompactação.')
                if nome == 'curso.json':
                    bruto = _ler_limitado(pacote, item, MAX_JSON)
                    documento = json.loads(bruto.decode('utf-8-sig'), object_pairs_hook=_objeto_unico,
                                           parse_constant=lambda _: _recusar('Número JSON inválido.'))
                    try:
                        ImportacaoCursoV1.model_validate(documento)
                    except ValidationError as erro:
                        raise HTTPException(422, [{'local': '.'.join(map(str, e['loc'])), 'mensagem': e['msg']}
                                                  for e in erro.errors(include_url=False, include_context=False, include_input=False)]) from erro
                elif (len(PurePosixPath(nome).parts) == 2 and nome.startswith('imagens/')
                      and PurePosixPath(nome).suffix.lower() in EXTENSOES):
                    if len(imagens) >= MAX_IMAGENS_PACOTE:
                        _recusar('O pacote contém imagens demais.')
                    imagens[nome] = validar_imagem(_ler_limitado(pacote, item, MAX_ARQUIVO))
                    total_normalizado += len(imagens[nome].dados)
                    if total_normalizado > MAX_DESCOMPACTADO:
                        _recusar('O total das imagens normalizadas excede o limite.')
                else:
                    _recusar('Use curso.json e imagens PNG, JPEG ou WebP em imagens/.')
            if documento is None:
                _recusar('O ZIP precisa conter curso.json na raiz.')
            return PacoteCurso(documento, imagens)
    except HTTPException:
        raise
    except (zipfile.BadZipFile, UnicodeError, json.JSONDecodeError, RecursionError,
            RuntimeError, NotImplementedError, OSError, EOFError, ValueError) as erro:
        raise HTTPException(422, 'ZIP ou JSON inválido, danificado ou não suportado.') from erro


def importar_pacote(db, usuario_id, chave, bruto, convertido, storage):
    from app import models as m
    from app.imagens_manutencao import travar_objeto
    from app.importacao_cursos import importar

    pacote = ler_pacote(bruto)
    mapa = mapa_pacote(pacote, bruto)
    enviados = []
    estado = {'commit_iniciado': False}
    conexao = db.connection()

    def enviar(sessao):
        # Um único objeto por hash normalizado, apenas dentro desta importação.
        ids = {}
        for nome, imagem in pacote.imagens.items():
            marcador = mapa[nome]
            if marcador in ids:
                continue
            id = str(uuid4())
            chave_objeto = id + '.' + imagem.extensao
            travar_objeto(sessao, chave_objeto)
            # Inclui envios sem confirmação: uma falha de rede pode ocorrer
            # depois que o Storage gravou o objeto.
            enviados.append(chave_objeto)
            storage.enviar(chave_objeto, imagem.dados, imagem.mime)
            sessao.add(m.ImagemTeoria(id=id, chave=chave_objeto, autor_id=usuario_id,
                mime=imagem.mime, tamanho=len(imagem.dados), largura=imagem.largura,
                altura=imagem.altura, sha256=imagem.sha256))
            ids[marcador] = id
        sessao.flush()
        return ids

    def iniciando_commit():
        estado['commit_iniciado'] = True

    try:
        return importar(db, usuario_id, chave, pacote.documento, convertido, mapa=mapa,
                        digest_pacote=hashlib.sha256(bruto).hexdigest(),
                        preparar_imagens=enviar, antes_commit=iniciando_commit)
    except Exception:
        confirmavel = (not estado['commit_iniciado'] and not conexao.closed
                       and not conexao.invalidated and conexao.in_transaction())
        try:
            db.rollback()
        except Exception:
            confirmavel = False
        if confirmavel:
            for objeto in enviados:
                try:
                    storage.excluir(objeto)
                except Exception:
                    logging.getLogger(__name__).warning('Objeto de importação aguarda reconciliação: %s', objeto)
        raise
