"""Gestão de perfis administrativos, com autorização e auditoria transacionais."""
from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from typing import Literal
from sqlalchemy import or_
from app import models
from app.admin_intermediario import exigir_geral, revalidar_geral


class AlteracaoPerfil(BaseModel):
    model_config = ConfigDict(extra='forbid')
    tipo_admin: Literal['admin_geral', 'admin_prod', 'admin_adm'] | None


def dados_perfil(db, usuario):
    vendedor = db.query(models.Vendedor).filter_by(usuario_id=usuario.id).first()
    return dict(id=usuario.id, nome=usuario.nome, email=usuario.email, cpf=usuario.cpf,
                ativo=usuario.ativo, is_admin=usuario.is_admin, tipo_admin=usuario.tipo_admin,
                is_aluno=usuario.perfil_inicial == 'ALUNO',
                vendedor_id=vendedor.id if vendedor else None,
                vendedor_ativo=vendedor.ativo if vendedor else False,
                is_vendedor=bool(vendedor and vendedor.ativo))


def registrar_rotas(app, get_db, get_usuario):
    def geral(usuario=Depends(get_usuario)):
        return exigir_geral(usuario)

    @app.get('/admin/usuarios/perfis')
    def buscar(q: str = Query('', max_length=200), db=Depends(get_db), autor=Depends(geral)):
        termo = q.strip()
        if not termo:
            return []
        usuarios = db.query(models.Usuario).filter(or_(
            models.Usuario.nome.ilike(f'%{termo}%'),
            models.Usuario.email.ilike(f'%{termo}%'),
            models.Usuario.cpf.ilike(f'%{termo}%'))).order_by(models.Usuario.id).limit(100).all()
        return [dados_perfil(db, u) for u in usuarios]

    @app.put('/admin/usuarios/{usuario_id}/tipo-admin')
    def alterar(usuario_id: int, dados: AlteracaoPerfil, db=Depends(get_db), autor=Depends(geral)):
        # O mesmo lock serializa todos os escritores de perfis no PostgreSQL.
        try:
            revalidar_geral(db, autor.id)
            alvo = db.query(models.Usuario).filter_by(id=usuario_id).populate_existing().with_for_update().first()
            if not alvo:
                raise HTTPException(404, 'Usuário não encontrado')
            if dados.tipo_admin and not alvo.ativo:
                raise HTTPException(409, 'Ative o usuário antes de atribuir um perfil')
            anterior = alvo.tipo_admin
            if anterior == 'admin_geral' and dados.tipo_admin != 'admin_geral':
                outros = db.query(models.Usuario).filter(
                    models.Usuario.id != alvo.id, models.Usuario.ativo.is_(True),
                    models.Usuario.is_admin.is_(True), models.Usuario.tipo_admin == 'admin_geral').count()
                if not outros:
                    raise HTTPException(409, 'Não é possível remover o último Administrador Geral ativo')
            if anterior != dados.tipo_admin:
                alvo.tipo_admin = dados.tipo_admin
                alvo.is_admin = dados.tipo_admin == 'admin_geral'
                db.add(models.AuditoriaPerfilAdmin(autor_id=autor.id, usuario_id=alvo.id,
                    tipo_anterior=anterior, tipo_novo=dados.tipo_admin))
                db.flush()
            resultado = dados_perfil(db, alvo)
            db.commit()
            return resultado
        except Exception:
            db.rollback()
            raise
