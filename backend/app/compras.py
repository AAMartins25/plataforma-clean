"""Validações de aquisição; não altera concessões administrativas."""
from fastapi import HTTPException
from sqlalchemy import or_
from app import models as m
from app.renovacao import renovacao_disponivel

LIMITE_DEMO = 'Você já possui acesso gratuito a 3 cursos. Para acessar outro curso gratuitamente, aguarde o término do prazo de acesso de pelo menos um deles.'
PAGO_DEMO = 'Você já possui acesso a este curso e, por isso, não pode solicitar a modalidade Teste (acesso gratuito) enquanto seu acesso pago estiver vigente.'
COMPRA_DUPLICADA = 'Você já possui acesso a este curso. A renovação estará disponível nos últimos 15 dias de validade do seu acesso. Quando esse período começar, você receberá um aviso na plataforma.'


def pagamento_vigente(db, usuario_id, curso_id, agora):
    return db.query(m.ContratacaoCurso).filter(
        m.ContratacaoCurso.usuario_id == usuario_id,
        m.ContratacaoCurso.curso_id == curso_id,
        m.ContratacaoCurso.origem == 'PAGAMENTO',
        m.ContratacaoCurso.data_inicio <= agora,
        or_(m.ContratacaoCurso.data_fim.is_(None), m.ContratacaoCurso.data_fim > agora),
    ).order_by(m.ContratacaoCurso.data_fim.desc().nullsfirst(), m.ContratacaoCurso.id.desc()).first()


def validar_nova_compra(db, usuario_id, curso_id, agora):
    contrato = pagamento_vigente(db, usuario_id, curso_id, agora)
    if not contrato:
        return
    if contrato.data_fim is not None and renovacao_disponivel(contrato.data_fim, agora):
        raise HTTPException(409, {'codigo': 'USE_RENOVACAO',
            'mensagem': 'Você já possui acesso a este curso. Utilize o fluxo de renovação.',
            'curso_id': curso_id, 'contratacao_id': contrato.id})
    raise HTTPException(409, COMPRA_DUPLICADA)


def validar_nova_demonstracao(db, usuario_id, curso_id, agora):
    # Chamador mantém o mesmo lock por aluno usado pelo checkout até o commit.
    if pagamento_vigente(db, usuario_id, curso_id, agora):
        raise HTTPException(409, PAGO_DEMO)
    vigentes = db.query(m.DemonstracaoCurso.curso_id).join(
        m.Curso, m.Curso.id == m.DemonstracaoCurso.curso_id
    ).filter(m.DemonstracaoCurso.usuario_id == usuario_id,
             m.DemonstracaoCurso.ativo == True, m.Curso.ativo == True,
             m.DemonstracaoCurso.data_inicio <= agora,
             m.DemonstracaoCurso.data_fim > agora).distinct().all()
    if len(vigentes) >= 3 and curso_id not in {id for (id,) in vigentes}:
        raise HTTPException(409, LIMITE_DEMO)


def validar_cupom(db, codigo):
    codigo = str(codigo or '').strip().upper()
    cupom = db.query(m.CupomDesconto).filter_by(codigo=codigo, ativo=True).first()
    if not cupom:
        raise HTTPException(400, 'Cupom de desconto inválido ou inativo.')
    if cupom.vendedor_id is None:
        raise HTTPException(400, 'Este cupom ainda não está vinculado a um parceiro/vendedor.')
    vendedor = db.query(m.Vendedor).filter_by(id=cupom.vendedor_id, ativo=True).first()
    if not vendedor:
        raise HTTPException(400, 'O parceiro/vendedor vinculado a este cupom está inativo.')
    return cupom, vendedor
