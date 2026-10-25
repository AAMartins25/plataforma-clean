"""Contratos usados pelas telas existentes de vendedores e perfis.

Não altera comissões, cupons, pagamentos nem o prazo de acesso após descredenciamento.
"""
from datetime import datetime
from fastapi import Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from app import models, schemas
from app.auth import hash_senha
from app.admin_intermediario import exigir_geral, revalidar_geral


def registrar_rotas(app, get_db, get_usuario):
    def geral(usuario=Depends(get_usuario)):
        return exigir_geral(usuario)

    def salvar(db, vendedor):
        try:
            db.commit()
            db.refresh(vendedor)
            return vendedor
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, 'Já existe usuário ou vendedor com esses dados')

    @app.post('/admin/vendedores', response_model=schemas.VendedorResponse)
    def criar(dados: schemas.VendedorCreate, db=Depends(get_db), autor=Depends(geral)):
        nome, email = dados.nome.strip(), (dados.email or '').strip().lower()
        cpf = (dados.cpf_cnpj or '').strip()
        if not nome or not email or not cpf:
            raise HTTPException(422, 'Informe nome, email e CPF/CNPJ')
        if db.query(models.Usuario).filter(or_(models.Usuario.email == email, models.Usuario.cpf == cpf)).first():
            raise HTTPException(409, 'Usuário já cadastrado; use Gerenciar perfis para ativar como vendedor')
        revalidar_geral(db, autor.id)
        usuario = models.Usuario(nome=nome, email=email, cpf=cpf, telefone=dados.telefone or '',
            data_nascimento=dados.data_nascimento, senha_hash=hash_senha(dados.senha), ativo=True,
            is_admin=False, tipo_admin=None, perfil_inicial='VENDEDOR')
        db.add(usuario)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Já existe usuário com esses dados")
        vendedor = models.Vendedor(usuario_id=usuario.id, **dados.model_dump(exclude={'senha'}))
        vendedor.nome, vendedor.email, vendedor.cpf_cnpj = nome, email, cpf
        db.add(vendedor)
        return salvar(db, vendedor)

    @app.put('/admin/vendedores/{vendedor_id}', response_model=schemas.VendedorResponse)
    def editar(vendedor_id: int, dados: schemas.VendedorUpdate, db=Depends(get_db), autor=Depends(geral)):
        revalidar_geral(db, autor.id)
        vendedor = db.query(models.Vendedor).filter_by(id=vendedor_id).with_for_update().first()
        if not vendedor:
            raise HTTPException(404, 'Vendedor não encontrado')
        for campo, valor in dados.model_dump(exclude_unset=True).items():
            if campo in {'nome', 'ativo'} and (valor is None or campo == 'nome' and not valor.strip()):
                raise HTTPException(422, 'Nome e status não podem ficar vazios')
            if campo == 'ativo' and valor != vendedor.ativo:
                vendedor.descredenciado_em = None if valor else datetime.utcnow()
            setattr(vendedor, campo, valor)
        return salvar(db, vendedor)

    @app.post('/admin/usuarios/{usuario_id}/tornar-vendedor', response_model=schemas.VendedorResponse)
    def tornar(usuario_id: int, db=Depends(get_db), autor=Depends(geral)):
        revalidar_geral(db, autor.id)
        usuario = db.query(models.Usuario).filter_by(id=usuario_id).with_for_update().first()
        if not usuario:
            raise HTTPException(404, 'Usuário não encontrado')
        vendedor = db.query(models.Vendedor).filter_by(usuario_id=usuario_id).first()
        if vendedor:
            raise HTTPException(409, 'Usuário já possui cadastro de vendedor')
        vendedor = models.Vendedor(usuario_id=usuario.id, nome=usuario.nome, email=usuario.email,
            telefone=usuario.telefone, cpf_cnpj=usuario.cpf, data_nascimento=usuario.data_nascimento, ativo=True)
        db.add(vendedor)
        return salvar(db, vendedor)

    @app.put('/admin/vendedores/{vendedor_id}/descredenciar', response_model=schemas.VendedorResponse)
    def descredenciar(vendedor_id: int, db=Depends(get_db), autor=Depends(geral)):
        return editar(vendedor_id, schemas.VendedorUpdate(ativo=False), db, autor)

    @app.put('/admin/vendedores/{vendedor_id}/reativar', response_model=schemas.VendedorResponse)
    def reativar(vendedor_id: int, db=Depends(get_db), autor=Depends(geral)):
        return editar(vendedor_id, schemas.VendedorUpdate(ativo=True), db, autor)
