"""Falhas transacionais e separação de buckets, sem rede ou banco configurado."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import event

from app import imagens as midias, imagens_arquivos as arquivos, models as m
from app.imagens_storage import SupabaseImagens
from test_imagens_teoria import ambiente_imagens, aulas, infraestrutura, StorageMemoria, png


class StorageAuditado(StorageMemoria):
    def __init__(self):
        super().__init__()
        self.exclusoes = []
        self.antes_excluir = lambda: None

    def excluir(self, chave):
        self.antes_excluir()
        self.exclusoes.append(chave)
        super().excluir(chave)


def lote():
    return {nome: arquivos.validar_imagem(png(cor))
            for nome, cor in (("primeira", "red"), ("segunda", "blue"))}


def test_rollback_comprovado_compensa_so_upload_confirmado(ambiente_imagens):
    _, _, factory, _, _ = ambiente_imagens
    storage = StorageAuditado()
    storage.falhar = True
    with factory() as db:
        rollbacks = []
        event.listen(db, "after_rollback", lambda _: rollbacks.append(True))
        def conferir():
            assert rollbacks == [True]
            assert db.query(m.ImagemTeoria).count() == 0
        storage.antes_excluir = conferir
        with pytest.raises(HTTPException, match="Falha simulada"):
            midias.registrar_lote(db, SimpleNamespace(id=1), lote(), storage)
    assert storage.envios == 2
    assert len(storage.exclusoes) == 1
    assert storage.objetos == {}


@pytest.mark.parametrize("persistiu", [False, True])
def test_commit_sem_confirmacao_preserva_objeto(ambiente_imagens, monkeypatch, persistiu):
    _, _, factory, _, _ = ambiente_imagens
    storage = StorageAuditado()
    with factory() as db:
        commit = db.commit
        def sem_confirmacao():
            if persistiu:
                commit()
            raise ConnectionError("Resultado do commit desconhecido")
        monkeypatch.setattr(db, "commit", sem_confirmacao)
        with pytest.raises(ConnectionError, match="desconhecido"):
            midias.registrar_lote(db, SimpleNamespace(id=1), {"uma": lote()["primeira"]}, storage)
    assert storage.exclusoes == []
    assert len(storage.objetos) == 1
    with factory() as db:
        assert db.query(m.ImagemTeoria).count() == int(persistiu)
        if persistiu:
            assert db.query(m.ImagemTeoria).one().chave in storage.objetos


@pytest.mark.parametrize("falha", ["rollback", "invalidada", "fechada"])
def test_rollback_nao_comprovado_preserva_objeto(ambiente_imagens, monkeypatch, falha):
    _, _, factory, _, _ = ambiente_imagens
    storage = StorageAuditado()
    storage.falhar = True
    with factory() as db:
        with monkeypatch.context() as mp:
            if falha == "rollback":
                def falhar():
                    raise ConnectionError("Rollback sem confirmação")
                mp.setattr(db, "rollback", falhar)
            else:
                mp.setattr(db, "connection", lambda: SimpleNamespace(
                    closed=falha == "fechada", invalidated=falha == "invalidada",
                    in_transaction=lambda: True))
            with pytest.raises(HTTPException, match="Falha simulada"):
                midias.registrar_lote(db, SimpleNamespace(id=1), lote(), storage)
        db.rollback()
    assert storage.exclusoes == []
    assert len(storage.objetos) == 1


@pytest.mark.parametrize("ambiente,bucket", [
    ("homologacao", "teoria-imagens"), ("producao", "teoria-imagens-producao")])
def test_perfis_isolam_bucket_e_desativam_manutencao(monkeypatch, ambiente, bucket):
    perfil = Path(__file__).resolve().parents[1] / "preparacao/fase2" / (ambiente + ".env.example")
    valores = dict(linha.split("=", 1) for linha in perfil.read_text().splitlines()
                   if linha and not linha.startswith("#"))
    assert valores["SUPABASE_IMAGENS_BUCKET"] == bucket
    assert valores["IMAGENS_MANUTENCAO_ATIVA"] == "false"
    assert valores["SUPABASE_URL"] == valores["SUPABASE_SECRET_KEY"] == ""
    for chave, valor in valores.items():
        monkeypatch.setenv(chave, valor)
    monkeypatch.setenv("SUPABASE_URL", "https://projeto-ficticio.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_" + "sintetico" * 4)
    storage = SupabaseImagens()
    chamadas = []
    def requisicao(metodo, caminho, **kwargs):
        chamadas.append((metodo, caminho))
        return SimpleNamespace(json=lambda: {"signedURL": "/object/sign/" + bucket + "/teste.png?token=ficticio"})
    monkeypatch.setattr(storage, "_request", requisicao)
    storage.enviar("teste.png", b"ficticio", "image/png")
    assert "/" + bucket + "/" in storage.assinar("teste.png")
    assert chamadas == [("POST", "/object/" + bucket + "/teste.png"),
                        ("POST", "/object/sign/" + bucket + "/teste.png")]
