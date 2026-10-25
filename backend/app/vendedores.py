"""Consultas pessoais restauradas de 37f8432^, sem mutações financeiras.

Mantém o contrato e a apuração histórica (APPROVED, sete dias e valor pago).
Adapta o acesso pós-descredenciamento e a atribuição ao vendedor do pagamento.
"""
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app import models


def _vendedor_com_acesso(db, usuario_id, agora, status_sem_vinculo=403):
    vendedor = db.query(models.Vendedor).filter_by(usuario_id=usuario_id).first()
    if vendedor is None:
        detalhe = ("Este usuário não está vinculado a um parceiro/vendedor."
                   if status_sem_vinculo == 404 else
                   "Usuário não autorizado como parceiro/vendedor.")
        raise HTTPException(status_sem_vinculo, detalhe)
    # Mesma janela de consulta já oferecida por /me e Minha Área.
    if not vendedor.ativo and not (
        vendedor.descredenciado_em is not None
        and agora < vendedor.descredenciado_em + timedelta(days=30)
    ):
        raise HTTPException(403, "Prazo de acesso do parceiro/vendedor encerrado.")
    return vendedor


def _resumo_cupom(codigo, ativo):
    return {
        "codigo_cupom": codigo,
        "total_vendas": 0,
        "vendas_efetivas": 0,
        "vendas_a_confirmar": 0,
        "valor_vendas_efetivas_cents": 0,
        "valor_vendas_a_confirmar_cents": 0,
        "cursos_total": {},
        "cursos_efetivos": {},
        "cursos_a_confirmar": {},
        "ativo": ativo,
    }


def registrar_rotas(app, get_db, get_usuario_atual):
    @app.get('/me/vendedor', tags=['Parceiro/Vendedor'])
    def obter_vendedor_logado(
        db: Session = Depends(get_db),
        usuario: models.Usuario = Depends(get_usuario_atual),
    ):
        agora = datetime.utcnow()
        vendedor = _vendedor_com_acesso(db, usuario.id, agora, status_sem_vinculo=404)
        return {
            'id': vendedor.id, 'nome': vendedor.nome,
            'email': vendedor.email, 'ativo': vendedor.ativo,
        }

    @app.get('/me/vendedor/vendas', tags=['Parceiro/Vendedor'])
    def obter_vendas_vendedor_logado(
        db: Session = Depends(get_db),
        usuario: models.Usuario = Depends(get_usuario_atual),
    ):
        agora = datetime.utcnow()
        vendedor = _vendedor_com_acesso(db, usuario.id, agora)
        # Ocorrências podem estar APPROVED sem representar uma venda válida.
        pagamentos = db.query(models.Pagamento).filter(
            models.Pagamento.vendedor_id == vendedor.id,
            models.Pagamento.status == 'APPROVED',
            models.Pagamento.ocorrencia_financeira.is_(None),
        ).order_by(models.Pagamento.criado_em.desc()).all()
        cupons_vendedor = db.query(models.CupomDesconto).filter(
            models.CupomDesconto.vendedor_id == vendedor.id,
        ).order_by(models.CupomDesconto.codigo.asc()).all()
        cupons = {}
        for cupom in cupons_vendedor:
            codigo = (cupom.codigo or '').strip().upper()
            if not codigo:
                continue
            cupons[codigo] = _resumo_cupom(codigo, cupom.ativo)
        vendas_efetivas = []
        vendas_a_confirmar = []
        valor_vendas_efetivas_cents = 0
        valor_vendas_a_confirmar_cents = 0

        def acumular_curso(destino, curso_id, nome_curso, valor_cents):
            # Preserva preços distintos para o mesmo curso e cupom.
            chave = f'{curso_id}_{valor_cents}'
            if chave not in destino:
                destino[chave] = {
                    'curso_id': curso_id, 'nome_curso': nome_curso,
                    'valor_cents': valor_cents, 'quantidade': 0,
                }
            destino[chave]['quantidade'] += 1

        for pagamento in pagamentos:
            codigo_cupom = (pagamento.codigo_cupom or '').strip().upper()
            if not codigo_cupom:
                continue
            # A atribuição histórica vem do pagamento, nunca do dono atual do cupom.
            # Um cupom transferido/desvinculado não habilita novas vendas aqui.
            if codigo_cupom not in cupons:
                cupons[codigo_cupom] = _resumo_cupom(codigo_cupom, False)
            data_referencia = pagamento.aprovado_em or pagamento.criado_em
            limite = data_referencia + timedelta(days=7)
            valor_cents = pagamento.valor_cents or 0
            curso_id = pagamento.curso_id
            nome_curso = pagamento.curso.nome if pagamento.curso else 'Curso não identificado'
            item = {
                'pagamento_id': pagamento.id, 'codigo_cupom': codigo_cupom,
                'curso_id': curso_id, 'nome_curso': nome_curso,
                'valor_cents': valor_cents, 'data_pagamento': data_referencia,
            }
            cupons[codigo_cupom]['total_vendas'] += 1
            acumular_curso(cupons[codigo_cupom]['cursos_total'], curso_id, nome_curso, valor_cents)
            if agora >= limite:
                vendas_efetivas.append(item)
                valor_vendas_efetivas_cents += valor_cents
                cupons[codigo_cupom]['vendas_efetivas'] += 1
                cupons[codigo_cupom]['valor_vendas_efetivas_cents'] += valor_cents
                acumular_curso(cupons[codigo_cupom]['cursos_efetivos'], curso_id, nome_curso, valor_cents)
            else:
                vendas_a_confirmar.append(item)
                valor_vendas_a_confirmar_cents += valor_cents
                cupons[codigo_cupom]['vendas_a_confirmar'] += 1
                cupons[codigo_cupom]['valor_vendas_a_confirmar_cents'] += valor_cents
                acumular_curso(cupons[codigo_cupom]['cursos_a_confirmar'], curso_id, nome_curso, valor_cents)
        for dados_cupom in cupons.values():
            dados_cupom['cursos_total'] = list(dados_cupom['cursos_total'].values())
            dados_cupom['cursos_efetivos'] = list(dados_cupom['cursos_efetivos'].values())
            dados_cupom['cursos_a_confirmar'] = list(dados_cupom['cursos_a_confirmar'].values())
        return {
            'vendedor': {'id': vendedor.id, 'nome': vendedor.nome},
            'total_vendas': len(vendas_efetivas) + len(vendas_a_confirmar),
            'total_vendas_efetivas': len(vendas_efetivas),
            'total_vendas_a_confirmar': len(vendas_a_confirmar),
            'valor_vendas_efetivas_cents': valor_vendas_efetivas_cents,
            'valor_vendas_a_confirmar_cents': valor_vendas_a_confirmar_cents,
            'vendas_efetivas': vendas_efetivas,
            'vendas_a_confirmar': vendas_a_confirmar,
            'cupons': list(cupons.values()),
        }
