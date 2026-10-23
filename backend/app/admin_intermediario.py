"""Compatibilidade com 022; restritos nunca recebem administração neste artefato."""
from fastapi import HTTPException
from sqlalchemy import text
from app.models import Usuario


def combinacao_valida(is_admin, tipo):
    return ((is_admin is True and tipo == 'admin_geral') or
            (is_admin is False and (tipo is None or tipo in {'admin_prod', 'admin_adm'})))


def exigir_geral(usuario):
    if (getattr(usuario, 'is_admin', None) is not True or
            getattr(usuario, 'tipo_admin', None) != 'admin_geral' or
            not getattr(usuario, 'ativo', True)):
        raise HTTPException(403, 'Acesso restrito ao Administrador Geral')
    return usuario


def revalidar_geral(db, autor_id):
    if db.bind.dialect.name == 'postgresql':
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('resumao:perfis-admin', 0))"))
    autor = db.query(Usuario).filter_by(id=autor_id).populate_existing().with_for_update().first()
    return exigir_geral(autor)
