"""Manutenção de bucket exclusivo da aplicação; sem DDL e sem credenciais em logs."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import logging
import os
import re
from threading import Event, Thread

from sqlalchemy import exists, inspect, text, literal
from app import models as m
from app.imagens_storage import obter_storage_imagens

log = logging.getLogger(__name__)
CHAVE = re.compile(r"^([0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})\.(png|jpg|webp)$")


def numero_lock(chave):
    return int.from_bytes(hashlib.sha256(("resumao-imagens:" + chave).encode()).digest()[:8], "big", signed=True)


def travar_objeto(db, chave, esperar=True):
    """Uploads e reconciliação usam o mesmo lock, inclusive antes do INSERT."""
    if db.get_bind().dialect.name != "postgresql":
        return True  # SQLite é usado somente nos testes sequenciais.
    funcao = "pg_advisory_xact_lock" if esperar else "pg_try_advisory_xact_lock"
    resultado = db.execute(text(f"SELECT {funcao}(:chave)"), {"chave": numero_lock(chave)}).scalar()
    return True if esperar else bool(resultado)


def referenciada(db, id):
    if db.query(m.ImagemTeoriaMaterial).filter_by(imagem_id=id).first():
        return True
    # Defesa adicional contra vínculo ausente/inconsistente: preservar também
    # referências presentes no HTML, inclusive materiais inativos e cópias.
    return db.query(m.Material.id).filter(m.Material.conteudo.contains("/midias/imagens/" + id)).first() is not None


def limpar_pendentes(db, storage, agora=None, limite_lote=100, parar=None):
    limite = (agora or datetime.utcnow()) - timedelta(hours=24)
    imagens = (db.query(m.ImagemTeoria).filter(m.ImagemTeoria.ultima_atividade < limite,
               ~exists().where(m.ImagemTeoriaMaterial.imagem_id == m.ImagemTeoria.id),
               ~exists().where(m.Material.conteudo.contains(literal("/midias/imagens/") + m.ImagemTeoria.id)))
               .order_by(m.ImagemTeoria.id).with_for_update(skip_locked=True).limit(limite_lote).all())
    chaves = []
    for imagem in imagens:
        if referenciada(db, imagem.id):
            continue
        # Remover os metadados primeiro, sob lock. Assim, rollback/falha SQL
        # jamais deixa uma imagem vinculável cujo objeto já tenha sido apagado.
        # Se o DELETE remoto falhar, a reconciliação encontra o órfão no Storage.
        chaves.append(imagem.chave)
        db.delete(imagem)
    db.commit()
    for chave in chaves:
        if parar is not None and parar.is_set():
            break
        try:
            storage.excluir(chave)
        except Exception:
            log.warning("Objeto pendente aguarda reconciliação automática: %s", chave)
    return len(chaves)


def data_storage(valor):
    try:
        data = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        if data.tzinfo is None:
            return None
        return data.astimezone(timezone.utc).replace(tzinfo=None)
    except (AttributeError, ValueError, TypeError, OverflowError):
        return None


def reconciliar_objetos(db, storage, agora=None, offset=0, tamanho_pagina=100, max_paginas=10, parar=None):
    """Só UUIDs gerenciados, antigos, sem metadados nem referência. Cursor limitado."""
    limite = (agora or datetime.utcnow()) - timedelta(hours=24)
    apagados = 0
    for _ in range(max_paginas):
        if parar is not None and parar.is_set():
            break
        objetos = storage.listar(offset, tamanho_pagina)
        removidos_pagina = 0
        for objeto in objetos:
            if parar is not None and parar.is_set():
                break
            if not isinstance(objeto, dict):
                continue
            chave = objeto.get("name", "")
            match = CHAVE.fullmatch(chave) if isinstance(chave, str) else None
            datas = [data_storage(objeto.get(campo)) for campo in ("created_at", "updated_at")]
            if not match or not all(datas) or max(datas) >= limite:
                continue  # Datas ausentes/inválidas nunca justificam exclusão.
            if not travar_objeto(db, chave, esperar=False):
                db.rollback()
                continue
            id = match[1]
            # Consultar depois de obter o lock: upload pode ter confirmado desde
            # que o Storage foi listado. Não apagar por divergência de extensão.
            if db.get(m.ImagemTeoria, id) or db.query(m.ImagemTeoria).filter_by(chave=chave).first() or referenciada(db, id):
                db.rollback()
                continue
            try:
                storage.excluir(chave)
                db.commit()
            except Exception:
                db.rollback()
                log.warning("Reconciliação de objeto será repetida automaticamente: %s", chave)
                continue
            apagados += 1
            removidos_pagina += 1
        offset += len(objetos) - removidos_pagina
        if len(objetos) < tamanho_pagina:
            return {"apagados": apagados, "offset": 0, "concluido": True}
    return {"apagados": apagados, "offset": offset, "concluido": False}


@contextmanager
def exclusao_mutua(engine, bucket):
    """Transação dedicada: commits dos lotes não liberam o lock global.

    Não usa locks de sessão, que poderiam vazar entre clientes do PgBouncer.
    """
    with engine.connect() as conexao:
        chave = numero_lock("manutencao:" + bucket)
        obteve = conexao.execute(text("SELECT pg_try_advisory_xact_lock(:chave)"), {"chave": chave}).scalar()
        try:
            yield bool(obteve)
        finally:
            conexao.rollback()


class ManutencaoImagens:
    def __init__(self, engine, factory, storage_factory=obter_storage_imagens):
        self.engine, self.factory, self.storage_factory = engine, factory, storage_factory
        self.parar = Event()
        self.thread = None
        self.offset = 0
        # Capturar no registro; fixtures isolados não iniciam trabalho de fundo.
        self.ativa = os.getenv("AMBIENTE_TESTE") != "1" and os.getenv("IMAGENS_MANUTENCAO_ATIVA", "").lower() == "true"

    def ciclo(self):
        storage = self.storage_factory()
        with exclusao_mutua(self.engine, storage.bucket) as obteve:
            if not obteve:
                return
            inspetor = inspect(self.engine)
            if not all(inspetor.has_table(t) for t in ("imagens_teoria", "imagens_teoria_materiais")):
                raise RuntimeError("Esquema de imagens indisponível")
            with self.factory() as db:
                limpar_pendentes(db, storage, parar=self.parar)
                resultado = reconciliar_objetos(db, storage, offset=self.offset, parar=self.parar)
                self.offset = resultado["offset"]

    def iniciar(self):
        if not self.ativa or (self.thread and self.thread.is_alive()):
            return
        if self.engine.dialect.name != "postgresql":
            log.warning("Manutenção automática de imagens requer PostgreSQL.")
            return
        self.parar.clear()
        def executar():
            while not self.parar.is_set():
                try:
                    self.ciclo()
                except Exception:
                    # Nem exception repr/traceback: podem conter parâmetros SQL,
                    # URLs assinadas ou cabeçalhos de transporte.
                    log.warning("Manutenção de imagens incompleta; nova tentativa automática em 5 minutos.")
                self.parar.wait(300)
        self.thread = Thread(target=executar, daemon=True, name="manutencao-imagens")
        self.thread.start()

    def encerrar(self):
        self.parar.set()
        if self.thread:
            self.thread.join(timeout=2)
