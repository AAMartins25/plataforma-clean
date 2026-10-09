from app.models import Curso, Disciplina, Assunto, Pasta, Aula, Video, Bateria, TentativaBateria, RespostaAlunoQuestao  
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from app.schemas import CursoCreate, CursoResponse, DisciplinaCreate, DisciplinaResponse, AssuntoCreate, AssuntoResponse
from app.models import Questao, Alternativa, Comentario, QuestaoPraticaAssunto, QuestaoPraticaAlternativa
from app.schemas import QuestaoCreate, AlternativaCreate, ComentarioGeralCreate
from app.schemas import Sprint10Create 
from app.schemas import VideoCreate 
from app.schemas import BateriaCreate 
from app.models import Material
from app.schemas import MaterialCreate, ConcluirBateriaCreate, TentativaBateriaResponse, RespostaQuestaoAlunoCreate
from sqlalchemy import text
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session 
from app.database import SessionLocal
from app.models import Curso
from app.models import ConversaQuestaoProfessor, MensagemConversaQuestao
from app.schemas import CursoCreate, CursoResponse  
from app.models import QuizIA, QuizIAItem, CartaoIA, QuestoesIA, QuestoesIAItem 
from urllib.parse import quote
from app.schemas import (
    CursoCreate, CursoResponse,
    DisciplinaCreate, DisciplinaResponse,
    AssuntoCreate, AssuntoResponse,
    AulaCreate, AulaResponse
) 
import re
import hashlib
import secrets
import string
import random
from app import schemas
from app.copias import (
    copiar_disciplina_conteudo, copiar_disciplina_para_curso,
    copiar_assunto_para_disciplina, executar_copia,
)
from app.aulas import (
    bloquear_pai, ordem_conteudo, confirmar_conteudo, validar_vinculo,
    validar_material, garantir_sem_historico, validar_alternativas,
    sincronizar_alternativas, validar_conclusao,
)
from app.schemas import (ReembolsoPixManualCreate, ContestacaoPagamentoCreate, ContestacaoDevolucaoConfirmadaCreate)
from app import models
from app.oportunidades import (
    obter_oportunidade,
    bloquear_oportunidade_pagamento,
    concluir_oportunidade,
)
from app.contratacoes import (
    registrar_contratacao,
    validar_data_aprovacao_mp,
    obter_data_aprovacao_mp,
    registrar_ocorrencia_financeira,
)
from app.renovacao import renovacao_disponivel
from sqlalchemy import func
from fastapi import HTTPException
import requests
from sqlalchemy.exc import IntegrityError
from app.models import (
    AcessoCurso,
    ConcessaoAcessoAdmin,
    TempoAcessoCurso,
    ProgressoAula,
    RevisaoAluno,
    TokenRecuperacaoSenha
)
from app.schemas import AcessoCursoCreate, AcessoCursoResponse
from app.schemas import (
    RecuperarSenhaRequest,
    RedefinirSenhaRequest
)
from app.models import (
    Pagamento,
    DemonstracaoCurso,
    ReembolsoFinanceiro,
    PeriodoAcessoPagamento,
    ContestacaoPagamento,
)
from app.models import Atendimento
from app.models import CursoDisciplinaPropria
from app.models import CursoAssuntoProprio
from app.models import ContratacaoCurso
from app.schemas import AulaUpdate

import os
import resend

import hmac
import hashlib

from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "")

MP_WEBHOOK_SECRET = os.getenv("MP_WEBHOOK_SECRET", "")

APP_BASE_URL = os.getenv(
    "APP_BASE_URL",
    "http://127.0.0.1:5500/site-html"
)

CLOUDFLARE_ACCOUNT_ID = os.getenv(
    "CLOUDFLARE_ACCOUNT_ID",
    ""
)

CLOUDFLARE_STREAM_API_TOKEN = os.getenv(
    "CLOUDFLARE_STREAM_API_TOKEN",
    ""
)

RESEND_API_KEY = os.getenv(
    "RESEND_API_KEY",
    ""
)

resend.api_key = RESEND_API_KEY

app = FastAPI(title="Plataforma de Cursos")

from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from app.auth import hash_senha, verificar_senha, criar_token, decodificar_token
from app.models import Usuario
from app.schemas import UsuarioCreate, UsuarioResponse, TokenResponse
from sqlalchemy import or_
from app.schemas import UsuarioUpdateMe
from app.schemas import AtendimentoCreate, AtendimentoResponse
from app.schemas import (
    CursoDisciplinaPropriaCreate,
    CursoDisciplinaPropriaUpdate,
    CursoDisciplinaPropriaResponse
)
from app.schemas import (
    CursoAssuntoProprioCreate,
    CursoAssuntoProprioUpdate,
    CursoAssuntoProprioResponse
)
from app.models import AnotacaoAlunoQuestao

from dateutil.relativedelta import relativedelta

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://plataforma-quality.onrender.com",
        "https://resumaoonline.com.br",
        "https://www.resumaoonline.com.br",
    ],
    allow_origin_regex=r"https://.*\.app\.github\.dev",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependência para abrir e fechar sessão do banco por requisição
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_usuario_atual(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Usuario:
    payload = decodificar_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token inválido")

    usuario = db.query(Usuario).filter(Usuario.id == int(user_id)).first()
    if not usuario or not usuario.ativo:
        raise HTTPException(status_code=401, detail="Usuário não encontrado/inativo")

    return usuario

def exigir_admin_aulas(usuario: Usuario = Depends(get_usuario_atual)):
    if not usuario.is_admin:
        raise HTTPException(403, "Apenas administradores podem gerenciar conteúdos de aulas")
    return usuario


def validar_contexto_estudo(
    db: Session,
    usuario: Usuario,
    curso_id: int,
    contratacao_id: int | None = None,
    demonstracao_id: int | None = None,
):
    if bool(contratacao_id) == bool(demonstracao_id):
        raise HTTPException(
            status_code=400,
            detail="Informe exatamente um contexto de acesso ao curso."
        )

    agora = datetime.utcnow()

    if contratacao_id:
        contratacao = (
            db.query(models.ContratacaoCurso)
            .filter(
                models.ContratacaoCurso.id == contratacao_id,
                models.ContratacaoCurso.usuario_id == usuario.id,
                models.ContratacaoCurso.curso_id == curso_id,
                models.ContratacaoCurso.origem.in_(["PAGAMENTO", "ADMIN"]),
                models.ContratacaoCurso.data_inicio <= agora,
                or_(
                    models.ContratacaoCurso.data_fim.is_(None),
                    models.ContratacaoCurso.data_fim > agora,
                ),
            )
            .first()
        )

        if not contratacao:
            raise HTTPException(
                status_code=403,
                detail="Contratação inválida ou sem acesso ativo a este curso."
            )

        return {
            "contratacao_id": contratacao.id,
            "demonstracao_id": None,
        }

    demonstracao = (
        db.query(DemonstracaoCurso)
        .filter(
            DemonstracaoCurso.id == demonstracao_id,
            DemonstracaoCurso.usuario_id == usuario.id,
            DemonstracaoCurso.curso_id == curso_id,
            DemonstracaoCurso.ativo == True,
            DemonstracaoCurso.data_inicio <= agora,
            DemonstracaoCurso.data_fim > agora,
        )
        .first()
    )

    if not demonstracao:
        raise HTTPException(
            status_code=403,
            detail="Demonstração inválida ou sem acesso ativo a este curso."
        )

    return {
        "contratacao_id": None,
        "demonstracao_id": demonstracao.id,
    }

def consultar_direitos_acesso_apos_reembolso(
    db: Session,
    usuario_id: int,
    curso_id: int,
    pagamento_reembolsado_id: int,
):
    """
    Consulta os direitos de acesso restantes após um reembolso.
    Não modifica o banco de dados.
    """
    agora = datetime.utcnow()

    # Excluir somente contestações cujo bloqueio administrativo
    # já foi efetivamente executado.
    from sqlalchemy import or_, select

    pagamentos_bloqueados = select(
        ContestacaoPagamento.pagamento_id
    ).where(
        ContestacaoPagamento.bloqueio_executado_em.isnot(None)
    )

    pagamentos_contestados_sem_bloqueio = select(
        ContestacaoPagamento.pagamento_id
    ).where(
        ContestacaoPagamento.bloqueio_executado_em.is_(None)
    )

    # Outras compras aprovadas que ainda geram direitos de acesso.
    outros_pagamentos = db.query(Pagamento).filter(
        Pagamento.usuario_id == usuario_id,
        Pagamento.curso_id == curso_id,
        Pagamento.id != pagamento_reembolsado_id,
        Pagamento.aprovado_em.isnot(None),
        or_(
            Pagamento.status != "REFUNDED",
            Pagamento.id.in_(pagamentos_contestados_sem_bloqueio),
        ),
        ~Pagamento.id.in_(pagamentos_bloqueados),
    ).all()

    ids_pagamentos = [p.id for p in outros_pagamentos]

    periodos = (
        db.query(PeriodoAcessoPagamento)
        .filter(
            PeriodoAcessoPagamento.pagamento_id.in_(ids_pagamentos)
        )
        .all()
        if ids_pagamentos
        else []
    )

    ids_com_historico = {p.pagamento_id for p in periodos}

    pagamentos_sem_historico = [
        p.id
        for p in outros_pagamentos
        if p.id not in ids_com_historico
    ]

    # Períodos válidos das demais compras.
    datas_fim = [
        p.data_fim
        for p in periodos
        if p.data_inicio <= agora < p.data_fim
    ]

    # Concessões administrativas vigentes.
    concessoes = db.query(ConcessaoAcessoAdmin).filter(
        ConcessaoAcessoAdmin.usuario_id == usuario_id,
        ConcessaoAcessoAdmin.curso_id == curso_id,
        ConcessaoAcessoAdmin.ativo == True,
        ConcessaoAcessoAdmin.data_inicio <= agora,
    ).all()

    acesso_sem_prazo = False

    for concessao in concessoes:
        if concessao.data_fim is None:
            acesso_sem_prazo = True
        elif concessao.data_fim > agora:
            datas_fim.append(concessao.data_fim)

    # Demonstrações vigentes.
    demonstracoes = db.query(DemonstracaoCurso).filter(
        DemonstracaoCurso.usuario_id == usuario_id,
        DemonstracaoCurso.curso_id == curso_id,
        DemonstracaoCurso.ativo == True,
        DemonstracaoCurso.data_inicio <= agora,
        DemonstracaoCurso.data_fim > agora,
    ).all()

    datas_fim.extend(d.data_fim for d in demonstracoes)

    return {
        "pagamentos_sem_historico": pagamentos_sem_historico,
        "requer_conferencia": bool(pagamentos_sem_historico),
        "possui_acesso_sem_prazo": acesso_sem_prazo,
        "maior_data_fim": max(datas_fim) if datas_fim else None,
    }

def recalcular_acesso_apos_reembolso(
    db: Session,
    usuario_id: int,
    curso_id: int,
    pagamento_reembolsado_id: int,
):
    direitos = consultar_direitos_acesso_apos_reembolso(
        db=db,
        usuario_id=usuario_id,
        curso_id=curso_id,
        pagamento_reembolsado_id=pagamento_reembolsado_id,
    )

    # Uma compra antiga sem histórico impede alterações automáticas.
    if direitos["requer_conferencia"]:
        return {
            "situacao": "CONFERENCIA_NECESSARIA",
            "pagamentos_sem_historico": direitos["pagamentos_sem_historico"],
        }

    acesso = db.query(AcessoCurso).filter(
        AcessoCurso.usuario_id == usuario_id,
        AcessoCurso.curso_id == curso_id,
    ).with_for_update().first()

    if direitos["possui_acesso_sem_prazo"]:
        nova_data_fim = None
    else:
        nova_data_fim = direitos["maior_data_fim"]

    if nova_data_fim is None and not direitos["possui_acesso_sem_prazo"]:
        if acesso:
            acesso.ativo = False

        return {"situacao": "SEM_DIREITOS_VIGENTES"}

    if acesso:
        acesso.ativo = True
        acesso.data_fim = nova_data_fim
    else:
        db.add(
            AcessoCurso(
                usuario_id=usuario_id,
                curso_id=curso_id,
                ativo=True,
                data_inicio=datetime.utcnow(),
                data_fim=nova_data_fim,
            )
        )

    return {
        "situacao": "ACESSO_PRESERVADO",
        "data_fim": nova_data_fim,
    }

@app.post("/admin/acessos", tags=["Acessos"])
def admin_criar_acesso(
    payload: AcessoCursoCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Apenas admin pode liberar acesso"
        )

    u = db.query(Usuario).filter(
        Usuario.id == payload.usuario_id
    ).first()

    if not u:
        raise HTTPException(
            status_code=404,
            detail="Usuário não encontrado"
        )

    c = db.query(Curso).filter(
        Curso.id == payload.curso_id
    ).first()

    if not c:
        raise HTTPException(
            status_code=404,
            detail="Curso não encontrado"
        )

    agora = datetime.utcnow()

    # Converte datas com fuso horário para UTC sem timezone,
    # compatível com as colunas DateTime atuais.
    data_fim = payload.data_fim

    if data_fim.tzinfo is not None:
        data_fim = data_fim.astimezone(
            timezone.utc
        ).replace(tzinfo=None)

    if data_fim <= agora:
        raise HTTPException(
            status_code=400,
            detail="A data de término deve ser posterior à data atual."
        )

    # ---------------------------------------------------------
    # Localiza uma contratação ADMIN vigente.
    #
    # Se ela estiver nos últimos 15 dias, a nova concessão
    # preservará a mesma contratação e, portanto, o histórico.
    #
    # Se não houver contratação ADMIN vigente/renovável,
    # uma nova contratação será criada.
    # ---------------------------------------------------------
    contratacao_admin = (
        db.query(ContratacaoCurso)
        .filter(
            ContratacaoCurso.usuario_id == payload.usuario_id,
            ContratacaoCurso.curso_id == payload.curso_id,
            ContratacaoCurso.origem == "ADMIN",
            ContratacaoCurso.data_inicio <= agora,
            ContratacaoCurso.data_fim > agora,
        )
        .order_by(
            ContratacaoCurso.data_fim.desc(),
            ContratacaoCurso.id.desc()
        )
        .with_for_update()
        .first()
    )

    if contratacao_admin:
        # Se estiver dentro da janela dos 15 dias,
        # preserva a mesma contratação.
        if renovacao_disponivel(
            contratacao_admin.data_fim,
            agora
        ):
            contratacao_admin.data_fim = data_fim
            contratacao = contratacao_admin

        else:
            # Ainda está vigente, mas fora da janela de renovação.
            # A nova concessão é uma nova contratação.
            contratacao = ContratacaoCurso(
                usuario_id=payload.usuario_id,
                curso_id=payload.curso_id,
                data_inicio=agora,
                data_fim=data_fim,
                origem="ADMIN",
            )
            db.add(contratacao)
    else:
        # Não existe contratação ADMIN vigente.
        # Portanto, esta concessão inicia novo histórico.
        contratacao = ContratacaoCurso(
            usuario_id=payload.usuario_id,
            curso_id=payload.curso_id,
            data_inicio=agora,
            data_fim=data_fim,
            origem="ADMIN",
        )
        db.add(contratacao)

    db.flush()

    # ---------------------------------------------------------
    # Mantém o mecanismo existente de AcessoCurso.
    # ---------------------------------------------------------
    existente = db.query(AcessoCurso).filter(
        AcessoCurso.usuario_id == payload.usuario_id,
        AcessoCurso.curso_id == payload.curso_id
    ).first()

    if existente:
        if payload.ativo:
            acesso_vigente = (
                existente.ativo
                and (
                    existente.data_inicio is None
                    or existente.data_inicio <= agora
                )
                and (
                    existente.data_fim is None
                    or existente.data_fim > agora
                )
            )

            if not acesso_vigente:
                existente.ativo = True
                existente.data_inicio = agora
                existente.data_fim = data_fim

            elif (
                existente.data_fim is not None
                and existente.data_fim < data_fim
            ):
                existente.data_fim = data_fim

        acesso = existente

    else:
        acesso = AcessoCurso(
            usuario_id=payload.usuario_id,
            curso_id=payload.curso_id,
            ativo=payload.ativo,
            data_inicio=agora,
            data_fim=data_fim
        )
        db.add(acesso)

    # ---------------------------------------------------------
    # Registra a concessão administrativa individual.
    # ---------------------------------------------------------
    concessao = ConcessaoAcessoAdmin(
        usuario_id=payload.usuario_id,
        curso_id=payload.curso_id,
        data_inicio=agora,
        data_fim=data_fim,
        ativo=payload.ativo
    )
    db.add(concessao)

    try:
        db.commit()
        db.refresh(acesso)
        db.refresh(contratacao)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Conflito ao registrar a concessão administrativa."
        )

    return {
        "ok": True,
        "msg": "Concessão administrativa registrada",
        "acesso_id": acesso.id,
        "contratacao_id": contratacao.id,
    }

@app.get("/me/compras/reembolso")
def listar_compras_reembolso(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    limite_7_dias = datetime.utcnow() - timedelta(days=7)

    compras_elegiveis = db.query(Pagamento).filter(
        Pagamento.usuario_id == usuario.id,
        Pagamento.status.in_(["APPROVED", "approved", "PAGO"]),
        Pagamento.criado_em >= limite_7_dias
    ).order_by(Pagamento.criado_em.desc()).all()

    if compras_elegiveis:
        return {
            "tipo": "elegiveis",
            "compras": [
                {
                    "pagamento_id": p.id,
                    "curso_id": p.curso_id,
                    "nome_curso": p.curso.nome if p.curso else "Curso",
                    "data_compra": p.criado_em,
                    "data_solicitacao": p.atualizado_em,
                    "valor_cents": p.valor_cents,
                    "status": p.status
                }
                for p in compras_elegiveis
            ]
        }

    compra_recente = db.query(Pagamento).filter(
        Pagamento.usuario_id == usuario.id
    ).order_by(Pagamento.criado_em.desc()).first()

    if compra_recente:
        return {
            "tipo": "mais_recente",
            "mensagem": "Sua compra mais recente foi:",
            "compras": [
                {
                    "pagamento_id": compra_recente.id,
                    "curso_id": compra_recente.curso_id,
                    "nome_curso": compra_recente.curso.nome if compra_recente.curso else "Curso",
                    "data_compra": compra_recente.criado_em,
                    "data_solicitacao": compra_recente.atualizado_em,
                    "valor_cents": compra_recente.valor_cents,
                    "status": compra_recente.status
                }
            ]
        }

    return {
        "tipo": "nenhuma",
        "compras": []
    }

@app.get(
    "/me/cursos",
    response_model=list[AcessoCursoResponse],
    tags=["Acessos"]
)
def meus_cursos(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    agora = datetime.utcnow()

    # Desativa automaticamente acessos cuja data final já passou.
    acessos_expirados = (
        db.query(AcessoCurso)
        .filter(
            AcessoCurso.usuario_id == usuario.id,
            AcessoCurso.ativo == True,
            AcessoCurso.data_fim.isnot(None),
            AcessoCurso.data_fim <= agora
        )
        .all()
    )

    for acesso in acessos_expirados:
        acesso.ativo = False

    if acessos_expirados:
        db.commit()

    acessos = (
        db.query(AcessoCurso)
        .join(
            Curso,
            Curso.id == AcessoCurso.curso_id
        )
        .filter(
            AcessoCurso.usuario_id == usuario.id,
            AcessoCurso.ativo == True,
            Curso.ativo == True
        )
        .all()
    )

    resultado = []

    for a in acessos:
        contratacoes = (
            db.query(models.ContratacaoCurso)
            .filter(
                models.ContratacaoCurso.usuario_id == usuario.id,
                models.ContratacaoCurso.curso_id == a.curso_id,
                models.ContratacaoCurso.data_inicio <= agora,
                models.ContratacaoCurso.data_fim > agora,
                models.ContratacaoCurso.origem.in_(["PAGAMENTO", "ADMIN"])
            )
            .order_by(models.ContratacaoCurso.data_fim.asc())
            .all()
        )

        contratos_resposta = []

        for contrato in contratacoes:
            pode_renovar = renovacao_disponivel(
                contrato.data_fim, agora
            )

            if pode_renovar:
                concluida = (
                    db.query(models.OportunidadeCompra.id)
                    .filter(
                        models.OportunidadeCompra.usuario_id == usuario.id,
                        models.OportunidadeCompra.curso_id == a.curso_id,
                        models.OportunidadeCompra.tipo_compra == "RENOVACAO",
                        models.OportunidadeCompra.contratacao_id == contrato.id,
                        models.OportunidadeCompra.vencimento_original == contrato.data_fim,
                        models.OportunidadeCompra.concluida_em.isnot(None)
                    )
                    .first()
                )
                pode_renovar = concluida is None

            contratos_resposta.append({
                "id": contrato.id,
                "origem": contrato.origem,
                "data_inicio": contrato.data_inicio,
                "data_fim": contrato.data_fim,
                "renovacao_disponivel": pode_renovar
            })

        demos = (
            db.query(DemonstracaoCurso)
            .filter(
                DemonstracaoCurso.usuario_id == usuario.id,
                DemonstracaoCurso.curso_id == a.curso_id,
                DemonstracaoCurso.ativo == True,
                DemonstracaoCurso.data_inicio <= agora,
                DemonstracaoCurso.data_fim > agora
            )
            .order_by(DemonstracaoCurso.id.desc())
            .all()
        )

        demonstracoes_resposta = []

        for demo in demos:
            compra_concluida = (
                db.query(models.OportunidadeCompra.id)
                .filter(
                    models.OportunidadeCompra.usuario_id == usuario.id,
                    models.OportunidadeCompra.curso_id == a.curso_id,
                    models.OportunidadeCompra.tipo_compra == "NOVA",
                    models.OportunidadeCompra.demonstracao_id == demo.id,
                    models.OportunidadeCompra.concluida_em.isnot(None)
                )
                .first()
            )

            demonstracoes_resposta.append({
                "id": demo.id,
                "data_inicio": demo.data_inicio,
                "data_fim": demo.data_fim,
                "aquisicao_disponivel": compra_concluida is None
            })

        resultado.append(
            AcessoCursoResponse(
                id=a.id,
                curso_id=a.curso_id,
                nome_curso=a.curso.nome,
                ativo=a.ativo,
                data_inicio=a.data_inicio,
                data_fim=a.data_fim,
                renovacao_disponivel=any(
                    c["renovacao_disponivel"]
                    for c in contratos_resposta
                ),
                contratacoes=contratos_resposta,
                demonstracoes=demonstracoes_resposta
            )
        )

    return resultado

@app.get("/me/cursos/historico", tags=["Acessos"])
def meus_cursos_historico(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    acessos = (
        db.query(AcessoCurso)
        .join(Curso, Curso.id == AcessoCurso.curso_id)
        .filter(
            AcessoCurso.usuario_id == usuario.id,
            AcessoCurso.ativo == False
        )
        .order_by(AcessoCurso.data_inicio.desc())
        .all()
    )

    return [
        {
            "id": a.id,
            "curso_id": a.curso_id,
            "nome_curso": a.curso.nome,
            "ativo": a.ativo,
            "data_inicio": a.data_inicio,
            "data_fim": a.data_fim
        }
        for a in acessos
    ]

@app.get("/")
def root():
    return {"mensagem": "Backend rodando com CRUD de cursos 🚀"}

# CREATE: criar curso
@app.post("/cursos", response_model=CursoResponse)
def criar_curso(curso: CursoCreate, db: Session = Depends(get_db)):
    nome = curso.nome.strip()

    existente = db.query(Curso).filter(
        Curso.nome.ilike(nome)
    ).first()

    if existente:
        raise HTTPException(
            status_code=400,
            detail="Já existe um curso com esse nome"
        )

    novo = Curso(nome=nome, ativo=curso.ativo)
    db.add(novo)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Já existe um curso com esse nome"
        )

    db.refresh(novo)
    return novo

@app.get("/admin/cursos", response_model=list[CursoResponse])
def listar_cursos_admin(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Apenas admin"
        )

    return (
        db.query(Curso)
        .order_by(Curso.nome.asc())
        .all()
    )

# READ: listar cursos
@app.get("/cursos", response_model=list[CursoResponse])
def listar_cursos(db: Session = Depends(get_db)):
    cursos = db.query(Curso).all()
    return cursos

@app.put("/cursos/{curso_id}")
def editar_curso(
    curso_id: int,
    dados: CursoCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas admin")

    curso = db.query(Curso).filter(Curso.id == curso_id).first()

    if not curso:
        raise HTTPException(status_code=404, detail="Curso não encontrado")

    curso.nome = dados.nome.strip()
    curso.ativo = dados.ativo

    db.commit()
    db.refresh(curso)

    return {
        "id": curso.id,
        "nome": curso.nome,
        "ativo": curso.ativo
    }

@app.delete("/cursos/{curso_id}")
def excluir_curso(
    curso_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas admin")

    curso = db.query(Curso).filter(Curso.id == curso_id).first()

    if not curso:
        raise HTTPException(status_code=404, detail="Curso não encontrado")

    curso.ativo = False

    db.commit()
    db.refresh(curso)

    return {
        "mensagem": "Curso desativado com sucesso",
        "id": curso.id,
        "nome": curso.nome,
        "ativo": curso.ativo
    }    

# CREATE: criar disciplina
@app.post("/disciplinas", response_model=DisciplinaResponse)
def criar_disciplina(disciplina: DisciplinaCreate, db: Session = Depends(get_db)):
    nome = disciplina.nome.strip()

    existente = db.query(Disciplina).filter(
        Disciplina.nome == nome
    ).first()

    if existente:
        return existente

    nova = Disciplina(nome=nome, ativo=disciplina.ativo)
    db.add(nova)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()

        existente = db.query(Disciplina).filter(
            Disciplina.nome == nome
        ).first()

        if existente:
            return existente

        raise HTTPException(status_code=400, detail="Erro ao criar disciplina")

    db.refresh(nova)
    return nova

# READ: listar disciplinas
@app.get("/disciplinas")
def listar_disciplinas(db: Session = Depends(get_db)):
    disciplinas = db.query(Disciplina).order_by(Disciplina.id).all()
    return [{"id": d.id, "nome": d.nome, "ativo": d.ativo} for d in disciplinas]

# ASSOCIAR DISCIPLINA A CURSO (N:N)
@app.post("/cursos/{curso_id}/disciplinas/{disciplina_id}")
def associar_disciplina_ao_curso(
    curso_id: int,
    disciplina_id: int,
    db: Session = Depends(get_db)
):
    curso = db.query(Curso).filter(Curso.id == curso_id).first()
    if not curso:
        return {"erro": "Curso não encontrado"}

    disciplina = db.query(Disciplina).filter(Disciplina.id == disciplina_id).first()
    if not disciplina:
        return {"erro": "Disciplina não encontrada"}

    if disciplina not in curso.disciplinas:
        curso.disciplinas.append(disciplina)
        db.commit()

    return {"mensagem": "Disciplina associada ao curso com sucesso"}

@app.get("/cursos/{curso_id}/disciplinas")
def listar_disciplinas_do_curso(curso_id: int, db: Session = Depends(get_db)):
    curso = db.query(Curso).filter(Curso.id == curso_id).first()
    if not curso:
        return {"erro": "Curso não encontrado"}
    return [{"id": d.id, "nome": d.nome, "ativo": d.ativo} for d in curso.disciplinas]

@app.post(
    "/cursos/{curso_id}/disciplinas-proprias",
    response_model=CursoDisciplinaPropriaResponse
)
def criar_disciplina_propria(
    curso_id: int,
    dados: CursoDisciplinaPropriaCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas admin")

    curso = db.query(Curso).filter(Curso.id == curso_id).first()

    if not curso:
        raise HTTPException(status_code=404, detail="Curso não encontrado")

    disciplina = CursoDisciplinaPropria(
        curso_id=curso_id,
        nome=dados.nome.strip(),
        ativo=dados.ativo,
        ordem=dados.ordem
    )

    db.add(disciplina)
    db.commit()
    db.refresh(disciplina)

    return disciplina

@app.get("/me/cursos-expirados/{curso_id}/disciplinas")
def listar_disciplinas_curso_expirado(
    curso_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    acesso_expirado = db.query(AcessoCurso).filter(
        AcessoCurso.usuario_id == usuario.id,
        AcessoCurso.curso_id == curso_id,
        AcessoCurso.ativo == False
    ).first()

    if not acesso_expirado:
        raise HTTPException(
            status_code=403,
            detail="Sem histórico de acesso a este curso"
        )

    disciplinas = (
        db.query(CursoDisciplinaPropria)
        .filter(
            CursoDisciplinaPropria.curso_id == curso_id,
            CursoDisciplinaPropria.ativo == True
        )
        .order_by(CursoDisciplinaPropria.ordem.asc())
        .all()
    )

    return [
        {
            "id": d.id,
            "nome": d.nome,
            "ativo": d.ativo,
            "disponivel_demonstracao": d.disponivel_demonstracao
        }
        for d in disciplinas
    ]

@app.get(
    "/cursos/{curso_id}/disciplinas-proprias",
    response_model=list[CursoDisciplinaPropriaResponse]
)
def listar_disciplinas_proprias(
    curso_id: int,
    contratacao_id: int | None = None,
    demonstracao_id: int | None = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    # ---------------------------------------------------------
    # Administrador não depende de contexto de estudo.
    # Aluno continua sujeito à validação de contratação/
    # demonstração.
    # ---------------------------------------------------------
    if usuario.is_admin:
        contexto = {
            "demonstracao_id": None
        }
    else:
        contexto = validar_contexto_estudo(
            db=db,
            usuario=usuario,
            curso_id=curso_id,
            contratacao_id=contratacao_id,
            demonstracao_id=demonstracao_id,
        )

    disciplinas = (
        db.query(CursoDisciplinaPropria)
        .filter(
            CursoDisciplinaPropria.curso_id == curso_id,
            CursoDisciplinaPropria.ativo == True
        )
        .order_by(
            CursoDisciplinaPropria.ordem.asc(),
            CursoDisciplinaPropria.id.asc()
        )
        .all()
    )

    # ---------------------------------------------------------
    # Identifica se o contexto atual é uma demonstração.
    #
    # A regra já existente permanece:
    # em demonstração, somente as duas primeiras disciplinas
    # ficam disponíveis.
    # ---------------------------------------------------------
    em_demonstracao = contexto["demonstracao_id"] is not None

    return [
        {
            "id": disciplina.id,
            "curso_id": disciplina.curso_id,
            "nome": disciplina.nome,
            "ativo": disciplina.ativo,
            "ordem": disciplina.ordem,
            "bloqueada": em_demonstracao and indice >= 2
        }
        for indice, disciplina in enumerate(disciplinas)
    ]


@app.put(
    "/disciplinas-proprias/{disciplina_id}",
    response_model=CursoDisciplinaPropriaResponse
)
def editar_disciplina_propria(
    disciplina_id: int,
    dados: CursoDisciplinaPropriaUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas admin")

    disciplina = (
        db.query(CursoDisciplinaPropria)
        .filter(CursoDisciplinaPropria.id == disciplina_id)
        .first()
    )

    if not disciplina:
        raise HTTPException(status_code=404, detail="Disciplina não encontrada")

    if dados.nome is not None:
        disciplina.nome = dados.nome.strip()

    if dados.ativo is not None:
        disciplina.ativo = dados.ativo

    if dados.ordem is not None:
        disciplina.ordem = dados.ordem

    db.commit()
    db.refresh(disciplina)

    return disciplina

@app.delete("/disciplinas-proprias/{disciplina_id}")
def excluir_disciplina_propria(
    disciplina_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas admin")
        
    disciplina = (
        db.query(CursoDisciplinaPropria)
        .filter(CursoDisciplinaPropria.id == disciplina_id)
        .first()
    )

    if not disciplina:
        raise HTTPException(status_code=404, detail="Disciplina não encontrada")

    db.delete(disciplina)
    db.commit()

    return {"mensagem": "Disciplina removida com sucesso"}

@app.post(
    "/disciplinas-proprias/{disciplina_id}/assuntos-proprios",
    response_model=CursoAssuntoProprioResponse
)
def criar_assunto_proprio(
    disciplina_id: int,
    dados: CursoAssuntoProprioCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):

    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas admin")

    disciplina = (
        db.query(CursoDisciplinaPropria)
        .filter(CursoDisciplinaPropria.id == disciplina_id)
        .first()
    )

    if not disciplina:
        raise HTTPException(status_code=404, detail="Disciplina não encontrada")

    assunto = CursoAssuntoProprio(
        curso_disciplina_propria_id=disciplina_id,
        nome=dados.nome.strip(),
        descricao=dados.descricao,
        ativo=dados.ativo,
        ordem=dados.ordem
    )

    db.add(assunto)
    db.commit()
    db.refresh(assunto)

    pasta_teoria = Pasta(
        curso_assunto_proprio_id=assunto.id,
        tipo="TEORIA",
        nome="Aulas"
    )

    db.add(pasta_teoria)
    db.commit()

    return assunto

@app.get(
    "/disciplinas-proprias/{disciplina_id}/assuntos-proprios",
    response_model=list[CursoAssuntoProprioResponse]
)
def listar_assuntos_proprios(
    disciplina_id: int,
    contratacao_id: int | None = None,
    demonstracao_id: int | None = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    # ---------------------------------------------------------
    # Localiza a disciplina.
    # ---------------------------------------------------------
    disciplina = (
        db.query(CursoDisciplinaPropria)
        .filter(
            CursoDisciplinaPropria.id == disciplina_id
        )
        .first()
    )

    if not disciplina:
        raise HTTPException(
            status_code=404,
            detail="Disciplina não encontrada"
        )

    # ---------------------------------------------------------
    # Administrador não depende de contexto de estudo.
    # Aluno continua sujeito à validação de contratação/
    # demonstração.
    # ---------------------------------------------------------
    if usuario.is_admin:
        contexto = {
            "demonstracao_id": None
        }
    else:
        contexto = validar_contexto_estudo(
            db=db,
            usuario=usuario,
            curso_id=disciplina.curso_id,
            contratacao_id=contratacao_id,
            demonstracao_id=demonstracao_id,
        )

    # ---------------------------------------------------------
    # Na demonstração, somente as duas primeiras disciplinas
    # do curso ficam disponíveis.
    # ---------------------------------------------------------
    if contexto["demonstracao_id"] is not None:
        disciplinas_liberadas = (
            db.query(CursoDisciplinaPropria)
            .filter(
                CursoDisciplinaPropria.curso_id == disciplina.curso_id,
                CursoDisciplinaPropria.ativo == True
            )
            .order_by(
                CursoDisciplinaPropria.ordem.asc(),
                CursoDisciplinaPropria.id.asc()
            )
            .limit(2)
            .all()
        )

        ids_liberados = {
            item.id
            for item in disciplinas_liberadas
        }

        if disciplina_id not in ids_liberados:
            raise HTTPException(
                status_code=403,
                detail="Esta disciplina não está disponível no acesso gratuito."
            )

    # ---------------------------------------------------------
    # Retorna somente os assuntos ativos da disciplina.
    # ---------------------------------------------------------
    return (
        db.query(CursoAssuntoProprio)
        .filter(
            CursoAssuntoProprio.curso_disciplina_propria_id == disciplina_id,
            CursoAssuntoProprio.ativo == True
        )
        .order_by(
            CursoAssuntoProprio.ordem.asc(),
            CursoAssuntoProprio.id.asc()
        )
        .all()
    )

@app.put(
    "/assuntos-proprios/{assunto_id}",
    response_model=CursoAssuntoProprioResponse
)
def editar_assunto_proprio(
    assunto_id: int,
    dados: CursoAssuntoProprioUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):

    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas admin")

    assunto = (
        db.query(CursoAssuntoProprio)
        .filter(CursoAssuntoProprio.id == assunto_id)
        .first()
    )

    if not assunto:
        raise HTTPException(status_code=404, detail="Assunto não encontrado")

    if dados.nome is not None:
        assunto.nome = dados.nome.strip()

    if dados.descricao is not None:
        assunto.descricao = dados.descricao

    if dados.ativo is not None:
        assunto.ativo = dados.ativo

    if dados.ordem is not None:
        assunto.ordem = dados.ordem

    db.commit()
    db.refresh(assunto)

    return assunto

@app.delete("/assuntos-proprios/{assunto_id}")
def excluir_assunto_proprio(
    assunto_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):

    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas admin")

    assunto = (
        db.query(CursoAssuntoProprio)
        .filter(CursoAssuntoProprio.id == assunto_id)
        .first()
    )

    if not assunto:
        raise HTTPException(status_code=404, detail="Assunto não encontrado")

    db.delete(assunto)
    db.commit()

    return {"mensagem": "Assunto removido com sucesso"}



@app.post("/assuntos")
def criar_assunto(assunto: AssuntoCreate, db: Session = Depends(get_db)):
    # Confere se disciplina existe
    disciplina = db.query(Disciplina).filter(Disciplina.id == assunto.disciplina_id).first()
    if not disciplina:
        return {"erro": "Disciplina não encontrada"}

    novo = Assunto(
        disciplina_id=assunto.disciplina_id,
        nome=assunto.nome,
        descricao=assunto.descricao,
        ativo=assunto.ativo
    )
    db.add(novo)
    db.commit()
    db.refresh(novo)

    # Cria as 2 pastas padrão do assunto (se não existirem)
    pastas_padrao = [
        {"tipo": "TEORIA", "nome": "Teoria e Questões"},
        {"tipo": "INTERATIVIDADE", "nome": "Interatividade"},
    ]

    for p in pastas_padrao:
        existe = db.query(Pasta).filter(
            Pasta.assunto_id == novo.id,
            Pasta.tipo == p["tipo"]
        ).first()

        if not existe:
            db.add(Pasta(assunto_id=novo.id, tipo=p["tipo"], nome=p["nome"]))

    db.commit()

    return {
        "id": novo.id,
        "disciplina_id": novo.disciplina_id,
        "nome": novo.nome,
        "descricao": novo.descricao,
        "ativo": novo.ativo
    }

@app.get("/disciplinas/{disciplina_id}/assuntos")
def listar_assuntos_por_disciplina(disciplina_id: int, db: Session = Depends(get_db)):
    assuntos = (
        db.query(Assunto)
        .filter(Assunto.disciplina_id == disciplina_id)
        .order_by(Assunto.id)
        .all()
    )
    return [{"id": a.id, "disciplina_id": a.disciplina_id, "nome": a.nome, "descricao": a.descricao, "ativo": a.ativo} for a in assuntos]

@app.get("/assuntos/{assunto_id}/pastas")
def listar_pastas_do_assunto(assunto_id: int, db: Session = Depends(get_db)):
    pastas = (
        db.query(Pasta)
        .filter(Pasta.assunto_id == assunto_id)
        .order_by(Pasta.id)
        .all()
    )
    return [{"id": p.id, "assunto_id": p.assunto_id, "tipo": p.tipo, "nome": p.nome} for p in pastas]

@app.post("/aulas")
def criar_aula(aula: AulaCreate, db: Session = Depends(get_db), usuario: Usuario = Depends(get_usuario_atual)):

    if not usuario.is_admin:
        raise HTTPException(403, "Apenas admin")

    pasta = db.query(Pasta).filter(Pasta.id == aula.pasta_id).first()
    if not pasta:
        return {"erro": "Pasta não encontrada"}

    if pasta.curso_assunto_proprio_id:
        db.query(Pasta).filter(Pasta.id == pasta.id).with_for_update().first()
        if db.query(Aula).filter(Aula.pasta_id == pasta.id).first():
            raise HTTPException(409, "O assunto já possui sua aula técnica")

    # Regra: Aula só pode ser criada dentro da pasta TEORIA
    if pasta.tipo != "TEORIA":
        return {"erro": "Aula só pode ser criada na pasta TEORIA (Teoria e Questões)"}

    # Impede ordem repetida na mesma pasta
    existe_ordem = db.query(Aula).filter(
        Aula.pasta_id == aula.pasta_id,
        Aula.ordem == aula.ordem
    ).first()

    if existe_ordem:
        return {
            "erro": f"Já existe uma aula com ordem {aula.ordem} nesta pasta. Use outra ordem (ex.: 1, 2, 3...)."
        }

    nova = Aula(
        pasta_id=aula.pasta_id,
        titulo=aula.titulo,
        descricao=aula.descricao,
        ordem=aula.ordem,
        ativo=aula.ativo
    )
    db.add(nova)
    db.commit()
    db.refresh(nova)

    return {
        "id": nova.id,
        "pasta_id": nova.pasta_id,
        "titulo": nova.titulo,
        "descricao": nova.descricao,
        "ordem": nova.ordem,
        "ativo": nova.ativo
    }

@app.get("/pastas/{pasta_id}/aulas")
def listar_aulas_por_pasta(
    pasta_id: int,
    contratacao_id: int | None = None,
    demonstracao_id: int | None = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    # ---------------------------------------------------------
    # Localiza a pasta.
    # ---------------------------------------------------------
    pasta = (
        db.query(Pasta)
        .filter(Pasta.id == pasta_id)
        .first()
    )

    if not pasta:
        raise HTTPException(
            status_code=404,
            detail="Pasta não encontrada"
        )

    # ---------------------------------------------------------
    # ADMIN
    #
    # O administrador continua podendo listar as aulas
    # diretamente, sem necessidade de contexto de estudo.
    # ---------------------------------------------------------
    if usuario.is_admin:
        aulas = (
            db.query(Aula)
            .filter(
                Aula.pasta_id == pasta_id
            )
            .order_by(
                Aula.ordem.asc(),
                Aula.id.asc()
            )
            .all()
        )

        return [
            {
                "id": a.id,
                "pasta_id": a.pasta_id,
                "titulo": a.titulo,
                "descricao": a.descricao,
                "ordem": a.ordem,
                "ativo": a.ativo
            }
            for a in aulas
        ]

    # ---------------------------------------------------------
    # ALUNO
    #
    # Para aluno, a pasta precisa estar vinculada a um
    # assunto próprio de curso.
    # ---------------------------------------------------------
    if not pasta.curso_assunto_proprio_id:
        raise HTTPException(
            status_code=400,
            detail="Pasta não vinculada a um assunto próprio de curso"
        )

    assunto = (
        db.query(CursoAssuntoProprio)
        .filter(
            CursoAssuntoProprio.id == pasta.curso_assunto_proprio_id
        )
        .first()
    )

    if not assunto:
        raise HTTPException(
            status_code=404,
            detail="Assunto próprio do curso não encontrado"
        )

    disciplina = (
        db.query(CursoDisciplinaPropria)
        .filter(
            CursoDisciplinaPropria.id ==
            assunto.curso_disciplina_propria_id
        )
        .first()
    )

    if not disciplina:
        raise HTTPException(
            status_code=404,
            detail="Disciplina própria do curso não encontrada"
        )

    # ---------------------------------------------------------
    # Valida o contexto de estudo.
    # ---------------------------------------------------------
    validar_contexto_estudo(
        db=db,
        usuario=usuario,
        curso_id=disciplina.curso_id,
        contratacao_id=contratacao_id,
        demonstracao_id=demonstracao_id,
    )

    # ---------------------------------------------------------
    # Busca somente as aulas da pasta.
    # ---------------------------------------------------------
    aulas = (
        db.query(Aula)
        .filter(
            Aula.pasta_id == pasta_id,
            Aula.ativo == True
        )
        .order_by(
            Aula.ordem.asc(),
            Aula.id.asc()
        )
        .all()
    )

    return [
        {
            "id": a.id,
            "pasta_id": a.pasta_id,
            "titulo": a.titulo,
            "descricao": a.descricao,
            "ordem": a.ordem,
            "ativo": a.ativo
        }
        for a in aulas
    ]

@app.get("/me/progresso")
def listar_meu_progresso(
    pasta_id: int,
    contratacao_id: int | None = None,
    demonstracao_id: int | None = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    # ---------------------------------------------------------
    # Valida o contexto de estudo.
    # ---------------------------------------------------------
    if contratacao_id is None and demonstracao_id is None:
        raise HTTPException(
            status_code=400,
            detail="É necessário informar contratacao_id ou demonstracao_id"
        )

    if contratacao_id is not None and demonstracao_id is not None:
        raise HTTPException(
            status_code=400,
            detail="Informe apenas um contexto de estudo"
        )

    # ---------------------------------------------------------
    # Identifica o curso a partir da pasta.
    # ---------------------------------------------------------
    pasta = (
        db.query(Pasta)
        .filter(Pasta.id == pasta_id)
        .first()
    )

    if not pasta:
        raise HTTPException(
            status_code=404,
            detail="Pasta não encontrada"
        )

    if not pasta.curso_assunto_proprio_id:
        raise HTTPException(
            status_code=400,
            detail="Pasta não vinculada a um assunto próprio de curso"
        )

    assunto = (
        db.query(CursoAssuntoProprio)
        .filter(
            CursoAssuntoProprio.id == pasta.curso_assunto_proprio_id
        )
        .first()
    )

    if not assunto:
        raise HTTPException(
            status_code=404,
            detail="Assunto próprio do curso não encontrado"
        )

    disciplina = (
        db.query(CursoDisciplinaPropria)
        .filter(
            CursoDisciplinaPropria.id ==
            assunto.curso_disciplina_propria_id
        )
        .first()
    )

    if not disciplina:
        raise HTTPException(
            status_code=404,
            detail="Disciplina própria do curso não encontrada"
        )

    validar_contexto_estudo(
        db=db,
        usuario=usuario,
        curso_id=disciplina.curso_id,
        contratacao_id=contratacao_id,
        demonstracao_id=demonstracao_id,
    )

    # ---------------------------------------------------------
    # Busca somente o progresso do contexto informado.
    # ---------------------------------------------------------
    progresso_query = (
        db.query(ProgressoAula)
        .filter(
            ProgressoAula.usuario_id == usuario.id,
            ProgressoAula.pasta_id == pasta_id,
            ProgressoAula.concluida == True
        )
    )

    if contratacao_id is not None:
        progresso_query = progresso_query.filter(
            ProgressoAula.contratacao_id == contratacao_id,
            ProgressoAula.demonstracao_id.is_(None)
        )
    else:
        progresso_query = progresso_query.filter(
            ProgressoAula.contratacao_id.is_(None),
            ProgressoAula.demonstracao_id == demonstracao_id
        )

    progresso = progresso_query.all()

    return [
        {
            "id": p.id,
            "usuario_id": p.usuario_id,
            "pasta_id": p.pasta_id,
            "aula_id": p.aula_id,
            "concluida": p.concluida,
            "data_conclusao": p.data_conclusao
        }
        for p in progresso
    ]


@app.post("/me/progresso/aulas/{aula_id}/concluir")
def concluir_aula(
    aula_id: int,
    contratacao_id: int | None = None,
    demonstracao_id: int | None = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    # ---------------------------------------------------------
    # Valida o contexto de estudo.
    # ---------------------------------------------------------
    if contratacao_id is None and demonstracao_id is None:
        raise HTTPException(
            status_code=400,
            detail="É necessário informar contratacao_id ou demonstracao_id"
        )

    if contratacao_id is not None and demonstracao_id is not None:
        raise HTTPException(
            status_code=400,
            detail="Informe apenas um contexto de estudo"
        )

    # ---------------------------------------------------------
    # Localiza a aula.
    # ---------------------------------------------------------
    aula = (
        db.query(Aula)
        .filter(Aula.id == aula_id)
        .first()
    )

    if not aula:
        raise HTTPException(
            status_code=404,
            detail="Aula não encontrada"
        )

    # ---------------------------------------------------------
    # Identifica o curso a partir da pasta da aula.
    # ---------------------------------------------------------
    pasta = (
        db.query(Pasta)
        .filter(Pasta.id == aula.pasta_id)
        .first()
    )

    if not pasta:
        raise HTTPException(
            status_code=404,
            detail="Pasta da aula não encontrada"
        )

    if not pasta.curso_assunto_proprio_id:
        raise HTTPException(
            status_code=400,
            detail="Aula não vinculada a um assunto próprio de curso"
        )

    assunto = (
        db.query(CursoAssuntoProprio)
        .filter(
            CursoAssuntoProprio.id == pasta.curso_assunto_proprio_id
        )
        .first()
    )

    if not assunto:
        raise HTTPException(
            status_code=404,
            detail="Assunto próprio do curso não encontrado"
        )

    disciplina = (
        db.query(CursoDisciplinaPropria)
        .filter(
            CursoDisciplinaPropria.id ==
            assunto.curso_disciplina_propria_id
        )
        .first()
    )

    if not disciplina:
        raise HTTPException(
            status_code=404,
            detail="Disciplina própria do curso não encontrada"
        )

    validar_contexto_estudo(
        db=db,
        usuario=usuario,
        curso_id=disciplina.curso_id,
        contratacao_id=contratacao_id,
        demonstracao_id=demonstracao_id,
    )

    # ---------------------------------------------------------
    # Busca somente o progresso do contexto informado.
    # ---------------------------------------------------------
    progresso_query = (
        db.query(ProgressoAula)
        .filter(
            ProgressoAula.usuario_id == usuario.id,
            ProgressoAula.aula_id == aula_id
        )
    )

    if contratacao_id is not None:
        progresso_query = progresso_query.filter(
            ProgressoAula.contratacao_id == contratacao_id,
            ProgressoAula.demonstracao_id.is_(None)
        )
    else:
        progresso_query = progresso_query.filter(
            ProgressoAula.contratacao_id.is_(None),
            ProgressoAula.demonstracao_id == demonstracao_id
        )

    existente = progresso_query.first()

    if existente:
        existente.concluida = True
        existente.data_conclusao = datetime.utcnow()
        progresso = existente
    else:
        progresso = ProgressoAula(
            usuario_id=usuario.id,
            pasta_id=aula.pasta_id,
            aula_id=aula.id,
            contratacao_id=contratacao_id,
            demonstracao_id=demonstracao_id,
            concluida=True
        )
        db.add(progresso)

    db.commit()
    db.refresh(progresso)

    return progresso


@app.post("/videos")
def criar_video(video: VideoCreate, db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin_aulas)):
    provedor = (video.provedor or "").strip().upper()

    if provedor not in {"YOUTUBE", "CLOUDFLARE"}:
        raise HTTPException(
            status_code=400,
            detail="Provedor de vídeo inválido"
        )

    if provedor == "YOUTUBE" and not video.url.strip():
        raise HTTPException(
            status_code=400,
            detail="Vídeo do YouTube deve possuir URL"
        )

    if provedor == "CLOUDFLARE" and not (video.cloudflare_uid or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Vídeo do Cloudflare deve possuir UID"
        )

    bloquear_pai(db, Aula, video.aula_id)
    if not video.titulo.strip():
        raise HTTPException(400, "Informe o título")
    video.ordem = ordem_conteudo(db, Video, Video.aula_id, video.aula_id, video)
    aula = db.query(Aula).filter(Aula.id == video.aula_id).first()
    if not aula:
        return {"erro": "Aula não encontrada"}

    # ✅ Checar se já existe vídeo com a mesma ordem naquela aula
    existe_ordem = db.query(Video).filter(
        Video.aula_id == video.aula_id,
        Video.ordem == video.ordem
    ).first()

    if existe_ordem:
        return {"erro": f"Já existe um vídeo com ordem {video.ordem} nesta aula. Use outra ordem (1, 2 ou 3)."}

    # regra extra no backend (além do trigger do banco)
    total = db.query(Video).filter(Video.aula_id == video.aula_id).count()
    if total >= 20:
        return {"erro": "Limite de 20 vídeos por aula atingido"}

    novo = Video(
        aula_id=video.aula_id,
        titulo=video.titulo,
        url=video.url,
        provedor=provedor,
        cloudflare_uid=(
            (video.cloudflare_uid or "").strip()
            if provedor == "CLOUDFLARE"
            else None
        ),
        duracao_segundos=video.duracao_segundos,
        transcricao=video.transcricao,
        ordem=video.ordem,
        ativo=video.ativo
    )
    db.add(novo)
    confirmar_conteudo(db)
    db.refresh(novo)

    return {
        "id": novo.id,
        "aula_id": novo.aula_id,
        "titulo": novo.titulo,
        "url": novo.url,
        "provedor": novo.provedor,
        "cloudflare_uid": novo.cloudflare_uid,
        "duracao_segundos": novo.duracao_segundos,
        "transcricao": novo.transcricao,
        "ordem": novo.ordem,
        "ativo": novo.ativo
    }

@app.get("/aulas/{aula_id}/videos")
def listar_videos_da_aula(
    aula_id: int,
    contratacao_id: int | None = None,
    demonstracao_id: int | None = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    # ---------------------------------------------------------
    # Localiza a aula.
    # ---------------------------------------------------------
    aula = (
        db.query(Aula)
        .filter(Aula.id == aula_id)
        .first()
    )

    if not aula:
        raise HTTPException(
            status_code=404,
            detail="Aula não encontrada"
        )

    # ---------------------------------------------------------
    # ADMIN
    # ---------------------------------------------------------
    if usuario.is_admin:
        videos = (
            db.query(Video)
            .filter(Video.aula_id == aula_id)
            .order_by(
                Video.ordem.asc(),
                Video.id.asc()
            )
            .all()
        )

        return [
            {
                "id": v.id,
                "aula_id": v.aula_id,
                "titulo": v.titulo,
                "url": v.url,
                "provedor": v.provedor,
                "cloudflare_uid": v.cloudflare_uid,
                "duracao_segundos": v.duracao_segundos,
                "transcricao": v.transcricao,
                "ordem": v.ordem,
                "ativo": v.ativo
            }
            for v in videos
        ]

    # ---------------------------------------------------------
    # ALUNO: identifica o curso da aula.
    # ---------------------------------------------------------
    pasta = (
        db.query(Pasta)
        .filter(Pasta.id == aula.pasta_id)
        .first()
    )

    if not pasta:
        raise HTTPException(
            status_code=404,
            detail="Pasta da aula não encontrada"
        )

    if not pasta.curso_assunto_proprio_id:
        raise HTTPException(
            status_code=400,
            detail="Aula não vinculada a um assunto próprio de curso"
        )

    assunto = (
        db.query(CursoAssuntoProprio)
        .filter(
            CursoAssuntoProprio.id ==
            pasta.curso_assunto_proprio_id
        )
        .first()
    )

    if not assunto:
        raise HTTPException(
            status_code=404,
            detail="Assunto próprio do curso não encontrado"
        )

    disciplina = (
        db.query(CursoDisciplinaPropria)
        .filter(
            CursoDisciplinaPropria.id ==
            assunto.curso_disciplina_propria_id
        )
        .first()
    )

    if not disciplina:
        raise HTTPException(
            status_code=404,
            detail="Disciplina própria do curso não encontrada"
        )

    # ---------------------------------------------------------
    # Valida o contexto de estudo.
    # ---------------------------------------------------------
    validar_contexto_estudo(
        db=db,
        usuario=usuario,
        curso_id=disciplina.curso_id,
        contratacao_id=contratacao_id,
        demonstracao_id=demonstracao_id,
    )

    # ---------------------------------------------------------
    # Busca os vídeos da aula.
    # ---------------------------------------------------------
    videos = (
        db.query(Video)
        .filter(
            Video.aula_id == aula_id,
            Video.ativo == True
        )
        .order_by(
            Video.ordem.asc(),
            Video.id.asc()
        )
        .all()
    )

    return [
        {
            "id": v.id,
            "aula_id": v.aula_id,
            "titulo": v.titulo,
            "url": v.url,
            "provedor": v.provedor,
            "cloudflare_uid": v.cloudflare_uid,
            "duracao_segundos": v.duracao_segundos,
            "transcricao": v.transcricao,
            "ordem": v.ordem,
            "ativo": v.ativo
        }
        for v in videos
    ]

@app.put("/videos/{video_id}")
def editar_video(
    video_id: int,
    dados: VideoCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(exigir_admin_aulas)
):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Vídeo não encontrado")
    bloquear_pai(db, Aula, video.aula_id)
    validar_vinculo(dados, video, "aula_id")
    dados = dados.model_copy(update={
        campo: getattr(video, campo)
        for campo in ("provedor", "url", "cloudflare_uid")
        if campo not in dados.model_fields_set
    })
    provedor = (dados.provedor or "").strip().upper()

    if provedor not in {"YOUTUBE", "CLOUDFLARE"}:
        raise HTTPException(
            status_code=400,
            detail="Provedor de vídeo inválido"
        )

    if provedor == "YOUTUBE" and not dados.url.strip():
        raise HTTPException(
            status_code=400,
            detail="Vídeo do YouTube deve possuir URL"
        )

    if provedor == "CLOUDFLARE" and not (dados.cloudflare_uid or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Vídeo do Cloudflare deve possuir UID"
        )

    if not dados.titulo.strip():
        raise HTTPException(400, "Informe o título do vídeo")
    video.ordem = ordem_conteudo(db, Video, Video.aula_id, video.aula_id, dados, video)
    video.titulo = dados.titulo
    video.url = dados.url
    video.provedor = provedor
    video.cloudflare_uid = (
        (dados.cloudflare_uid or "").strip()
        if provedor == "CLOUDFLARE"
        else None
    )
    if "duracao_segundos" in dados.model_fields_set:
        video.duracao_segundos = dados.duracao_segundos
    if "transcricao" in dados.model_fields_set:
        video.transcricao = dados.transcricao
    if "ativo" in dados.model_fields_set:
        video.ativo = dados.ativo

    confirmar_conteudo(db)
    db.refresh(video)

    return {
        "id": video.id,
        "aula_id": video.aula_id,
        "titulo": video.titulo,
        "url": video.url,
        "provedor": video.provedor,
        "cloudflare_uid": video.cloudflare_uid,
        "duracao_segundos": video.duracao_segundos,
        "transcricao": video.transcricao,
        "ordem": video.ordem,
        "ativo": video.ativo
    }

@app.get("/videos/{video_id}/playback")
def obter_playback_video(
    video_id: int,
    contratacao_id: int | None = None,
    demonstracao_id: int | None = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    video = db.query(Video).filter(
        Video.id == video_id,
        Video.ativo == True
    ).first()

    if not video:
        raise HTTPException(
            status_code=404,
            detail="Vídeo não encontrado"
        )

    if (video.provedor or "").upper() != "CLOUDFLARE":
        raise HTTPException(
            status_code=400,
            detail="Este vídeo não utiliza Cloudflare Stream"
        )

    if not video.cloudflare_uid:
        raise HTTPException(
            status_code=500,
            detail="Vídeo Cloudflare sem UID configurado"
        )

    aula = db.query(Aula).filter(
        Aula.id == video.aula_id
    ).first()

    if not aula:
        raise HTTPException(
            status_code=404,
            detail="Aula do vídeo não encontrada"
        )

    pasta = db.query(Pasta).filter(
        Pasta.id == aula.pasta_id
    ).first()

    if not pasta:
        raise HTTPException(
            status_code=404,
            detail="Pasta da aula não encontrada"
        )

    if not pasta.curso_assunto_proprio_id:
        raise HTTPException(
            status_code=400,
            detail="Vídeo não vinculado a um assunto próprio de curso"
        )

    assunto = db.query(CursoAssuntoProprio).filter(
        CursoAssuntoProprio.id == pasta.curso_assunto_proprio_id
    ).first()

    if not assunto:
        raise HTTPException(
            status_code=404,
            detail="Assunto próprio do curso não encontrado"
        )

    disciplina = db.query(CursoDisciplinaPropria).filter(
        CursoDisciplinaPropria.id == assunto.curso_disciplina_propria_id
    ).first()

    if not disciplina:
        raise HTTPException(
            status_code=404,
            detail="Disciplina própria do curso não encontrada"
        )

    curso_id = disciplina.curso_id

        # ---------------------------------------------------------
    # Valida o contexto de estudo.
    # ---------------------------------------------------------
    validar_contexto_estudo(
        db=db,
        usuario=usuario,
        curso_id=curso_id,
        contratacao_id=contratacao_id,
        demonstracao_id=demonstracao_id,
    )

    # ---------------------------------------------------------
    # Na demonstração, somente as 2 primeiras disciplinas
    # do curso ficam disponíveis.
    # ---------------------------------------------------------
    if demonstracao_id is not None:
        disciplinas_liberadas = (
            db.query(CursoDisciplinaPropria)
            .filter(
                CursoDisciplinaPropria.curso_id == curso_id,
                CursoDisciplinaPropria.ativo == True
            )
            .order_by(
                CursoDisciplinaPropria.ordem.asc(),
                CursoDisciplinaPropria.id.asc()
            )
            .limit(2)
            .all()
        )

        ids_liberados = {
            item.id
            for item in disciplinas_liberadas
        }

        if disciplina.id not in ids_liberados:
            raise HTTPException(
                status_code=403,
                detail="Esta disciplina não está disponível no acesso gratuito."
            )

    if not CLOUDFLARE_ACCOUNT_ID or not CLOUDFLARE_STREAM_API_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="Cloudflare Stream não configurado no servidor"
        )

    endpoint_cloudflare = (
        f"https://api.cloudflare.com/client/v4/accounts/"
        f"{CLOUDFLARE_ACCOUNT_ID}/stream/"
        f"{video.cloudflare_uid}/token"
    )

    try:
        resposta = requests.post(
            endpoint_cloudflare,
            headers={
                "Authorization": f"Bearer {CLOUDFLARE_STREAM_API_TOKEN}"
            },
            timeout=10
        )
    except requests.RequestException:
        raise HTTPException(
            status_code=502,
            detail="Não foi possível comunicar com o Cloudflare Stream"
        )

    if not resposta.ok:
        raise HTTPException(
            status_code=502,
            detail="Cloudflare Stream não conseguiu gerar o token do vídeo"
        )

    try:
        dados_cloudflare = resposta.json()
    except ValueError:
        raise HTTPException(
            status_code=502,
            detail="Cloudflare Stream retornou uma resposta inválida"
        )

    token = (dados_cloudflare.get("result") or {}).get("token")

    if not token:
        raise HTTPException(
            status_code=502,
            detail="Cloudflare Stream não retornou token de reprodução"
        )

    return {
        "video_id": video.id,
        "token": token
    }

@app.post("/baterias")
def criar_bateria(bateria: BateriaCreate, db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin_aulas)):
    bloquear_pai(db, Aula, bateria.aula_id)
    if bateria.status != "EM_ANDAMENTO":
        raise HTTPException(400, "Crie a bateria em rascunho e conclua após cadastrar as 10 questões")
    if not bateria.titulo.strip():
        raise HTTPException(400, "Informe o título")
    bateria.ordem = ordem_conteudo(db, Bateria, Bateria.aula_id, bateria.aula_id, bateria)
    aula = db.query(Aula).filter(Aula.id == bateria.aula_id).first()
    if not aula:
        return {"erro": "Aula não encontrada"}

    # checa limite 3 (backend) - além do trigger do banco
    total = db.query(Bateria).filter(Bateria.aula_id == bateria.aula_id).count()
    if total >= 20:
        return {"erro": "Limite de 20 baterias (sprints) por aula atingido"}

    # checa ordem única por aula (mensagem amigável)
    existe_ordem = db.query(Bateria).filter(
        Bateria.aula_id == bateria.aula_id,
        Bateria.ordem == bateria.ordem
    ).first()
    if existe_ordem:
        return {"erro": f"Já existe uma bateria com ordem {bateria.ordem} nesta aula. Use 1, 2 ou 3."}

    nova = Bateria(
        aula_id=bateria.aula_id,
        titulo=bateria.titulo,
        ordem=bateria.ordem,
        status=bateria.status or "EM_ANDAMENTO",
        ativo=bateria.ativo
    )
    db.add(nova)
    confirmar_conteudo(db)
    db.refresh(nova)

    return {
        "id": nova.id,
        "aula_id": nova.aula_id,
        "titulo": nova.titulo,
        "ordem": nova.ordem,
        "status": nova.status,
        "ativo": nova.ativo
    }

@app.get("/aulas/{aula_id}/baterias")
def listar_baterias_da_aula(
    aula_id: int,
    contratacao_id: int | None = None,
    demonstracao_id: int | None = None,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    aula = db.query(Aula).filter(Aula.id == aula_id).first()

    if not aula:
        raise HTTPException(
            status_code=404,
            detail="Aula não encontrada"
        )

    if not usuario_atual.is_admin:
        pasta = db.query(Pasta).filter(Pasta.id == aula.pasta_id).first()

        if not pasta:
            raise HTTPException(
                status_code=404,
                detail="Pasta da aula não encontrada"
            )

        if not pasta.curso_assunto_proprio_id:
            raise HTTPException(
                status_code=400,
                detail="Aula não vinculada a um assunto próprio de curso"
            )

        assunto = db.query(CursoAssuntoProprio).filter(
            CursoAssuntoProprio.id == pasta.curso_assunto_proprio_id
        ).first()

        if not assunto:
            raise HTTPException(
                status_code=404,
                detail="Assunto próprio do curso não encontrado"
            )

        disciplina = db.query(CursoDisciplinaPropria).filter(
            CursoDisciplinaPropria.id == assunto.curso_disciplina_propria_id
        ).first()

        if not disciplina:
            raise HTTPException(
                status_code=404,
                detail="Disciplina própria do curso não encontrada"
            )

        validar_contexto_estudo(
            db=db,
            usuario=usuario_atual,
            curso_id=disciplina.curso_id,
            contratacao_id=contratacao_id,
            demonstracao_id=demonstracao_id,
        )

    baterias = (
        db.query(Bateria)
        .filter(Bateria.aula_id == aula_id)
        .order_by(Bateria.ordem.asc(), Bateria.id.asc())
        .all()
    )
    return [
        {
            "id": b.id,
            "aula_id": b.aula_id,
            "titulo": b.titulo,
            "ordem": b.ordem,
            "status": b.status,
            "ativo": b.ativo,
            "questoes_count": db.query(Questao).filter(
                Questao.bateria_id == b.id
            ).count()
        }
        for b in baterias
    ]

@app.post("/questoes")
def criar_questao(questao: QuestaoCreate, db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin_aulas)):
    bateria = bloquear_pai(db, Bateria, questao.bateria_id)
    alternativas = validar_alternativas(questao)
    questao.ordem = ordem_conteudo(db, Questao, Questao.bateria_id, questao.bateria_id, questao)
    if db.query(Questao).filter_by(bateria_id=bateria.id).count() >= 10:
        raise HTTPException(400, "A bateria já possui 10 questões")
    bateria = db.query(Bateria).filter(Bateria.id == questao.bateria_id).first()

    if not bateria:
        return {"erro": "Bateria não encontrada"}

    existe_ordem = db.query(Questao).filter(
        Questao.bateria_id == questao.bateria_id,
        Questao.ordem == questao.ordem
    ).first()

    if existe_ordem:
        return {"erro": f"Já existe questão com ordem {questao.ordem} nesta bateria"}

    tipo_questao = (questao.tipo_questao or "").strip().upper()

    if tipo_questao not in ("MULTIPLA_5", "MULTIPLA_4", "CERTO_ERRADO"):
        return {"erro": "Tipo de questão inválido"}

    if tipo_questao == "MULTIPLA_5":
        tipo = "MULTIPLA"
        quantidade_alternativas = 5
        gabaritos_validos = ("A", "B", "C", "D", "E")
    elif tipo_questao == "MULTIPLA_4":
        tipo = "MULTIPLA"
        quantidade_alternativas = 4
        gabaritos_validos = ("A", "B", "C", "D")
    else:
        tipo = "CERTO_ERRADO"
        quantidade_alternativas = 2
        gabaritos_validos = ("C", "E")

    gabarito = (questao.gabarito or "").strip().upper()

    if gabarito not in gabaritos_validos:
        return {"erro": "Gabarito inválido para o tipo de questão selecionado"}

    nova = Questao(
        bateria_id=questao.bateria_id,
        enunciado=questao.enunciado.strip(),
        tipo=tipo,
        tipo_questao=tipo_questao,
        quantidade_alternativas=quantidade_alternativas,
        gabarito=gabarito,
        comentario=questao.comentario.strip() if questao.comentario else None,
        ordem=questao.ordem,
        ativo=questao.ativo
    )

    db.add(nova)
    confirmar_conteudo(db, flush=True)
    sincronizar_alternativas(db, nova, alternativas)
    bateria.status = "EM_ANDAMENTO"
    confirmar_conteudo(db)
    db.refresh(nova)

    return {
        "id": nova.id,
        "bateria_id": nova.bateria_id,
        "enunciado": nova.enunciado,
        "tipo": nova.tipo,
        "tipo_questao": nova.tipo_questao,
        "quantidade_alternativas": nova.quantidade_alternativas,
        "gabarito": nova.gabarito,
        "comentario": nova.comentario,
        "ordem": nova.ordem,
        "ativo": nova.ativo
    }

@app.put("/questoes/{questao_id}")
def editar_questao(
    questao_id: int,
    dados: QuestaoCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(exigir_admin_aulas)
):
    questao = db.query(Questao).filter(Questao.id == questao_id).first()

    if not questao:
        raise HTTPException(status_code=404, detail="Questão não encontrada")

    bateria = bloquear_pai(db, Bateria, questao.bateria_id)
    validar_vinculo(dados, questao, "bateria_id")
    alternativas = validar_alternativas(dados, questao)
    if dados.tipo_questao.strip().upper() != questao.tipo_questao:
        garantir_sem_historico(db, bateria)
    questao.ordem = ordem_conteudo(db, Questao, Questao.bateria_id, questao.bateria_id, dados, questao)
    tipo_questao = (dados.tipo_questao or "").strip().upper()

    if tipo_questao not in ("MULTIPLA_5", "MULTIPLA_4", "CERTO_ERRADO"):
        return {"erro": "Tipo de questão inválido"}

    if tipo_questao == "MULTIPLA_5":
        tipo = "MULTIPLA"
        quantidade_alternativas = 5
        gabaritos_validos = ("A", "B", "C", "D", "E")
    elif tipo_questao == "MULTIPLA_4":
        tipo = "MULTIPLA"
        quantidade_alternativas = 4
        gabaritos_validos = ("A", "B", "C", "D")
    else:
        tipo = "CERTO_ERRADO"
        quantidade_alternativas = 2
        gabaritos_validos = ("C", "E")

    gabarito = (dados.gabarito or "").strip().upper()

    if gabarito not in gabaritos_validos:
        return {"erro": "Gabarito inválido para o tipo de questão selecionado"}

    questao.enunciado = dados.enunciado.strip()
    questao.tipo = tipo
    questao.tipo_questao = tipo_questao
    questao.quantidade_alternativas = quantidade_alternativas
    questao.gabarito = gabarito
    questao.comentario = dados.comentario.strip() if dados.comentario else None
    if "ativo" in dados.model_fields_set:
        questao.ativo = dados.ativo

    sincronizar_alternativas(db, questao, alternativas)
    confirmar_conteudo(db)
    db.refresh(questao)

    return {
        "id": questao.id,
        "bateria_id": questao.bateria_id,
        "enunciado": questao.enunciado,
        "tipo": questao.tipo,
        "tipo_questao": questao.tipo_questao,
        "quantidade_alternativas": questao.quantidade_alternativas,
        "gabarito": questao.gabarito,
        "comentario": questao.comentario,
        "ordem": questao.ordem,
        "ativo": questao.ativo
    }

@app.delete("/questoes/{questao_id}")
def excluir_questao(
    questao_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(exigir_admin_aulas)
):
    questao = db.query(Questao).filter(Questao.id == questao_id).first()

    if not questao:
        raise HTTPException(status_code=404, detail="Questão não encontrada")

    bateria = bloquear_pai(db, Bateria, questao.bateria_id)
    garantir_sem_historico(db, bateria)
    db.query(Comentario).filter(Comentario.questao_id == questao_id).delete(synchronize_session=False)
    db.query(Alternativa).filter(Alternativa.questao_id == questao_id).delete(synchronize_session=False)
    db.delete(questao)
    bateria.status = "EM_ANDAMENTO"
    confirmar_conteudo(db)

    return {"mensagem": "Questão excluída com sucesso!"}

@app.post("/questoes/{questao_id}/alternativas")
def criar_alternativa(
    questao_id: int,
    alt: AlternativaCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(exigir_admin_aulas)
):
    questao = db.query(Questao).filter(Questao.id == questao_id).first()

    if not questao:
        return {"erro": "Questão não encontrada"}

    bateria = bloquear_pai(db, Bateria, questao.bateria_id)
    if bateria.status == "CONCLUIDA":
        raise HTTPException(409, "Edite a questão completa para alterar uma bateria concluída")
    if questao.tipo != "MULTIPLA":
        return {"erro": "Alternativas só podem ser adicionadas a questões de múltipla escolha"}

    letra = alt.letra.strip().upper()

    letras_validas = ("A", "B", "C", "D", "E") if questao.quantidade_alternativas == 5 else ("A", "B", "C", "D")

    if letra not in letras_validas:
        return {"erro": "Letra inválida para o tipo de questão selecionado"}

    existe = db.query(Alternativa).filter(
        Alternativa.questao_id == questao_id,
        Alternativa.letra == letra
    ).first()

    if existe:
        return {"erro": f"Já existe alternativa {letra} nesta questão"}

    nova_alt = Alternativa(
        questao_id=questao_id,
        letra=letra,
        texto=alt.texto.strip()
    )

    db.add(nova_alt)
    confirmar_conteudo(db)
    db.refresh(nova_alt)

    return {
        "id": nova_alt.id,
        "questao_id": nova_alt.questao_id,
        "letra": nova_alt.letra,
        "texto": nova_alt.texto
    }

@app.post("/questoes/{questao_id}/comentario-geral")
def criar_comentario_geral(questao_id: int, payload: ComentarioGeralCreate, db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin_aulas)):
    questao = db.query(Questao).filter(Questao.id == questao_id).first()
    if not questao:
        return {"erro": "Questão não encontrada"}

    bateria = bloquear_pai(db, Bateria, questao.bateria_id)
    if bateria.status == "CONCLUIDA":
        raise HTTPException(409, "Edite a questão completa para alterar uma bateria concluída")
    if questao.tipo != "CERTO_ERRADO":
        return {"erro": "Comentário geral é usado apenas em questões do tipo CERTO_ERRADO"}

    existe = db.query(Comentario).filter(
        Comentario.questao_id == questao_id,
        Comentario.alternativa_id.is_(None)
    ).first()
    if existe:
        return {"erro": "Já existe comentário geral para esta questão."}

    novo = Comentario(
        questao_id=questao_id,
        alternativa_id=None,
        texto=payload.texto
    )
    db.add(novo)
    confirmar_conteudo(db)
    db.refresh(novo)

    return {"id": novo.id, "questao_id": novo.questao_id, "texto": novo.texto}


@app.get("/baterias/{bateria_id}/questoes")
def listar_questoes_da_bateria(
    bateria_id: int,
    contratacao_id: int | None = None,
    demonstracao_id: int | None = None,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    bateria = db.query(Bateria).filter(
        Bateria.id == bateria_id
    ).first()

    if not bateria:
        raise HTTPException(
            status_code=404,
            detail="Bateria não encontrada"
        )

    if usuario_atual.is_admin:
        questoes = db.query(Questao).filter(Questao.bateria_id == bateria_id).order_by(Questao.ordem, Questao.id).all()
    else:
        aula = db.query(Aula).filter(
            Aula.id == bateria.aula_id
        ).first()

        if not aula:
            raise HTTPException(
                status_code=404,
                detail="Aula da bateria não encontrada"
            )

        pasta = db.query(Pasta).filter(
            Pasta.id == aula.pasta_id
        ).first()

        if not pasta:
            raise HTTPException(
                status_code=404,
                detail="Pasta da aula não encontrada"
            )

        if not pasta.curso_assunto_proprio_id:
            raise HTTPException(
                status_code=400,
                detail="Bateria não vinculada a um assunto próprio de curso"
            )

        assunto = db.query(CursoAssuntoProprio).filter(
            CursoAssuntoProprio.id == pasta.curso_assunto_proprio_id
        ).first()

        if not assunto:
            raise HTTPException(
                status_code=404,
                detail="Assunto próprio do curso não encontrado"
            )

        disciplina = db.query(CursoDisciplinaPropria).filter(
            CursoDisciplinaPropria.id == assunto.curso_disciplina_propria_id
        ).first()

        if not disciplina:
            raise HTTPException(
                status_code=404,
                detail="Disciplina própria do curso não encontrada"
            )

        validar_contexto_estudo(
            db=db,
            usuario=usuario_atual,
            curso_id=disciplina.curso_id,
            contratacao_id=contratacao_id,
            demonstracao_id=demonstracao_id,
        )

        from app.revisoes import disponiveis
        questoes = next((qs for b, qs in disponiveis(db, aula.id) if b.id == bateria_id), None)
        if questoes is None:
            raise HTTPException(404, "Bateria indisponível ao aluno")

    resultado = []

    for q in questoes:
        alternativas = (
            db.query(Alternativa)
            .filter(Alternativa.questao_id == q.id)
            .order_by(Alternativa.letra.asc())
            .all()
        )

        resultado.append({
            "id": q.id,
            "bateria_id": q.bateria_id,
            "enunciado": q.enunciado,
            "tipo": q.tipo,
            "tipo_questao": q.tipo_questao,
            "quantidade_alternativas": q.quantidade_alternativas,
            "gabarito": q.gabarito,
            "comentario": q.comentario,
            "ordem": q.ordem,
            "ativo": q.ativo,
            "alternativas": [
                {
                    "id": a.id,
                    "letra": a.letra,
                    "texto": a.texto
                }
                for a in alternativas
            ]
        })

    return resultado

@app.post("/baterias/{bateria_id}/gerar-10-questoes")
def gerar_10_questoes(bateria_id: int, payload: Sprint10Create, db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin_aulas)):
    bloquear_pai(db, Bateria, bateria_id)
    # valida bateria
    bateria = db.query(Bateria).filter(Bateria.id == bateria_id).first()
    if not bateria:
        return {"erro": "Bateria (Sprint) não encontrada"}

    # valida coerência do body
    if payload.bateria_id != bateria_id:
        return {"erro": "bateria_id do path e do body não conferem"}

    tipo = payload.tipo.strip().upper()
    if tipo not in ("MULTIPLA", "CERTO_ERRADO"):
        return {"erro": "Tipo inválido. Use 'MULTIPLA' ou 'CERTO_ERRADO'."}

    # Se não vierem enunciados, gera placeholders
    if not payload.enunciados:
        enunciados = [f"Questão {i} (editar depois)" for i in range(1, 11)]
    else:
        enunciados = payload.enunciados

    if len(enunciados) != 10:
        return {"erro": "Você deve enviar exatamente 10 enunciados (ou nenhum)."}

    # checa quantas questões já existem
    total_existentes = db.query(Questao).filter(Questao.bateria_id == bateria_id).count()
    if total_existentes > 0:
        return {"erro": f"Esta bateria já tem {total_existentes} questão(ões). Use uma bateria vazia para gerar as 10."}

    criadas = []

    for i, enun in enumerate(enunciados, start=1): 
        q = Questao(
            bateria_id=bateria_id,
            enunciado=enun,
            tipo=tipo,
            ordem=i,
            ativo=True
        )
        db.add(q)
        db.flush()
        db.refresh(q)

        # Se MULTIPLA: cria A-E com placeholders + comentários
        if tipo == "MULTIPLA":
            alternativas_padrao = [
                ("A", "Alternativa A (editar depois)", "Comentário A (sem dizer se está certa/errada)."),
                ("B", "Alternativa B (editar depois)", "Comentário B (sem dizer se está certa/errada)."),
                ("C", "Alternativa C (editar depois)", "Comentário C (sem dizer se está certa/errada)."),
                ("D", "Alternativa D (editar depois)", "Comentário D (sem dizer se está certa/errada)."),
                ("E", "Alternativa E (editar depois)", "Comentário E (sem dizer se está certa/errada)."),
            ]

            for letra, texto, comentario in alternativas_padrao:
                alt = Alternativa(questao_id=q.id, letra=letra, texto=texto)
                db.add(alt)
                db.flush()
                db.refresh(alt)

                db.add(Comentario(questao_id=q.id, alternativa_id=alt.id, texto=comentario))
                db.flush()

        # Se CERTO_ERRADO: cria comentário geral placeholder
        if tipo == "CERTO_ERRADO":
            db.add(Comentario(
                questao_id=q.id,
                alternativa_id=None,
                texto="Comentário geral (sem dizer explicitamente certo/errado)."
            ))
            db.flush()

        criadas.append({"questao_id": q.id, "ordem": q.ordem})

    confirmar_conteudo(db)

    return {
        "bateria_id": bateria_id,
        "tipo": tipo,
        "questoes_criadas": len(criadas),
        "ids": criadas
    }

@app.put("/baterias/{bateria_id}")
def editar_bateria(
    bateria_id: int,
    dados: BateriaCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(exigir_admin_aulas)
):
    bateria = db.query(Bateria).filter(Bateria.id == bateria_id).first()

    if not bateria:
        raise HTTPException(status_code=404, detail="Bateria não encontrada")

    bloquear_pai(db, Aula, bateria.aula_id)
    validar_vinculo(dados, bateria, "aula_id")
    titulo = dados.titulo.strip()
    if not titulo:
        raise HTTPException(400, "Informe o título da bateria")
    bateria.titulo = titulo
    bateria.ordem = ordem_conteudo(db, Bateria, Bateria.aula_id, bateria.aula_id, dados, bateria)
    if "status" in dados.model_fields_set:
        if dados.status not in {"EM_ANDAMENTO", "CONCLUIDA"}:
            raise HTTPException(400, "Status de bateria inválido")
        if dados.status == "CONCLUIDA":
            validar_conclusao(db, bateria)
        bateria.status = dados.status
    if "ativo" in dados.model_fields_set:
        bateria.ativo = dados.ativo

    confirmar_conteudo(db)
    db.refresh(bateria)

    return {
        "id": bateria.id,
        "aula_id": bateria.aula_id,
        "titulo": bateria.titulo,
        "ordem": bateria.ordem,
        "status": bateria.status,
        "ativo": bateria.ativo
    }

@app.put("/baterias/{bateria_id}/concluir")
def concluir_bateria(
    bateria_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(exigir_admin_aulas)
):
    bateria = bloquear_pai(db, Bateria, bateria_id)
    validar_conclusao(db, bateria)

    bateria.status = "CONCLUIDA"

    confirmar_conteudo(db)
    db.refresh(bateria)

    return {
        "id": bateria.id,
        "aula_id": bateria.aula_id,
        "titulo": bateria.titulo,
        "ordem": bateria.ordem,
        "status": bateria.status,
        "ativo": bateria.ativo
    }

@app.post("/materiais")
def criar_material(material: MaterialCreate, db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin_aulas)):
    bloquear_pai(db, Aula, material.aula_id)
    if not material.titulo.strip():
        raise HTTPException(400, "Informe o título")
    material.ordem = ordem_conteudo(db, Material, Material.aula_id, material.aula_id, material)
    material.tipo = validar_material(material)
    aula = db.query(Aula).filter(Aula.id == material.aula_id).first()
    if not aula:
        return {"erro": "Aula não encontrada"}

    tipo = material.tipo.strip().upper()
    if tipo not in ("PDF", "LINK", "TEXTO"):
        return {"erro": "Tipo inválido. Use 'PDF', 'LINK' ou 'TEXTO'."}

    # limite 3 (backend) além do trigger
    total = db.query(Material).filter(Material.aula_id == material.aula_id).count()
    if total >= 20:
        return {"erro": "Limite de 20 materiais por aula atingido"}

    # ordem única por aula
    existe_ordem = db.query(Material).filter(
        Material.aula_id == material.aula_id,
        Material.ordem == material.ordem
    ).first()
    if existe_ordem:
        return {"erro": f"Já existe material com ordem {material.ordem} nesta aula. Use 1, 2 ou 3."}

    # valida campos conforme tipo
    if tipo in ("PDF", "LINK") and (not material.url or not material.url.strip()):
        return {"erro": "Para tipo PDF/LINK, informe 'url'."}

    if tipo == "TEXTO" and (not material.conteudo or not material.conteudo.strip()):
        return {"erro": "Para tipo TEXTO, informe 'conteudo'."}

    novo = Material(
        aula_id=material.aula_id,
        tipo=tipo,
        titulo=material.titulo,
        url=material.url.strip() if material.url else None,
        conteudo=material.conteudo.strip() if material.conteudo else None,
        ordem=material.ordem,
        ativo=material.ativo
    )
    db.add(novo)
    confirmar_conteudo(db)
    db.refresh(novo)

    return {
        "id": novo.id,
        "aula_id": novo.aula_id,
        "tipo": novo.tipo,
        "titulo": novo.titulo,
        "url": novo.url,
        "conteudo": novo.conteudo,
        "ordem": novo.ordem,
        "ativo": novo.ativo
    }

@app.get("/aulas/{aula_id}/materiais")
def listar_materiais_da_aula(
    aula_id: int,
    contratacao_id: int | None = None,
    demonstracao_id: int | None = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    # ---------------------------------------------------------
    # Localiza a aula.
    # ---------------------------------------------------------
    aula = (
        db.query(Aula)
        .filter(Aula.id == aula_id)
        .first()
    )

    if not aula:
        raise HTTPException(
            status_code=404,
            detail="Aula não encontrada"
        )

    if usuario.is_admin:
        materiais = db.query(Material).filter(Material.aula_id == aula_id).order_by(Material.ordem, Material.id).all()
        return [{"id": m.id, "aula_id": m.aula_id, "tipo": m.tipo,
                 "titulo": m.titulo, "url": m.url, "conteudo": m.conteudo,
                 "ordem": m.ordem, "ativo": m.ativo} for m in materiais]

    # ---------------------------------------------------------
    # Localiza a pasta da aula.
    # ---------------------------------------------------------
    pasta = (
        db.query(Pasta)
        .filter(Pasta.id == aula.pasta_id)
        .first()
    )

    if not pasta:
        raise HTTPException(
            status_code=404,
            detail="Pasta da aula não encontrada"
        )

    if not pasta.curso_assunto_proprio_id:
        raise HTTPException(
            status_code=400,
            detail="Aula não vinculada a um assunto próprio de curso"
        )

    # ---------------------------------------------------------
    # Localiza o assunto próprio.
    # ---------------------------------------------------------
    assunto = (
        db.query(CursoAssuntoProprio)
        .filter(
            CursoAssuntoProprio.id == pasta.curso_assunto_proprio_id
        )
        .first()
    )

    if not assunto:
        raise HTTPException(
            status_code=404,
            detail="Assunto próprio do curso não encontrado"
        )

    # ---------------------------------------------------------
    # Localiza a disciplina própria.
    # ---------------------------------------------------------
    disciplina = (
        db.query(CursoDisciplinaPropria)
        .filter(
            CursoDisciplinaPropria.id ==
            assunto.curso_disciplina_propria_id
        )
        .first()
    )

    if not disciplina:
        raise HTTPException(
            status_code=404,
            detail="Disciplina própria do curso não encontrada"
        )

    # ---------------------------------------------------------
    # Valida o contexto de estudo.
    # ---------------------------------------------------------
    validar_contexto_estudo(
        db=db,
        usuario=usuario,
        curso_id=disciplina.curso_id,
        contratacao_id=contratacao_id,
        demonstracao_id=demonstracao_id,
    )

    # ---------------------------------------------------------
    # Busca somente os materiais ativos da aula.
    # ---------------------------------------------------------
    materiais = (
        db.query(Material)
        .filter(
            Material.aula_id == aula_id,
            Material.ativo == True
        )
        .order_by(
            Material.ordem.asc(),
            Material.id.asc()
        )
        .all()
    )

    return [
        {
            "id": m.id,
            "aula_id": m.aula_id,
            "tipo": m.tipo,
            "titulo": m.titulo,
            "url": m.url,
            "conteudo": m.conteudo,
            "ordem": m.ordem,
            "ativo": m.ativo
        }
        for m in materiais
    ]

@app.put("/materiais/{material_id}")
def editar_material(
    material_id: int,
    dados: MaterialCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(exigir_admin_aulas)
):
    material = db.query(Material).filter(Material.id == material_id).first()

    if not material:
        raise HTTPException(status_code=404, detail="Material não encontrado")

    bloquear_pai(db, Aula, material.aula_id)
    validar_vinculo(dados, material, "aula_id")
    dados = dados.model_copy(update={
        campo: getattr(material, campo)
        for campo in ("url", "conteudo") if campo not in dados.model_fields_set
    })
    tipo = validar_material(dados)
    material.ordem = ordem_conteudo(db, Material, Material.aula_id, material.aula_id, dados, material)
    material.titulo = dados.titulo.strip()
    material.tipo = tipo
    for campo in ("url", "conteudo", "ativo"):
        if campo in dados.model_fields_set:
            setattr(material, campo, getattr(dados, campo))

    confirmar_conteudo(db)
    db.refresh(material)

    return {
        "id": material.id,
        "aula_id": material.aula_id,
        "tipo": material.tipo,
        "titulo": material.titulo,
        "url": material.url,
        "conteudo": material.conteudo,
        "ordem": material.ordem,
        "ativo": material.ativo
    }

def validar_pasta_interatividade(db: Session, pasta_id: int):
    pasta = db.query(Pasta).filter(Pasta.id == pasta_id).first()
    if not pasta:
        return None, {"erro": "Pasta não encontrada"}
    if pasta.tipo != "INTERATIVIDADE":
        return None, {"erro": "Esta rota só aceita pasta do tipo INTERATIVIDADE"}
    return pasta, None

@app.post("/quiz-ia")
def criar_quiz_ia(payload: dict, db: Session = Depends(get_db)):
    pasta_id = payload.get("pasta_id")
    titulo = payload.get("titulo")
    itens = payload.get("itens", [])

    if not pasta_id or not titulo:
        return {"erro": "Informe pasta_id e titulo"}

    _, erro = validar_pasta_interatividade(db, pasta_id)
    if erro:
        return erro

    if len(itens) != 5:
        return {"erro": "QuizIA deve ter exatamente 5 itens"}

    quiz = QuizIA(pasta_id=pasta_id, titulo=titulo)
    db.add(quiz)
    db.commit()
    db.refresh(quiz)

    for item in itens:
        alternativas = item.get("alternativas")
        resp = (item.get("resposta_correta") or "").upper().strip()

        if resp not in ("A", "B", "C", "D", "E"):
            return {"erro": "resposta_correta deve ser A-E"}

        db.add(QuizIAItem(
            quiz_id=quiz.id,
            pergunta=item.get("pergunta"),
            alternativas=alternativas,
            resposta_correta=resp,
            comentario_curto=item.get("comentario_curto"),
            ordem=item.get("ordem", 1)
        ))

    db.commit()
    return {"id": quiz.id, "pasta_id": quiz.pasta_id, "titulo": quiz.titulo}

@app.get("/pastas/{pasta_id}/quiz-ia")
def listar_quiz_ia(pasta_id: int, db: Session = Depends(get_db)):
    quizzes = db.query(QuizIA).filter(QuizIA.pasta_id == pasta_id).order_by(QuizIA.id.desc()).all()
    retorno = []
    for q in quizzes:
        itens = db.query(QuizIAItem).filter(QuizIAItem.quiz_id == q.id).order_by(QuizIAItem.ordem.asc()).all()
        retorno.append({
            "id": q.id,
            "titulo": q.titulo,
            "itens": [
                {
                    "id": i.id,
                    "pergunta": i.pergunta,
                    "alternativas": i.alternativas,
                    "resposta_correta": i.resposta_correta,
                    "comentario_curto": i.comentario_curto,
                    "ordem": i.ordem
                } for i in itens
            ]
        })
    return retorno

@app.post("/cartoes-ia")
def criar_cartao_ia(payload: dict, db: Session = Depends(get_db)):
    pasta_id = payload.get("pasta_id")
    frente = payload.get("frente")
    verso = payload.get("verso")

    if not pasta_id or not frente or not verso:
        return {"erro": "Informe pasta_id, frente e verso"}

    _, erro = validar_pasta_interatividade(db, pasta_id)
    if erro:
        return erro

    novo = CartaoIA(
        pasta_id=pasta_id,
        frente=frente,
        verso=verso,
        ordem=payload.get("ordem", 1)
    )
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return {"id": novo.id, "pasta_id": novo.pasta_id, "ordem": novo.ordem}

@app.get("/pastas/{pasta_id}/cartoes-ia")
def listar_cartoes_ia(pasta_id: int, db: Session = Depends(get_db)):
    cartoes = db.query(CartaoIA).filter(CartaoIA.pasta_id == pasta_id).order_by(CartaoIA.ordem.asc()).all()
    return [{"id": c.id, "frente": c.frente, "verso": c.verso, "ordem": c.ordem} for c in cartoes]

@app.post("/questoes-ia")
def criar_questoes_ia(payload: dict, db: Session = Depends(get_db)):
    pasta_id = payload.get("pasta_id")
    titulo = payload.get("titulo")
    itens = payload.get("itens", [])

    if not pasta_id or not titulo:
        return {"erro": "Informe pasta_id e titulo"}

    _, erro = validar_pasta_interatividade(db, pasta_id)
    if erro:
        return erro

    if len(itens) != 10:
        return {"erro": "QuestoesIA deve ter exatamente 10 itens"}

    cab = QuestoesIA(pasta_id=pasta_id, titulo=titulo)
    db.add(cab)
    db.commit()
    db.refresh(cab)

    for item in itens:
        tipo = (item.get("tipo") or "").upper().strip()
        if tipo not in ("MULTIPLA", "CERTO_ERRADO"):
            return {"erro": "tipo deve ser MULTIPLA ou CERTO_ERRADO"}

        db.add(QuestoesIAItem(
            questoes_ia_id=cab.id,
            enunciado=item.get("enunciado"),
            tipo=tipo,
            alternativas=item.get("alternativas"),
            comentario=item.get("comentario"),
            ordem=item.get("ordem", 1)
        ))

    db.commit()
    return {"id": cab.id, "pasta_id": cab.pasta_id, "titulo": cab.titulo}

@app.get("/pastas/{pasta_id}/questoes-ia")
def listar_questoes_ia(pasta_id: int, db: Session = Depends(get_db)):
    cabecalhos = db.query(QuestoesIA).filter(QuestoesIA.pasta_id == pasta_id).order_by(QuestoesIA.id.desc()).all()
    retorno = []
    for cab in cabecalhos:
        itens = db.query(QuestoesIAItem).filter(QuestoesIAItem.questoes_ia_id == cab.id).order_by(QuestoesIAItem.ordem.asc()).all()
        retorno.append({
            "id": cab.id,
            "titulo": cab.titulo,
            "itens": [
                {
                    "id": i.id,
                    "enunciado": i.enunciado,
                    "tipo": i.tipo,
                    "alternativas": i.alternativas,
                    "comentario": i.comentario,
                    "ordem": i.ordem
                } for i in itens
            ]
        })
    return retorno

@app.post("/register", response_model=UsuarioResponse)
def register(
    dados: UsuarioCreate,
    db: Session = Depends(get_db)
):
    existe_email = (
        db.query(Usuario)
        .filter(
            Usuario.email == dados.email
        )
        .first()
    )

    if existe_email:
        raise HTTPException(
            status_code=400,
            detail="E-mail já cadastrado"
        )

    existe_cpf = (
        db.query(Usuario)
        .filter(
            Usuario.cpf == dados.cpf
        )
        .first()
    )

    if existe_cpf:
        raise HTTPException(
            status_code=400,
            detail="CPF já cadastrado"
        )

    novo = Usuario(
        nome=dados.nome,
        email=dados.email,
        cpf=dados.cpf,
        telefone=dados.telefone,
        senha_hash=hash_senha(
            dados.senha
        ),
        ativo=True,
        is_admin=False,
        perfil_inicial="ALUNO"
    )

    db.add(novo)

    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=400,
            detail=(
                "E-mail ou CPF já cadastrado"
            )
        )

    db.refresh(novo)

    return novo

@app.post("/login", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    login_digitado = form_data.username.strip()

    usuario = (
        db.query(Usuario)
        .filter(
            or_(
                Usuario.email == login_digitado,
                Usuario.cpf == login_digitado
            )
        )
        .first()
    )

    if not usuario:
        raise HTTPException(
            status_code=401,
            detail="Credenciais inválidas"
        )

    if usuario.bloqueado_login:
        raise HTTPException(
            status_code=403,
            detail=(
                "Usuário bloqueado. "
                "Vá em Recuperar ou atualizar minha senha "
                "para redefinir sua senha (desbloquear seu acesso)."
            )
        )

    senha_correta = verificar_senha(
        form_data.password,
        usuario.senha_hash
    )

    if not senha_correta:
        usuario.tentativas_login += 1

        if usuario.tentativas_login >= 6:
            usuario.bloqueado_login = True

            db.commit()

            raise HTTPException(
                status_code=403,
                detail=(
                    "Usuário bloqueado. "
                    "Vá em Recuperar ou atualizar minha senha "
                    "para redefinir sua senha (desbloquear seu acesso)."
                )
            )

        db.commit()

        tentativas_restantes = (
            6 - usuario.tentativas_login
        )

        raise HTTPException(
            status_code=401,
            detail=(
                "Senha incorreta. "
                "O acesso poderá ser bloqueado. "
                f"Restam {tentativas_restantes} tentativa(s)."
            )
        )
    if usuario.tentativas_login != 0:
        usuario.tentativas_login = 0
        db.commit()

    token = criar_token({
        "sub": str(usuario.id)
    })

    return {
        "access_token": token,
        "token_type": "bearer"
    }

@app.get("/me", response_model=UsuarioResponse)
def me(
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db)
):
    vendedor = (
        db.query(models.Vendedor)
        .filter(
            models.Vendedor.usuario_id == usuario.id
        )
        .first()
    )

    is_vendedor = False

    if vendedor:
        if vendedor.ativo:
            is_vendedor = True

        elif vendedor.descredenciado_em:
            limite = (
                vendedor.descredenciado_em
                + timedelta(days=30)
            )

            if datetime.utcnow() < limite:
                is_vendedor = True


    tem_cursos = (
        db.query(AcessoCurso)
        .filter(
            AcessoCurso.usuario_id == usuario.id,
            AcessoCurso.ativo == True
        )
        .first()
        is not None
    )


    is_aluno = (
        usuario.perfil_inicial == "ALUNO"
        or tem_cursos
    )


    return {
        "id": usuario.id,
        "nome": usuario.nome,
        "email": usuario.email,
        "cpf": usuario.cpf,
        "telefone": usuario.telefone,
        "ativo": usuario.ativo,
        "is_admin": usuario.is_admin,
        "perfil_inicial": usuario.perfil_inicial,
        "is_vendedor": is_vendedor,
        "is_aluno": is_aluno,
        "tem_cursos": tem_cursos
    }
        
@app.post("/me/dados", response_model=UsuarioResponse)
def atualizar_meus_dados(
    dados: UsuarioUpdateMe,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    email_em_uso = db.query(Usuario).filter(
        Usuario.email == dados.email,
        Usuario.id != usuario.id
    ).first()

    if email_em_uso:
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")

    cpf_em_uso = db.query(Usuario).filter(
        Usuario.cpf == dados.cpf,
        Usuario.id != usuario.id
    ).first()

    if cpf_em_uso:
        raise HTTPException(status_code=400, detail="CPF já cadastrado")

    usuario.nome = dados.nome
    usuario.email = dados.email
    usuario.cpf = dados.cpf
    usuario.telefone = dados.telefone

    if dados.senha:
        usuario.senha_hash = hash_senha(dados.senha)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="E-mail ou CPF já cadastrado")

    db.refresh(usuario)
    return usuario

from fastapi import HTTPException, Request

def mp_headers():
    if not MP_ACCESS_TOKEN:
        raise HTTPException(status_code=500, detail="MP_ACCESS_TOKEN não configurado no ambiente.")
    return {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}

@app.get("/public/cursos/{curso_id}/checkout")
def dados_publicos_checkout(
    curso_id: int,
    db: Session = Depends(get_db)
):
    curso = db.query(Curso).filter(
        Curso.id == curso_id,
        Curso.ativo == True
    ).first()

    if not curso:
        raise HTTPException(
            status_code=404,
            detail="Curso não encontrado"
        )

    tempos = (
        db.query(TempoAcessoCurso)
        .filter(
            TempoAcessoCurso.curso_id == curso_id,
            TempoAcessoCurso.ativo == True
        )
        .order_by(TempoAcessoCurso.meses.asc())
        .all()
    )

    disciplinas = (
        db.query(CursoDisciplinaPropria)
        .filter(
            CursoDisciplinaPropria.curso_id == curso_id,
            CursoDisciplinaPropria.ativo == True
        )
        .order_by(
            CursoDisciplinaPropria.ordem.asc(),
            CursoDisciplinaPropria.id.asc()
        )
        .all()
    )

    estrutura = []

    for disciplina in disciplinas:
        assuntos = (
            db.query(CursoAssuntoProprio)
            .filter(
                CursoAssuntoProprio.curso_disciplina_propria_id == disciplina.id,
                CursoAssuntoProprio.ativo == True
            )
            .order_by(
                CursoAssuntoProprio.ordem.asc(),
                CursoAssuntoProprio.id.asc()
            )
            .all()
        )

        estrutura.append({
            "id": disciplina.id,
            "nome": disciplina.nome,
            "assuntos": [
                {
                    "id": assunto.id,
                    "nome": assunto.nome
                }
                for assunto in assuntos
            ]
        })

    return {
        "id": curso.id,
        "nome": curso.nome,
        "descricao_publica": curso.descricao_publica,
        "tempos_acesso": [
            {
                "id": tempo.id,
                "meses": tempo.meses,
                "valor_cents": tempo.valor_cents
            }
            for tempo in tempos
        ],
        "disciplinas": estrutura
    }

@app.get("/cursos-publicos")
def listar_cursos_publicos(
    db: Session = Depends(get_db)
):
    cursos = (
        db.query(Curso)
        .filter(
            Curso.ativo == True,
            Curso.publicado == True
        )
        .order_by(Curso.nome.asc())
        .all()
    )

    return [
        {
            "id": curso.id,
            "nome": curso.nome,
            "ativo": curso.ativo,
            "publicado": curso.publicado
        }
        for curso in cursos
    ]

@app.put("/admin/cursos/{curso_id}/publicar")
def publicar_curso(
    curso_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Apenas administrador."
        )

    curso = db.query(Curso).filter(
        Curso.id == curso_id,
        Curso.ativo == True
    ).first()

    if not curso:
        raise HTTPException(
            status_code=404,
            detail="Curso não encontrado."
        )

    curso.publicado = True

    db.commit()
    db.refresh(curso)

    return {
        "ok": True,
        "curso_id": curso.id,
        "publicado": curso.publicado,
        "mensagem": "Curso publicado com sucesso."
    }

@app.get("/admin/cursos/{curso_id}/config-publica")
def obter_config_publica_curso(
    curso_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Apenas administrador."
        )

    curso = db.query(Curso).filter(
        Curso.id == curso_id
    ).first()

    if not curso:
        raise HTTPException(
            status_code=404,
            detail="Curso não encontrado."
        )

    tempos = (
        db.query(TempoAcessoCurso)
        .filter(
            TempoAcessoCurso.curso_id == curso_id
        )
        .order_by(
            TempoAcessoCurso.meses.asc()
        )
        .all()
    )

    return {
        "curso_id": curso.id,
        "nome": curso.nome,
        "descricao_publica": curso.descricao_publica or "",
        "publicado": bool(curso.publicado),
        "tempos_acesso": [
            {
                "id": t.id,
                "meses": t.meses,
                "valor_cents": t.valor_cents,
                "ativo": t.ativo
            }
            for t in tempos
        ]
    }


@app.put("/admin/cursos/{curso_id}/config-publica")
def salvar_config_publica_curso(
    curso_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Apenas administrador."
        )

    curso = db.query(Curso).filter(
        Curso.id == curso_id
    ).first()

    if not curso:
        raise HTTPException(
            status_code=404,
            detail="Curso não encontrado."
        )

    curso.descricao_publica = (
        payload.get("descricao_publica") or ""
    )

    tempos = payload.get("tempos_acesso") or []
    meses_validos = {4, 8, 12}

    for item in tempos:
        meses = int(item["meses"])
        valor_cents = int(item["valor_cents"])

        if meses not in meses_validos:
            raise HTTPException(
                status_code=400,
                detail=f"Tempo inválido: {meses} meses."
            )

        registro = (
            db.query(TempoAcessoCurso)
            .filter(
                TempoAcessoCurso.curso_id == curso_id,
                TempoAcessoCurso.meses == meses
            )
            .first()
        )

        if registro:
            registro.valor_cents = valor_cents
            registro.ativo = True
        else:
            db.add(
                TempoAcessoCurso(
                    curso_id=curso_id,
                    meses=meses,
                    valor_cents=valor_cents,
                    ativo=True
                )
            )

    db.commit()

    return {"ok": True}

@app.post("/cursos/{curso_id}/demonstracao")
def iniciar_demonstracao_curso(
    curso_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    curso = db.query(Curso).filter(
        Curso.id == curso_id,
        Curso.ativo == True
    ).first()

    if not curso:
        raise HTTPException(
            status_code=404,
            detail="Curso não encontrado."
        )

    agora = datetime.utcnow()

    ultima_demo = (
        db.query(DemonstracaoCurso)
        .filter(
            DemonstracaoCurso.usuario_id == usuario.id,
            DemonstracaoCurso.curso_id == curso_id
        )
        .order_by(DemonstracaoCurso.id.desc())
        .first()
    )

    if ultima_demo and ultima_demo.liberado_novamente_em > agora:
        raise HTTPException(
            status_code=400,
            detail=(
                "Esta modalidade estará disponível novamente para você, "
                "para este Curso, após 30 dias do último acesso nesta modalidade."
            )
        )

    data_inicio = agora
    data_fim = data_inicio + timedelta(days=1)
    liberado_novamente_em = data_inicio + timedelta(days=30)

    demo = DemonstracaoCurso(
        usuario_id=usuario.id,
        curso_id=curso_id,
        data_inicio=data_inicio,
        data_fim=data_fim,
        liberado_novamente_em=liberado_novamente_em,
        ativo=True
    )

    db.add(demo)

    db.flush()

    db.execute(text("""
        INSERT INTO acessos_curso (
            usuario_id,
            curso_id,
            ativo,
            data_inicio,
            data_fim
        )
        VALUES (
            :u,
            :c,
            TRUE,
            :inicio,
            :fim
        )
        ON CONFLICT (usuario_id, curso_id)
        DO UPDATE SET
            ativo = TRUE,
            data_inicio = :inicio,
            data_fim = :fim
    """), {
        "u": usuario.id,
        "c": curso_id,
        "inicio": data_inicio,
        "fim": data_fim
    })

    db.commit()

    return {
        "ok": True,
        "tipo": "DEMONSTRACAO",
        "curso_id": curso_id,
        "demonstracao_id": demo.id,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "liberado_novamente_em": liberado_novamente_em
    }

@app.post("/checkout/mercadopago")
def criar_checkout_mp(
    payload: dict,
    db: Session = Depends(get_db),
    user=Depends(get_usuario_atual)
):
    tempo_acesso_id = payload.get("tempo_acesso_id")

    codigo_cupom = payload.get("codigo_cupom")

    if not tempo_acesso_id:
        raise HTTPException(status_code=400, detail="tempo_acesso_id inválido.")

    tempo = db.query(TempoAcessoCurso).filter(
        TempoAcessoCurso.id == int(tempo_acesso_id),
        TempoAcessoCurso.ativo == True
    ).first()

    if not tempo:
        raise HTTPException(status_code=404, detail="Tempo de acesso não encontrado.")

    curso = db.query(Curso).filter(
        Curso.id == tempo.curso_id,
        Curso.ativo == True
    ).first()

    if not curso:
        raise HTTPException(status_code=404, detail="Curso não encontrado.")

    # Bloqueio de concorrência do checkout por aluno
    db.query(models.Usuario).filter(
        models.Usuario.id == user.id
    ).with_for_update().one()

    agora = datetime.utcnow()
    tipo_compra = payload.get("tipo_compra", "NOVA")
    contratacao_id = None
    vencimento_original = None

    if tipo_compra not in ("NOVA", "RENOVACAO"):
        raise HTTPException(
            status_code=400,
            detail="Tipo de compra inválido."
        )

    demonstracao_id = None

    if tipo_compra == "NOVA" and payload.get("demonstracao_id") is not None:
        try:
            demonstracao_id = int(payload["demonstracao_id"])
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail="Identificador da demonstração inválido."
            )

        demonstracao = db.query(DemonstracaoCurso).filter(
            DemonstracaoCurso.id == demonstracao_id,
            DemonstracaoCurso.usuario_id == user.id,
            DemonstracaoCurso.curso_id == curso.id,
            DemonstracaoCurso.ativo == True,
            DemonstracaoCurso.data_inicio <= agora,
            DemonstracaoCurso.data_fim > agora
        ).first()

        if not demonstracao:
            raise HTTPException(
                status_code=409,
                detail="Demonstração vigente não encontrada."
            )

    if tipo_compra == "RENOVACAO" and payload.get("demonstracao_id") is not None:
        raise HTTPException(
            status_code=400,
            detail="Uma renovação não pode indicar uma demonstração."
        )

    if tipo_compra == "RENOVACAO":
        try:
            contratacao_id = int(payload["contratacao_id"])
        except (KeyError, TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail="Informe o contrato que deseja renovar."
            )

        contratacao = db.query(models.ContratacaoCurso).filter(
            models.ContratacaoCurso.id == contratacao_id,
            models.ContratacaoCurso.usuario_id == user.id,
            models.ContratacaoCurso.curso_id == curso.id,
            models.ContratacaoCurso.origem.in_(["PAGAMENTO", "ADMIN"]),
            models.ContratacaoCurso.data_inicio <= agora,
            models.ContratacaoCurso.data_fim > agora
        ).with_for_update().first()

        if not contratacao:
            raise HTTPException(
                status_code=409,
                detail="Contrato vigente não encontrado para renovação."
            )

        if not renovacao_disponivel(contratacao.data_fim, agora):
            raise HTTPException(
                status_code=409,
                detail="A renovação só está disponível nos últimos 15 dias do contrato."
            )

        vencimento_original = contratacao.data_fim

    oportunidade = obter_oportunidade(
        db=db,
        usuario_id=user.id,
        curso_id=curso.id,
        tipo_compra=tipo_compra,
        contratacao_id=contratacao_id,
        demonstracao_id=demonstracao_id,
        vencimento_original=vencimento_original,
    )

    if oportunidade.concluida_em is not None:
        raise HTTPException(
            status_code=409,
            detail="Esta oportunidade de compra já foi concluída."
        )

    titulos_gerados = db.query(Pagamento).filter(
        Pagamento.oportunidade_id == oportunidade.id,
        Pagamento.mp_preference_id.isnot(None)
    ).count()

    if titulos_gerados >= 8:
        raise HTTPException(
            status_code=409,
            detail="Limite de oito títulos atingido para esta oportunidade."
        )

    valor_cents = int(tempo.valor_cents)

    valor_original_cents = valor_cents
    valor_desconto_cents = 0
    percentual_desconto = 0
    vendedor_id = None
    codigo_cupom_usado = None

    if codigo_cupom:
        codigo_cupom = str(
            codigo_cupom
        ).strip().upper()

        cupom = (
            db.query(models.CupomDesconto)
            .filter(
                models.CupomDesconto.codigo
                == codigo_cupom,

                models.CupomDesconto.ativo
                == True
            )
            .first()
        )

        if not cupom:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Cupom de desconto inválido "
                    "ou inativo."
                )
            )

        if cupom.vendedor_id is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Este cupom ainda não está "
                    "vinculado a um parceiro/vendedor."
                )
            )

        vendedor = (
            db.query(models.Vendedor)
            .filter(
                models.Vendedor.id
                == cupom.vendedor_id,

                models.Vendedor.ativo
                == True
            )
            .first()
        )

        if not vendedor:
            raise HTTPException(
                status_code=400,
                detail=(
                    "O parceiro/vendedor vinculado "
                    "a este cupom está inativo."
                )
            )

        percentual_desconto = int(
            cupom.percentual_desconto
        )

        valor_desconto_cents = (
            valor_original_cents *
            percentual_desconto +
            50
        ) // 100

        valor_cents = (
            valor_original_cents -
            valor_desconto_cents
        )

        vendedor_id = vendedor.id
        codigo_cupom_usado = cupom.codigo

    pagamento_id = db.execute(text("""
        INSERT INTO pagamentos (
            usuario_id,
            curso_id,
            tempo_acesso_id,
            status,
            valor_cents,
            codigo_cupom,
            vendedor_id,
            tipo_compra,
            vencimento_original,
            contratacao_id,
            oportunidade_id
        )
        VALUES (
            :u,
            :c,
            :t,
            'PENDENTE',
            :v,
            :codigo_cupom,
            :vendedor_id,
            :tipo_compra,
            :vencimento_original,
            :contratacao_id,
            :oportunidade_id
        )
        RETURNING id
    """), {
        "u": user.id,
        "c": curso.id,
        "t": tempo.id,
        "v": valor_cents,
        "codigo_cupom": codigo_cupom_usado,
        "vendedor_id": vendedor_id,
        "tipo_compra": tipo_compra,
        "vencimento_original": vencimento_original,
        "contratacao_id": contratacao_id,
        "oportunidade_id": oportunidade.id
    }).scalar()

    db.flush()

    base = (APP_BASE_URL or "").rstrip("/")
    if not base:
        base = "http://127.0.0.1:5500/site-html"

    payload_mp = {
        "items": [{
            "title": f"{curso.nome} - {tempo.meses} meses",
            "quantity": 1,
            "unit_price": round(valor_cents / 100, 2),
            "currency_id": "BRL"
        }],
        "payer": {"email": user.email},
        "external_reference": f"user:{user.id}|curso:{curso.id}|tempo:{tempo.id}|pagamento:{pagamento_id}",
        "back_urls": {
            "success": f"{base}/pagamento_sucesso.html",
            "failure": f"{base}/curso-info.html?curso_id={curso.id}&curso_nome={quote(curso.nome)}",
            "pending": f"{base}/curso-info.html?curso_id={curso.id}&curso_nome={quote(curso.nome)}",
        },
        "notification_url": os.getenv(
            "MP_WEBHOOK_URL",
            "https://reimagined-waffle-4jv4jw9pqpwjfqqp4-8000.app.github.dev/webhooks/mercadopago"
        ),
    }


    if tipo_compra == "RENOVACAO":
        from datetime import timezone

        # O sistema armazena e compara os vencimentos em UTC.
        vencimento_mp = vencimento_original.replace(
            tzinfo=timezone.utc
        )

        payload_mp["expires"] = True
        payload_mp["expiration_date_to"] = vencimento_mp.isoformat(
            timespec="seconds"
        )

    url = "https://api.mercadopago.com/checkout/preferences"
    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        resp = requests.post(url, headers=headers, json=payload_mp, timeout=20)
    except requests.RequestException as e:
        db.rollback()
        raise HTTPException(status_code=502, detail=f"Falha de rede ao chamar MP: {e}")

    if resp.status_code >= 400:
        db.rollback()
        raise HTTPException(status_code=502, detail=f"Erro MP {resp.status_code}: {resp.text}")

    data = resp.json()

    pref_id = data.get("id")
    init_point = data.get("init_point")

    if not pref_id or not init_point:
        db.rollback()
        raise HTTPException(status_code=502, detail=f"MP retornou sem pref_id/init_point: {data}")

    db.execute(text("""
        UPDATE pagamentos
        SET mp_preference_id = :pid
        WHERE id = :pag_id
    """), {
        "pid": str(pref_id),
        "pag_id": int(pagamento_id)
    })

    db.commit()

    return {
        "preference_id": str(pref_id),
        "pagamento_id": int(pagamento_id),
        "init_point": init_point,
        "sandbox_init_point": data.get("sandbox_init_point"),
        "curso_id": curso.id,
        "tempo_acesso_id": tempo.id,
        "meses": tempo.meses,

        "valor_cents": valor_cents,

        "valor_original_cents":
            valor_original_cents,

        "valor_desconto_cents":
            valor_desconto_cents,

        "percentual_desconto":
            percentual_desconto,

        "codigo_cupom":
            codigo_cupom_usado,

        "vendedor_id":
            vendedor_id
    }

from fastapi import HTTPException

@app.post("/pagamentos/confirmar")
def confirmar_pagamento(
    payload: dict,
    db: Session = Depends(get_db),
    user=Depends(get_usuario_atual)
):
    payment_id = payload.get("payment_id")
    curso_id = payload.get("curso_id")

    if not payment_id or not curso_id:
        raise HTTPException(status_code=400, detail="Informe payment_id e curso_id")

    r = requests.get(
        f"https://api.mercadopago.com/v1/payments/{payment_id}",
        headers=mp_headers(),
        timeout=20
    )

    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Erro MP: {r.text}")

    p = r.json()
    status = (p.get("status") or "").lower()

    external_reference = p.get("external_reference") or ""

    referencias = {}
    for parte in external_reference.split("|"):
        if ":" in parte:
            chave, valor = parte.split(":", 1)
            referencias[chave] = valor

    try:
        usuario_ref = int(referencias["user"])
        curso_ref = int(referencias["curso"])
        tempo_ref = int(referencias["tempo"])
        pagamento_ref = int(referencias["pagamento"])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="Referência do pagamento ausente ou inválida."
        )

    if usuario_ref != user.id or curso_ref != int(curso_id):
        raise HTTPException(
            status_code=403,
            detail="O pagamento não corresponde ao usuário e curso informados."
        )

    db.query(models.Usuario).filter(
        models.Usuario.id == user.id
    ).with_for_update().one()

    pagamento = db.query(Pagamento).filter(
        Pagamento.id == pagamento_ref,
        Pagamento.usuario_id == user.id,
        Pagamento.curso_id == curso_ref
    ).with_for_update().populate_existing().first()

    if pagamento and pagamento.mp_payment_id not in (None, str(payment_id)):
        raise HTTPException(
            status_code=409,
            detail="Esta compra já está vinculada a outra transação."
        )

    if not pagamento:
        raise HTTPException(status_code=404, detail="Pagamento não encontrado.")

    if tempo_ref != pagamento.tempo_acesso_id:
        raise HTTPException(
            status_code=409,
            detail="O período de acesso não corresponde à compra registrada."
        )

    from decimal import Decimal, InvalidOperation

    try:
        valor_mp = Decimal(str(p["transaction_amount"])) * 100

        if not valor_mp.is_finite() or valor_mp != valor_mp.to_integral_value():
            raise ValueError("Valor monetário inválido")

        valor_mp_cents = int(valor_mp)
    except (KeyError, TypeError, ValueError, InvalidOperation):
        raise HTTPException(
            status_code=400,
            detail="Valor do pagamento ausente ou inválido no Mercado Pago."
        )

    if (
        p.get("currency_id") != "BRL"
        or valor_mp_cents != pagamento.valor_cents
    ):
        raise HTTPException(
            status_code=409,
            detail="Valor ou moeda não corresponde à compra registrada."
        )

    if pagamento.ocorrencia_financeira is not None:
        return {
            "ok": True,
            "status": pagamento.status,
            "curso_id": curso_id,
            "liberou_acesso": False,
            "ocorrencia_financeira": pagamento.ocorrencia_financeira,
        }

    oportunidade = bloquear_oportunidade_pagamento(db, pagamento)

    if (
        status == "approved"
        and oportunidade is not None
        and oportunidade.concluida_em is not None
        and pagamento.aprovado_em is None
    ):
        registrar_ocorrencia_financeira(
            db, pagamento, "COBRANCA_DUPLICADA", p
        )
        db.commit()
        return {
            "ok": True,
            "status": "APPROVED",
            "curso_id": curso_id,
            "liberou_acesso": False,
            "ocorrencia_financeira": "COBRANCA_DUPLICADA",
        }

    if (
        status == "approved"
        and pagamento.aprovado_em is None
        and pagamento.tipo_compra == "RENOVACAO"
        and pagamento.vencimento_original is not None
        and obter_data_aprovacao_mp(p) > pagamento.vencimento_original
    ):
        registrar_ocorrencia_financeira(
            db, pagamento, "APROVACAO_FORA_PRAZO", p
        )
        db.commit()
        return {
            "ok": True,
            "status": "APPROVED",
            "curso_id": curso_id,
            "liberou_acesso": False,
            "ocorrencia_financeira": "APROVACAO_FORA_PRAZO",
        }

    ja_aprovado = pagamento.aprovado_em is not None

    # Uma confirmação posterior não pode rebaixar
    # um pagamento que já foi aprovado.
    if ja_aprovado and status in ("pending", "rejected"):
        return {
            "ok": True,
            "status": "APPROVED",
            "curso_id": curso_id,
            "liberou_acesso": False,
        }

    pagamento.status = status.upper()
    pagamento.mp_payment_id = str(payment_id)

    if (
        status == "approved"
        and not pagamento.aprovado_em
    ):
        pagamento.aprovado_em = validar_data_aprovacao_mp(pagamento, p)

    pagamento.atualizado_em = datetime.utcnow()

    liberou = False

    if status == "approved" and not ja_aprovado:
        tempo = db.query(TempoAcessoCurso).filter(
            TempoAcessoCurso.id == pagamento.tempo_acesso_id
        ).first()

        if not tempo:
            raise HTTPException(status_code=400, detail="Tempo de acesso não encontrado para este pagamento.")

        if pagamento.tipo_compra == 'RENOVACAO':
            if pagamento.vencimento_original is None:
                raise HTTPException(
                    status_code=500,
                    detail='Renovação sem vencimento original.'
                )
            data_inicio = pagamento.vencimento_original
        else:
            data_inicio = datetime.utcnow()

        data_fim = data_inicio + relativedelta(months=tempo.meses)

        contratacao = registrar_contratacao(
            db, pagamento, data_inicio, data_fim
        )

        db.add(
            PeriodoAcessoPagamento(
                pagamento_id=pagamento.id,
                contratacao_id=contratacao.id,
                usuario_id=pagamento.usuario_id,
                curso_id=pagamento.curso_id,
                data_inicio=data_inicio,
                data_fim=data_fim,
            )
        )

        try:
            db.execute(text("""
                INSERT INTO acessos_curso (usuario_id, curso_id, ativo, data_inicio, data_fim)
                VALUES (:u, :c, TRUE, :inicio, :fim)
                ON CONFLICT (usuario_id, curso_id)
                DO UPDATE SET
                    ativo = TRUE,
                    data_inicio = CASE
                        WHEN acessos_curso.ativo = TRUE
                            AND (
                                acessos_curso.data_fim IS NULL
                                OR acessos_curso.data_fim > :fim
                            )
                        THEN acessos_curso.data_inicio
                        ELSE :inicio
                    END,
                    data_fim = CASE
                        WHEN acessos_curso.ativo = TRUE
                            AND (
                                acessos_curso.data_fim IS NULL
                                OR acessos_curso.data_fim > :fim
                            )
                        THEN acessos_curso.data_fim
                        ELSE :fim
                    END
            """), {
                "u": user.id,
                "c": curso_id,
                "inicio": data_inicio,
                "fim": data_fim
            })

        except Exception:
            db.rollback()
            raise

        concluir_oportunidade(db, oportunidade)
        liberou = True

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "ok": True,
        "status": status.upper(),
        "curso_id": curso_id,
        "liberou_acesso": liberou
    }

from fastapi import Request, HTTPException

def validar_assinatura_mercadopago(request: Request, payment_id: str) -> bool:
    if not MP_WEBHOOK_SECRET:
        return False

    assinatura = request.headers.get("x-signature", "")
    request_id = request.headers.get("x-request-id", "")

    partes = {}
    for item in assinatura.split(","):
        if "=" in item:
            chave, valor = item.strip().split("=", 1)
            partes[chave] = valor

    ts = partes.get("ts")
    recebido = partes.get("v1")

    if not ts or not recebido or not request_id:
        return False

    manifest = (
        f"id:{payment_id.lower()};"
        f"request-id:{request_id};"
        f"ts:{ts};"
    )

    esperado = hmac.new(
        MP_WEBHOOK_SECRET.encode("utf-8"),
        manifest.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(esperado, recebido)

@app.post("/webhooks/mercadopago")
async def webhook_mercadopago(request: Request, db: Session = Depends(get_db)):
    data = await request.json()

    tipo_notificacao = (
        request.query_params.get("type")
        or request.query_params.get("topic")
        or (data.get("type") if isinstance(data, dict) else None)
    )

    if tipo_notificacao not in ("payment",):
        return {
            "ok": True,
            "ignored": True,
            "msg": "Tipo de notificação não processado"
        }

    payment_id = request.query_params.get("data.id")

    if not payment_id and isinstance(data, dict):
        payment_id = (
            (data.get("data") or {}).get("id")
            or data.get("id")
            or data.get("payment_id")
        )

    if not payment_id:
        payment_id = request.query_params.get("id")

    if not payment_id:
        return {
            "ok": True,
            "ignored": True,
            "msg": "Notificação sem identificador de pagamento"
        }

    notificacao_webhook = (
        request.query_params.get("data.id") is not None
    )

    if notificacao_webhook:
        if not validar_assinatura_mercadopago(
            request, str(payment_id)
        ):
            raise HTTPException(
                status_code=401,
                detail="Assinatura do Mercado Pago inválida"
            )

    else:
        return {
            "ok": True,
            "ignored": True,
            "msg": "Notificação legada não processada"
        }

    r = requests.get(
        f"https://api.mercadopago.com/v1/payments/{payment_id}",
        headers=mp_headers(),
        timeout=20
    )

    if r.status_code == 404:
        return {
            "ok": True,
            "ignored": True,
            "msg": "Pagamento não encontrado no Mercado Pago"
        }

    if r.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Erro ao consultar pagamento no Mercado Pago: {r.status_code}"
        )

    pagamento_mp = r.json()

    status = (pagamento_mp.get("status") or "desconhecido").upper()
    external_reference = pagamento_mp.get("external_reference") or ""

    user_id = None
    curso_id = None
    tempo_acesso_id = None
    pagamento_id = None

    try:
        for p in external_reference.split("|"):
            if p.startswith("user:"):
                user_id = int(p.split(":", 1)[1])
            elif p.startswith("curso:"):
                curso_id = int(p.split(":", 1)[1])
            elif p.startswith("tempo:"):
                tempo_acesso_id = int(p.split(":", 1)[1])
            elif p.startswith("pagamento:"):
                pagamento_id = int(p.split(":", 1)[1])
    except:
        pass

    if not user_id or not curso_id:
        return {
            "ok": True,
            "ignored": True,
            "msg": "external_reference inválida; nenhum pagamento alterado",
            "payment_id": str(payment_id)
        }

    if user_id and curso_id:
        db.query(models.Usuario).filter(
            models.Usuario.id == user_id
        ).with_for_update().one()

        if pagamento_id:
            pagamento = db.query(Pagamento).filter(
                Pagamento.id == pagamento_id,
                Pagamento.usuario_id == user_id,
                Pagamento.curso_id == curso_id
            ).with_for_update().populate_existing().first()
        else:
            pagamento = db.query(Pagamento).filter(
                Pagamento.mp_payment_id == str(payment_id),
                Pagamento.usuario_id == user_id,
                Pagamento.curso_id == curso_id
            ).with_for_update().populate_existing().first()

        if (
            pagamento
            and pagamento.mp_payment_id
            and pagamento.mp_payment_id != str(payment_id)
        ):
            raise HTTPException(
                status_code=409,
                detail="Pagamento já associado a outra transação"
            )

        if pagamento:
            from decimal import Decimal, InvalidOperation

            # Confere o período de acesso da compra.
            if (
                tempo_acesso_id is None
                or tempo_acesso_id != pagamento.tempo_acesso_id
            ):
                raise HTTPException(
                    status_code=409,
                    detail="O período de acesso não corresponde à compra registrada."
                )

            # Confere o valor recebido do Mercado Pago.
            try:
                valor_mp = (
                    Decimal(str(pagamento_mp["transaction_amount"])) * 100
                )

                if (
                    not valor_mp.is_finite()
                    or valor_mp != valor_mp.to_integral_value()
                ):
                    raise ValueError("Valor monetário inválido")

                valor_mp_cents = int(valor_mp)

            except (KeyError, TypeError, ValueError, InvalidOperation):
                raise HTTPException(
                    status_code=400,
                    detail="Valor do pagamento ausente ou inválido."
                )

            # Confere o valor e a moeda da compra.
            if (
                pagamento_mp.get("currency_id") != "BRL"
                or valor_mp_cents != pagamento.valor_cents
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Valor ou moeda não corresponde à compra registrada."
                )

            if pagamento.ocorrencia_financeira is not None:
                return {
                    "ok": True,
                    "status": pagamento.status,
                    "liberou_acesso": False,
                    "ocorrencia_financeira": pagamento.ocorrencia_financeira,
                }

            oportunidade = bloquear_oportunidade_pagamento(db, pagamento)

            if (
                status == "APPROVED"
                and oportunidade is not None
                and oportunidade.concluida_em is not None
                and pagamento.aprovado_em is None
            ):
                registrar_ocorrencia_financeira(
                    db, pagamento, "COBRANCA_DUPLICADA", pagamento_mp
                )
                db.commit()
                return {
                    "ok": True,
                    "status": "APPROVED",
                    "liberou_acesso": False,
                    "ocorrencia_financeira": "COBRANCA_DUPLICADA",
                }

            if (
                status == "APPROVED"
                and pagamento.aprovado_em is None
                and pagamento.tipo_compra == "RENOVACAO"
                and pagamento.vencimento_original is not None
                and obter_data_aprovacao_mp(pagamento_mp)
                > pagamento.vencimento_original
            ):
                registrar_ocorrencia_financeira(
                    db, pagamento, "APROVACAO_FORA_PRAZO", pagamento_mp
                )
                db.commit()
                return {
                    "ok": True,
                    "status": "APPROVED",
                    "liberou_acesso": False,
                    "ocorrencia_financeira": "APROVACAO_FORA_PRAZO",
                }

            ja_aprovado = pagamento.aprovado_em is not None

            if ja_aprovado and status in ("PENDING", "REJECTED"):
                return {
                    "ok": True,
                    "ignored": True,
                    "msg": "Notificação pendente recebida após aprovação"
                }

            pagamento.status = status
            pagamento.mp_payment_id = str(payment_id)

            if (
                status == "APPROVED"
                and not pagamento.aprovado_em
            ):
                pagamento.aprovado_em = validar_data_aprovacao_mp(pagamento, pagamento_mp)

            pagamento.atualizado_em = datetime.utcnow()

            if (
                tempo_acesso_id
                and not pagamento.tempo_acesso_id
            ):
                pagamento.tempo_acesso_id = tempo_acesso_id

            if status != "APPROVED" or ja_aprovado:
                db.commit()
        else:
            return {
                "ok": True,
                "ignored": True,
                "msg": "external_reference não identificada; nenhum pagamento alterado",
                "payment_id": str(payment_id)
            }

    if status == "APPROVED" and not ja_aprovado:
        # Utiliza o pagamento já identificado e atualizado acima.

        if not pagamento:
            return {
                "ok": False,
                "status": status,
                "msg": "Pagamento não encontrado para liberar acesso.",
                "payment_id": payment_id
            }

        tempo = db.query(TempoAcessoCurso).filter(
            TempoAcessoCurso.id == pagamento.tempo_acesso_id
        ).first()

        if not tempo:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail="Tempo de acesso não encontrado para este pagamento."
            )

        if pagamento.tipo_compra == 'RENOVACAO':
            if pagamento.vencimento_original is None:
                raise HTTPException(
                    status_code=500,
                    detail='Renovação sem vencimento original.'
                )
            data_inicio = pagamento.vencimento_original
        else:
            data_inicio = datetime.utcnow()

        data_fim = data_inicio + relativedelta(months=tempo.meses)

        contratacao = registrar_contratacao(db, pagamento, data_inicio, data_fim)

        db.add(
            PeriodoAcessoPagamento(
                pagamento_id=pagamento.id,
                contratacao_id=contratacao.id,
                usuario_id=pagamento.usuario_id,
                curso_id=pagamento.curso_id,
                data_inicio=data_inicio,
                data_fim=data_fim,
            )
        )

        try:
            db.execute(text("""
                INSERT INTO acessos_curso (
                    usuario_id, curso_id, ativo,
                    data_inicio, data_fim
                )
                VALUES (:u, :c, TRUE, :inicio, :fim)
                ON CONFLICT (usuario_id, curso_id)
                DO UPDATE SET
                    ativo = TRUE,
                    data_inicio = CASE
                        WHEN acessos_curso.ativo = TRUE
                            AND (
                                acessos_curso.data_fim IS NULL
                                OR acessos_curso.data_fim > :fim
                            )
                        THEN acessos_curso.data_inicio
                        ELSE :inicio
                    END,
                    data_fim = CASE
                        WHEN acessos_curso.ativo = TRUE
                            AND (
                                acessos_curso.data_fim IS NULL
                                OR acessos_curso.data_fim > :fim
                            )
                        THEN acessos_curso.data_fim
                        ELSE :fim
                    END
            """), {
                "u": user_id,
                "c": curso_id,
                "inicio": data_inicio,
                "fim": data_fim
            })

            concluir_oportunidade(db, oportunidade)
            db.commit()

        except Exception:
            db.rollback()
            raise

    return {
        "ok": True,
        "status": status.upper(),
        "curso_id": curso_id,
        "tempo_acesso_id": tempo_acesso_id
    }


from dotenv import dotenv_values

@app.post("/me/atendimentos", response_model=AtendimentoResponse)
def criar_atendimento_aluno(
    dados: AtendimentoCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    assunto = dados.assunto.strip()
    mensagem = dados.mensagem.strip()

    if not assunto:
        raise HTTPException(status_code=400, detail="Informe o assunto.")

    if not mensagem:
        raise HTTPException(status_code=400, detail="Informe a mensagem.")

    novo = Atendimento(
        usuario_id=usuario.id,
        assunto=assunto,
        mensagem=mensagem,
        status="ABERTO"
    )

    db.add(novo)
    db.commit()
    db.refresh(novo)

    return novo

@app.get("/me/atendimentos")
def listar_meus_atendimentos(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    atendimentos = (
        db.query(Atendimento)
        .filter(Atendimento.usuario_id == usuario.id)
        .order_by(Atendimento.criado_em.desc())
        .all()
    )

    return [
        {
            "id": a.id,
            "assunto": a.assunto,
            "mensagem": a.mensagem,
            "status": a.status,
            "resposta_admin": a.resposta_admin,
            "criado_em": a.criado_em,
            "respondido_em": a.respondido_em
        }
        for a in atendimentos
    ]

@app.get("/admin/atendimentos")
def admin_listar_atendimentos(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas admin")

    rows = db.execute(text("""
        SELECT
            a.id,
            a.usuario_id,
            u.nome AS usuario_nome,
            u.email AS usuario_email,
            a.assunto,
            a.mensagem,
            a.status,
            a.resposta_admin,
            a.criado_em,
            a.atualizado_em
        FROM atendimentos a
        JOIN usuarios u ON u.id = a.usuario_id
        ORDER BY a.criado_em ASC
    """)).mappings().all()

    return [dict(r) for r in rows]

@app.post("/admin/atendimentos/{atendimento_id}/concluir")
def admin_concluir_atendimento(
    atendimento_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas admin")

    atendimento = db.query(Atendimento).filter(
        Atendimento.id == atendimento_id
    ).first()

    if not atendimento:
        raise HTTPException(status_code=404, detail="Atendimento não encontrado")

    atendimento.status = "CONCLUIDO"
    atendimento.atualizado_em = datetime.utcnow()

    db.commit()

    return {
        "ok": True,
        "message": "Atendimento concluído com sucesso"
    }

@app.post("/admin/atendimentos/{atendimento_id}/responder")
def admin_responder_atendimento(
    atendimento_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas admin")

    resposta = (payload.get("resposta") or "").strip()

    if not resposta:
        raise HTTPException(status_code=400, detail="Informe a resposta")

    atendimento = db.query(Atendimento).filter(
        Atendimento.id == atendimento_id
    ).first()

    if not atendimento:
        raise HTTPException(status_code=404, detail="Atendimento não encontrado")

    atendimento.resposta_admin = resposta
    atendimento.respondido_em = datetime.utcnow()
    atendimento.status = "CONCLUIDO"

    db.commit()

    return {
        "ok": True,
        "message": "Resposta enviada com sucesso"
    }

@app.get("/admin/reembolsos", tags=["Admin Reembolsos"])
def admin_listar_reembolsos(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas admin")

    rows = db.execute(text("""
        SELECT
            p.id AS pagamento_id,
            p.usuario_id,
            u.nome AS usuario_nome,
            u.email AS usuario_email,
            p.curso_id,
            c.nome AS curso_nome,
            p.status,
            p.criado_em AS data_compra,
            p.atualizado_em AS data_solicitacao,
            p.valor_cents,
            p.mp_payment_id,
            p.mp_preference_id
        FROM pagamentos p
        JOIN usuarios u ON u.id = p.usuario_id
        JOIN cursos c ON c.id = p.curso_id
        WHERE p.status IN (
            'REFUND_REQUESTED',
            'REFUND_IN_PROCESS',
            'REFUNDED',
            'REFUND_DENIED',
            'REFUND_ERROR'
        )
        ORDER BY p.atualizado_em DESC
    """)).mappings().all()

    return [dict(r) for r in rows]

@app.post("/admin/pagamentos/revalidar", tags=["Admin Pagamentos"])
def admin_revalidar_pagamento(
    payload: dict,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas admin")

    mp_payment_id = (payload.get("mp_payment_id") or "").strip()
    if not mp_payment_id:
        raise HTTPException(status_code=400, detail="Informe mp_payment_id")

    # 1) acha pagamento no banco (pelo mp_payment_id)
    pag = db.execute(text("""
        SELECT id, usuario_id, curso_id, tempo_acesso_id, aprovado_em, criado_em
        FROM pagamentos
        WHERE mp_payment_id = :pid
        ORDER BY id DESC
        LIMIT 1
    """), {"pid": mp_payment_id}).mappings().first()

    if not pag:
        raise HTTPException(status_code=404, detail="Pagamento não encontrado no banco para esse mp_payment_id")

    user_id = int(pag["usuario_id"])
    curso_id = int(pag["curso_id"])

    # Serializa a revalidação com a confirmação direta e o webhook.
    db.query(models.Usuario).filter(
        models.Usuario.id == user_id
    ).with_for_update().one()

    pagamento = db.query(Pagamento).filter(
        Pagamento.id == int(pag["id"])
    ).with_for_update().populate_existing().one()

    oportunidade = bloquear_oportunidade_pagamento(db, pagamento)


    # Impede a revalidação de pagamentos envolvidos em reembolso.
    status_atual = db.execute(
        text("SELECT status FROM pagamentos WHERE id = :id"),
        {"id": int(pag["id"])}
    ).scalar_one()

    if status_atual in (
        "REFUND_REQUESTED",
        "REFUND_IN_PROCESS",
        "REFUNDED",
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Este pagamento está envolvido em um processo de "
                "reembolso e não pode ser revalidado."
            ),
        )

    ja_aprovado = pagamento.aprovado_em is not None

    # 2) consulta no Mercado Pago
    r = requests.get(
        f"https://api.mercadopago.com/v1/payments/{mp_payment_id}",
        headers=mp_headers(),
        timeout=20
    )
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Erro MP: {r.text}")

    p = r.json()
    status_mp = (p.get("status") or "").lower().strip()  # approved/pending/rejected...

    # Confere a identidade e o valor da compra antes de alterar o banco.
    referencia = str(p.get("external_reference") or "")
    referencias = {}

    for parte in referencia.split("|"):
        if ":" in parte:
            chave, valor = parte.split(":", 1)
            referencias[chave] = valor

    try:
        usuario_ref = int(referencias["user"])
        curso_ref = int(referencias["curso"])
        tempo_ref = int(referencias["tempo"])
        pagamento_ref = int(referencias["pagamento"])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="Referência do pagamento ausente ou inválida.",
        )

    if (
        usuario_ref != user_id
        or curso_ref != curso_id
        or tempo_ref != pagamento.tempo_acesso_id
        or pagamento_ref != pagamento.id
        or str(p.get("id")) != mp_payment_id
    ):
        raise HTTPException(
            status_code=409,
            detail="Pagamento não corresponde à compra registrada.",
        )

    try:
        valor_mp = Decimal(str(p["transaction_amount"])) * 100
        if not valor_mp.is_finite() or valor_mp != valor_mp.to_integral_value():
            raise ValueError("Valor monetário inválido")
        valor_mp_cents = int(valor_mp)
    except (KeyError, TypeError, ValueError, InvalidOperation):
        raise HTTPException(
            status_code=400,
            detail="Valor inválido no Mercado Pago.",
        )

    if p.get("currency_id") != "BRL" or valor_mp_cents != pagamento.valor_cents:
        raise HTTPException(
            status_code=409,
            detail="Valor ou moeda não corresponde à compra registrada.",
        )

    if pagamento.ocorrencia_financeira is not None:
        return {
            "ok": True,
            "status": pagamento.status,
            "liberou_acesso": False,
            "ocorrencia_financeira": pagamento.ocorrencia_financeira,
        }

    if (
        status_mp == "approved"
        and oportunidade is not None
        and oportunidade.concluida_em is not None
        and not ja_aprovado
    ):
        registrar_ocorrencia_financeira(
            db, pagamento, "COBRANCA_DUPLICADA", p
        )
        db.commit()
        return {
            "ok": True,
            "status": "APPROVED",
            "liberou_acesso": False,
            "ocorrencia_financeira": "COBRANCA_DUPLICADA",
        }

    if (
        status_mp == "approved"
        and not ja_aprovado
        and pagamento.tipo_compra == "RENOVACAO"
        and pagamento.vencimento_original is not None
        and obter_data_aprovacao_mp(p) > pagamento.vencimento_original
    ):
        registrar_ocorrencia_financeira(
            db, pagamento, "APROVACAO_FORA_PRAZO", p
        )
        db.commit()
        return {
            "ok": True,
            "status": "APPROVED",
            "liberou_acesso": False,
            "ocorrencia_financeira": "APROVACAO_FORA_PRAZO",
        }

    # Preserva a aprovação já registrada por outro caminho.
    if ja_aprovado and status_mp in ("pending", "rejected"):
        status_mp = "approved"

    pagamento.status = status_mp.upper()
    pagamento.atualizado_em = datetime.utcnow()

    # 4) se aprovado, libera acesso
    liberou = False
    if status_mp == "approved" and not ja_aprovado:
        acesso_atual = db.query(AcessoCurso).filter(
            AcessoCurso.usuario_id == user_id,
            AcessoCurso.curso_id == curso_id,
            AcessoCurso.ativo == True
        ).first()

        tempo = db.query(TempoAcessoCurso).filter(
            TempoAcessoCurso.id == pag["tempo_acesso_id"]
        ).first()

        if not tempo:
            raise HTTPException(
                status_code=500,
                detail="Prazo contratado não encontrado para este pagamento."
            )

        data_aprovacao = validar_data_aprovacao_mp(pagamento, p)

        if pagamento.tipo_compra == "RENOVACAO":
            data_inicio = pagamento.vencimento_original
        else:
            data_inicio = data_aprovacao

        data_fim = data_inicio + relativedelta(months=tempo.meses)

        contratacao = registrar_contratacao(
            db, pagamento, data_inicio, data_fim
        )

        db.add(
            PeriodoAcessoPagamento(
                pagamento_id=pagamento.id,
                contratacao_id=contratacao.id,
                usuario_id=user_id,
                curso_id=curso_id,
                data_inicio=data_inicio,
                data_fim=data_fim,
            )
        )

        compra_ainda_valida = data_fim > datetime.utcnow()

        if compra_ainda_valida:
            db.execute(text("""
                INSERT INTO acessos_curso (
                    usuario_id, curso_id, ativo, data_inicio, data_fim
                )
                VALUES (:u, :c, TRUE, :inicio, :fim)
                ON CONFLICT (usuario_id, curso_id)
                DO UPDATE SET
                    ativo = TRUE,
                    data_inicio = CASE
                        WHEN acessos_curso.ativo = TRUE
                            AND (
                                acessos_curso.data_fim IS NULL
                                OR acessos_curso.data_fim > :fim
                            )
                        THEN acessos_curso.data_inicio
                        ELSE :inicio
                    END,
                    data_fim = CASE
                        WHEN acessos_curso.ativo = TRUE
                            AND (
                                acessos_curso.data_fim IS NULL
                                OR acessos_curso.data_fim > :fim
                            )
                        THEN acessos_curso.data_fim
                        ELSE :fim
                    END
            """), {
                "u": user_id,
                "c": curso_id,
                "inicio": data_inicio,
                "fim": data_fim
            })

        pagamento.aprovado_em = data_aprovacao
        pagamento.atualizado_em = datetime.utcnow()

        concluir_oportunidade(db, oportunidade)
        db.commit()
        liberou = compra_ainda_valida

    else:
        db.commit()

    return {
        "ok": True,
        "mp_payment_id": mp_payment_id,
        "status": status_mp.upper(),
        "usuario_id": user_id,
        "curso_id": curso_id,
        "liberou_acesso": liberou
    }

@app.get("/admin/pagamentos", tags=["Admin Pagamentos"])
def admin_listar_pagamentos(
    q: str | None = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas admin")

    q_norm = (q or "").strip().lower()

    sql = """
        SELECT
            p.id,
            p.usuario_id,
            u.nome AS usuario_nome,
            u.email AS usuario_email,
            p.curso_id,
            c.nome AS curso_nome,
            p.status,
            p.valor_cents,
            p.provedor,
            p.moeda,
            p.mp_preference_id,
            p.mp_payment_id,
            p.criado_em,
            p.atualizado_em
        FROM pagamentos p
        JOIN usuarios u ON u.id = p.usuario_id
        JOIN cursos c ON c.id = p.curso_id
    """

    params = {}
    if q_norm:
        sql += """
        WHERE
            LOWER(u.email) LIKE :q
            OR LOWER(u.nome) LIKE :q
            OR LOWER(c.nome) LIKE :q
            OR LOWER(p.status) LIKE :q
            OR CAST(p.id AS TEXT) LIKE :q2
            OR COALESCE(p.mp_payment_id, '') LIKE :q2
            OR COALESCE(p.mp_preference_id, '') LIKE :q2
        """
        params["q"] = f"%{q_norm}%"
        params["q2"] = f"%{(q or '').strip()}%"

    sql += " ORDER BY p.id DESC LIMIT 200"

    rows = db.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]


from fastapi import Body

@app.post("/admin/alunos", tags=["Admin Alunos"])
def admin_criar_aluno(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    if not usuario.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Apenas admin"
        )

    nome = (
        payload.get("nome") or ""
    ).strip()

    email = (
        payload.get("email") or ""
    ).strip().lower()

    cpf = (
        payload.get("cpf") or ""
    ).strip()
    
    data_nascimento = (
        payload.get("data_nascimento")
        or None
    )

    telefone = (
        payload.get("telefone") or ""
    ).strip()

    senha = (
        payload.get("senha") or ""
    ).strip()

    is_admin = bool(
        payload.get(
            "is_admin",
            False
        )
    )

    if (
        not nome
        or not cpf
        or not data_nascimento
        or not email
        or not telefone
        or not senha
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Informe nome, CPF, data de nascimento, "
                "email, telefone e senha"
            )
        )

    existe = (
        db.query(Usuario)
        .filter(
            Usuario.email == email
        )
        .first()
    )

    if existe:
        raise HTTPException(
            status_code=409,
            detail=(
                "Já existe usuário "
                "com esse email"
            )
        )

    existe_cpf = (
        db.query(Usuario)
        .filter(
            Usuario.cpf == cpf
        )
        .first()
    )

    if existe_cpf:
        raise HTTPException(
            status_code=409,
            detail=(
                "Já existe usuário "
                "com esse CPF"
            )
        )

    senha_hash = hash_senha(senha)

    u = Usuario(
        nome=nome,
        email=email,
        cpf=cpf,
        data_nascimento=data_nascimento,
        telefone=telefone,
        senha_hash=senha_hash,
        ativo=True,
        is_admin=is_admin,
        perfil_inicial=(
            "ADMIN"
            if is_admin
            else "ALUNO"
        )
    )

    db.add(u)
    db.commit()
    db.refresh(u)

    return {
        "id": u.id,
        "nome": u.nome,
        "email": u.email,
        "ativo": u.ativo,
        "is_admin": u.is_admin,
        "perfil_inicial":
            u.perfil_inicial
    }

from fastapi import Query

@app.get("/admin/alunos", tags=["Admin Alunos"])
def admin_listar_alunos(
    q: str = Query(default=""),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas admin")

    q = (q or "").strip()
    cpf_busca = "".join(ch for ch in q if ch.isdigit())

    query = db.query(Usuario)

    if q:
        filtros = [
            Usuario.email.ilike(f"%{q}%"),
            Usuario.nome.ilike(f"%{q}%")
        ]

        if cpf_busca and len(cpf_busca) == 11:
            filtros.append(Usuario.cpf == cpf_busca)

        query = query.filter(or_(*filtros))

    # ordena pelos mais recentes
    alunos = query.order_by(Usuario.id.desc()).limit(100).all()

    return [{
        "id": u.id,
        "nome": u.nome,
        "cpf": u.cpf,
        "email": u.email,
        "ativo": u.ativo,
        "is_admin": u.is_admin
    } for u in alunos]

@app.post("/recuperar-senha")
def recuperar_senha(
    dados: RecuperarSenhaRequest,
    db: Session = Depends(get_db)
):
    login_digitado = dados.login.strip()

    login_apenas_digitos = ''.join(
        ch for ch in login_digitado if ch.isdigit()
    )

    eh_email = "@" in login_digitado

    if eh_email:
        usuario = db.query(Usuario).filter(
            Usuario.email == login_digitado.lower()
        ).first()

        if not usuario:
            raise HTTPException(
                status_code=404,
                detail="Não há cadastro registrado com o email informado."
            )

    else:
        usuario = db.query(Usuario).filter(
            Usuario.cpf == login_apenas_digitos
        ).first()

        if not usuario:
            raise HTTPException(
                status_code=404,
                detail="Não há cadastro registrado com o CPF informado."
            )

    # O NOVO TRECHO ENTRA A PARTIR DAQUI

    token_recuperacao = secrets.token_urlsafe(32)

    token_hash = hashlib.sha256(
        token_recuperacao.encode("utf-8")
    ).hexdigest()

    expira_em = (
        datetime.utcnow()
        + timedelta(minutes=30)
    )

    novo_token = TokenRecuperacaoSenha(
        usuario_id=usuario.id,
        token_hash=token_hash,
        expira_em=expira_em,
        usado=False
    )

    db.add(novo_token)

    link_redefinicao = (
        f"{APP_BASE_URL}/redefinir-senha.html"
        f"?token={token_recuperacao}"
    )

    try:
        resend.Emails.send({
            "from": "Quality Estudos <onboarding@resend.dev>",
            "to": [usuario.email],
            "subject": "Redefinição de senha - Quality Estudos",
            "html": f"""
                <h2>Redefinição de senha</h2>

                <p>
                    Olá, {usuario.nome}.
                </p>

                <p>
                    Recebemos uma solicitação para redefinir
                    a senha da sua conta na Quality Estudos.
                </p>

                <p>
                    <a href="{link_redefinicao}">
                        Redefinir minha senha
                    </a>
                </p>

                <p>
                    Este link é válido por 30 minutos.
                </p>

                <p>
                    Se você não solicitou a redefinição,
                    ignore este e-mail.
                </p>
            """
        })

        db.commit()

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=(
                "Não foi possível enviar o e-mail de recuperação. "
                "Tente novamente mais tarde."
            )
        )

    # TERMINA AQUI

    return {
        "ok": True,
        "message": (
            "Verifique seu e-mail para redefinir sua senha!"
        )
    }

@app.post("/redefinir-senha")
def redefinir_senha(
    dados: RedefinirSenhaRequest,
    db: Session = Depends(get_db)
):
    token_hash = hashlib.sha256(
        dados.token.encode("utf-8")
    ).hexdigest()

    registro_token = (
        db.query(TokenRecuperacaoSenha)
        .filter(
            TokenRecuperacaoSenha.token_hash == token_hash
        )
        .first()
    )

    if not registro_token:
        raise HTTPException(
            status_code=400,
            detail="Link de redefinição inválido."
        )

    if registro_token.usado:
        raise HTTPException(
            status_code=400,
            detail=(
                "Este link de redefinição já foi utilizado."
            )
        )

    if registro_token.expira_em < datetime.utcnow():
        raise HTTPException(
            status_code=400,
            detail=(
                "Este link de redefinição expirou. "
                "Solicite uma nova recuperação de senha."
            )
        )

    usuario = (
        db.query(Usuario)
        .filter(
            Usuario.id == registro_token.usuario_id
        )
        .first()
    )

    if not usuario:
        raise HTTPException(
            status_code=404,
            detail="Usuário não encontrado."
        )

    usuario.senha_hash = hash_senha(
        dados.nova_senha
    )

    usuario.tentativas_login = 0
    usuario.bloqueado_login = False

    registro_token.usado = True
    registro_token.usado_em = datetime.utcnow()

    db.commit()

    return {
        "ok": True,
        "message": (
            "Senha redefinida com sucesso!"
        )
    }

@app.post("/me/reembolso/{pagamento_id}")
def solicitar_reembolso(
    pagamento_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    pagamento = db.query(Pagamento).filter(
        Pagamento.id == pagamento_id,
        Pagamento.usuario_id == usuario.id
    ).first()

    if not pagamento:
        raise HTTPException(status_code=404, detail="Pagamento não encontrado")

    if pagamento.status not in ["APPROVED", "approved", "PAGO"]:
        raise HTTPException(
            status_code=400,
            detail="Este pagamento não está elegível para solicitação de reembolso"
        )

    data_referencia = (
        pagamento.aprovado_em
        or pagamento.criado_em
    )

    limite_reembolso = (
        data_referencia
        + timedelta(days=7)
    )

    if datetime.utcnow() > limite_reembolso:
        raise HTTPException(
            status_code=400,
            detail="Prazo de reembolso expirado"
        )

    pagamento.status = "REFUND_REQUESTED"
    pagamento.atualizado_em = datetime.utcnow()

    db.commit()

    return {
        "ok": True,
        "message": "Solicitação de reembolso recebida com sucesso. Nossa equipe processará o estorno em até 72h.",
        "status": pagamento.status
    }

@app.get("/me/reembolsos")
def listar_meus_reembolsos(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    rows = db.execute(text("""
        SELECT
            p.id AS pagamento_id,
            p.curso_id,
            c.nome AS curso_nome,
            p.status,
            p.criado_em AS data_compra,
            p.atualizado_em AS data_atualizacao,
            p.valor_cents
        FROM pagamentos p
        JOIN cursos c ON c.id = p.curso_id
        WHERE p.usuario_id = :usuario_id
          AND p.status IN (
              'REFUND_REQUESTED',
              'REFUNDED',
              'REFUND_DENIED',
              'REFUND_IN_PROCESS',
              'REFUND_ERROR'
          )
        ORDER BY p.atualizado_em DESC
    """), {"usuario_id": usuario.id}).mappings().all()

    return [dict(r) for r in rows]

@app.post("/admin/reembolsos/{pagamento_id}/aprovar")
def aprovar_reembolso(
    pagamento_id: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(get_usuario_atual)
):
    if not admin.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Apenas administradores podem aprovar reembolsos"
        )

    pagamento = db.query(Pagamento).filter(
        Pagamento.id == pagamento_id
    ).first()

    if not pagamento:
        raise HTTPException(
            status_code=404,
            detail="Pagamento não encontrado"
        )

    if pagamento.status != "REFUND_REQUESTED":
        raise HTTPException(
            status_code=400,
            detail="Este pagamento não possui solicitação pendente"
        )

    pagamento.status = "REFUND_IN_PROCESS"
    pagamento.atualizado_em = datetime.utcnow()

    db.commit()

    return {
        "ok": True,
        "message": (
            "Solicitação aprovada. "
            "A devolução financeira ainda precisa ser processada e confirmada."
        ),
        "status": pagamento.status
    }


@app.post("/admin/reembolsos/{pagamento_id}/recusar")
def recusar_reembolso(
    pagamento_id: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(get_usuario_atual)
):
    if not admin.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Apenas administradores podem recusar reembolsos"
        )

    pagamento = db.query(Pagamento).filter(
        Pagamento.id == pagamento_id
    ).first()

    if not pagamento:
        raise HTTPException(
            status_code=404,
            detail="Pagamento não encontrado"
        )

    if pagamento.status != "REFUND_REQUESTED":
        raise HTTPException(
            status_code=400,
            detail="Este pagamento não possui solicitação pendente"
        )

    pagamento.status = "REFUND_DENIED"
    pagamento.atualizado_em = datetime.utcnow()

    db.commit()

    return {
        "ok": True,
        "message": "Solicitação de reembolso recusada. O acesso permanece inalterado.",
        "status": pagamento.status
    }

@app.post("/admin/reembolsos/{pagamento_id}/pix-manual")
def registrar_reembolso_pix_manual(
    pagamento_id: int,
    dados: ReembolsoPixManualCreate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(get_usuario_atual)
):
    if not admin.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Apenas administradores podem registrar reembolsos"
        )

    pagamento = db.query(Pagamento).filter(
        Pagamento.id == pagamento_id
    ).with_for_update().first()

    if not pagamento:
        raise HTTPException(
            status_code=404,
            detail="Pagamento não encontrado"
        )

    if pagamento.status != "REFUND_IN_PROCESS":
        raise HTTPException(
            status_code=400,
            detail="A solicitação precisa estar aprovada"
        )

    # Nesta primeira versão, permitimos apenas reembolso integral.
    if dados.valor_cents != pagamento.valor_cents:
        raise HTTPException(
            status_code=400,
            detail="O valor deve corresponder ao valor integral da compra"
        )

    existente = db.query(ReembolsoFinanceiro).filter(
        ReembolsoFinanceiro.pagamento_id == pagamento_id,
        ReembolsoFinanceiro.status.in_([
            "PENDENTE",
            "EM_PROCESSAMENTO",
            "CONFIRMADO",
            "VERIFICACAO_NECESSARIA"
        ])
    ).first()

    if existente:
        raise HTTPException(
            status_code=409,
            detail="Já existe uma operação de reembolso para este pagamento"
        )

    reembolso = ReembolsoFinanceiro(
        pagamento_id=pagamento_id,
        metodo="PIX_MANUAL",
        valor_cents=dados.valor_cents,
        status="PENDENTE",
        referencia_comprovante=dados.referencia_comprovante
    )

    try:
        db.add(reembolso)
        db.commit()
        db.refresh(reembolso)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Já existe uma operação de reembolso para este pagamento"
        )

    return {
        "ok": True,
        "reembolso_id": reembolso.id,
        "status": reembolso.status,
        "message": (
            "Reembolso manual registrado. "
            "A confirmação financeira ainda está pendente. "
            "O acesso do aluno permanece inalterado."
        )
    }

@app.post("/admin/reembolsos/{reembolso_id}/pix-manual/confirmar")
def confirmar_reembolso_pix_manual(
    reembolso_id: int,
    confirmacao_extrato: bool,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(get_usuario_atual)
):
    if not admin.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Apenas administradores podem confirmar reembolsos"
        )

    if confirmacao_extrato is not True:
        raise HTTPException(
            status_code=400,
            detail="É obrigatório confirmar a conferência do extrato bancário"
        )

    reembolso = db.query(ReembolsoFinanceiro).filter(
        ReembolsoFinanceiro.id == reembolso_id
    ).with_for_update().first()

    if not reembolso:
        raise HTTPException(
            status_code=404,
            detail="Reembolso financeiro não encontrado"
        )

    if reembolso.metodo != "PIX_MANUAL" or reembolso.status != "PENDENTE":
        raise HTTPException(
            status_code=400,
            detail="Este reembolso não está pendente de confirmação manual"
        )

    pagamento = db.query(Pagamento).filter(
        Pagamento.id == reembolso.pagamento_id
    ).with_for_update().first()

    if not pagamento or pagamento.status != "REFUND_IN_PROCESS":
        raise HTTPException(
            status_code=400,
            detail="O pagamento não está apto para confirmação do reembolso"
        )

    if reembolso.valor_cents != pagamento.valor_cents:
        raise HTTPException(
            status_code=400,
            detail="O valor do reembolso não corresponde ao valor da compra"
        )

    agora = datetime.utcnow()

    reembolso.status = "CONFIRMADO"
    reembolso.confirmado_em = agora

    pagamento.status = "REFUNDED"
    pagamento.atualizado_em = agora

    try:
        resultado_acesso = recalcular_acesso_apos_reembolso(
            db=db,
            usuario_id=pagamento.usuario_id,
            curso_id=pagamento.curso_id,
            pagamento_reembolsado_id=pagamento.id,
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    situacao = resultado_acesso["situacao"]

    mensagens = {
        "CONFERENCIA_NECESSARIA": (
            "Reembolso financeiro confirmado. O acesso foi mantido "
            "porque existem compras antigas que exigem conferência."
        ),
        "SEM_DIREITOS_VIGENTES": (
            "Reembolso financeiro confirmado. O acesso ao curso "
            "foi desativado porque não existem outros direitos vigentes."
        ),
        "ACESSO_PRESERVADO": (
            "Reembolso financeiro confirmado. O acesso ao curso "
            "foi preservado por existir outro direito vigente."
        ),
    }

    return {
        "ok": True,
        "reembolso_id": reembolso.id,
        "status": reembolso.status,
        "pagamento_status": pagamento.status,
        "situacao_acesso": situacao,
        "pagamentos_sem_historico": resultado_acesso.get(
            "pagamentos_sem_historico", []
        ),
        "message": mensagens[situacao],
    }

@app.get("/me/compras/historico")
def historico_compras_usuario(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    rows = db.execute(text("""
        SELECT
            p.id AS pagamento_id,
            p.usuario_id,
            p.curso_id,
            c.nome AS nome_curso,
            c.ativo AS curso_ativo,
            p.status AS pagamento_status,
            p.criado_em AS data_aquisicao,
            p.atualizado_em AS data_atualizacao,
            a.ativo AS acesso_ativo,
            a.data_inicio,
            a.data_fim
        FROM pagamentos p
        JOIN cursos c ON c.id = p.curso_id
        LEFT JOIN LATERAL (
            SELECT *
            FROM acessos_curso ax
            WHERE ax.usuario_id = p.usuario_id
              AND ax.curso_id = p.curso_id
            ORDER BY ax.data_inicio DESC NULLS LAST
            LIMIT 1
        ) a ON TRUE
        WHERE p.usuario_id = :usuario_id
          AND p.status IN (
              'APPROVED',
              'PAGO',
              'REFUND_REQUESTED',
              'REFUNDED',
              'REFUND_IN_PROCESS',
              'REFUND_ERROR'
          )
    """), {"usuario_id": usuario.id}).mappings().all()

    historico = []

    for r in rows:
        status_pagamento = (r["pagamento_status"] or "").upper()

        if status_pagamento in ["REFUND_REQUESTED", "REFUNDED", "REFUND_IN_PROCESS", "REFUND_ERROR"]:
            situacao = "Cancelado"
            ordem = 4
        elif r["acesso_ativo"] is True and r["curso_ativo"] is True:
            situacao = "Ativo"
            ordem = 1
        elif r["acesso_ativo"] is True and r["curso_ativo"] is False:
            situacao = "Indisponível"
            ordem = 3
        else:
            situacao = "Expirado"
            ordem = 2

        historico.append({
            "pagamento_id": r["pagamento_id"],
            "curso_id": r["curso_id"],
            "nome_curso": r["nome_curso"],
            "situacao": situacao,
            "pagamento_status": status_pagamento,
            "data_aquisicao": r["data_aquisicao"],
            "data_inicio": r["data_inicio"],
            "data_fim": r["data_fim"],
            "data_atualizacao": r["data_atualizacao"],
            "_ordem": ordem
        })

    historico.sort(
        key=lambda x: (
            x["_ordem"],
            -(x["data_aquisicao"].timestamp() if x["data_aquisicao"] else 0)
        )
    )

    for item in historico:
        item.pop("_ordem", None)

    return historico

@app.get("/assuntos-proprios/{assunto_id}/pasta-teoria")
def obter_pasta_teoria_assunto_proprio(
    assunto_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    assunto = db.query(CursoAssuntoProprio).filter(
        CursoAssuntoProprio.id == assunto_id
    ).first()

    if not assunto:
        raise HTTPException(status_code=404, detail="Assunto não encontrado")

    disciplina = db.query(CursoDisciplinaPropria).filter(
        CursoDisciplinaPropria.id == assunto.curso_disciplina_propria_id
    ).first()

    if not disciplina:
        raise HTTPException(status_code=404, detail="Disciplina não encontrada")

    tem_acesso = db.query(AcessoCurso).filter(
        AcessoCurso.usuario_id == usuario.id,
        AcessoCurso.curso_id == disciplina.curso_id,
        AcessoCurso.ativo == True
    ).first()

    if not usuario.is_admin and not tem_acesso:
        raise HTTPException(status_code=403, detail="Sem acesso a este curso")

    pasta = (
        db.query(Pasta)
        .filter(
            Pasta.curso_assunto_proprio_id == assunto_id,
            Pasta.tipo == "TEORIA"
        )
        .first()
    )

    if not pasta:
        raise HTTPException(status_code=404, detail="Pasta TEORIA não encontrada")

    db.query(Pasta).filter(Pasta.id == pasta.id).with_for_update().first()

    aula = (
        db.query(Aula)
        .filter(Aula.pasta_id == pasta.id)
        .order_by(Aula.ordem.asc(), Aula.id.asc())
        .first()
    )

    if not aula:
        aula = Aula(
            pasta_id=pasta.id,
            titulo="Aula principal",
            descricao=None,
            ordem=1,
            ativo=True
        )

        db.add(aula)
        db.commit()
        db.refresh(aula)

    return {
        "id": pasta.id,
        "curso_assunto_proprio_id": pasta.curso_assunto_proprio_id,
        "tipo": pasta.tipo,
        "nome": pasta.nome,
        "aula_id": aula.id
    }

@app.post("/pastas/{pasta_id}/aulas")
def criar_aula_pasta(
    pasta_id: int,
    dados: AulaCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):

    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas admin")

    pasta = db.query(Pasta).filter(Pasta.id == pasta_id).first()

    if not pasta:
        raise HTTPException(status_code=404, detail="Pasta não encontrada")

    if pasta.curso_assunto_proprio_id:
        db.query(Pasta).filter(Pasta.id == pasta.id).with_for_update().first()
        if db.query(Aula).filter(Aula.pasta_id == pasta.id).first():
            raise HTTPException(409, "O assunto já possui sua aula técnica")

    aula = Aula(
        pasta_id=pasta_id,
        titulo=dados.titulo.strip(),
        descricao=dados.descricao,
        ordem=dados.ordem,
        ativo=dados.ativo
    )

    db.add(aula)
    db.commit()
    db.refresh(aula)

    return aula

@app.put("/aulas/{aula_id}")
def editar_aula(
    aula_id: int,
    dados: AulaUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):

    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas admin")

    aula = db.query(Aula).filter(Aula.id == aula_id).first()

    if not aula:
        raise HTTPException(status_code=404, detail="Aula não encontrada")

    if dados.titulo is not None:
        aula.titulo = dados.titulo.strip()

    if dados.descricao is not None:
        aula.descricao = dados.descricao

    if dados.ordem is not None:
        aula.ordem = dados.ordem

    if dados.ativo is not None:
        aula.ativo = dados.ativo

    db.commit()
    db.refresh(aula)

    return aula

@app.delete("/aulas/{aula_id}")
def excluir_aula(
    aula_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):

    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas admin")

    aula = db.query(Aula).filter(Aula.id == aula_id).first()

    if not aula:
        raise HTTPException(status_code=404, detail="Aula não encontrada")

    db.delete(aula)
    db.commit()

    return {"mensagem": "Aula removida com sucesso"}

@app.post("/baterias/concluir")
def concluir_bateria_aluno(
    dados: ConcluirBateriaCreate,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    bateria = db.query(Bateria).filter(Bateria.id == dados.bateria_id).first()

    if not bateria:
        raise HTTPException(status_code=404, detail="Bateria não encontrada")

    questoes = (
        db.query(Questao)
        .filter(Questao.bateria_id == dados.bateria_id)
        .order_by(Questao.ordem.asc(), Questao.id.asc())
        .all()
    )

    if len(questoes) != 10:
        raise HTTPException(
            status_code=400,
            detail="A bateria precisa ter 10 questões"
        )

    respostas_por_questao = {
        r.questao_id: r
        for r in dados.respostas
    }

    questoes_nao_respondidas = [
        q.ordem
        for q in questoes
        if q.id not in respostas_por_questao
    ]

    if questoes_nao_respondidas:
        raise HTTPException(
            status_code=400,
            detail=f"Questões não respondidas: {questoes_nao_respondidas}"
        )

    aula = db.query(Aula).filter(Aula.id == bateria.aula_id).first()

    if not aula:
        raise HTTPException(status_code=404, detail="Aula da bateria não encontrada")

    pasta = db.query(Pasta).filter(Pasta.id == aula.pasta_id).first()

    if not pasta:
        raise HTTPException(status_code=404, detail="Pasta da aula não encontrada")

    if not pasta.curso_assunto_proprio_id:
        raise HTTPException(
            status_code=400,
            detail="Bateria não vinculada a um assunto próprio de curso"
        )

    assunto = db.query(CursoAssuntoProprio).filter(
        CursoAssuntoProprio.id == pasta.curso_assunto_proprio_id
    ).first()

    if not assunto:
        raise HTTPException(
            status_code=404,
            detail="Assunto próprio do curso não encontrado"
        )

    disciplina = db.query(CursoDisciplinaPropria).filter(
        CursoDisciplinaPropria.id == assunto.curso_disciplina_propria_id
    ).first()

    if not disciplina:
        raise HTTPException(
            status_code=404,
            detail="Disciplina própria do curso não encontrada"
        )

    contexto = validar_contexto_estudo(
        db=db,
        usuario=usuario_atual,
        curso_id=disciplina.curso_id,
        contratacao_id=dados.contratacao_id,
        demonstracao_id=dados.demonstracao_id,
    )

    try:
        tentativa = TentativaBateria(
            usuario_id=usuario_atual.id,
            bateria_id=dados.bateria_id,
            contratacao_id=contexto["contratacao_id"],
            demonstracao_id=contexto["demonstracao_id"],
            status="EM_ANDAMENTO",
            percentual_acerto=0,
            concluida_em=datetime.utcnow(),
            ativo=True
        )

        db.add(tentativa)
        db.flush()

        total_acertos = 0

        for q in questoes:
            resposta = respostas_por_questao[q.id]

            marcada = (resposta.resposta_marcada or "").strip().upper()
            gabarito = (q.gabarito or "").strip().upper()

            pulou = marcada in ("NAO_SEI", "NAO TENHO CERTEZA OU NAO SEI", "PULOU")
            acertou = (marcada == gabarito) and not pulou

            if acertou:
                total_acertos += 1

            db.add(RespostaAlunoQuestao(
                tentativa_id=tentativa.id,
                usuario_id=usuario_atual.id,
                bateria_id=dados.bateria_id,
                questao_id=q.id,
                contratacao_id=contexto["contratacao_id"],
                demonstracao_id=contexto["demonstracao_id"],
                resposta_marcada=marcada,
                gabarito=gabarito,
                acertou=acertou,
                pulou=pulou,
                rever=resposta.rever,
                dificuldade=resposta.dificuldade
            ))

        tem_certo_errado = any(q.tipo == "CERTO_ERRADO" for q in questoes)

        if tem_certo_errado:
            total_erros = 0

            for q in questoes:
                resposta = respostas_por_questao[q.id]
                marcada = (resposta.resposta_marcada or "").strip().upper()
                gabarito = (q.gabarito or "").strip().upper()

                pulou = marcada in ("NAO_SEI", "NAO TENHO CERTEZA OU NAO SEI", "PULOU")

                if not pulou and marcada != gabarito:
                    total_erros += 1

            pontuacao_liquida = total_acertos - total_erros
            percentual = round((pontuacao_liquida / len(questoes)) * 100)

        else:
            percentual = round((total_acertos / len(questoes)) * 100)

        tentativa.percentual_acerto = percentual

        db.commit()
        db.refresh(tentativa)

        return {
            "id": tentativa.id,
            "usuario_id": tentativa.usuario_id,
            "bateria_id": tentativa.bateria_id,
            "status": tentativa.status,
            "percentual_acerto": tentativa.percentual_acerto
        }
    except Exception:
        db.rollback()
        raise

@app.delete("/baterias/{bateria_id}")
def excluir_bateria(
    bateria_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):

    if not usuario.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Apenas admin"
        )

    bateria = bloquear_pai(db, Bateria, bateria_id)
    garantir_sem_historico(db, bateria)
    questoes_ids = [q.id for q in db.query(Questao.id).filter(Questao.bateria_id == bateria_id).all()]
    if questoes_ids:
        db.query(Comentario).filter(Comentario.questao_id.in_(questoes_ids)).delete(synchronize_session=False)
        db.query(Alternativa).filter(Alternativa.questao_id.in_(questoes_ids)).delete(synchronize_session=False)
        db.query(Questao).filter(Questao.bateria_id == bateria_id).delete(synchronize_session=False)
    db.delete(bateria)
    confirmar_conteudo(db)

    return {
        "mensagem": "Bateria removida com sucesso"
    }   

@app.put("/tentativas/{tentativa_id}/finalizar-revisao")
def finalizar_revisao_tentativa(
    tentativa_id: int,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    tentativa = db.query(TentativaBateria).filter(
        TentativaBateria.id == tentativa_id,
        TentativaBateria.usuario_id == usuario_atual.id
    ).first()

    if not tentativa:
        raise HTTPException(
            status_code=404,
            detail="Tentativa não encontrada"
        )

    # O contexto da revisão é o mesmo contexto em que
    # a tentativa foi realizada.
    contexto_contratacao_id = tentativa.contratacao_id
    contexto_demonstracao_id = tentativa.demonstracao_id

    if bool(contexto_contratacao_id) == bool(contexto_demonstracao_id):
        raise HTTPException(
            status_code=400,
            detail="Tentativa sem contexto de acesso válido."
        )

    tentativa.status = "FEITA"
    tentativa.revisao_concluida_em = datetime.utcnow()

    bateria = db.query(Bateria).filter(
        Bateria.id == tentativa.bateria_id
    ).first()

    if not bateria:
        raise HTTPException(
            status_code=404,
            detail="Bateria não encontrada"
        )

    aula = db.query(Aula).filter(
        Aula.id == bateria.aula_id
    ).first()

    if not aula:
        raise HTTPException(
            status_code=404,
            detail="Aula não encontrada"
        )

    from app.revisoes import estrutura, programar_primeira
    _, _, disciplina, _ = estrutura(db, aula.pasta_id)
    validar_contexto_estudo(db=db, usuario=usuario_atual, curso_id=disciplina.curso_id,
                           contratacao_id=contexto_contratacao_id,
                           demonstracao_id=contexto_demonstracao_id)
    if tentativa.revisao_id is not None:
        raise HTTPException(409, "Use o fluxo próprio de Revisões")
    if not tentativa.ativo:
        raise HTTPException(409, "Tentativa inativa")
    programar_primeira(db, usuario_atual.id, aula,
                      contexto_contratacao_id, contexto_demonstracao_id)

    db.commit()
    db.refresh(tentativa)

    return {
        "id": tentativa.id,
        "bateria_id": tentativa.bateria_id,
        "status": tentativa.status,
        "percentual_acerto": tentativa.percentual_acerto
    }

@app.get("/aulas/{aula_id}/baterias-com-status")
def listar_baterias_com_status_do_aluno(
    aula_id: int,
    contratacao_id: int | None = None,
    demonstracao_id: int | None = None,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    aula = db.query(Aula).filter(
        Aula.id == aula_id
    ).first()

    if not aula:
        raise HTTPException(
            status_code=404,
            detail="Aula não encontrada"
        )

    pasta = db.query(Pasta).filter(
        Pasta.id == aula.pasta_id
    ).first()

    if not pasta:
        raise HTTPException(
            status_code=404,
            detail="Pasta da aula não encontrada"
        )

    if not pasta.curso_assunto_proprio_id:
        raise HTTPException(
            status_code=400,
            detail="Aula não vinculada a um assunto próprio de curso"
        )

    assunto = db.query(CursoAssuntoProprio).filter(
        CursoAssuntoProprio.id == pasta.curso_assunto_proprio_id
    ).first()

    if not assunto:
        raise HTTPException(
            status_code=404,
            detail="Assunto próprio do curso não encontrado"
        )

    disciplina = db.query(CursoDisciplinaPropria).filter(
        CursoDisciplinaPropria.id == assunto.curso_disciplina_propria_id
    ).first()

    if not disciplina:
        raise HTTPException(
            status_code=404,
            detail="Disciplina própria do curso não encontrada"
        )

    validar_contexto_estudo(
        db=db,
        usuario=usuario_atual,
        curso_id=disciplina.curso_id,
        contratacao_id=contratacao_id,
        demonstracao_id=demonstracao_id,
    )

    from app.revisoes import disponiveis
    conjunto = disponiveis(db, aula_id)
    baterias = [b for b, _ in conjunto]
    quantidade = {b.id: len(qs) for b, qs in conjunto}

    resultado = []

    for b in baterias:
        tentativa_query = (
            db.query(TentativaBateria)
            .filter(
                TentativaBateria.usuario_id == usuario_atual.id,
                TentativaBateria.bateria_id == b.id,
                TentativaBateria.ativo == True,
                TentativaBateria.revisao_id.is_(None)
            )
        )

        if contratacao_id is not None:
            tentativa_query = tentativa_query.filter(
                TentativaBateria.contratacao_id == contratacao_id,
                TentativaBateria.demonstracao_id.is_(None)
            )
        else:
            tentativa_query = tentativa_query.filter(
                TentativaBateria.contratacao_id.is_(None),
                TentativaBateria.demonstracao_id == demonstracao_id
            )

        tentativa = (
            tentativa_query
            .order_by(TentativaBateria.id.desc())
            .first()
        )

        resultado.append({
            "id": b.id,
            "aula_id": b.aula_id,
            "titulo": b.titulo,
            "ordem": b.ordem,
            "status_bateria": b.status,
            "questoes_count": quantidade[b.id],
            "status_aluno": tentativa.status if tentativa else None,
            "percentual_acerto": tentativa.percentual_acerto if tentativa else None,
            "tentativa_id": tentativa.id if tentativa else None
        })

    return resultado

@app.put("/baterias/{bateria_id}/limpar-minha-sprint")
def limpar_minha_sprint(
    bateria_id: int,
    contratacao_id: int | None = None,
    demonstracao_id: int | None = None,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    # ---------------------------------------------------------
    # Valida o contexto de estudo.
    # ---------------------------------------------------------
    if contratacao_id is None and demonstracao_id is None:
        raise HTTPException(
            status_code=400,
            detail="É necessário informar contratacao_id ou demonstracao_id"
        )

    if contratacao_id is not None and demonstracao_id is not None:
        raise HTTPException(
            status_code=400,
            detail="Informe apenas um contexto de estudo"
        )

    # ---------------------------------------------------------
    # Localiza a bateria.
    # ---------------------------------------------------------
    bateria = (
        db.query(Bateria)
        .filter(Bateria.id == bateria_id)
        .first()
    )

    if not bateria:
        raise HTTPException(
            status_code=404,
            detail="Bateria não encontrada"
        )

    # ---------------------------------------------------------
    # Identifica o curso da bateria:
    # bateria -> aula -> pasta -> assunto -> disciplina -> curso
    # ---------------------------------------------------------
    aula = (
        db.query(Aula)
        .filter(Aula.id == bateria.aula_id)
        .first()
    )

    if not aula:
        raise HTTPException(
            status_code=404,
            detail="Aula da bateria não encontrada"
        )

    pasta = (
        db.query(Pasta)
        .filter(Pasta.id == aula.pasta_id)
        .first()
    )

    if not pasta:
        raise HTTPException(
            status_code=404,
            detail="Pasta da aula não encontrada"
        )

    if not pasta.curso_assunto_proprio_id:
        raise HTTPException(
            status_code=400,
            detail="Bateria não vinculada a um assunto próprio de curso"
        )

    assunto = (
        db.query(CursoAssuntoProprio)
        .filter(
            CursoAssuntoProprio.id == pasta.curso_assunto_proprio_id
        )
        .first()
    )

    if not assunto:
        raise HTTPException(
            status_code=404,
            detail="Assunto próprio do curso não encontrado"
        )

    disciplina = (
        db.query(CursoDisciplinaPropria)
        .filter(
            CursoDisciplinaPropria.id ==
            assunto.curso_disciplina_propria_id
        )
        .first()
    )

    if not disciplina:
        raise HTTPException(
            status_code=404,
            detail="Disciplina própria do curso não encontrada"
        )

    # ---------------------------------------------------------
    # Valida que o contexto pertence ao usuário e ao curso.
    # ---------------------------------------------------------
    contexto = validar_contexto_estudo(
        db=db,
        usuario=usuario_atual,
        curso_id=disciplina.curso_id,
        contratacao_id=contratacao_id,
        demonstracao_id=demonstracao_id,
    )

    # ---------------------------------------------------------
    # Desativa SOMENTE a tentativa do contexto informado.
    # ---------------------------------------------------------
    tentativas_query = (
        db.query(TentativaBateria)
        .filter(
            TentativaBateria.usuario_id == usuario_atual.id,
            TentativaBateria.bateria_id == bateria_id,
            TentativaBateria.ativo == True,
            TentativaBateria.contratacao_id ==
                contexto["contratacao_id"],
            TentativaBateria.demonstracao_id ==
                contexto["demonstracao_id"],
        )
    )

    tentativas_ativas = tentativas_query.all()

    for tentativa in tentativas_ativas:
        tentativa.ativo = False

    db.commit()

    return {
        "mensagem": "Sprint liberada para ser refeita."
    }


@app.get("/baterias/{bateria_id}/minha-tentativa-ativa")
def obter_minha_tentativa_ativa(
    bateria_id: int,
    contratacao_id: int | None = None,
    demonstracao_id: int | None = None,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    bateria = db.query(Bateria).filter(
        Bateria.id == bateria_id
    ).first()

    if not bateria:
        raise HTTPException(
            status_code=404,
            detail="Bateria não encontrada"
        )

    aula = db.query(Aula).filter(
        Aula.id == bateria.aula_id
    ).first()

    if not aula:
        raise HTTPException(
            status_code=404,
            detail="Aula da bateria não encontrada"
        )

    pasta = db.query(Pasta).filter(
        Pasta.id == aula.pasta_id
    ).first()

    if not pasta:
        raise HTTPException(
            status_code=404,
            detail="Pasta da aula não encontrada"
        )

    if not pasta.curso_assunto_proprio_id:
        raise HTTPException(
            status_code=400,
            detail="Bateria não vinculada a um assunto próprio de curso"
        )

    assunto = db.query(CursoAssuntoProprio).filter(
        CursoAssuntoProprio.id == pasta.curso_assunto_proprio_id
    ).first()

    if not assunto:
        raise HTTPException(
            status_code=404,
            detail="Assunto próprio do curso não encontrado"
        )

    disciplina = db.query(CursoDisciplinaPropria).filter(
        CursoDisciplinaPropria.id == assunto.curso_disciplina_propria_id
    ).first()

    if not disciplina:
        raise HTTPException(
            status_code=404,
            detail="Disciplina própria do curso não encontrada"
        )

    contexto = validar_contexto_estudo(
        db=db,
        usuario=usuario_atual,
        curso_id=disciplina.curso_id,
        contratacao_id=contratacao_id,
        demonstracao_id=demonstracao_id,
    )

    tentativa_query = (
        db.query(TentativaBateria)
        .filter(
            TentativaBateria.usuario_id == usuario_atual.id,
            TentativaBateria.bateria_id == bateria_id,
            TentativaBateria.ativo == True,
            TentativaBateria.revisao_id.is_(None),
            TentativaBateria.contratacao_id == contexto["contratacao_id"],
            TentativaBateria.demonstracao_id == contexto["demonstracao_id"],
        )
    )

    tentativa = (
        tentativa_query
        .order_by(TentativaBateria.id.desc())
        .first()
    )

    if not tentativa:
        return {
            "tentativa": None,
            "respostas": []
        }

    respostas = (
        db.query(RespostaAlunoQuestao)
        .filter(
            RespostaAlunoQuestao.tentativa_id == tentativa.id,
            RespostaAlunoQuestao.usuario_id == usuario_atual.id,
            RespostaAlunoQuestao.bateria_id == bateria_id,
            RespostaAlunoQuestao.contratacao_id == contexto["contratacao_id"],
            RespostaAlunoQuestao.demonstracao_id == contexto["demonstracao_id"],
        )
        .all()
    )

    return {
        "tentativa": {
            "id": tentativa.id,
            "bateria_id": tentativa.bateria_id,
            "status": tentativa.status,
            "percentual_acerto": tentativa.percentual_acerto
        },
        "respostas": [
            {
                "questao_id": r.questao_id,
                "resposta_marcada": r.resposta_marcada,
                "dificuldade": r.dificuldade,
                "acertou": r.acertou,
                "pulou": r.pulou,
                "rever": r.rever
            }
            for r in respostas
        ]
    }

@app.get("/me/questoes-para-rever")
def listar_questoes_para_rever(
    contratacao_id: int | None = None,
    demonstracao_id: int | None = None,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    # ---------------------------------------------------------
    # Valida o contexto de estudo.
    # ---------------------------------------------------------
    if contratacao_id is None and demonstracao_id is None:
        raise HTTPException(
            status_code=400,
            detail="É necessário informar contratacao_id ou demonstracao_id"
        )

    if contratacao_id is not None and demonstracao_id is not None:
        raise HTTPException(
            status_code=400,
            detail="Informe apenas um contexto de estudo"
        )

    # ---------------------------------------------------------
    # Identifica o curso a partir do contexto informado.
    # ---------------------------------------------------------
    if contratacao_id is not None:
        contratacao = (
            db.query(ContratacaoCurso)
            .filter(
                ContratacaoCurso.id == contratacao_id,
                ContratacaoCurso.usuario_id == usuario_atual.id
            )
            .first()
        )

        if not contratacao:
            raise HTTPException(
                status_code=404,
                detail="Contratação não encontrada"
            )

        curso_id = contratacao.curso_id

    else:
        demonstracao = (
            db.query(DemonstracaoCurso)
            .filter(
                DemonstracaoCurso.id == demonstracao_id,
                DemonstracaoCurso.usuario_id == usuario_atual.id
            )
            .first()
        )

        if not demonstracao:
            raise HTTPException(
                status_code=404,
                detail="Demonstração não encontrada"
            )

        curso_id = demonstracao.curso_id

    # ---------------------------------------------------------
    # Valida o contexto de estudo.
    # ---------------------------------------------------------
    validar_contexto_estudo(
        db=db,
        usuario=usuario_atual,
        curso_id=curso_id,
        contratacao_id=contratacao_id,
        demonstracao_id=demonstracao_id,
    )

    # ---------------------------------------------------------
    # Busca somente questões marcadas para revisão dentro
    # do contexto informado.
    # ---------------------------------------------------------
    respostas_query = (
        db.query(RespostaAlunoQuestao)
        .filter(
            RespostaAlunoQuestao.usuario_id == usuario_atual.id,
            RespostaAlunoQuestao.rever == True
        )
    )

    if contratacao_id is not None:
        respostas_query = respostas_query.filter(
            RespostaAlunoQuestao.contratacao_id == contratacao_id,
            RespostaAlunoQuestao.demonstracao_id.is_(None)
        )
    else:
        respostas_query = respostas_query.filter(
            RespostaAlunoQuestao.contratacao_id.is_(None),
            RespostaAlunoQuestao.demonstracao_id == demonstracao_id
        )

    respostas = (
        respostas_query
        .order_by(RespostaAlunoQuestao.criada_em.desc())
        .all()
    )

    resultado = []

    for r in respostas:
        questao = (
            db.query(Questao)
            .filter(Questao.id == r.questao_id)
            .first()
        )

        bateria = (
            db.query(Bateria)
            .filter(Bateria.id == r.bateria_id)
            .first()
        )

        resultado.append({
            "resposta_id": r.id,
            "questao_id": r.questao_id,
            "bateria_id": r.bateria_id,
            "bateria_titulo": bateria.titulo if bateria else None,
            "enunciado": questao.enunciado if questao else None,
            "comentario": questao.comentario if questao else None,
            "resposta_marcada": r.resposta_marcada,
            "gabarito": r.gabarito,
            "acertou": r.acertou,
            "pulou": r.pulou,
            "dificuldade": r.dificuldade,
            "rever": r.rever,
            "criada_em": r.criada_em
        })

    return resultado

@app.get("/me/questoes-criticas")
def listar_questoes_criticas(
    curso_id: int | None = None,
    contratacao_id: int | None = None,
    demonstracao_id: int | None = None,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    # ---------------------------------------------------------
    # Valida e identifica o contexto de estudo.
    # ---------------------------------------------------------
    contexto_contratacao_id = contratacao_id
    contexto_demonstracao_id = demonstracao_id

    if contratacao_id is None and demonstracao_id is None:
        raise HTTPException(
            status_code=400,
            detail="É necessário informar contratacao_id ou demonstracao_id"
        )

    if contratacao_id is not None and demonstracao_id is not None:
        raise HTTPException(
            status_code=400,
            detail="Informe apenas um contexto de estudo"
        )

    # ---------------------------------------------------------
    # Obtém o curso diretamente do contexto informado.
    #
    # Não dependemos de existir uma resposta anterior.
    # Um contexto válido pode existir mesmo que o aluno ainda
    # não tenha respondido nenhuma questão.
    # ---------------------------------------------------------
    if contratacao_id is not None:
        contratacao = (
            db.query(ContratacaoCurso)
            .filter(
                ContratacaoCurso.id == contratacao_id,
                ContratacaoCurso.usuario_id == usuario_atual.id
            )
            .first()
        )

        if not contratacao:
            raise HTTPException(
                status_code=404,
                detail="Contratação não encontrada"
            )

        curso_id_contexto = contratacao.curso_id

    else:
        demonstracao = (
            db.query(DemonstracaoCurso)
            .filter(
                DemonstracaoCurso.id == demonstracao_id,
                DemonstracaoCurso.usuario_id == usuario_atual.id
            )
            .first()
        )

        if not demonstracao:
            raise HTTPException(
                status_code=404,
                detail="Demonstração não encontrada"
            )

        curso_id_contexto = demonstracao.curso_id

    if curso_id is not None and curso_id_contexto != curso_id:
        raise HTTPException(
            status_code=403,
            detail="O contexto informado não pertence ao curso solicitado"
        )

    validar_contexto_estudo(
        db=db,
        usuario=usuario_atual,
        curso_id=curso_id_contexto,
        contratacao_id=contexto_contratacao_id,
        demonstracao_id=contexto_demonstracao_id,
    )

    # ---------------------------------------------------------
    query = (
        db.query(
            RespostaAlunoQuestao,
            Questao,
            Bateria,
            Aula,
            Pasta,
            CursoAssuntoProprio,
            CursoDisciplinaPropria
        )
        .join(
            Questao,
            Questao.id == RespostaAlunoQuestao.questao_id
        )
        .join(
            Bateria,
            Bateria.id == RespostaAlunoQuestao.bateria_id
        )
        .join(
            Aula,
            Aula.id == Bateria.aula_id
        )
        .join(
            Pasta,
            Pasta.id == Aula.pasta_id
        )
        .join(
            CursoAssuntoProprio,
            CursoAssuntoProprio.id ==
            Pasta.curso_assunto_proprio_id
        )
        .join(
            CursoDisciplinaPropria,
            CursoDisciplinaPropria.id ==
            CursoAssuntoProprio.curso_disciplina_propria_id
        )
        .filter(
            RespostaAlunoQuestao.usuario_id == usuario_atual.id
        )
    )

    if contexto_contratacao_id is not None:
        query = query.filter(
            RespostaAlunoQuestao.contratacao_id ==
            contexto_contratacao_id,
            RespostaAlunoQuestao.demonstracao_id.is_(None)
        )
    else:
        query = query.filter(
            RespostaAlunoQuestao.contratacao_id.is_(None),
            RespostaAlunoQuestao.demonstracao_id ==
            contexto_demonstracao_id
        )

    if curso_id is not None:
        query = query.filter(
            CursoDisciplinaPropria.curso_id == curso_id
        )

    registros = (
        query
        .order_by(
            CursoDisciplinaPropria.ordem.asc(),
            CursoAssuntoProprio.ordem.asc(),
            Bateria.ordem.asc(),
            Questao.ordem.asc(),
            RespostaAlunoQuestao.criada_em.desc()
        )
        .all()
    )

    agrupadas = {}

    for resposta, questao, bateria, aula, pasta, assunto, disciplina in registros:
        erro = resposta.acertou is False and resposta.pulou is False
        dificil = resposta.dificuldade == "DIFICIL"
        para_rever = resposta.rever is True

        if not erro and not dificil and not para_rever:
            continue

        chave = questao.id

        if chave not in agrupadas:
            agrupadas[chave] = {
                "resposta_id": resposta.id,
                "questao_id": questao.id,
                "bateria_id": bateria.id,
                "bateria_titulo": bateria.titulo,

                "disciplina_id": disciplina.id,
                "disciplina_nome": disciplina.nome,
                "disciplina_ordem": disciplina.ordem,

                "assunto_id": assunto.id,
                "assunto_nome": assunto.nome,
                "assunto_ordem": assunto.ordem,

                "questao_ordem": questao.ordem,
                "tipo": questao.tipo,
                "tipo_questao": questao.tipo_questao,
                "enunciado": questao.enunciado,
                "comentario": questao.comentario,

                "alternativas": [
                    {
                        "letra": alternativa.letra,
                        "texto": alternativa.texto
                    }
                    for alternativa in (
                        db.query(Alternativa)
                        .filter(
                            Alternativa.questao_id == questao.id
                        )
                        .order_by(Alternativa.letra.asc())
                        .all()
                    )
                ],

                "resposta_marcada": resposta.resposta_marcada,
                "gabarito": resposta.gabarito,

                "erro": False,
                "dificil": False,
                "para_rever": False,

                "qtd_erros": 0,
                "criada_em": resposta.criada_em
            }

        if erro:
            agrupadas[chave]["erro"] = True
            agrupadas[chave]["qtd_erros"] += 1

        if dificil:
            agrupadas[chave]["dificil"] = True

        if para_rever:
            agrupadas[chave]["para_rever"] = True

    resultado = list(agrupadas.values())

    resultado.sort(
        key=lambda q: (
            q["disciplina_ordem"],
            q["assunto_ordem"],
            q["questao_ordem"]
        )
    )

    return resultado

@app.get("/me/revisoes")
def listar_minhas_revisoes(
    contratacao_id: int | None = None,
    demonstracao_id: int | None = None,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    # ---------------------------------------------------------
    # Valida o contexto de estudo.
    # ---------------------------------------------------------
    if contratacao_id is None and demonstracao_id is None:
        raise HTTPException(
            status_code=400,
            detail="É necessário informar contratacao_id ou demonstracao_id"
        )

    if contratacao_id is not None and demonstracao_id is not None:
        raise HTTPException(
            status_code=400,
            detail="Informe apenas um contexto de estudo"
        )

    # ---------------------------------------------------------
    # Localiza uma revisão do contexto para descobrir o curso.
    # ---------------------------------------------------------
    revisao_base_query = (
        db.query(RevisaoAluno)
        .filter(
            RevisaoAluno.usuario_id == usuario_atual.id
        )
    )

    if contratacao_id is not None:
        revisao_base_query = revisao_base_query.filter(
            RevisaoAluno.contratacao_id == contratacao_id,
            RevisaoAluno.demonstracao_id.is_(None)
        )
    else:
        revisao_base_query = revisao_base_query.filter(
            RevisaoAluno.contratacao_id.is_(None),
            RevisaoAluno.demonstracao_id == demonstracao_id
        )

    revisao_base = (
        revisao_base_query
        .order_by(RevisaoAluno.id.desc())
        .first()
    )

    # ---------------------------------------------------------
    # Se ainda não existe revisão, valida diretamente o contexto.
    # ---------------------------------------------------------
    if revisao_base is None:
        if contratacao_id is not None:
            contratacao = (
                db.query(ContratacaoCurso)
                .filter(
                    ContratacaoCurso.id == contratacao_id,
                    ContratacaoCurso.usuario_id == usuario_atual.id
                )
                .first()
            )

            if not contratacao:
                raise HTTPException(
                    status_code=404,
                    detail="Contratação não encontrada"
                )

            curso_id = contratacao.curso_id

        else:
            demonstracao = (
                db.query(DemonstracaoCurso)
                .filter(
                    DemonstracaoCurso.id == demonstracao_id,
                    DemonstracaoCurso.usuario_id == usuario_atual.id
                )
                .first()
            )

            if not demonstracao:
                raise HTTPException(
                    status_code=404,
                    detail="Demonstração não encontrada"
                )

            curso_id = demonstracao.curso_id

    else:
        pasta = db.query(Pasta).filter(
            Pasta.id == revisao_base.pasta_id
        ).first()

        if not pasta or not pasta.curso_assunto_proprio_id:
            raise HTTPException(
                status_code=400,
                detail="Revisão não vinculada a um assunto próprio de curso"
            )

        assunto = db.query(CursoAssuntoProprio).filter(
            CursoAssuntoProprio.id == pasta.curso_assunto_proprio_id
        ).first()

        if not assunto:
            raise HTTPException(
                status_code=404,
                detail="Assunto próprio do curso não encontrado"
            )

        disciplina = db.query(CursoDisciplinaPropria).filter(
            CursoDisciplinaPropria.id == assunto.curso_disciplina_propria_id
        ).first()

        if not disciplina:
            raise HTTPException(
                status_code=404,
                detail="Disciplina própria do curso não encontrada"
            )

        curso_id = disciplina.curso_id

    validar_contexto_estudo(
        db=db,
        usuario=usuario_atual,
        curso_id=curso_id,
        contratacao_id=contratacao_id,
        demonstracao_id=demonstracao_id,
    )

    # ---------------------------------------------------------
    # Busca somente revisões do contexto informado.
    # ---------------------------------------------------------
    revisoes_query = (
        db.query(RevisaoAluno)
        .filter(
            RevisaoAluno.usuario_id == usuario_atual.id,
            RevisaoAluno.status == "PENDENTE"
        )
    )

    if contratacao_id is not None:
        revisoes_query = revisoes_query.filter(
            RevisaoAluno.contratacao_id == contratacao_id,
            RevisaoAluno.demonstracao_id.is_(None)
        )
    else:
        revisoes_query = revisoes_query.filter(
            RevisaoAluno.contratacao_id.is_(None),
            RevisaoAluno.demonstracao_id == demonstracao_id
        )

    revisoes = (
        revisoes_query
        .order_by(RevisaoAluno.data_prevista.asc())
        .all()
    )

    resultado = []

    for r in revisoes:
        aula = db.query(Aula).filter(
            Aula.id == r.aula_id
        ).first()

        resultado.append({
            "id": r.id,
            "aula_id": r.aula_id,
            "pasta_id": r.pasta_id,
            "titulo": aula.titulo if aula else "Aula",
            "etapa": r.etapa,
            "data_prevista": r.data_prevista,
            "status": r.status,
            "contratacao_id": r.contratacao_id,
            "demonstracao_id": r.demonstracao_id
        })

    return resultado


from app.revisoes import registrar_rotas as registrar_rotas_revisoes
registrar_rotas_revisoes(app, get_db, get_usuario_atual, validar_contexto_estudo)


@app.post("/me/anotacoes-questoes")
def criar_anotacao_questao(
    payload: schemas.AnotacaoQuestaoCreate,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    payload = payload.model_dump()
    questao_id = payload.get("questao_id")
    bateria_id = payload.get("bateria_id")
    texto = (payload.get("texto") or "").strip()

    contratacao_id = payload.get("contratacao_id")
    demonstracao_id = payload.get("demonstracao_id")

    if not questao_id or not bateria_id:
        raise HTTPException(
            status_code=400,
            detail="Informe questao_id e bateria_id"
        )

    if not texto:
        raise HTTPException(
            status_code=400,
            detail="Informe a anotação"
        )

    if len(texto.split()) > 300:
        raise HTTPException(
            status_code=400,
            detail="A anotação deve ter no máximo 300 palavras"
        )

    # ---------------------------------------------------------
    # Valida o contexto de estudo.
    # ---------------------------------------------------------
    if contratacao_id is None and demonstracao_id is None:
        raise HTTPException(
            status_code=400,
            detail="É necessário informar contratacao_id ou demonstracao_id"
        )

    if contratacao_id is not None and demonstracao_id is not None:
        raise HTTPException(
            status_code=400,
            detail="Informe apenas um contexto de estudo"
        )

    questao = (
        db.query(Questao)
        .filter(Questao.id == questao_id)
        .first()
    )

    if not questao:
        raise HTTPException(
            status_code=404,
            detail="Questão não encontrada"
        )

    # ---------------------------------------------------------
    # Confirma que a bateria informada corresponde à questão.
    # ---------------------------------------------------------
    if questao.bateria_id != bateria_id:
        raise HTTPException(
            status_code=400,
            detail="A questão não pertence à bateria informada"
        )

    # ---------------------------------------------------------
    # Descobre o curso da questão.
    # ---------------------------------------------------------
    bateria = (
        db.query(Bateria)
        .filter(Bateria.id == bateria_id)
        .first()
    )

    if not bateria:
        raise HTTPException(
            status_code=404,
            detail="Bateria não encontrada"
        )

    aula = (
        db.query(Aula)
        .filter(Aula.id == bateria.aula_id)
        .first()
    )

    if not aula:
        raise HTTPException(
            status_code=404,
            detail="Aula não encontrada"
        )

    pasta = (
        db.query(Pasta)
        .filter(Pasta.id == aula.pasta_id)
        .first()
    )

    if not pasta or not pasta.curso_assunto_proprio_id:
        raise HTTPException(
            status_code=400,
            detail="Aula não vinculada a um assunto próprio de curso"
        )

    assunto = (
        db.query(CursoAssuntoProprio)
        .filter(
            CursoAssuntoProprio.id == pasta.curso_assunto_proprio_id
        )
        .first()
    )

    if not assunto:
        raise HTTPException(
            status_code=404,
            detail="Assunto próprio do curso não encontrado"
        )

    disciplina = (
        db.query(CursoDisciplinaPropria)
        .filter(
            CursoDisciplinaPropria.id ==
            assunto.curso_disciplina_propria_id
        )
        .first()
    )

    if not disciplina:
        raise HTTPException(
            status_code=404,
            detail="Disciplina própria do curso não encontrada"
        )

    validar_contexto_estudo(
        db=db,
        usuario=usuario_atual,
        curso_id=disciplina.curso_id,
        contratacao_id=contratacao_id,
        demonstracao_id=demonstracao_id,
    )

    tentativa = db.query(TentativaBateria).filter_by(
        id=payload["tentativa_id"], usuario_id=usuario_atual.id,
        bateria_id=bateria_id, contratacao_id=contratacao_id,
        demonstracao_id=demonstracao_id,
    ).with_for_update().first()
    if not tentativa or not db.query(RespostaAlunoQuestao).filter_by(
        tentativa_id=tentativa.id, questao_id=questao_id,
        usuario_id=usuario_atual.id, bateria_id=bateria_id,
        contratacao_id=contratacao_id, demonstracao_id=demonstracao_id,
        respondida=True,
    ).first():
        raise HTTPException(404, "Tentativa/resposta da questão não encontrada")
    existente = db.query(AnotacaoAlunoQuestao).filter_by(
        tentativa_id=tentativa.id, questao_id=questao_id).first()
    if existente:
        raise HTTPException(409, "Já existe anotação para esta questão nesta tentativa")

    nova = AnotacaoAlunoQuestao(
        tentativa_id=tentativa.id,
        usuario_id=usuario_atual.id,
        questao_id=questao_id,
        bateria_id=bateria_id,
        contratacao_id=contratacao_id,
        demonstracao_id=demonstracao_id,
        texto=texto
    )

    db.add(nova)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Já existe anotação para esta questão nesta tentativa")
    db.refresh(nova)

    return {
        "id": nova.id,
        "questao_id": nova.questao_id,
        "bateria_id": nova.bateria_id,
        "contratacao_id": nova.contratacao_id,
        "demonstracao_id": nova.demonstracao_id,
        "texto": nova.texto
    }


@app.put("/me/anotacoes-questoes/{anotacao_id}")
def editar_anotacao_questao(
    anotacao_id: int,
    payload: schemas.AnotacaoTexto,
    contratacao_id: int | None = None,
    demonstracao_id: int | None = None,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    payload = payload.model_dump()
    texto = (payload.get("texto") or "").strip()

    if not texto:
        raise HTTPException(
            status_code=400,
            detail="Informe a anotação"
        )

    if len(texto.split()) > 300:
        raise HTTPException(
            status_code=400,
            detail="A anotação deve ter no máximo 300 palavras"
        )

    if contratacao_id is None and demonstracao_id is None:
        raise HTTPException(
            status_code=400,
            detail="É necessário informar contratacao_id ou demonstracao_id"
        )

    if contratacao_id is not None and demonstracao_id is not None:
        raise HTTPException(
            status_code=400,
            detail="Informe apenas um contexto de estudo"
        )

    anotacao_query = (
        db.query(AnotacaoAlunoQuestao)
        .filter(
            AnotacaoAlunoQuestao.id == anotacao_id,
            AnotacaoAlunoQuestao.usuario_id == usuario_atual.id
        )
    )

    if contratacao_id is not None:
        anotacao_query = anotacao_query.filter(
            AnotacaoAlunoQuestao.contratacao_id == contratacao_id,
            AnotacaoAlunoQuestao.demonstracao_id.is_(None)
        )
    else:
        anotacao_query = anotacao_query.filter(
            AnotacaoAlunoQuestao.contratacao_id.is_(None),
            AnotacaoAlunoQuestao.demonstracao_id == demonstracao_id
        )

    anotacao = anotacao_query.first()

    if not anotacao:
        raise HTTPException(
            status_code=404,
            detail="Anotação não encontrada"
        )

    # Descobre o curso da anotação para validar o contexto.
    questao = (
        db.query(Questao)
        .filter(Questao.id == anotacao.questao_id)
        .first()
    )

    if not questao:
        raise HTTPException(
            status_code=404,
            detail="Questão da anotação não encontrada"
        )

    bateria = (
        db.query(Bateria)
        .filter(Bateria.id == questao.bateria_id)
        .first()
    )

    if not bateria:
        raise HTTPException(
            status_code=404,
            detail="Bateria da anotação não encontrada"
        )

    aula = (
        db.query(Aula)
        .filter(Aula.id == bateria.aula_id)
        .first()
    )

    if not aula:
        raise HTTPException(
            status_code=404,
            detail="Aula da anotação não encontrada"
        )

    pasta = (
        db.query(Pasta)
        .filter(Pasta.id == aula.pasta_id)
        .first()
    )

    if not pasta or not pasta.curso_assunto_proprio_id:
        raise HTTPException(
            status_code=400,
            detail="Anotação não vinculada a um assunto próprio de curso"
        )

    assunto = (
        db.query(CursoAssuntoProprio)
        .filter(
            CursoAssuntoProprio.id == pasta.curso_assunto_proprio_id
        )
        .first()
    )

    if not assunto:
        raise HTTPException(
            status_code=404,
            detail="Assunto próprio do curso não encontrado"
        )

    disciplina = (
        db.query(CursoDisciplinaPropria)
        .filter(
            CursoDisciplinaPropria.id ==
            assunto.curso_disciplina_propria_id
        )
        .first()
    )

    if not disciplina:
        raise HTTPException(
            status_code=404,
            detail="Disciplina própria do curso não encontrada"
        )

    validar_contexto_estudo(
        db=db,
        usuario=usuario_atual,
        curso_id=disciplina.curso_id,
        contratacao_id=contratacao_id,
        demonstracao_id=demonstracao_id,
    )

    anotacao.texto = texto
    anotacao.atualizado_em = datetime.utcnow()

    db.commit()
    db.refresh(anotacao)

    return {
        "id": anotacao.id,
        "texto": anotacao.texto
    }


@app.delete("/me/anotacoes-questoes/{anotacao_id}")
def excluir_anotacao_questao(
    anotacao_id: int,
    contratacao_id: int | None = None,
    demonstracao_id: int | None = None,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    if contratacao_id is None and demonstracao_id is None:
        raise HTTPException(
            status_code=400,
            detail="É necessário informar contratacao_id ou demonstracao_id"
        )

    if contratacao_id is not None and demonstracao_id is not None:
        raise HTTPException(
            status_code=400,
            detail="Informe apenas um contexto de estudo"
        )

    anotacao_query = (
        db.query(AnotacaoAlunoQuestao)
        .filter(
            AnotacaoAlunoQuestao.id == anotacao_id,
            AnotacaoAlunoQuestao.usuario_id == usuario_atual.id
        )
    )

    if contratacao_id is not None:
        anotacao_query = anotacao_query.filter(
            AnotacaoAlunoQuestao.contratacao_id == contratacao_id,
            AnotacaoAlunoQuestao.demonstracao_id.is_(None)
        )
    else:
        anotacao_query = anotacao_query.filter(
            AnotacaoAlunoQuestao.contratacao_id.is_(None),
            AnotacaoAlunoQuestao.demonstracao_id == demonstracao_id
        )

    anotacao = anotacao_query.first()

    if not anotacao:
        raise HTTPException(
            status_code=404,
            detail="Anotação não encontrada"
        )

    # Descobre o curso da anotação para validar o contexto.
    questao = (
        db.query(Questao)
        .filter(Questao.id == anotacao.questao_id)
        .first()
    )

    if not questao:
        raise HTTPException(
            status_code=404,
            detail="Questão da anotação não encontrada"
        )

    bateria = (
        db.query(Bateria)
        .filter(Bateria.id == questao.bateria_id)
        .first()
    )

    if not bateria:
        raise HTTPException(
            status_code=404,
            detail="Bateria da anotação não encontrada"
        )

    aula = (
        db.query(Aula)
        .filter(Aula.id == bateria.aula_id)
        .first()
    )

    if not aula:
        raise HTTPException(
            status_code=404,
            detail="Aula da anotação não encontrada"
        )

    pasta = (
        db.query(Pasta)
        .filter(Pasta.id == aula.pasta_id)
        .first()
    )

    if not pasta or not pasta.curso_assunto_proprio_id:
        raise HTTPException(
            status_code=400,
            detail="Anotação não vinculada a um assunto próprio de curso"
        )

    assunto = (
        db.query(CursoAssuntoProprio)
        .filter(
            CursoAssuntoProprio.id == pasta.curso_assunto_proprio_id
        )
        .first()
    )

    if not assunto:
        raise HTTPException(
            status_code=404,
            detail="Assunto próprio do curso não encontrado"
        )

    disciplina = (
        db.query(CursoDisciplinaPropria)
        .filter(
            CursoDisciplinaPropria.id ==
            assunto.curso_disciplina_propria_id
        )
        .first()
    )

    if not disciplina:
        raise HTTPException(
            status_code=404,
            detail="Disciplina própria do curso não encontrada"
        )

    validar_contexto_estudo(
        db=db,
        usuario=usuario_atual,
        curso_id=disciplina.curso_id,
        contratacao_id=contratacao_id,
        demonstracao_id=demonstracao_id,
    )

    db.delete(anotacao)
    db.commit()

    return {"ok": True}


@app.get("/me/minhas-anotacoes")
def listar_minhas_anotacoes(
    curso_id: int | None = None,
    contratacao_id: int | None = None,
    demonstracao_id: int | None = None,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    # ---------------------------------------------------------
    # Valida o contexto de estudo.
    # ---------------------------------------------------------
    if contratacao_id is None and demonstracao_id is None:
        raise HTTPException(
            status_code=400,
            detail="É necessário informar contratacao_id ou demonstracao_id"
        )

    if contratacao_id is not None and demonstracao_id is not None:
        raise HTTPException(
            status_code=400,
            detail="Informe apenas um contexto de estudo"
        )

    # ---------------------------------------------------------
    # Descobre o curso a partir do contexto.
    # ---------------------------------------------------------
    if contratacao_id is not None:
        contratacao = (
            db.query(ContratacaoCurso)
            .filter(
                ContratacaoCurso.id == contratacao_id,
                ContratacaoCurso.usuario_id == usuario_atual.id
            )
            .first()
        )

        if not contratacao:
            raise HTTPException(
                status_code=404,
                detail="Contratação não encontrada"
            )

        curso_id_contexto = contratacao.curso_id

    else:
        demonstracao = (
            db.query(DemonstracaoCurso)
            .filter(
                DemonstracaoCurso.id == demonstracao_id,
                DemonstracaoCurso.usuario_id == usuario_atual.id
            )
            .first()
        )

        if not demonstracao:
            raise HTTPException(
                status_code=404,
                detail="Demonstração não encontrada"
            )

        curso_id_contexto = demonstracao.curso_id

    # Se o curso foi informado, ele deve corresponder ao contexto.
    if curso_id is not None and curso_id != curso_id_contexto:
        raise HTTPException(
            status_code=400,
            detail="O curso informado não corresponde ao contexto de estudo"
        )

    curso_id = curso_id_contexto

    validar_contexto_estudo(
        db=db,
        usuario=usuario_atual,
        curso_id=curso_id,
        contratacao_id=contratacao_id,
        demonstracao_id=demonstracao_id,
    )

    # ---------------------------------------------------------
    # Busca somente anotações do contexto informado.
    # ---------------------------------------------------------
    return _consultar_anotacoes(db, usuario_atual.id, curso_id, contratacao_id, demonstracao_id)


def _consultar_anotacoes(db, usuario_id, curso_id, contratacao_id, demonstracao_id):
    query = (
        db.query(
            AnotacaoAlunoQuestao,
            Questao,
            Bateria,
            Aula,
            Pasta,
            CursoAssuntoProprio,
            CursoDisciplinaPropria
        )
        .join(
            Questao,
            Questao.id == AnotacaoAlunoQuestao.questao_id
        )
        .join(
            Bateria,
            Bateria.id == Questao.bateria_id
        )
        .join(
            Aula,
            Aula.id == Bateria.aula_id
        )
        .join(
            Pasta,
            Pasta.id == Aula.pasta_id
        )
        .join(
            CursoAssuntoProprio,
            CursoAssuntoProprio.id ==
            Pasta.curso_assunto_proprio_id
        )
        .join(
            CursoDisciplinaPropria,
            CursoDisciplinaPropria.id ==
            CursoAssuntoProprio.curso_disciplina_propria_id
        )
        .filter(
            AnotacaoAlunoQuestao.usuario_id == usuario_id,
            CursoDisciplinaPropria.curso_id == curso_id
        )
    )

    if contratacao_id is not None:
        query = query.filter(
            AnotacaoAlunoQuestao.contratacao_id == contratacao_id,
            AnotacaoAlunoQuestao.demonstracao_id.is_(None)
        )
    else:
        query = query.filter(
            AnotacaoAlunoQuestao.contratacao_id.is_(None),
            AnotacaoAlunoQuestao.demonstracao_id == demonstracao_id
        )

    registros = (
        query
        .order_by(
            CursoDisciplinaPropria.ordem.asc(),
            CursoAssuntoProprio.ordem.asc(),
            Questao.ordem.asc(),
            AnotacaoAlunoQuestao.criado_em.desc()
        )
        .all()
    )

    resultado = []

    for (
        anotacao,
        questao,
        bateria,
        aula,
        pasta,
        assunto,
        disciplina
    ) in registros:

        alternativa_correta = None

        if questao.tipo == "MULTIPLA":
            alternativa_correta = (
                db.query(Alternativa)
                .filter(
                    Alternativa.questao_id == questao.id,
                    Alternativa.letra == questao.gabarito
                )
                .first()
            )

        texto_resposta = (
            alternativa_correta.texto
            if alternativa_correta
            else None
        )

        resultado.append({
            "anotacao_id": anotacao.id,
            "tentativa_id": anotacao.tentativa_id,

            "contratacao_id": anotacao.contratacao_id,
            "demonstracao_id": anotacao.demonstracao_id,

            "disciplina_id": disciplina.id,
            "disciplina_nome": disciplina.nome,
            "disciplina_ordem": disciplina.ordem,

            "assunto_id": assunto.id,
            "assunto_nome": assunto.nome,
            "assunto_ordem": assunto.ordem,

            "aula_id": aula.id,
            "aula_titulo": aula.titulo,

            "questao_id": questao.id,
            "questao_ordem": questao.ordem,
            "tipo": questao.tipo,
            "tipo_questao": questao.tipo_questao,
            "enunciado": questao.enunciado,
            "gabarito": questao.gabarito,
            "texto_resposta": texto_resposta,
            "comentario": questao.comentario,

            "bateria_id": bateria.id,
            "bateria_titulo": bateria.titulo,

            "anotacao": anotacao.texto,
            "criado_em": anotacao.criado_em,
            "atualizado_em": anotacao.atualizado_em
        })

    return resultado


@app.get("/me/cursos-expirados/{curso_id}/anotacoes")
def anotacoes_curso_expirado(curso_id: int, db: Session = Depends(get_db),
                            usuario_atual: Usuario = Depends(get_usuario_atual)):
    agora = datetime.utcnow()
    resultado = []
    for modelo, campo in [(ContratacaoCurso, "contratacao_id"), (DemonstracaoCurso, "demonstracao_id")]:
        contextos = db.query(modelo).filter(modelo.usuario_id == usuario_atual.id,
            modelo.curso_id == curso_id, modelo.data_fim.isnot(None),
            modelo.data_fim <= agora, modelo.data_inicio <= modelo.data_fim).all()
        for acesso in contextos:
            if campo == "contratacao_id" and acesso.origem not in {"ADMIN", "PAGAMENTO"}:
                continue
            registros = _consultar_anotacoes(db, usuario_atual.id, curso_id,
                acesso.id if campo == "contratacao_id" else None,
                acesso.id if campo == "demonstracao_id" else None)
            resultado.extend(r for r in registros if acesso.data_inicio <= r["criado_em"] < acesso.data_fim)
    return sorted(resultado, key=lambda r: r["criado_em"], reverse=True)


def _estrutura_conversa(db, questao_id, bateria_id):
    questao = db.get(Questao, questao_id)
    bateria = db.get(Bateria, bateria_id)
    aula = db.get(Aula, bateria.aula_id) if bateria else None
    pasta = db.get(Pasta, aula.pasta_id) if aula else None
    assunto = db.get(CursoAssuntoProprio, pasta.curso_assunto_proprio_id) if pasta else None
    disciplina = db.get(CursoDisciplinaPropria, assunto.curso_disciplina_propria_id) if assunto else None
    if not questao or questao.bateria_id != bateria_id or not disciplina:
        raise HTTPException(404, "Questão/bateria do curso não encontrada")
    return questao, bateria, assunto, disciplina


def _contexto_conversa(db, conversa, vigente=False):
    _, _, _, disciplina = _estrutura_conversa(db, conversa.questao_id, conversa.bateria_id)
    cid, did = conversa.contratacao_id, conversa.demonstracao_id
    if (cid is None) == (did is None):
        raise HTTPException(409, "Conversa sem contexto exclusivo válido")
    modelo, aid = (ContratacaoCurso, cid) if cid is not None else (DemonstracaoCurso, did)
    acesso = db.query(modelo).filter_by(id=aid, usuario_id=conversa.usuario_id, curso_id=disciplina.curso_id).first()
    if not acesso or (cid is not None and acesso.origem not in {'ADMIN', 'PAGAMENTO'}):
        raise HTTPException(403, "Contexto da conversa inválido")
    if vigente:
        validar_contexto_estudo(db, SimpleNamespace(id=conversa.usuario_id), disciplina.curso_id, cid, did)
    return acesso


def _resultado_conversa(db, conversa):
    questao, bateria, assunto, disciplina = _estrutura_conversa(db, conversa.questao_id, conversa.bateria_id)
    aluno = db.get(Usuario, conversa.usuario_id)
    curso = db.get(Curso, disciplina.curso_id)
    mensagens = db.query(MensagemConversaQuestao).filter_by(conversa_id=conversa.id).order_by(
        MensagemConversaQuestao.criada_em, MensagemConversaQuestao.id).all()
    return {'conversa_id': conversa.id, 'tentativa_id': conversa.tentativa_id,
        'status': conversa.status, 'contratacao_id': conversa.contratacao_id, 'demonstracao_id': conversa.demonstracao_id,
        'aluno_id': conversa.usuario_id, 'aluno_nome': aluno.nome if aluno else '',
        'curso_id': disciplina.curso_id, 'curso_nome': curso.nome if curso else '',
        'disciplina_id': disciplina.id, 'disciplina_nome': disciplina.nome, 'disciplina_ordem': disciplina.ordem,
        'assunto_id': assunto.id, 'assunto_nome': assunto.nome, 'assunto_ordem': assunto.ordem,
        'questao_id': questao.id, 'questao_ordem': questao.ordem, 'tipo': questao.tipo, 'tipo_questao': questao.tipo_questao,
        'enunciado': questao.enunciado, 'gabarito': questao.gabarito, 'comentario': questao.comentario,
        'bateria_id': bateria.id, 'bateria_titulo': bateria.titulo,
        'criado_em': conversa.criado_em, 'atualizado_em': conversa.atualizado_em,
        'mensagens': [{'id': m.id, 'autor': m.autor, 'texto': m.texto, 'criada_em': m.criada_em} for m in mensagens]}


@app.post('/me/mensagens-prof')
def iniciar_conversa_prof(dados: schemas.ConversaProfessorCreate, db: Session = Depends(get_db),
                         usuario: Usuario = Depends(get_usuario_atual)):
    _, _, _, disciplina = _estrutura_conversa(db, dados.questao_id, dados.bateria_id)
    validar_contexto_estudo(db, usuario, disciplina.curso_id, dados.contratacao_id, dados.demonstracao_id)
    tentativa = db.query(TentativaBateria).filter_by(id=dados.tentativa_id, usuario_id=usuario.id,
        bateria_id=dados.bateria_id, contratacao_id=dados.contratacao_id, demonstracao_id=dados.demonstracao_id).with_for_update().first()
    resposta = db.query(RespostaAlunoQuestao).filter_by(tentativa_id=dados.tentativa_id, questao_id=dados.questao_id,
        usuario_id=usuario.id, bateria_id=dados.bateria_id, contratacao_id=dados.contratacao_id,
        demonstracao_id=dados.demonstracao_id, respondida=True).first()
    if not tentativa or not resposta or not resposta.resposta_marcada:
        raise HTTPException(404, 'Tentativa/resposta da questão não encontrada')
    if db.query(ConversaQuestaoProfessor).filter_by(tentativa_id=tentativa.id, questao_id=dados.questao_id).first():
        raise HTTPException(409, 'Já existe conversa para esta questão nesta tentativa')
    conversa = ConversaQuestaoProfessor(usuario_id=usuario.id, questao_id=dados.questao_id,
        bateria_id=dados.bateria_id, tentativa_id=tentativa.id, contratacao_id=dados.contratacao_id,
        demonstracao_id=dados.demonstracao_id, status='ABERTA')
    db.add(conversa)
    try:
        db.flush()
        db.add(MensagemConversaQuestao(conversa_id=conversa.id, autor='ALUNO', texto=dados.texto))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Já existe conversa para esta questão nesta tentativa')
    return _resultado_conversa(db, conversa)


@app.get('/me/mensagens-prof')
def minhas_conversas_prof(curso_id: int | None = None, contratacao_id: int | None = None,
                         demonstracao_id: int | None = None, db: Session = Depends(get_db),
                         usuario: Usuario = Depends(get_usuario_atual)):
    if (contratacao_id is None) == (demonstracao_id is None):
        raise HTTPException(400, 'Informe exatamente um contexto de acesso ao curso.')
    modelo, aid = (ContratacaoCurso, contratacao_id) if contratacao_id is not None else (DemonstracaoCurso, demonstracao_id)
    acesso = db.query(modelo).filter_by(id=aid, usuario_id=usuario.id).first()
    if not acesso or (curso_id is not None and curso_id != acesso.curso_id):
        raise HTTPException(403, 'Curso/contexto inválido')
    validar_contexto_estudo(db, usuario, acesso.curso_id, contratacao_id, demonstracao_id)
    conversas = db.query(ConversaQuestaoProfessor).filter_by(usuario_id=usuario.id,
        contratacao_id=contratacao_id, demonstracao_id=demonstracao_id).order_by(ConversaQuestaoProfessor.id.desc()).all()
    resultado = []
    for c in conversas:
        _contexto_conversa(db, c)
        resultado.append(_resultado_conversa(db, c))
    return resultado


def _responder_conversa(db, conversa, texto, autor):
    if conversa.status == 'ENCERRADA':
        raise HTTPException(409, 'Conversa encerrada')
    mensagens = db.query(MensagemConversaQuestao).filter_by(conversa_id=conversa.id).order_by(
        MensagemConversaQuestao.criada_em, MensagemConversaQuestao.id).all()
    if not mensagens or mensagens[-1].autor == autor:
        raise HTTPException(409, 'Aguarde a resposta do outro participante')
    quantidade = sum(m.autor == autor for m in mensagens)
    if quantidade >= 3:
        raise HTTPException(409, 'Limite de mensagens atingido')
    db.add(MensagemConversaQuestao(conversa_id=conversa.id, autor=autor, texto=texto))
    conversa.status = 'ENCERRADA' if autor == 'PROFESSOR' and quantidade == 2 else 'ABERTA'
    conversa.atualizado_em = datetime.utcnow()
    db.commit()
    return _resultado_conversa(db, conversa)


@app.post('/me/mensagens-prof/{conversa_id}/responder')
def continuar_conversa_prof(conversa_id: int, dados: schemas.MensagemProfessorTexto,
        contratacao_id: int | None = None, demonstracao_id: int | None = None,
        db: Session = Depends(get_db), usuario: Usuario = Depends(get_usuario_atual)):
    if (contratacao_id is None) == (demonstracao_id is None):
        raise HTTPException(400, 'Informe exatamente um contexto de acesso ao curso.')
    conversa = db.query(ConversaQuestaoProfessor).filter_by(id=conversa_id, usuario_id=usuario.id,
        contratacao_id=contratacao_id, demonstracao_id=demonstracao_id).with_for_update().first()
    if not conversa:
        raise HTTPException(404, 'Conversa não encontrada')
    _contexto_conversa(db, conversa, vigente=True)
    return _responder_conversa(db, conversa, dados.texto, 'ALUNO')


@app.get('/admin/mensagens-questoes')
def conversas_prof_admin(curso_id: int | None = None, disciplina_id: int | None = None,
        concluidas: bool = False, db: Session = Depends(get_db), usuario: Usuario = Depends(get_usuario_atual)):
    if not usuario.is_admin:
        raise HTTPException(403, 'Acesso restrito')
    query = db.query(ConversaQuestaoProfessor)
    query = query.filter(ConversaQuestaoProfessor.status == 'ENCERRADA') if concluidas else query.filter(ConversaQuestaoProfessor.status != 'ENCERRADA')
    resultado = []
    for conversa in query.order_by(ConversaQuestaoProfessor.criado_em, ConversaQuestaoProfessor.id):
        _contexto_conversa(db, conversa)
        r = _resultado_conversa(db, conversa)
        if (curso_id is None or r['curso_id'] == curso_id) and (disciplina_id is None or r['disciplina_id'] == disciplina_id):
            resultado.append(r)
    return resultado


@app.post('/admin/mensagens-questoes/{conversa_id}/responder')
def responder_conversa_prof_admin(conversa_id: int, dados: schemas.MensagemProfessorTexto,
        db: Session = Depends(get_db), usuario: Usuario = Depends(get_usuario_atual)):
    if not usuario.is_admin:
        raise HTTPException(403, 'Acesso restrito')
    conversa = db.query(ConversaQuestaoProfessor).filter_by(id=conversa_id).with_for_update().first()
    if not conversa:
        raise HTTPException(404, 'Conversa não encontrada')
    _contexto_conversa(db, conversa)
    return _responder_conversa(db, conversa, dados.texto, 'PROFESSOR')


@app.get('/me/cursos-expirados/{curso_id}/mensagens-prof')
def historico_conversas_prof(curso_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(get_usuario_atual)):
    resultado = []
    for conversa in db.query(ConversaQuestaoProfessor).filter_by(usuario_id=usuario.id).order_by(ConversaQuestaoProfessor.id.desc()):
        _, _, _, disciplina = _estrutura_conversa(db, conversa.questao_id, conversa.bateria_id)
        if disciplina.curso_id != curso_id:
            continue
        acesso = _contexto_conversa(db, conversa)
        if acesso.data_fim is not None and acesso.data_fim <= datetime.utcnow() and acesso.data_inicio <= conversa.criado_em < acesso.data_fim:
            resultado.append(_resultado_conversa(db, conversa))
    return resultado


# Questões práticas: conteúdo do assunto, independente de baterias/Sprint.
SEGREDO_SESSAO_PRATICA = (os.getenv("QUESTOES_PRATICA_SESSION_SECRET") or "").strip()


def exigir_segredo_pratica():
    if len(SEGREDO_SESSAO_PRATICA) < 32:
        raise HTTPException(503, "Questões práticas temporariamente indisponíveis: configuração de sessão ausente ou inválida.")
    return SEGREDO_SESSAO_PRATICA


def versao_questao_pratica(db, questao, alternativas=None):
    # HMAC evita expor um hash que permitiria adivinhar o gabarito C/E ou A–E.
    import json
    if alternativas is None:
        alternativas = db.query(models.QuestaoPraticaAlternativa).filter_by(
            questao_pratica_id=questao.id).order_by(models.QuestaoPraticaAlternativa.letra).all()
    conteudo = [questao.id, questao.curso_assunto_proprio_id, questao.tipo,
                questao.enunciado, questao.gabarito, questao.comentario, questao.ativo,
                [[a.letra, a.texto, a.correta] for a in alternativas]]
    return hmac.new(exigir_segredo_pratica().encode(),
                    json.dumps(conteudo, ensure_ascii=False, separators=(",", ":")).encode(),
                    hashlib.sha256).hexdigest()

FILTROS_PRATICA_BITS = {"DIFICIL": 1, "MEDIA": 2, "FACIL": 4, "ERREI": 8, "REVER": 16}


def chave_filtros_pratica(filtros):
    return "TODAS" if "TODAS" in filtros else "F:" + str(sum(FILTROS_PRATICA_BITS[f] for f in set(filtros)))


def contexto_query_pratica(query, modelo, usuario_id, contexto):
    return query.filter(
        modelo.usuario_id == usuario_id,
        modelo.contratacao_id == contexto["contratacao_id"],
        modelo.demonstracao_id == contexto["demonstracao_id"],
    )


def acesso_assunto_pratica(db, usuario, assunto_id, contratacao_id, demonstracao_id):
    assunto = db.query(models.CursoAssuntoProprio).filter_by(id=assunto_id, ativo=True).first()
    if not assunto:
        raise HTTPException(404, "Assunto não encontrado ou inativo.")
    disciplina = db.query(models.CursoDisciplinaPropria).filter_by(
        id=assunto.curso_disciplina_propria_id, ativo=True).first()
    if not disciplina:
        raise HTTPException(404, "Disciplina não encontrada ou inativa.")
    if not db.query(models.Curso).filter_by(id=disciplina.curso_id, ativo=True).first():
        raise HTTPException(404, "Curso não encontrado ou inativo.")
    contexto = validar_contexto_estudo(db, usuario, disciplina.curso_id, contratacao_id, demonstracao_id)
    if contexto["demonstracao_id"] is not None:
        liberadas = db.query(models.CursoDisciplinaPropria.id).filter_by(
            curso_id=disciplina.curso_id, ativo=True).order_by(
                models.CursoDisciplinaPropria.ordem, models.CursoDisciplinaPropria.id).limit(2).all()
        if disciplina.id not in {d.id for d in liberadas}:
            raise HTTPException(403, "Esta disciplina não está disponível no acesso gratuito.")
    return assunto, contexto


def bloquear_pratica(db, usuario_id, assunto_id, contexto):
    # Serializa as rotas deste módulo enquanto a migração de unicidade está adiada.
    if db.get_bind().dialect.name == "postgresql":
        import hashlib
        valor = f"pratica:{usuario_id}:{assunto_id}:{contexto['contratacao_id']}:{contexto['demonstracao_id']}"
        chave = int.from_bytes(hashlib.sha256(valor.encode()).digest()[:8], "big", signed=True)
        db.execute(text("SELECT pg_advisory_xact_lock(:chave)"), {"chave": chave})


def questoes_elegiveis_pratica(db, assunto_id, usuario_id, contexto, filtros):
    query = db.query(models.QuestaoPraticaAssunto).filter_by(
        curso_assunto_proprio_id=assunto_id, ativo=True)
    if "TODAS" not in filtros:
        m = models.QuestaoPraticaMarcacaoAluno
        marcacoes = contexto_query_pratica(db.query(m.questao_id), m, usuario_id, contexto)
        condicoes = []
        for dificuldade in ("DIFICIL", "MEDIA", "FACIL"):
            if dificuldade in filtros:
                condicoes.append(m.dificuldade_marcada == dificuldade)
        if "ERREI" in filtros:
            condicoes.append((m.acertou == False) & (m.nao_soube == False))
        if "REVER" in filtros:
            condicoes.append(m.rever == True)
        query = query.filter(models.QuestaoPraticaAssunto.id.in_(marcacoes.filter(or_(*condicoes))))
    return query


def validar_conjunto_pratica(db, assunto_id, usuario_id, contexto, filtros, ids):
    elegiveis = sorted(q.id for q in questoes_elegiveis_pratica(
        db, assunto_id, usuario_id, contexto, filtros).all())
    if ids is not None:
        # Compatibilidade com o frontend: a lista nunca define o conjunto do ciclo.
        pertencentes = {q.id for q in db.query(models.QuestaoPraticaAssunto).filter(
            models.QuestaoPraticaAssunto.curso_assunto_proprio_id == assunto_id,
            models.QuestaoPraticaAssunto.id.in_(ids)).all()}
        if set(ids) - pertencentes:
            raise HTTPException(400, "IDs da sessão não pertencem a este assunto.")
    return elegiveis


def rotatividade_query_pratica(db, assunto_id, usuario_id, contexto, chave):
    r = models.QuestaoPraticaRotatividadeAluno
    return contexto_query_pratica(db.query(r), r, usuario_id, contexto).filter_by(
        curso_assunto_proprio_id=assunto_id, filtro=chave)


def estado_ciclo_pratica(db, assunto_id, usuario_id, contexto, chave, ids):
    registros = rotatividade_query_pratica(db, assunto_id, usuario_id, contexto, chave).all()
    ciclo = max((r.ciclo for r in registros), default=1)
    respondidas = {r.questao_id for r in registros if r.ciclo == ciclo}
    pendentes = set(ids) - respondidas
    # Só avança depois de percorrer TODO o conjunto elegível calculado no servidor.
    if ids and not pendentes:
        ciclo += 1
        respondidas = set()
        pendentes = set(ids)
    return ciclo, respondidas, pendentes


@app.get("/curso-assuntos-proprios/{assunto_id}/questoes-pratica/filtros",
         response_model=dict[str, schemas.DisponibilidadeFiltroPratica])
def obter_filtros_questoes_pratica(assunto_id: int, contratacao_id: int | None = None,
                                  demonstracao_id: int | None = None,
                                  db: Session = Depends(get_db), usuario: Usuario = Depends(get_usuario_atual)):
    _, contexto = acesso_assunto_pratica(db, usuario, assunto_id, contratacao_id, demonstracao_id)
    resultado = {}
    for filtro in ("TODAS", *FILTROS_PRATICA_BITS):
        quantidade = questoes_elegiveis_pratica(db, assunto_id, usuario.id, contexto, [filtro]).count()
        resultado[filtro] = {"habilitado": quantidade > 0, "quantidade": quantidade}
    return resultado


@app.post("/curso-assuntos-proprios/{assunto_id}/questoes-pratica/proxima",
          response_model=schemas.ProximaQuestaoPraticaResponse)
def obter_proxima_questao_pratica(assunto_id: int, dados: schemas.ProximaQuestaoPraticaRequest,
                                 db: Session = Depends(get_db), usuario: Usuario = Depends(get_usuario_atual)):
    from jose import jwt
    exigir_segredo_pratica()
    _, contexto = acesso_assunto_pratica(db, usuario, assunto_id, dados.contratacao_id, dados.demonstracao_id)
    bloquear_pratica(db, usuario.id, assunto_id, contexto)
    ids = validar_conjunto_pratica(db, assunto_id, usuario.id, contexto, dados.filtros, dados.ids_questoes_sessao)
    if not ids:
        raise HTTPException(404, "Nenhuma questão disponível para os filtros selecionados.")
    chave = chave_filtros_pratica(dados.filtros)
    ciclo, respondidas, disponiveis = estado_ciclo_pratica(
        db, assunto_id, usuario.id, contexto, chave, ids)
    questao = db.query(models.QuestaoPraticaAssunto).filter(
        models.QuestaoPraticaAssunto.id.in_(disponiveis)).order_by(func.random()).first()
    alternativas = db.query(models.QuestaoPraticaAlternativa).filter_by(
        questao_pratica_id=questao.id).order_by(models.QuestaoPraticaAlternativa.letra).all()
    token = jwt.encode({"sub": str(usuario.id), "uso": "questoes_pratica", "assunto_id": assunto_id,
                         "questao_id": questao.id, "ids": ids, "ciclo": ciclo, "filtro": chave,
                         "versao_questao": versao_questao_pratica(db, questao, alternativas),
                         "exp": datetime.utcnow() + timedelta(hours=1),
                         **contexto}, SEGREDO_SESSAO_PRATICA, algorithm="HS256")
    return {"numero_questao": len(respondidas & set(ids)) + 1, "ciclo": ciclo, "filtro": chave,
            "ids_questoes_sessao": ids, "token_sessao": token,
            "questao": {"id": questao.id, "curso_assunto_proprio_id": assunto_id,
                        "tipo": questao.tipo, "enunciado": questao.enunciado,
                        "alternativas": [{"id": a.id, "letra": a.letra, "texto": a.texto} for a in alternativas]}}


@app.post("/questoes-pratica/{questao_id}/responder", response_model=schemas.ResultadoQuestaoPraticaResponse)
def responder_questao_pratica(questao_id: int, dados: schemas.ResponderQuestaoPraticaRequest,
                              db: Session = Depends(get_db), usuario: Usuario = Depends(get_usuario_atual)):
    from jose import jwt
    exigir_segredo_pratica()
    questao = db.query(models.QuestaoPraticaAssunto).filter_by(id=questao_id, ativo=True).first()
    if not questao:
        raise HTTPException(404, "Questão não encontrada ou inativa.")
    _, contexto = acesso_assunto_pratica(db, usuario, questao.curso_assunto_proprio_id,
                                        dados.contratacao_id, dados.demonstracao_id)
    bloquear_pratica(db, usuario.id, questao.curso_assunto_proprio_id, contexto)
    # Serializa com edição/exclusão administrativa e atualiza o objeto já carregado.
    db.refresh(questao, with_for_update=True)
    if not questao.ativo:
        raise HTTPException(404, "Questão não encontrada ou inativa.")
    try:
        sessao = jwt.decode(dados.token_sessao, SEGREDO_SESSAO_PRATICA, algorithms=["HS256"])
    except Exception:
        raise HTTPException(409, "Sessão inválida ou expirada. Carregue novamente a questão.")
    chave = chave_filtros_pratica(dados.filtros)
    esperado = {"sub": str(usuario.id), "uso": "questoes_pratica", "assunto_id": questao.curso_assunto_proprio_id,
                "questao_id": questao.id, "filtro": chave, **contexto}
    if not sessao or any(sessao.get(k) != v for k, v in esperado.items()):
        raise HTTPException(409, "Sessão incompatível com a questão ou contexto.")
    if not hmac.compare_digest(sessao.get("versao_questao", ""), versao_questao_pratica(db, questao)):
        raise HTTPException(409, "Questão alterada após a seleção. Carregue novamente.")
    ids = validar_conjunto_pratica(db, questao.curso_assunto_proprio_id, usuario.id, contexto, dados.filtros, None)
    if ids != sessao["ids"] or questao.id not in ids:
        raise HTTPException(409, "Conjunto deixou de atender aos filtros. Carregue novamente.")
    ciclo, _, pendentes = estado_ciclo_pratica(
        db, questao.curso_assunto_proprio_id, usuario.id, contexto, chave, ids)
    if sessao.get("ciclo") != ciclo or questao.id not in pendentes:
        raise HTTPException(409, "Questão já respondida ou ciclo desatualizado.")
    resposta = dados.resposta_marcada
    if questao.tipo == "CERTO_ERRADO":
        if resposta not in {"C", "E", "NAO_SEI"}:
            raise HTTPException(400, "Resposta inválida para CERTO/ERRADO.")
        if questao.gabarito not in {"C", "E"}:
            raise HTTPException(409, "Gabarito inválido no cadastro.")
    elif questao.tipo == "MULTIPLA":
        alternativas = db.query(models.QuestaoPraticaAlternativa).filter_by(questao_pratica_id=questao.id).all()
        letras = sorted(a.letra for a in alternativas)
        if letras not in [list("ABCD"), list("ABCDE")] or sum(a.correta for a in alternativas) != 1 or not any(a.correta and a.letra == questao.gabarito for a in alternativas):
            raise HTTPException(409, "Alternativas ou gabarito inválidos no cadastro.")
        if resposta not in letras:
            raise HTTPException(400, "Resposta não corresponde a uma alternativa.")
    else:
        raise HTTPException(409, "Tipo de questão inválido no cadastro.")
    nao_soube = resposta == "NAO_SEI"
    acertou = None if nao_soube else resposta == questao.gabarito
    m = models.QuestaoPraticaMarcacaoAluno
    marcacoes = contexto_query_pratica(db.query(m), m, usuario.id, contexto).filter_by(questao_id=questao.id).all()
    if len(marcacoes) > 1:
        raise HTTPException(409, "Marcações duplicadas; dados precisam de revisão.")
    marcacao = marcacoes[0] if marcacoes else m(usuario_id=usuario.id, questao_id=questao.id, **contexto)
    marcacao.dificuldade_marcada = dados.dificuldade_marcada
    marcacao.acertou = acertou
    marcacao.rever = dados.rever
    marcacao.nao_soube = nao_soube
    db.add(marcacao)
    db.add(models.QuestaoPraticaRotatividadeAluno(usuario_id=usuario.id,
        curso_assunto_proprio_id=questao.curso_assunto_proprio_id, questao_id=questao.id,
        filtro=chave, ciclo=ciclo, **contexto))
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"questao_id": questao.id, "acertou": acertou, "nao_soube": nao_soube,
            "gabarito": questao.gabarito, "comentario": questao.comentario,
            "dificuldade_marcada": marcacao.dificuldade_marcada, "rever": marcacao.rever,
            "ciclo": ciclo, "filtro": chave}


@app.post("/admin/questoes-pratica")
def criar_questao_pratica_admin(
    dados: schemas.QuestaoPraticaAdminCreate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas administrador.")

    if not dados.enunciado.strip():
        raise HTTPException(400, "Enunciado não pode ser vazio.")
    tipo = (dados.tipo or "").strip().upper()

    if tipo not in ["CERTO_ERRADO", "MULTIPLA"]:
        raise HTTPException(status_code=400, detail="Tipo inválido.")

    assunto = db.query(models.CursoAssuntoProprio).filter(
        models.CursoAssuntoProprio.id == dados.curso_assunto_proprio_id
    ).first()

    if not assunto:
        raise HTTPException(status_code=404, detail="Assunto não encontrado.")

    if tipo == "CERTO_ERRADO":
        gabarito = (dados.gabarito or "").strip().upper()

        if gabarito not in ["C", "E"]:
            raise HTTPException(
                status_code=400,
                detail="Para CERTO/ERRADO, o gabarito deve ser C ou E."
            )

        questao = models.QuestaoPraticaAssunto(
            curso_assunto_proprio_id=dados.curso_assunto_proprio_id,
            tipo=tipo,
            enunciado=dados.enunciado.strip(),
            gabarito=gabarito,
            comentario=dados.comentario,
            ativo=dados.ativo
        )

        db.add(questao)
        db.commit()
        db.refresh(questao)

        return {
            "id": questao.id,
            "tipo": questao.tipo,
            "gabarito": questao.gabarito,
            "mensagem": "Questão cadastrada com sucesso."
        }

    alternativas = dados.alternativas or []

    if len(alternativas) not in [4, 5]:
        raise HTTPException(
            status_code=400,
            detail="A questão de múltipla escolha deve possuir 4 ou 5 alternativas."
        )

    letras = [a.letra.strip().upper() for a in alternativas]

    if len(set(letras)) != len(letras):
        raise HTTPException(
            status_code=400,
            detail="Não pode haver letras repetidas nas alternativas."
        )

    letras_validas = list("ABCD" if len(alternativas) == 4 else "ABCDE")
    if set(letras) != set(letras_validas) or any(not a.texto.strip() for a in alternativas):
        raise HTTPException(400, "Use exatamente A–D ou A–E, com textos não vazios.")

    for letra in letras:
        if letra not in letras_validas:
            raise HTTPException(
                status_code=400,
                detail="As letras das alternativas devem ser A, B, C, D ou E."
            )

    alternativas_corretas = [
        a for a in alternativas
        if a.correta
    ]

    if len(alternativas_corretas) != 1:
        raise HTTPException(
            status_code=400,
            detail="A questão deve possuir exatamente uma alternativa correta."
        )

    gabarito = alternativas_corretas[0].letra.strip().upper()

    questao = models.QuestaoPraticaAssunto(
        curso_assunto_proprio_id=dados.curso_assunto_proprio_id,
        tipo=tipo,
        enunciado=dados.enunciado.strip(),
        gabarito=gabarito,
        comentario=dados.comentario,
        ativo=dados.ativo
    )

    db.add(questao)
    db.flush()

    for alternativa in alternativas:
        db.add(
            models.QuestaoPraticaAlternativa(
                questao_pratica_id=questao.id,
                letra=alternativa.letra.strip().upper(),
                texto=alternativa.texto.strip(),
                correta=alternativa.correta
            )
        )

    db.commit()
    db.refresh(questao)

    return {
        "id": questao.id,
        "tipo": questao.tipo,
        "gabarito": questao.gabarito,
        "mensagem": "Questão cadastrada com sucesso."
    }

@app.get("/admin/curso-assuntos-proprios/{curso_assunto_proprio_id}/questoes-pratica")
def listar_questoes_pratica_admin(
    curso_assunto_proprio_id: int,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas administrador.")

    questoes = (
        db.query(models.QuestaoPraticaAssunto)
        .filter(
            models.QuestaoPraticaAssunto.curso_assunto_proprio_id == curso_assunto_proprio_id
        )
        .order_by(models.QuestaoPraticaAssunto.id.asc())
        .all()
    )

    resultado = []

    for q in questoes:
        alternativas = (
            db.query(models.QuestaoPraticaAlternativa)
            .filter(models.QuestaoPraticaAlternativa.questao_pratica_id == q.id)
            .order_by(models.QuestaoPraticaAlternativa.letra.asc())
            .all()
        )

        resultado.append({
            "id": q.id,
            "curso_assunto_proprio_id": q.curso_assunto_proprio_id,
            "tipo": q.tipo,
            "enunciado": q.enunciado,
            "gabarito": q.gabarito,
            "comentario": q.comentario,
            "ativo": q.ativo,
            "alternativas": [
                {
                    "id": a.id,
                    "letra": a.letra,
                    "texto": a.texto,
                    "correta": a.correta
                }
                for a in alternativas
            ]
        })

    return resultado

@app.put("/admin/questoes-pratica/{questao_id}")
def editar_questao_pratica_admin(
    questao_id: int,
    dados: schemas.QuestaoPraticaAdminUpdate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas administrador.")

    questao = db.query(models.QuestaoPraticaAssunto).filter(
        models.QuestaoPraticaAssunto.id == questao_id
    ).with_for_update().first()

    if not questao:
        raise HTTPException(status_code=404, detail="Questão não encontrada.")

    if not dados.enunciado.strip():
        raise HTTPException(400, "Enunciado não pode ser vazio.")
    tipo = (dados.tipo or "").strip().upper()

    if tipo not in ["CERTO_ERRADO", "MULTIPLA"]:
        raise HTTPException(status_code=400, detail="Tipo inválido.")

    if tipo == "CERTO_ERRADO":
        gabarito = (dados.gabarito or "").strip().upper()

        if gabarito not in ["C", "E"]:
            raise HTTPException(
                status_code=400,
                detail="Para CERTO/ERRADO, o gabarito deve ser C ou E."
            )

        db.query(models.QuestaoPraticaAlternativa).filter(
            models.QuestaoPraticaAlternativa.questao_pratica_id == questao.id
        ).delete()

        questao.tipo = tipo
        questao.enunciado = dados.enunciado.strip()
        questao.gabarito = gabarito
        questao.comentario = dados.comentario
        questao.ativo = dados.ativo

        db.commit()
        db.refresh(questao)

        return {
            "id": questao.id,
            "tipo": questao.tipo,
            "gabarito": questao.gabarito,
            "mensagem": "Questão atualizada com sucesso."
        }

    alternativas = dados.alternativas or []

    if len(alternativas) not in [4, 5]:
        raise HTTPException(
            status_code=400,
            detail="A questão de múltipla escolha deve possuir 4 ou 5 alternativas."
        )

    letras = [a.letra.strip().upper() for a in alternativas]

    if len(set(letras)) != len(letras):
        raise HTTPException(
            status_code=400,
            detail="Não pode haver letras repetidas nas alternativas."
        )

    letras_validas = list("ABCD" if len(alternativas) == 4 else "ABCDE")
    if set(letras) != set(letras_validas) or any(not a.texto.strip() for a in alternativas):
        raise HTTPException(400, "Use exatamente A–D ou A–E, com textos não vazios.")

    for letra in letras:
        if letra not in letras_validas:
            raise HTTPException(
                status_code=400,
                detail="As letras das alternativas devem ser A, B, C, D ou E."
            )

    alternativas_corretas = [a for a in alternativas if a.correta]

    if len(alternativas_corretas) != 1:
        raise HTTPException(
            status_code=400,
            detail="A questão deve possuir exatamente uma alternativa correta."
        )

    gabarito = alternativas_corretas[0].letra.strip().upper()

    questao.tipo = tipo
    questao.enunciado = dados.enunciado.strip()
    questao.gabarito = gabarito
    questao.comentario = dados.comentario
    questao.ativo = dados.ativo

    db.query(models.QuestaoPraticaAlternativa).filter(
        models.QuestaoPraticaAlternativa.questao_pratica_id == questao.id
    ).delete()

    for alternativa in alternativas:
        db.add(
            models.QuestaoPraticaAlternativa(
                questao_pratica_id=questao.id,
                letra=alternativa.letra.strip().upper(),
                texto=alternativa.texto.strip(),
                correta=alternativa.correta
            )
        )

    db.commit()
    db.refresh(questao)

    return {
        "id": questao.id,
        "tipo": questao.tipo,
        "gabarito": questao.gabarito,
        "mensagem": "Questão atualizada com sucesso."
    }

@app.delete("/admin/questoes-pratica/{questao_id}")
def excluir_questao_pratica_admin(
    questao_id: int,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas administrador.")

    questao = db.query(models.QuestaoPraticaAssunto).filter(
        models.QuestaoPraticaAssunto.id == questao_id
    ).with_for_update().first()

    if not questao:
        raise HTTPException(status_code=404, detail="Questão não encontrada.")

    db.query(models.QuestaoPraticaAlternativa).filter(
        models.QuestaoPraticaAlternativa.questao_pratica_id == questao.id
    ).delete()

    db.delete(questao)
    db.commit()

    return {
        "mensagem": "Questão excluída com sucesso."
    }


from app.desempenho import registrar_rotas as registrar_rotas_desempenho
registrar_rotas_desempenho(app, get_db, get_usuario_atual, validar_contexto_estudo)


@app.post(
    "/admin/cursos/{curso_id}/duplicar",
    tags=["Admin"]
)
def duplicar_curso_inteiro(
    curso_id: int,
    dados: schemas.DuplicarCursoRequest,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito ao administrador."
        )

    from sqlalchemy import func

    novo_nome = (dados.novo_nome or "").strip()

    if not novo_nome or len(novo_nome) > 255:
        raise HTTPException(
            status_code=400,
            detail="Informe um nome de curso entre 1 e 255 caracteres."
        )

    curso_origem = (
        db.query(models.Curso)
        .filter(
            models.Curso.id == curso_id
        )
        .first()
    )

    if not curso_origem:
        raise HTTPException(
            status_code=404,
            detail="Curso de origem não encontrado."
        )

    # Serializa o mesmo nome no PostgreSQL sem criar índices ou tabelas.
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:nome, 0))"),
                   {"nome": "duplicar_curso:" + novo_nome.casefold()})

    curso_nome_existente = (
        db.query(models.Curso)
        .filter(
            func.lower(models.Curso.nome) == novo_nome.lower()
        )
        .first()
    )

    if curso_nome_existente:
        raise HTTPException(
            status_code=400,
            detail="Já existe um curso com este nome."
        )

    # Não adaptar silenciosamente conteúdos incompatíveis com a estrutura atual.
    for disciplina in db.query(models.CursoDisciplinaPropria).filter_by(curso_id=curso_id):
        for assunto in db.query(models.CursoAssuntoProprio).filter_by(curso_disciplina_propria_id=disciplina.id):
            pastas = db.query(models.Pasta).filter_by(curso_assunto_proprio_id=assunto.id).all()
            if len(pastas) > 1:
                raise HTTPException(409, "O assunto de origem possui mais de uma pasta; revise sua estrutura.")
            for pasta in pastas:
                if pasta.tipo == "TEORIA" and db.query(models.Aula).filter_by(pasta_id=pasta.id).count() > 1:
                    raise HTTPException(409, "A pasta de origem possui mais de uma aula técnica; revise sua estrutura.")

    try:
        # ---------------------------------------------------------
        # 1. CURSO
        # ---------------------------------------------------------

        novo_curso = models.Curso(
            nome=novo_nome,
            ativo=curso_origem.ativo,
            publicado=False,
            descricao_publica=curso_origem.descricao_publica
        )

        db.add(novo_curso)
        db.flush()

        # ---------------------------------------------------------
        # 2. TEMPOS DE ACESSO / VALORES
        # ---------------------------------------------------------

        tempos_origem = (
            db.query(models.TempoAcessoCurso)
            .filter(
                models.TempoAcessoCurso.curso_id == curso_id
            )
            .all()
        )

        for tempo in tempos_origem:
            novo_tempo = models.TempoAcessoCurso(
                curso_id=novo_curso.id,
                meses=tempo.meses,
                valor_cents=tempo.valor_cents,
                ativo=tempo.ativo
            )

            db.add(novo_tempo)

        # ---------------------------------------------------------
        # 3. DISCIPLINAS PRÓPRIAS
        # ---------------------------------------------------------

        disciplinas_origem = (
            db.query(models.CursoDisciplinaPropria)
            .filter(
                models.CursoDisciplinaPropria.curso_id == curso_id
            )
            .order_by(
                models.CursoDisciplinaPropria.ordem.asc(),
                models.CursoDisciplinaPropria.id.asc()
            )
            .all()
        )

        for disciplina_origem in disciplinas_origem:
            copiar_disciplina_conteudo(db, disciplina_origem, novo_curso.id)

        db.commit()

        return {
            "ok": True,
            "curso_origem_id": curso_origem.id,
            "novo_curso_id": novo_curso.id,
            "novo_curso_nome": novo_curso.nome,
            "publicado": novo_curso.publicado
        }

    except Exception:
        db.rollback()
        import logging
        logging.getLogger(__name__).exception("Falha ao duplicar curso %s", curso_id)

        raise HTTPException(
            status_code=500,
            detail="Falha ao duplicar curso; nenhuma cópia foi gravada."
        )


@app.delete("/materiais/{material_id}")
def excluir_material(material_id: int, db: Session = Depends(get_db),
                     usuario: Usuario = Depends(exigir_admin_aulas)):
    material = db.query(Material).filter(Material.id == material_id).first()
    if not material:
        raise HTTPException(404, "Material não encontrado")
    bloquear_pai(db, Aula, material.aula_id)
    db.delete(material)
    confirmar_conteudo(db)
    return {"mensagem": "Material excluído com sucesso"}


@app.delete("/videos/{video_id}")
def excluir_video(video_id: int, db: Session = Depends(get_db),
                  usuario: Usuario = Depends(exigir_admin_aulas)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "Vídeo não encontrado")
    bloquear_pai(db, Aula, video.aula_id)
    db.delete(video)
    confirmar_conteudo(db)
    return {"mensagem": "Vídeo excluído com sucesso"}


@app.post("/admin/disciplinas/{disciplina_id}/copiar", tags=["Admin"])
def copiar_disciplina_entre_cursos(
    disciplina_id: int,
    dados: schemas.CopiarDisciplinaRequest,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(exigir_admin_aulas)
):
    return executar_copia(
        db, lambda: copiar_disciplina_para_curso(db, disciplina_id, dados.curso_destino_id),
        "disciplina"
    )


@app.post("/admin/assuntos/{assunto_id}/copiar", tags=["Admin"])
def copiar_assunto_entre_disciplinas(
    assunto_id: int,
    dados: schemas.CopiarAssuntoRequest,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(exigir_admin_aulas)
):
    return executar_copia(
        db, lambda: copiar_assunto_para_disciplina(db, assunto_id, dados.disciplina_destino_id),
        "assunto"
    )
