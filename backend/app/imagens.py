"""Imagens privadas de teoria: referências estáveis e autorização pela aplicação."""
from datetime import datetime
from html.parser import HTMLParser
import logging
import re
from uuid import uuid4

from fastapi import Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, event, exists, select, update

from app import models as m
from app.imagens_arquivos import MAX_ARQUIVO, MAX_IMAGENS, MAX_LOTE, baixar_imagem, ler_zip, validar_imagem
from app.imagens_storage import obter_storage_imagens
from app.imagens_manutencao import limpar_pendentes, travar_objeto

PADRAO_SRC = re.compile(r"^/midias/imagens/([0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})$")
logger = logging.getLogger(__name__)


class _Referencias(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.quantidade = 0

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            self.quantidade += 1
            if self.quantidade > MAX_IMAGENS:
                raise HTTPException(422, "Cada teoria pode conter até 20 imagens.")
            src = dict(attrs).get("src", "")
            match = PADRAO_SRC.fullmatch(src)
            if not match:
                raise HTTPException(422, "Há imagem sem referência permanente válida. Importe os arquivos antes de salvar.")
            self.ids.add(match[1])
            if len(self.ids) > MAX_IMAGENS:
                raise HTTPException(422, "Cada teoria pode conter até 20 imagens diferentes.")


def referencias(html):
    if not html or "<img" not in html.lower():
        return set()
    parser = _Referencias()
    parser.feed(html)
    return parser.ids


def sincronizar_referencias(db, material, autor_id=None, anterior=""):
    ids = referencias(material.conteudo) if material.conteudo_formato == "html_v1" else set()
    antigos = referencias(anterior)
    if not ids and not antigos:
        return
    db.flush()
    _sincronizar(db, ids, antigos, m.ImagemTeoriaMaterial, "material_id", material.id, autor_id)


def sincronizar_referencias_questao(db, questao, autor_id=None, antigos=None):
    from app.questoes_html import referencias_questao
    ids = referencias_questao(questao)
    if antigos is None:
        # Textos legados não precisam consultar tabelas novas para serem salvos.
        if not ids:
            return
        antigos = {r.imagem_id for r in db.query(m.ImagemQuestao).filter_by(questao_id=questao.id)}
    if ids or antigos:
        _sincronizar(db, ids, antigos, m.ImagemQuestao, "questao_id", questao.id, autor_id)


def _sincronizar(db, ids, antigos, modelo, campo, identificador, autor_id):
    # Mesmo lock usado pela limpeza. Cópias compartilham arquivos imutáveis.
    imagens = (db.query(m.ImagemTeoria).filter(m.ImagemTeoria.id.in_(ids | antigos))
               .order_by(m.ImagemTeoria.id).with_for_update().all())
    por_id = {i.id: i for i in imagens}
    for id in ids:
        imagem = por_id.get(id)
        vinculada = db.query(m.ImagemTeoriaMaterial).filter_by(imagem_id=id).first() is not None or db.query(m.ImagemQuestao).filter_by(imagem_id=id).first() is not None
        if imagem is None or (not vinculada and imagem.autor_id != autor_id):
            raise HTTPException(422, "Uma imagem não existe ou não está disponível para este administrador.")
    db.flush()
    db.execute(delete(modelo).where(getattr(modelo, campo) == identificador))
    for id in ids:
        db.add(modelo(**{campo: identificador, "imagem_id": id}))
    for imagem in imagens:
        imagem.ultima_atividade = datetime.utcnow()


@event.listens_for(m.Material, "before_delete")
def _carencia_apos_exclusao(mapper, conexao, material):
    ids = referencias(material.conteudo) if material.conteudo_formato == "html_v1" else set()
    if ids:
        conexao.execute(select(m.ImagemTeoria.id).where(m.ImagemTeoria.id.in_(ids))
                        .order_by(m.ImagemTeoria.id).with_for_update()).all()
        conexao.execute(update(m.ImagemTeoria).where(m.ImagemTeoria.id.in_(ids))
                        .values(ultima_atividade=datetime.utcnow()))


def registrar_lote(db, usuario, imagens, storage):
    if not imagens or len(imagens) > MAX_IMAGENS:
        raise HTTPException(422, "Selecione entre 1 e 20 imagens.")
    if sum(len(i.dados) for i in imagens.values()) > MAX_LOTE:
        raise HTTPException(422, "O lote normalizado excede 25 MB.")
    # Limitar também armazenamento pendente por administrador, inclusive falhas
    # na interface. A limpeza só remove objetos não referenciados após carência.
    db.query(m.Usuario.id).filter(m.Usuario.id == usuario.id).with_for_update().one()
    pendentes = (db.query(m.ImagemTeoria).filter(m.ImagemTeoria.autor_id == usuario.id,
                 ~exists().where(m.ImagemTeoriaMaterial.imagem_id == m.ImagemTeoria.id),
                 ~exists().where(m.ImagemQuestao.imagem_id == m.ImagemTeoria.id)).count())
    if pendentes + len(imagens) > 100:
        raise HTTPException(429, "Há muitos uploads pendentes. Salve os materiais ou solicite a limpeza dos pendentes antigos.")
    enviados, resultados = [], []
    conexao = db.connection()
    commit_iniciado = False
    try:
        for nome, validada in imagens.items():
            id = str(uuid4())
            chave = id + "." + validada.extensao
            travar_objeto(db, chave)
            storage.enviar(chave, validada.dados, validada.mime)
            enviados.append(chave)
            imagem = m.ImagemTeoria(id=id, chave=chave, autor_id=usuario.id,
                mime=validada.mime, tamanho=len(validada.dados), largura=validada.largura,
                altura=validada.altura, sha256=validada.sha256)
            db.add(imagem)
            resultados.append(dict(id=id, nome=nome, src="/midias/imagens/" + id,
                                   largura=validada.largura, altura=validada.altura))
        # Uma falha a partir daqui pode significar commit persistido sem ACK.
        commit_iniciado = True
        db.commit()
        return {"imagens": resultados}
    except Exception:
        # Session.rollback() pode ser apenas local após perder a conexão.
        # Só compensar antes do commit, com transação conectada e rollback bem-sucedido.
        rollback_confirmavel = (not commit_iniciado and not conexao.closed
                                and not conexao.invalidated and conexao.in_transaction())
        rollback_confirmado = False
        try:
            db.rollback()
            rollback_confirmado = rollback_confirmavel
        except Exception:
            logger.warning("Rollback de imagens não confirmado; objetos preservados.")
        if rollback_confirmado:
            for chave in enviados:
                try:
                    storage.excluir(chave)
                except Exception:
                    logger.warning("Reconciliar objeto de imagem após falha de compensação: %s", chave)
        else:
            logger.warning("Resultado transacional de imagens não confirmado; objetos preservados.")
        raise


def limpar_nao_referenciadas(db, storage, agora=None):
    """Entrada compatível para manutenção e testes anteriores."""
    return limpar_pendentes(db, storage, agora)


class PedidoAssinaturas(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=MAX_IMAGENS)


class PedidoRemotas(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=MAX_IMAGENS)


def assinar(db, ids, storage):
    registros = db.query(m.ImagemTeoria).filter(m.ImagemTeoria.id.in_(set(ids))).all()
    if len(registros) != len(set(ids)):
        raise HTTPException(404, "Imagem não encontrada.")
    return {"imagens": [{"id": i.id, "src": "/midias/imagens/" + i.id,
             "url": storage.assinar(i.chave)} for i in registros], "validade_segundos": 900}


def ler_upload(arquivo, limite):
    dados = arquivo.file.read(limite + 1)
    if len(dados) > limite:
        raise HTTPException(413, "O arquivo excede o tamanho permitido.")
    return dados


def registrar_rotas(app, get_db, get_usuario, exigir_admin, listar_materiais, listar_questoes):
    app.add_middleware(LimiteImagensMiddleware)
    @app.post("/admin/imagens/arquivos")
    def upload(arquivos: list[UploadFile] = File(...), db=Depends(get_db),
                     usuario=Depends(exigir_admin), storage=Depends(obter_storage_imagens)):
        if not 1 <= len(arquivos) <= MAX_IMAGENS:
            raise HTTPException(422, "Selecione entre 1 e 20 imagens.")
        imagens, total = {}, 0
        for n, arquivo in enumerate(arquivos):
            dados = ler_upload(arquivo, MAX_ARQUIVO)
            total += len(dados)
            if total > MAX_LOTE:
                raise HTTPException(413, "O lote excede 25 MB.")
            # Índice fornecido pelo cliente não é usado como caminho no Storage.
            imagens[str(n)] = validar_imagem(dados)
        return registrar_lote(db, usuario, imagens, storage)

    @app.post("/admin/imagens/zip")
    def pacote(arquivo: UploadFile = File(...), db=Depends(get_db),
                     usuario=Depends(exigir_admin), storage=Depends(obter_storage_imagens)):
        markdown, imagens = ler_zip(ler_upload(arquivo, MAX_LOTE))
        resultado = registrar_lote(db, usuario, imagens, storage) if imagens else {"imagens": []}
        return {"markdown": markdown, **resultado}

    @app.post("/admin/imagens/remotas")
    def remotas(dados: PedidoRemotas, db=Depends(get_db), usuario=Depends(exigir_admin),
                storage=Depends(obter_storage_imagens)):
        imagens = {}
        for n, url in enumerate(dict.fromkeys(dados.urls)):
            try:
                imagens[url] = baixar_imagem(url)
            except HTTPException as erro:
                raise HTTPException(erro.status_code, f"Imagem remota {n + 1}: {erro.detail}") from None
            if sum(len(i.dados) for i in imagens.values()) > MAX_LOTE:
                raise HTTPException(413, "O lote excede 25 MB.")
        return registrar_lote(db, usuario, imagens, storage)

    @app.post("/admin/imagens/assinaturas")
    def assinaturas_admin(dados: PedidoAssinaturas, db=Depends(get_db), usuario=Depends(exigir_admin),
                          storage=Depends(obter_storage_imagens)):
        for id in sorted(set(dados.ids)):
            imagem = db.query(m.ImagemTeoria).filter_by(id=id).with_for_update().first()
            vinculada = (db.query(m.ImagemTeoriaMaterial).filter_by(imagem_id=id).first()
                         or db.query(m.ImagemQuestao).filter_by(imagem_id=id).first())
            if not imagem or (imagem.autor_id != usuario.id and not vinculada):
                raise HTTPException(404, "Imagem não encontrada.")
            if not vinculada:
                imagem.ultima_atividade = datetime.utcnow()
        # A renovação periódica da prévia mantém rascunhos abertos fora da
        # carência; a limpeza disputa o mesmo lock antes de decidir removê-los.
        db.commit()
        return assinar(db, dados.ids, storage)


    @app.post("/aulas/{aula_id}/imagens/assinaturas")
    def assinaturas_aluno(aula_id: int, dados: PedidoAssinaturas,
                          contratacao_id: int | None = None, demonstracao_id: int | None = None,
                          db=Depends(get_db), usuario=Depends(get_usuario), storage=Depends(obter_storage_imagens)):
        materiais = listar_materiais(aula_id, contratacao_id, demonstracao_id, db, usuario)
        permitidas = set()
        for material in materiais:
            if material.get("conteudo_formato") == "html_v1":
                permitidas.update(referencias(material.get("conteudo")))
        if not set(dados.ids).issubset(permitidas):
            raise HTTPException(403, "A imagem não pertence a um material disponível neste contexto.")
        return assinar(db, dados.ids, storage)

    @app.post("/baterias/{bateria_id}/imagens/assinaturas")
    def assinaturas_questoes(bateria_id: int, dados: PedidoAssinaturas,
                            contratacao_id: int | None = None, demonstracao_id: int | None = None,
                            db=Depends(get_db), usuario=Depends(get_usuario), storage=Depends(obter_storage_imagens)):
        questoes = listar_questoes(bateria_id, contratacao_id, demonstracao_id, db, usuario)
        permitidas = set()
        for questao in questoes:
            for campo in ("enunciado", "comentario"):
                if questao.get(campo + "_formato") == "html_v1":
                    permitidas.update(referencias(questao.get(campo)))
            for alternativa in questao.get("alternativas", []):
                if alternativa.get("texto_formato") == "html_v1":
                    permitidas.update(referencias(alternativa.get("texto")))
        if not set(dados.ids).issubset(permitidas):
            raise HTTPException(403, "A imagem não pertence a uma questão disponível neste contexto.")
        return assinar(db, dados.ids, storage)


class _ExcessoUpload(HTTPException):
    def __init__(self):
        super().__init__(413, "O envio excede o tamanho permitido.")


class LimiteImagensMiddleware:
    """Limita bytes antes do parser multipart (inclusive transferências chunked)."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "POST" or not (
            scope.get("path", "").startswith("/admin/imagens/")
            or scope.get("path", "").endswith("/imagens/assinaturas")
        ):
            return await self.app(scope, receive, send)
        from starlette.responses import JSONResponse
        tamanho = 0
        limite = MAX_LOTE + 1024 * 1024 if scope["path"].endswith(("/arquivos", "/zip")) else 131072

        async def receber():
            nonlocal tamanho
            msg = await receive()
            tamanho += len(msg.get("body", b""))
            if tamanho > limite:
                raise _ExcessoUpload()
            return msg

        try:
            for chave, valor in scope.get("headers", []):
                if chave.lower() == b"content-length" and (not valor.isdigit() or int(valor) > limite):
                    raise _ExcessoUpload()
            await self.app(scope, receber, send)
        except _ExcessoUpload:
            await JSONResponse({"detail": "O envio excede o tamanho permitido."}, status_code=413)(scope, receive, send)


@event.listens_for(m.Questao, "before_delete")
def _carencia_questao(mapper, conexao, questao):
    ids = list(conexao.execute(select(m.ImagemQuestao.imagem_id).where(m.ImagemQuestao.questao_id == questao.id)).scalars())
    if ids:
        conexao.execute(select(m.ImagemTeoria.id).where(m.ImagemTeoria.id.in_(ids)).order_by(m.ImagemTeoria.id).with_for_update()).all()
        conexao.execute(update(m.ImagemTeoria).where(m.ImagemTeoria.id.in_(ids)).values(ultima_atividade=datetime.utcnow()))
