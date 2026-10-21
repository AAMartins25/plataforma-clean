"""Aceite apenas no início do checkout. Sem chamadas ao provedor ou commits próprios."""
import json
import re
from pathlib import Path
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
from sqlalchemy import inspect
from fastapi import HTTPException, Response
from fastapi.responses import HTMLResponse
from app.models import (DocumentoJuridicoVersao as Documento, PoliticaAceiteJuridico as Politica,
    AceiteJuridico, AceiteJuridicoDocumento, AceiteJuridicoPagamento)

DECLARACAO = "Ciente dos Termos de Contratação e da Política de Privacidade e Proteção de Dados."


ARQUIVOS_JURIDICOS = Path(__file__).resolve().parents[1] / "documentos_juridicos"


def pdf_original(hash_pdf, documento=None):
    """Retorna apenas PDFs arquivados cujo conteúdo corresponde ao hash imutável."""
    if not isinstance(hash_pdf, str) or not re.fullmatch(r"[0-9a-f]{64}", hash_pdf):
        raise HTTPException(404, "PDF não encontrado.")
    for manifesto in sorted(ARQUIVOS_JURIDICOS.glob("*/manifesto.json")):
        for item in json.loads(manifesto.read_text(encoding="utf-8"))["documentos"]:
            if item["pdf_sha256"] != hash_pdf:
                continue
            if documento is not None and (item["tipo"] != documento.tipo or
                    item["versao"] != documento.versao or item["texto_sha256"] != documento.sha256):
                raise HTTPException(503, "Vínculo entre texto e PDF jurídico inválido.")
            nome = item["pdf"]
            if Path(nome).name != nome:
                raise HTTPException(503, "Arquivo jurídico inválido.")
            arquivo = manifesto.parent / nome
            if not arquivo.is_file():
                raise HTTPException(503, "PDF jurídico indisponível.")
            dados = arquivo.read_bytes()
            if sha256(dados).hexdigest() != hash_pdf:
                raise HTTPException(503, "Integridade do PDF jurídico inválida.")
            return nome, dados
    raise HTTPException(503, "PDF jurídico arquivado indisponível.")


def url_pdf_site(documento):
    if not documento.pdf_sha256:
        return None
    for manifesto in sorted(ARQUIVOS_JURIDICOS.glob("*/manifesto.json")):
        for item in json.loads(manifesto.read_text(encoding="utf-8"))["documentos"]:
            if (item["pdf_sha256"] == documento.pdf_sha256 and item["texto_sha256"] == documento.sha256
                    and item["tipo"] == documento.tipo and item["versao"] == documento.versao):
                return item.get("site_url")
    return None


def conferir_documento(documento):
    if not documento.conteudo.strip() or sha256(documento.conteudo.encode()).hexdigest() != documento.sha256:
        raise HTTPException(503, "Integridade do documento jurídico inválida.")
    if documento.pdf_sha256:
        pdf_original(documento.pdf_sha256, documento)


def par_vigente(db):
    # Compatível com backend implantado antes da migração, sem criar tabelas.
    if not inspect(db.connection()).has_table(Politica.__tablename__):
        return None
    # O bloqueio compartilhado impede troca de versões durante a transação do checkout.
    politica = db.query(Politica).filter_by(id=1).with_for_update(read=True).first()
    if not politica or not politica.habilitada:
        return None
    documentos = []
    for tipo, identificador in (("TERMOS", politica.termos_id), ("PRIVACIDADE", politica.privacidade_id)):
        documento = db.get(Documento, identificador) if identificador else None
        if not documento or documento.tipo != tipo:
            raise HTTPException(503, "Documentos jurídicos indisponíveis.")
        conferir_documento(documento)
        documentos.append(documento)
    return documentos


def validar_aceite(db, payload):
    documentos = par_vigente(db)
    if documentos is None:
        return None
    aceite = payload.get("aceite_juridico")
    if not isinstance(aceite, dict) or aceite.get("aceito") is not True:
        raise HTTPException(400, "ACEITE_OBRIGATORIO: confirme a leitura dos documentos.")
    for campo, documento in zip(("termos_id", "privacidade_id"), documentos):
        if type(aceite.get(campo)) is not int or aceite[campo] != documento.id:
            raise HTTPException(409, "ACEITE_DESATUALIZADO: leia as versões atuais e confirme novamente.")
    return documentos


def registrar_aceite(db, documentos, usuario_id, curso_id, tempo, oportunidade_id,
                     modalidade, valor_original, valor, pagamento_id, meses=None):
    if documentos is None:
        return
    aceite = AceiteJuridico(usuario_id=usuario_id, curso_id=curso_id,
        tempo_acesso_id=tempo.id, oportunidade_id=oportunidade_id, meses=meses or tempo.meses,
        modalidade=modalidade, valor_original_cents=valor_original, valor_cents=valor,
        declaracao=DECLARACAO, aceito_em=datetime.now(timezone.utc))
    db.add(aceite)
    db.flush()
    for documento in documentos:
        db.add(AceiteJuridicoDocumento(aceite_id=aceite.id, documento_id=documento.id))
    db.add(AceiteJuridicoPagamento(aceite_id=aceite.id, pagamento_id=pagamento_id))
    db.flush()


def registrar_rotas(app, get_db):
    from fastapi import Depends

    @app.get("/public/juridico/vigente")
    def vigente(response: Response, db=Depends(get_db)):
        response.headers["Cache-Control"] = "no-store"
        documentos = par_vigente(db)
        return {"obrigatorio": documentos is not None, "documentos": [
            {"id": d.id, "tipo": d.tipo, "versao": d.versao, "titulo": d.titulo,
             "url": f"/public/juridico/documentos/{d.id}", "sha256": d.sha256,
             "pdf_sha256": d.pdf_sha256, "pdf_site_url": url_pdf_site(d),
             "pdf_url": f"/public/juridico/arquivos/{d.pdf_sha256}.pdf" if d.pdf_sha256 else None}
            for d in (documentos or [])]}

    @app.get("/public/juridico/documentos/{documento_id}", response_class=HTMLResponse)
    def conteudo(documento_id: int, db=Depends(get_db)):
        documento = db.get(Documento, documento_id)
        if not documento:
            raise HTTPException(404, "Documento não encontrado.")
        conferir_documento(documento)
        original = ('<p><a href="/public/juridico/arquivos/' + documento.pdf_sha256 +
            '.pdf">Abrir PDF original integral</a></p>') if documento.pdf_sha256 else ''
        return HTMLResponse('<!doctype html><html lang="pt-BR"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>' + escape(documento.titulo) + '</title><main style="max-width:850px;'
            'margin:24px auto;padding:16px;font:16px/1.6 sans-serif;overflow-wrap:anywhere">'
            '<h1>' + escape(documento.titulo) + '</h1><p>Versão ' + escape(documento.versao) +
            '</p>' + original + '<pre style="white-space:pre-wrap;font:inherit">' + escape(documento.conteudo) +
            '</pre></main></html>', headers={"X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"})

    @app.get("/public/juridico/arquivos/{hash_pdf}.pdf")
    def arquivo_original(hash_pdf: str):
        nome, dados = pdf_original(hash_pdf)
        return Response(content=dados, media_type="application/pdf", headers={
            "Content-Disposition": f'inline; filename="{nome}"',
            "X-Content-Type-Options": "nosniff", "ETag": f'"{hash_pdf}"',
            "Cache-Control": "public, max-age=31536000, immutable"})
