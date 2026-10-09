"""Gestão administrativa de cupons, preservando o contrato histórico."""
import secrets
import string
from datetime import datetime
from fastapi import Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from app import models as m, schemas


def gerar_codigo():
    return ''.join(secrets.choice(string.ascii_uppercase) for _ in range(2)) + ''.join(
        secrets.choice(string.digits) for _ in range(3))


def dados_cupom(cupom):
    return {campo: getattr(cupom, campo) for campo in ('id','codigo','vendedor_id','percentual_desconto','ativo')}


def registrar_rotas(app, get_db, get_usuario):
    def exigir_admin(usuario=Depends(get_usuario)):
        if not usuario.is_admin:
            raise HTTPException(403,'Acesso restrito ao administrador.')
        return usuario

    @app.get('/admin/cupons-desconto', response_model=list[schemas.CupomDescontoResponse])
    def listar(db=Depends(get_db), usuario=Depends(exigir_admin)):
        return db.query(m.CupomDesconto).order_by(m.CupomDesconto.id.desc()).all()

    @app.get('/admin/vendedores', response_model=list[schemas.VendedorResponse])
    def vendedores(db=Depends(get_db), usuario=Depends(exigir_admin)):
        return db.query(m.Vendedor).order_by(m.Vendedor.ativo.desc(),m.Vendedor.nome.asc()).all()

    @app.post('/admin/cupons-desconto/gerar', response_model=list[schemas.CupomDescontoResponse])
    def gerar(dados: schemas.CupomDescontoGerarRequest, db=Depends(get_db), usuario=Depends(exigir_admin)):
        if not 1 <= dados.quantidade <= 100:
            raise HTTPException(400,'A quantidade deve estar entre 1 e 100.')
        try:
            if db.bind.dialect.name == 'postgresql':
                db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('resumao:cupons:gerar',0))"))
            novos=[]
            for _ in range(dados.quantidade):
                for tentativa in range(1000):
                    codigo=gerar_codigo()
                    if db.query(m.CupomDesconto.id).filter_by(codigo=codigo).first():
                        continue
                    try:
                        with db.begin_nested():
                            cupom=m.CupomDesconto(codigo=codigo,vendedor_id=None,ativo=True,percentual_desconto=12)
                            db.add(cupom);db.flush()
                        novos.append(dados_cupom(cupom))
                        break
                    except IntegrityError:
                        # Recuperar apenas colisão real; outras falhas abortam o lote inteiro.
                        if not db.query(m.CupomDesconto.id).filter_by(codigo=codigo).first():
                            raise
                else:
                    raise HTTPException(409,'Não foi possível gerar códigos únicos. Tente novamente.')
            db.commit()
            return novos
        except HTTPException:
            db.rollback();raise
        except SQLAlchemyError:
            db.rollback()
            raise HTTPException(500,'Não foi possível gerar cupons. Tente novamente.')

    def localizar(db, cupom_id):
        cupom=db.query(m.CupomDesconto).filter_by(id=cupom_id).with_for_update().first()
        if not cupom:
            raise HTTPException(404,'Cupom não encontrado.')
        return cupom

    def salvar(db,cupom):
        try:
            cupom.atualizado_em=datetime.utcnow()
            db.flush();resultado=dados_cupom(cupom);db.commit()
            return resultado
        except SQLAlchemyError:
            db.rollback()
            raise HTTPException(500,'Não foi possível atualizar o cupom. Tente novamente.')

    @app.put('/admin/cupons-desconto/{cupom_id}/vendedor',response_model=schemas.CupomDescontoResponse)
    def vincular(cupom_id: int,dados: schemas.CupomDescontoVincularVendedorRequest,db=Depends(get_db),usuario=Depends(exigir_admin)):
        cupom=localizar(db,cupom_id)
        if dados.vendedor_id is not None:
            vendedor=db.query(m.Vendedor).filter_by(id=dados.vendedor_id).with_for_update().first()
            if not vendedor:
                raise HTTPException(404,'Parceiro/vendedor não encontrado.')
            if not vendedor.ativo:
                raise HTTPException(400,'Não é possível vincular um parceiro/vendedor inativo.')
        cupom.vendedor_id=dados.vendedor_id
        return salvar(db,cupom)

    @app.put('/admin/cupons-desconto/{cupom_id}/status',response_model=schemas.CupomDescontoResponse)
    def status(cupom_id: int,ativo: bool,db=Depends(get_db),usuario=Depends(exigir_admin)):
        cupom=localizar(db,cupom_id);cupom.ativo=ativo
        return salvar(db,cupom)
