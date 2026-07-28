from app.models import Curso, Disciplina, Assunto, Pasta, Aula, Video, Bateria, TentativaBateria, RespostaAlunoQuestao  
from datetime import datetime, timedelta
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
from app import models
from sqlalchemy import func
from fastapi import HTTPException
import requests
from sqlalchemy.exc import IntegrityError
from app.models import (
    AcessoCurso,
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
from app.models import Pagamento, DemonstracaoCurso
from app.models import Atendimento
from app.models import CursoDisciplinaPropria
from app.models import CursoAssuntoProprio
from app.schemas import AulaUpdate

import os
import resend

from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "")
APP_BASE_URL = os.getenv(
    "APP_BASE_URL",
    "http://127.0.0.1:5500/site-html"
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

@app.post("/admin/acessos", tags=["Acessos"])
def admin_criar_acesso(payload: AcessoCursoCreate, db: Session = Depends(get_db), usuario: Usuario = Depends(get_usuario_atual)):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas admin pode liberar acesso")

    u = db.query(Usuario).filter(Usuario.id == payload.usuario_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    c = db.query(Curso).filter(Curso.id == payload.curso_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Curso não encontrado")

    novo = AcessoCurso(usuario_id=payload.usuario_id, curso_id=payload.curso_id, ativo=payload.ativo)
    db.add(novo)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existente = db.query(AcessoCurso).filter(
            AcessoCurso.usuario_id == payload.usuario_id,
            AcessoCurso.curso_id == payload.curso_id
        ).first()
        if existente:
            existente.ativo = True
            db.commit()
            return {"ok": True, "msg": "Acesso já existia e foi reativado", "acesso_id": existente.id}
        raise HTTPException(status_code=400, detail="Erro ao criar acesso")

    db.refresh(novo)
    return {"ok": True, "acesso_id": novo.id}

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

    return [
        AcessoCursoResponse(
            id=a.id,
            curso_id=a.curso_id,
            nome_curso=a.curso.nome,
            ativo=a.ativo,
            data_inicio=a.data_inicio,
            data_fim=a.data_fim
        )
        for a in acessos
    ]

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

@app.get("/debug/dbinfo")
def debug_db(db: Session = Depends(get_db)):
    db_name = db.execute(text("SELECT current_database()")).scalar()
    db_user = db.execute(text("SELECT current_user")).scalar()
    db_port = db.execute(text("SHOW port")).scalar()
    return {"database": db_name, "user": db_user, "port": db_port}


@app.get("/debug/disciplinas_count")
def debug_disciplinas_count(db: Session = Depends(get_db)):
    total = db.execute(text("SELECT COUNT(*) FROM disciplinas")).scalar()
    return {"disciplinas_count": total}


@app.get("/debug/dbversion")
def debug_db(db: Session = Depends(get_db)):
    db_name = db.execute(text("SELECT current_database()")).scalar()
    db_user = db.execute(text("SELECT current_user")).scalar()
    db_host = db.execute(text("SHOW server_version")).scalar()
    return {"database": db_name, "user": db_user, "server_version": db_host}


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
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    agora = datetime.utcnow()

    acesso = db.query(AcessoCurso).filter(
        AcessoCurso.usuario_id == usuario.id,
        AcessoCurso.curso_id == curso_id,
        AcessoCurso.ativo == True
    ).first()

    if not usuario.is_admin and not acesso:
        raise HTTPException(
            status_code=403,
            detail="Sem acesso a este curso"
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

    em_demonstracao = False

    if not usuario.is_admin and acesso:
        demonstracao = (
            db.query(DemonstracaoCurso)
            .filter(
                DemonstracaoCurso.usuario_id == usuario.id,
                DemonstracaoCurso.curso_id == curso_id,
                DemonstracaoCurso.ativo == True,
                DemonstracaoCurso.data_fim > agora
            )
            .order_by(DemonstracaoCurso.id.desc())
            .first()
        )

        if demonstracao:
            em_demonstracao = (
                acesso.data_inicio == demonstracao.data_inicio
                and acesso.data_fim == demonstracao.data_fim
            )

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
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    agora = datetime.utcnow()

    disciplina = db.query(CursoDisciplinaPropria).filter(
        CursoDisciplinaPropria.id == disciplina_id
    ).first()

    if not disciplina:
        raise HTTPException(
            status_code=404,
            detail="Disciplina não encontrada"
        )

    acesso = db.query(AcessoCurso).filter(
        AcessoCurso.usuario_id == usuario.id,
        AcessoCurso.curso_id == disciplina.curso_id,
        AcessoCurso.ativo == True
    ).first()

    if not usuario.is_admin and not acesso:
        raise HTTPException(
            status_code=403,
            detail="Sem acesso a este curso"
        )

    if not usuario.is_admin and acesso:
        demonstracao = (
            db.query(DemonstracaoCurso)
            .filter(
                DemonstracaoCurso.usuario_id == usuario.id,
                DemonstracaoCurso.curso_id == disciplina.curso_id,
                DemonstracaoCurso.ativo == True,
                DemonstracaoCurso.data_fim > agora
            )
            .order_by(DemonstracaoCurso.id.desc())
            .first()
        )

        em_demonstracao = False

        if demonstracao:
            em_demonstracao = (
                acesso.data_inicio == demonstracao.data_inicio
                and acesso.data_fim == demonstracao.data_fim
            )

        if em_demonstracao:
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

    return (
        db.query(CursoAssuntoProprio)
        .filter(
            CursoAssuntoProprio.curso_disciplina_propria_id == disciplina_id,
            CursoAssuntoProprio.ativo == True
        )
        .order_by(CursoAssuntoProprio.ordem.asc())
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
def criar_aula(aula: AulaCreate, db: Session = Depends(get_db)): 

    pasta = db.query(Pasta).filter(Pasta.id == aula.pasta_id).first()
    if not pasta:
        return {"erro": "Pasta não encontrada"}

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
def listar_aulas_por_pasta(pasta_id: int, db: Session = Depends(get_db)):
    aulas = (
        db.query(Aula)
        .filter(Aula.pasta_id == pasta_id)
        .order_by(Aula.ordem.asc(), Aula.id.asc())
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
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    progresso = (
        db.query(ProgressoAula)
        .filter(
            ProgressoAula.usuario_id == usuario.id,
            ProgressoAula.pasta_id == pasta_id,
            ProgressoAula.concluida == True
        )
        .all()
    )

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
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    aula = db.query(Aula).filter(Aula.id == aula_id).first()

    if not aula:
        raise HTTPException(status_code=404, detail="Aula não encontrada")

    existente = (
        db.query(ProgressoAula)
        .filter(
            ProgressoAula.usuario_id == usuario.id,
            ProgressoAula.aula_id == aula_id
        )
        .first()
    )

    if existente:
        existente.concluida = True
        existente.data_conclusao = datetime.utcnow()
        progresso = existente
    else:
        progresso = ProgressoAula(
            usuario_id=usuario.id,
            pasta_id=aula.pasta_id,
            aula_id=aula.id,
            concluida=True
        )
        db.add(progresso)

    db.commit()
    db.refresh(progresso)

    return progresso

@app.post("/videos")
def criar_video(video: VideoCreate, db: Session = Depends(get_db)):
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
        duracao_segundos=video.duracao_segundos,
        transcricao=video.transcricao,
        ordem=video.ordem,
        ativo=video.ativo
    )
    db.add(novo)
    db.commit()
    db.refresh(novo)

    return {
        "id": novo.id,
        "aula_id": novo.aula_id,
        "titulo": novo.titulo,
        "url": novo.url,
        "duracao_segundos": novo.duracao_segundos,
        "transcricao": novo.transcricao,
        "ordem": novo.ordem,
        "ativo": novo.ativo
    }

@app.get("/aulas/{aula_id}/videos")
def listar_videos_da_aula(aula_id: int, db: Session = Depends(get_db)):
    videos = (
        db.query(Video)
        .filter(Video.aula_id == aula_id)
        .order_by(Video.ordem.asc(), Video.id.asc())
        .all()
    )
    return [
        {
            "id": v.id,
            "aula_id": v.aula_id,
            "titulo": v.titulo,
            "url": v.url,
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
    db: Session = Depends(get_db)
):
    video = db.query(Video).filter(Video.id == video_id).first()

    if not video:
        raise HTTPException(status_code=404, detail="Vídeo não encontrado")

    video.titulo = dados.titulo
    video.url = dados.url
    video.duracao_segundos = dados.duracao_segundos
    video.transcricao = dados.transcricao
    video.ordem = dados.ordem
    video.ativo = dados.ativo

    db.commit()
    db.refresh(video)

    return {
        "id": video.id,
        "aula_id": video.aula_id,
        "titulo": video.titulo,
        "url": video.url,
        "duracao_segundos": video.duracao_segundos,
        "transcricao": video.transcricao,
        "ordem": video.ordem,
        "ativo": video.ativo
    }

@app.post("/baterias")
def criar_bateria(bateria: BateriaCreate, db: Session = Depends(get_db)):
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
    db.commit()
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
def listar_baterias_da_aula(aula_id: int, db: Session = Depends(get_db)):
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
def criar_questao(questao: QuestaoCreate, db: Session = Depends(get_db)):
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
    db.commit()
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
    db: Session = Depends(get_db)
):
    questao = db.query(Questao).filter(Questao.id == questao_id).first()

    if not questao:
        raise HTTPException(status_code=404, detail="Questão não encontrada")

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
    questao.ativo = dados.ativo

    db.commit()
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
    db: Session = Depends(get_db)
):
    questao = db.query(Questao).filter(Questao.id == questao_id).first()

    if not questao:
        raise HTTPException(status_code=404, detail="Questão não encontrada")

    bateria_id = questao.bateria_id

    db.query(Alternativa).filter(
        Alternativa.questao_id == questao_id
    ).delete()

    db.query(Comentario).filter(
        Comentario.questao_id == questao_id
    ).delete()

    db.delete(questao)
    db.commit()

    questoes_restantes = (
        db.query(Questao)
        .filter(Questao.bateria_id == bateria_id)
        .order_by(Questao.ordem.asc(), Questao.id.asc())
        .all()
    )

    for i, q in enumerate(questoes_restantes, start=1):
        q.ordem = i

    bateria = db.query(Bateria).filter(Bateria.id == bateria_id).first()

    if bateria and len(questoes_restantes) < 10:
        bateria.status = "EM_ANDAMENTO"

    db.commit()

    return {"mensagem": "Questão excluída com sucesso!"}

@app.post("/questoes/{questao_id}/alternativas")
def criar_alternativa(
    questao_id: int,
    alt: AlternativaCreate,
    db: Session = Depends(get_db)
):
    questao = db.query(Questao).filter(Questao.id == questao_id).first()

    if not questao:
        return {"erro": "Questão não encontrada"}

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
    db.commit()
    db.refresh(nova_alt)

    return {
        "id": nova_alt.id,
        "questao_id": nova_alt.questao_id,
        "letra": nova_alt.letra,
        "texto": nova_alt.texto
    }

@app.post("/questoes/{questao_id}/comentario-geral")
def criar_comentario_geral(questao_id: int, payload: ComentarioGeralCreate, db: Session = Depends(get_db)):
    questao = db.query(Questao).filter(Questao.id == questao_id).first()
    if not questao:
        return {"erro": "Questão não encontrada"}

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
    db.commit()
    db.refresh(novo)

    return {"id": novo.id, "questao_id": novo.questao_id, "texto": novo.texto}


@app.get("/baterias/{bateria_id}/questoes")
def listar_questoes_da_bateria(bateria_id: int, db: Session = Depends(get_db)):
    questoes = (
        db.query(Questao)
        .filter(Questao.bateria_id == bateria_id)
        .order_by(Questao.ordem.asc(), Questao.id.asc())
        .all()
    )

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
def gerar_10_questoes(bateria_id: int, payload: Sprint10Create, db: Session = Depends(get_db)):
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
        db.commit()
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
                db.commit()
                db.refresh(alt)

                db.add(Comentario(questao_id=q.id, alternativa_id=alt.id, texto=comentario))
                db.commit()

        # Se CERTO_ERRADO: cria comentário geral placeholder
        if tipo == "CERTO_ERRADO":
            db.add(Comentario(
                questao_id=q.id,
                alternativa_id=None,
                texto="Comentário geral (sem dizer explicitamente certo/errado)."
            ))
            db.commit()

        criadas.append({"questao_id": q.id, "ordem": q.ordem})

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
    db: Session = Depends(get_db)
):
    bateria = db.query(Bateria).filter(Bateria.id == bateria_id).first()

    if not bateria:
        raise HTTPException(status_code=404, detail="Bateria não encontrada")

    titulo = dados.titulo.strip()

    if not titulo:
        raise HTTPException(status_code=400, detail="Informe o título da bateria")

    bateria.titulo = titulo
    bateria.ordem = dados.ordem
    bateria.status = dados.status
    bateria.ativo = dados.ativo

    db.commit()
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
    db: Session = Depends(get_db)
):
    bateria = db.query(Bateria).filter(Bateria.id == bateria_id).first()

    if not bateria:
        raise HTTPException(status_code=404, detail="Bateria não encontrada")

    total_questoes = db.query(Questao).filter(
        Questao.bateria_id == bateria_id
    ).count()

    if total_questoes < 10:
        raise HTTPException(
            status_code=400,
            detail="A bateria precisa ter 10 questões para ser concluída"
        )

    bateria.status = "CONCLUIDA"

    db.commit()
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
def criar_material(material: MaterialCreate, db: Session = Depends(get_db)):
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
    db.commit()
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
def listar_materiais_da_aula(aula_id: int, db: Session = Depends(get_db)):
    materiais = (
        db.query(Material)
        .filter(Material.aula_id == aula_id)
        .order_by(Material.ordem.asc(), Material.id.asc())
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
    db: Session = Depends(get_db)
):
    material = db.query(Material).filter(Material.id == material_id).first()

    if not material:
        raise HTTPException(status_code=404, detail="Material não encontrado")

    material.titulo = dados.titulo
    material.tipo = dados.tipo
    material.url = dados.url
    material.conteudo = dados.conteudo
    material.ordem = dados.ordem
    material.ativo = dados.ativo

    db.commit()
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
            vendedor_id
        )
        VALUES (
            :u,
            :c,
            :t,
            'PENDENTE',
            :v,
            :codigo_cupom,
            :vendedor_id
        )
        RETURNING id
    """), {
        "u": user.id,
        "c": curso.id,
        "t": tempo.id,
        "v": valor_cents,
        "codigo_cupom": codigo_cupom_usado,
        "vendedor_id": vendedor_id
    }).scalar()

    db.commit()

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
        "external_reference": f"user:{user.id}|curso:{curso.id}|tempo:{tempo.id}",
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

    url = "https://api.mercadopago.com/checkout/preferences"
    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        resp = requests.post(url, headers=headers, json=payload_mp, timeout=20)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Falha de rede ao chamar MP: {e}")

    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Erro MP {resp.status_code}: {resp.text}")

    data = resp.json()

    pref_id = data.get("id")
    init_point = data.get("sandbox_init_point") or data.get("init_point")

    if not pref_id or not init_point:
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

    pagamento = db.query(Pagamento).filter(
        Pagamento.usuario_id == user.id,
        Pagamento.curso_id == curso_id
    ).order_by(Pagamento.id.desc()).first()

    if not pagamento:
        raise HTTPException(status_code=404, detail="Pagamento não encontrado.")

    pagamento.status = status.upper()
    pagamento.mp_payment_id = str(payment_id)

    if (
        status == "approved"
        and not pagamento.aprovado_em
    ):
        pagamento.aprovado_em = datetime.utcnow()

    pagamento.atualizado_em = datetime.utcnow()

    db.commit()

    liberou = False

    if status == "approved":
        tempo = db.query(TempoAcessoCurso).filter(
            TempoAcessoCurso.id == pagamento.tempo_acesso_id
        ).first()

        if not tempo:
            raise HTTPException(status_code=400, detail="Tempo de acesso não encontrado para este pagamento.")

        data_inicio = datetime.utcnow()
        data_fim = data_inicio + relativedelta(months=tempo.meses)

        db.execute(text("""
            INSERT INTO acessos_curso (usuario_id, curso_id, ativo, data_inicio, data_fim)
            VALUES (:u, :c, TRUE, :inicio, :fim)
            ON CONFLICT (usuario_id, curso_id)
            DO UPDATE SET
                ativo = TRUE,
                data_inicio = :inicio,
                data_fim = :fim
        """), {
            "u": user.id,
            "c": curso_id,
            "inicio": data_inicio,
            "fim": data_fim
        })

        db.commit()
        liberou = True

    return {
        "ok": True,
        "status": status.upper(),
        "curso_id": curso_id,
        "liberou_acesso": liberou
    }

from fastapi import Request, HTTPException

@app.post("/webhooks/mercadopago")
async def webhook_mercadopago(request: Request, db: Session = Depends(get_db)):
    data = await request.json()

    payment_id = None
    if isinstance(data, dict):
        payment_id = (data.get("data") or {}).get("id") or data.get("id") or data.get("payment_id")

    if not payment_id:
        return {"ok": True, "ignored": True, "msg": "sem payment_id", "payload": data}

    r = requests.get(
        f"https://api.mercadopago.com/v1/payments/{payment_id}",
        headers=mp_headers(),
        timeout=20
    )

    if r.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"MP erro ao consultar payment: {r.status_code} {r.text}"
        )

    pagamento_mp = r.json()
    status = (pagamento_mp.get("status") or "desconhecido").upper()
    external_reference = pagamento_mp.get("external_reference") or ""

    user_id = None
    curso_id = None
    tempo_acesso_id = None

    try:
        for p in external_reference.split("|"):
            if p.startswith("user:"):
                user_id = int(p.split(":", 1)[1])
            elif p.startswith("curso:"):
                curso_id = int(p.split(":", 1)[1])
            elif p.startswith("tempo:"):
                tempo_acesso_id = int(p.split(":", 1)[1])
    except:
        pass

    if user_id and curso_id:
        pagamento = db.query(Pagamento).filter(
            Pagamento.usuario_id == user_id,
            Pagamento.curso_id == curso_id
        ).order_by(Pagamento.id.desc()).first()

        if pagamento:
            pagamento.status = status
            pagamento.mp_payment_id = str(payment_id)

            if (
                status == "APPROVED"
                and not pagamento.aprovado_em
            ):
                pagamento.aprovado_em = datetime.utcnow()

            pagamento.atualizado_em = datetime.utcnow()

            if (
                tempo_acesso_id
                and not pagamento.tempo_acesso_id
            ):
                pagamento.tempo_acesso_id = tempo_acesso_id

            db.commit()
    else:
        db.execute(text("""
            UPDATE pagamentos
            SET
                status = :st,
                mp_payment_id = :pid,
                aprovado_em = CASE
                    WHEN :st = 'APPROVED'
                        AND aprovado_em IS NULL
                    THEN NOW()
                    ELSE aprovado_em
                END,
                atualizado_em = NOW()
            WHERE status = 'PENDENTE'
            ORDER BY id DESC
            LIMIT 1
        """), {
            "st": status,
            "pid": str(payment_id)
        })

        db.commit()

        return {
            "ok": True,
            "status": status,
            "msg": "external_reference não parseável",
            "payment_id": payment_id
        }

    if status == "APPROVED":
        pagamento = db.query(Pagamento).filter(
            Pagamento.usuario_id == user_id,
            Pagamento.curso_id == curso_id
        ).order_by(Pagamento.id.desc()).first()

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
            return {
                "ok": False,
                "status": status,
                "msg": "Tempo de acesso não encontrado para este pagamento.",
                "payment_id": payment_id
            }

        data_inicio = datetime.utcnow()
        data_fim = data_inicio + relativedelta(months=tempo.meses)

        db.execute(text("""
            INSERT INTO acessos_curso (usuario_id, curso_id, ativo, data_inicio, data_fim)
            VALUES (:u, :c, TRUE, :inicio, :fim)
            ON CONFLICT (usuario_id, curso_id)
            DO UPDATE SET
                ativo = TRUE,
                data_inicio = :inicio,
                data_fim = :fim
        """), {
            "u": user_id,
            "c": curso_id,
            "inicio": data_inicio,
            "fim": data_fim
        })

        db.commit()

    return {
        "ok": True,
        "status": status.upper(),
        "curso_id": curso_id,
        "tempo_acesso_id": tempo_acesso_id
    }


from dotenv import dotenv_values

@app.get("/debug/env")
def debug_env():
    token_env = os.getenv("MP_ACCESS_TOKEN", "")
    valores_env = dotenv_values(ENV_PATH)
    token_arquivo = valores_env.get("MP_ACCESS_TOKEN", "")

    return {
        "env_path": str(ENV_PATH),
        "env_existe": ENV_PATH.exists(),
        "token_os_inicio": token_env[:12],
        "token_arquivo_inicio": token_arquivo[:12],
        "app_base_url": os.getenv("APP_BASE_URL", ""),
        "mp_webhook_url": os.getenv("MP_WEBHOOK_URL", "")
    }

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
        WHERE p.status IN ('REFUND_REQUESTED', 'REFUND_IN_PROCESS', 'REFUNDED', 'REFUND_ERROR')
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
        SELECT id, usuario_id, curso_id
        FROM pagamentos
        WHERE mp_payment_id = :pid
        ORDER BY id DESC
        LIMIT 1
    """), {"pid": mp_payment_id}).mappings().first()

    if not pag:
        raise HTTPException(status_code=404, detail="Pagamento não encontrado no banco para esse mp_payment_id")

    user_id = int(pag["usuario_id"])
    curso_id = int(pag["curso_id"])

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

    # 3) atualiza status no banco
    db.execute(text("""
        UPDATE pagamentos
        SET status = :st,
            atualizado_em = NOW()
        WHERE id = :id
    """), {"st": status_mp.upper(), "id": int(pag["id"])})
    db.commit()

    # 4) se aprovado, libera acesso
    liberou = False
    if status_mp == "approved":
        db.execute(text("""
            INSERT INTO acessos_curso (usuario_id, curso_id, ativo, data_inicio, data_fim)
            VALUES (:u, :c, TRUE, NOW(), NULL)
            ON CONFLICT (usuario_id, curso_id)
            DO UPDATE SET
                ativo = TRUE,
                data_inicio = COALESCE(acessos_curso.data_inicio, NOW()),
                data_fim = NULL
        """), {"u": user_id, "c": curso_id})
        db.commit()
        liberou = True

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

    q = (q or "").strip().lower()

    query = db.query(Usuario)
    if q:
        query = query.filter(
            (Usuario.email.ilike(f"%{q}%")) |
            (Usuario.nome.ilike(f"%{q}%"))
        )

    # ordena pelos mais recentes
    alunos = query.order_by(Usuario.id.desc()).limit(100).all()

    return [{
        "id": u.id,
        "nome": u.nome,
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

    acesso = db.query(AcessoCurso).filter(
        AcessoCurso.usuario_id == usuario.id,
        AcessoCurso.curso_id == pagamento.curso_id,
        AcessoCurso.ativo == True
    ).first()

    if acesso:
        acesso.ativo = False
        acesso.data_fim = datetime.utcnow()

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

@app.get("/debug/mp/payment/{payment_id}")
def debug_mp_payment(payment_id: str):
    r = requests.get(
        f"https://api.mercadopago.com/v1/payments/{payment_id}",
        headers=mp_headers(),
        timeout=20
    )

    return {
        "status_code": r.status_code,
        "resposta": r.json() if r.text else None
    }


@app.post("/admin/reembolsos/{pagamento_id}/aprovar")
def aprovar_reembolso(
    pagamento_id: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(get_usuario_atual)
):
    pagamento = db.query(Pagamento).filter(
        Pagamento.id == pagamento_id
    ).first()

    if not pagamento:
        raise HTTPException(status_code=404, detail="Pagamento não encontrado")

    pagamento.status = "REFUNDED"
    pagamento.atualizado_em = datetime.utcnow()

    db.commit()

    return {
        "ok": True,
        "message": "Reembolso aprovado com sucesso"
    }


@app.post("/admin/reembolsos/{pagamento_id}/recusar")
def recusar_reembolso(
    pagamento_id: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(get_usuario_atual)
):
    pagamento = db.query(Pagamento).filter(
        Pagamento.id == pagamento_id
    ).first()

    if not pagamento:
        raise HTTPException(status_code=404, detail="Pagamento não encontrado")

    acesso = db.query(AcessoCurso).filter(
        AcessoCurso.usuario_id == pagamento.usuario_id,
        AcessoCurso.curso_id == pagamento.curso_id
    ).first()

    if acesso:
        acesso.ativo = True
        acesso.data_fim = None

    pagamento.status = "APPROVED"
    pagamento.atualizado_em = datetime.utcnow()

    db.commit()

    return {
        "ok": True,
        "message": "Reembolso recusado e acesso reativado"
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

@app.get("/pastas/{pasta_id}/aulas")
def listar_aulas_pasta(
    pasta_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):

    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas admin")

    aulas = (
        db.query(Aula)
        .filter(Aula.pasta_id == pasta_id)
        .order_by(Aula.ordem.asc())
        .all()
    )

    return aulas

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

    tentativa = TentativaBateria(
        usuario_id=usuario_atual.id,
        bateria_id=dados.bateria_id,
        status="EM_ANDAMENTO",
        percentual_acerto=0,
        concluida_em=datetime.utcnow(),
        ativo=True
    )

    db.add(tentativa)
    db.commit()
    db.refresh(tentativa)

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

    questoes_ids = [
        q.id
        for q in db.query(Questao.id)
        .filter(Questao.bateria_id == bateria_id)
        .all()
    ]

    if questoes_ids:
        db.query(Alternativa).filter(
            Alternativa.questao_id.in_(questoes_ids)
        ).delete(synchronize_session=False)

        db.query(Questao).filter(
            Questao.bateria_id == bateria_id
        ).delete(synchronize_session=False)

    db.delete(bateria)
    db.commit()

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
        raise HTTPException(status_code=404, detail="Tentativa não encontrada")

    tentativa.status = "FEITA"
    tentativa.revisao_concluida_em = datetime.utcnow()

    bateria = db.query(Bateria).filter(
        Bateria.id == tentativa.bateria_id
    ).first()

    if not bateria:
        raise HTTPException(status_code=404, detail="Bateria não encontrada")

    aula = db.query(Aula).filter(
        Aula.id == bateria.aula_id
    ).first()

    if not aula:
        raise HTTPException(status_code=404, detail="Aula não encontrada")

    baterias_da_aula = (
        db.query(Bateria)
        .filter(
            Bateria.aula_id == aula.id,
            Bateria.ativo == True
        )
        .all()
    )

    print(
        "AULA",
        aula.id,
        "BATERIAS",
        len(baterias_da_aula)
    )

    todas_feitas = True

    for b in baterias_da_aula:
        tentativa_feita = (
            db.query(TentativaBateria)
            .filter(
                TentativaBateria.usuario_id == usuario_atual.id,
                TentativaBateria.bateria_id == b.id,
                TentativaBateria.status == "FEITA"
            )
            .first()
        )

        if not tentativa_feita:
            todas_feitas = False
            break

    print("TODAS_FEITAS =", todas_feitas)

    if todas_feitas and baterias_da_aula:
        progresso_existente = (
            db.query(ProgressoAula)
            .filter(
                ProgressoAula.usuario_id == usuario_atual.id,
                ProgressoAula.aula_id == aula.id
            )
            .first()
        )

        if progresso_existente:
            progresso_existente.concluida = True
            progresso_existente.data_conclusao = datetime.utcnow()
        else:
            db.add(
                ProgressoAula(
                    usuario_id=usuario_atual.id,
                    pasta_id=aula.pasta_id,
                    aula_id=aula.id,
                    concluida=True
                )
            )

        revisao_existente = (
            db.query(RevisaoAluno)
            .filter(
                RevisaoAluno.usuario_id == usuario_atual.id,
                RevisaoAluno.aula_id == aula.id,
                RevisaoAluno.etapa == 1
            )
            .first()
        )

        if not revisao_existente:
            db.add(
                RevisaoAluno(
                    usuario_id=usuario_atual.id,
                    aula_id=aula.id,
                    pasta_id=aula.pasta_id,
                    etapa=1,
                    data_prevista=datetime.utcnow() + timedelta(days=7)
                )
            )

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
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    baterias = (
        db.query(Bateria)
        .filter(
            Bateria.aula_id == aula_id,
            Bateria.status == "CONCLUIDA",
            Bateria.ativo == True
        )
        .order_by(Bateria.ordem.asc(), Bateria.id.asc())
        .all()
    )

    resultado = []

    for b in baterias:
        tentativa = (
            db.query(TentativaBateria)
            .filter(
                TentativaBateria.usuario_id == usuario_atual.id,
                TentativaBateria.bateria_id == b.id,
                TentativaBateria.ativo == True
            )
            .order_by(TentativaBateria.id.desc())
            .first()
        )

        resultado.append({
            "id": b.id,
            "aula_id": b.aula_id,
            "titulo": b.titulo,
            "ordem": b.ordem,
            "status_bateria": b.status,
            "questoes_count": db.query(Questao).filter(
                Questao.bateria_id == b.id
            ).count(),
            "status_aluno": tentativa.status if tentativa else None,
            "percentual_acerto": tentativa.percentual_acerto if tentativa else None,
            "tentativa_id": tentativa.id if tentativa else None
        })

    return resultado

@app.put("/baterias/{bateria_id}/limpar-minha-sprint")
def limpar_minha_sprint(
    bateria_id: int,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    bateria = db.query(Bateria).filter(Bateria.id == bateria_id).first()

    if not bateria:
        raise HTTPException(status_code=404, detail="Bateria não encontrada")

    tentativas_ativas = db.query(TentativaBateria).filter(
        TentativaBateria.usuario_id == usuario_atual.id,
        TentativaBateria.bateria_id == bateria_id,
        TentativaBateria.ativo == True
    ).all()

    for tentativa in tentativas_ativas:
        tentativa.ativo = False

    db.commit()

    return {
        "mensagem": "Sprint liberada para ser refeita."
    }


@app.get("/baterias/{bateria_id}/minha-tentativa-ativa")
def obter_minha_tentativa_ativa(
    bateria_id: int,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    tentativa = (
        db.query(TentativaBateria)
        .filter(
            TentativaBateria.usuario_id == usuario_atual.id,
            TentativaBateria.bateria_id == bateria_id,
            TentativaBateria.ativo == True
        )
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
            RespostaAlunoQuestao.bateria_id == bateria_id
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
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    respostas = (
        db.query(RespostaAlunoQuestao)
        .filter(
            RespostaAlunoQuestao.usuario_id == usuario_atual.id,
            RespostaAlunoQuestao.rever == True
        )
        .order_by(RespostaAlunoQuestao.criada_em.desc())
        .all()
    )

    resultado = []

    for r in respostas:
        questao = db.query(Questao).filter(Questao.id == r.questao_id).first()
        bateria = db.query(Bateria).filter(Bateria.id == r.bateria_id).first()

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
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
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
        .join(Questao, Questao.id == RespostaAlunoQuestao.questao_id)
        .join(Bateria, Bateria.id == RespostaAlunoQuestao.bateria_id)
        .join(Aula, Aula.id == Bateria.aula_id)
        .join(Pasta, Pasta.id == Aula.pasta_id)
        .join(CursoAssuntoProprio, CursoAssuntoProprio.id == Pasta.curso_assunto_proprio_id)
        .join(CursoDisciplinaPropria, CursoDisciplinaPropria.id == CursoAssuntoProprio.curso_disciplina_propria_id)
        .filter(RespostaAlunoQuestao.usuario_id == usuario_atual.id)
    )

    if curso_id:
        query = query.filter(CursoDisciplinaPropria.curso_id == curso_id)

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
                "enunciado": questao.enunciado,
                "comentario": questao.comentario,

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
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    revisoes = (
        db.query(RevisaoAluno)
        .filter(
            RevisaoAluno.usuario_id == usuario_atual.id,
            RevisaoAluno.concluida == False
        )
        .order_by(RevisaoAluno.data_prevista.asc())
        .all()
    )

    resultado = []

    for r in revisoes:
        aula = db.query(Aula).filter(Aula.id == r.aula_id).first()

        resultado.append({
            "id": r.id,
            "aula_id": r.aula_id,
            "pasta_id": r.pasta_id,
            "titulo": aula.titulo if aula else "Aula",
            "etapa": r.etapa,
            "data_prevista": r.data_prevista
        })

    return resultado

@app.put("/me/revisoes/{revisao_id}/concluir")
def concluir_revisao(
    revisao_id: int,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    revisao = (
        db.query(RevisaoAluno)
        .filter(
            RevisaoAluno.id == revisao_id,
            RevisaoAluno.usuario_id == usuario_atual.id
        )
        .first()
    )

    if not revisao:
        raise HTTPException(
            status_code=404,
            detail="Revisão não encontrada"
        )

    revisao.concluida = True

    db.commit()

    from datetime import timedelta

    proxima_etapa = revisao.etapa + 1

    intervalo = {
        2: 15,
        3: 21,
        4: 28
    }

    if proxima_etapa <= 4:
        db.add(
            RevisaoAluno(
                usuario_id=revisao.usuario_id,
                aula_id=revisao.aula_id,
                pasta_id=revisao.pasta_id,
                etapa=proxima_etapa,
                data_prevista=datetime.utcnow() +
                timedelta(days=intervalo[proxima_etapa])
            )
        )

        db.commit()

    return {"ok": True}

@app.post("/me/anotacoes-questoes")
def criar_anotacao_questao(
    payload: dict,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    questao_id = payload.get("questao_id")
    bateria_id = payload.get("bateria_id")
    texto = (payload.get("texto") or "").strip()

    if not questao_id or not bateria_id:
        raise HTTPException(status_code=400, detail="Informe questao_id e bateria_id")

    if not texto:
        raise HTTPException(status_code=400, detail="Informe a anotação")

    if len(texto.split()) > 300:
        raise HTTPException(status_code=400, detail="A anotação deve ter no máximo 300 palavras")

    questao = db.query(Questao).filter(Questao.id == questao_id).first()

    if not questao:
        raise HTTPException(status_code=404, detail="Questão não encontrada")

    nova = AnotacaoAlunoQuestao(
        usuario_id=usuario_atual.id,
        questao_id=questao_id,
        bateria_id=bateria_id,
        texto=texto
    )

    db.add(nova)
    db.commit()
    db.refresh(nova)

    return {
        "id": nova.id,
        "questao_id": nova.questao_id,
        "bateria_id": nova.bateria_id,
        "texto": nova.texto
    }

@app.put("/me/anotacoes-questoes/{anotacao_id}")
def editar_anotacao_questao(
    anotacao_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    texto = (payload.get("texto") or "").strip()

    if not texto:
        raise HTTPException(status_code=400, detail="Informe a anotação")

    if len(texto.split()) > 300:
        raise HTTPException(status_code=400, detail="A anotação deve ter no máximo 300 palavras")

    anotacao = db.query(AnotacaoAlunoQuestao).filter(
        AnotacaoAlunoQuestao.id == anotacao_id,
        AnotacaoAlunoQuestao.usuario_id == usuario_atual.id
    ).first()

    if not anotacao:
        raise HTTPException(status_code=404, detail="Anotação não encontrada")

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
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    anotacao = db.query(AnotacaoAlunoQuestao).filter(
        AnotacaoAlunoQuestao.id == anotacao_id,
        AnotacaoAlunoQuestao.usuario_id == usuario_atual.id
    ).first()

    if not anotacao:
        raise HTTPException(status_code=404, detail="Anotação não encontrada")

    db.delete(anotacao)
    db.commit()

    return {"ok": True}

@app.get("/me/minhas-anotacoes")
def listar_minhas_anotacoes(
    curso_id: int | None = None,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
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
        .join(Questao, Questao.id == AnotacaoAlunoQuestao.questao_id)
        .join(Bateria, Bateria.id == Questao.bateria_id)
        .join(Aula, Aula.id == Bateria.aula_id)
        .join(Pasta, Pasta.id == Aula.pasta_id)
        .join(CursoAssuntoProprio, CursoAssuntoProprio.id == Pasta.curso_assunto_proprio_id)
        .join(CursoDisciplinaPropria, CursoDisciplinaPropria.id == CursoAssuntoProprio.curso_disciplina_propria_id)
        .filter(AnotacaoAlunoQuestao.usuario_id == usuario_atual.id)
    )

    if curso_id:
        query = query.filter(CursoDisciplinaPropria.curso_id == curso_id)

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

    for anotacao, questao, bateria, aula, pasta, assunto, disciplina in registros:
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

        texto_resposta = alternativa_correta.texto if alternativa_correta else None

        resultado.append({
            "anotacao_id": anotacao.id,

            "disciplina_id": disciplina.id,
            "disciplina_nome": disciplina.nome,
            "disciplina_ordem": disciplina.ordem,

            "assunto_id": assunto.id,
            "assunto_nome": assunto.nome,
            "assunto_ordem": assunto.ordem,

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

@app.post("/me/mensagens-prof")
def aluno_enviar_mensagem_prof(
    payload: dict,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    questao_id = payload.get("questao_id")
    bateria_id = payload.get("bateria_id")
    texto = (payload.get("texto") or "").strip()

    if not questao_id or not bateria_id:
        raise HTTPException(status_code=400, detail="Informe questao_id e bateria_id")

    if not texto:
        raise HTTPException(status_code=400, detail="Informe a mensagem")

    if len(texto.split()) > 300:
        raise HTTPException(status_code=400, detail="A mensagem deve ter no máximo 300 palavras")

    questao = db.query(Questao).filter(Questao.id == questao_id).first()

    if not questao:
        raise HTTPException(status_code=404, detail="Questão não encontrada")

    conversa = (
        db.query(ConversaQuestaoProfessor)
        .filter(
            ConversaQuestaoProfessor.usuario_id == usuario_atual.id,
            ConversaQuestaoProfessor.questao_id == questao_id,
            ConversaQuestaoProfessor.status == "ABERTA"
        )
        .first()
    )

    if not conversa:
        conversa = ConversaQuestaoProfessor(
            usuario_id=usuario_atual.id,
            questao_id=questao_id,
            bateria_id=bateria_id,
            status="ABERTA"
        )
        db.add(conversa)
        db.commit()
        db.refresh(conversa)

    mensagens_aluno = (
        db.query(MensagemConversaQuestao)
        .filter(
            MensagemConversaQuestao.conversa_id == conversa.id,
            MensagemConversaQuestao.autor == "ALUNO"
        )
        .count()
    )

    if mensagens_aluno >= 3:
        raise HTTPException(
            status_code=400,
            detail="Limite de 3 mensagens ao professor atingido"
        )

    ultima_msg = (
        db.query(MensagemConversaQuestao)
        .filter(MensagemConversaQuestao.conversa_id == conversa.id)
        .order_by(MensagemConversaQuestao.criada_em.desc())
        .first()
    )

    if ultima_msg and ultima_msg.autor == "ALUNO":
        raise HTTPException(
            status_code=400,
            detail="Aguarde a resposta do professor antes de enviar nova mensagem"
        )

    nova = MensagemConversaQuestao(
        conversa_id=conversa.id,
        autor="ALUNO",
        texto=texto
    )

    db.add(nova)

    if mensagens_aluno + 1 >= 3:
        conversa.status = "AGUARDANDO_RESPOSTA_FINAL"
    else:
        conversa.status = "ABERTA"

    conversa.atualizado_em = datetime.utcnow()

    db.commit()
    db.refresh(nova)

    return {
        "conversa_id": conversa.id,
        "mensagem_id": nova.id,
        "autor": nova.autor,
        "texto": nova.texto
    }

@app.get("/me/mensagens-prof")
def listar_minhas_mensagens_prof(
    curso_id: int | None = None,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    query = (
        db.query(
            ConversaQuestaoProfessor,
            Questao,
            Bateria,
            Aula,
            Pasta,
            CursoAssuntoProprio,
            CursoDisciplinaPropria
        )
        .join(Questao, Questao.id == ConversaQuestaoProfessor.questao_id)
        .join(Bateria, Bateria.id == ConversaQuestaoProfessor.bateria_id)
        .join(Aula, Aula.id == Bateria.aula_id)
        .join(Pasta, Pasta.id == Aula.pasta_id)
        .join(CursoAssuntoProprio, CursoAssuntoProprio.id == Pasta.curso_assunto_proprio_id)
        .join(CursoDisciplinaPropria, CursoDisciplinaPropria.id == CursoAssuntoProprio.curso_disciplina_propria_id)
        .filter(ConversaQuestaoProfessor.usuario_id == usuario_atual.id)
    )

    if curso_id:
        query = query.filter(CursoDisciplinaPropria.curso_id == curso_id)

    conversas = (
        query
        .order_by(
            CursoDisciplinaPropria.ordem.asc(),
            CursoAssuntoProprio.ordem.asc(),
            ConversaQuestaoProfessor.criado_em.desc()
        )
        .all()
    )

    resultado = []

    for conversa, questao, bateria, aula, pasta, assunto, disciplina in conversas:
        mensagens = (
            db.query(MensagemConversaQuestao)
            .filter(MensagemConversaQuestao.conversa_id == conversa.id)
            .order_by(MensagemConversaQuestao.criada_em.asc())
            .all()
        )

        resultado.append({
            "conversa_id": conversa.id,
            "status": conversa.status,

            "disciplina_id": disciplina.id,
            "disciplina_nome": disciplina.nome,
            "disciplina_ordem": disciplina.ordem,

            "assunto_id": assunto.id,
            "assunto_nome": assunto.nome,
            "assunto_ordem": assunto.ordem,

            "questao_id": questao.id,
            "questao_ordem": questao.ordem,
            "tipo": questao.tipo,
            "tipo_questao": questao.tipo_questao,
            "enunciado": questao.enunciado,
            "gabarito": questao.gabarito,
            "comentario": questao.comentario,

            "bateria_id": bateria.id,
            "bateria_titulo": bateria.titulo,

            "mensagens": [
                {
                    "id": m.id,
                    "autor": m.autor,
                    "texto": m.texto,
                    "criada_em": m.criada_em
                }
                for m in mensagens
            ],

            "criado_em": conversa.criado_em,
            "atualizado_em": conversa.atualizado_em
        })

    return resultado

@app.get("/admin/mensagens-questoes")
def listar_mensagens_questoes_admin(
    curso_id: int | None = None,
    disciplina_id: int | None = None,
    concluidas: bool = False,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    if not usuario_atual.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito"
        )

    query = (
        db.query(
            ConversaQuestaoProfessor,
            Questao,
            Bateria,
            Aula,
            Pasta,
            CursoAssuntoProprio,
            CursoDisciplinaPropria,
            Curso,
            Usuario
        )
        .join(
            Questao,
            Questao.id == ConversaQuestaoProfessor.questao_id
        )
        .join(
            Bateria,
            Bateria.id == ConversaQuestaoProfessor.bateria_id
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
            CursoAssuntoProprio.id == Pasta.curso_assunto_proprio_id
        )
        .join(
            CursoDisciplinaPropria,
            CursoDisciplinaPropria.id ==
            CursoAssuntoProprio.curso_disciplina_propria_id
        )
        .join(
            Curso,
            Curso.id == CursoDisciplinaPropria.curso_id
        )
        .join(
            Usuario,
            Usuario.id == ConversaQuestaoProfessor.usuario_id
        )
    )

    if concluidas:
        query = query.filter(
            ConversaQuestaoProfessor.status == "ENCERRADA"
        )
    else:
        query = query.filter(
            ConversaQuestaoProfessor.status != "ENCERRADA"
        )

    if curso_id:
        query = query.filter(
            Curso.id == curso_id
        )

    if disciplina_id:
        query = query.filter(
            CursoDisciplinaPropria.id == disciplina_id
        )

    registros = (
        query
        .order_by(
            ConversaQuestaoProfessor.criado_em.asc()
        )
        .all()
    )

    resultado = []

    for (
        conversa,
        questao,
        bateria,
        aula,
        pasta,
        assunto,
        disciplina,
        curso,
        usuario
    ) in registros:

        mensagens = (
            db.query(MensagemConversaQuestao)
            .filter(
                MensagemConversaQuestao.conversa_id == conversa.id
            )
            .order_by(
                MensagemConversaQuestao.criada_em.asc()
            )
            .all()
        )

        resultado.append({
            "conversa_id": conversa.id,
            "status": conversa.status,

            "aluno_id": usuario.id,
            "aluno_nome": usuario.nome,

            "curso_id": curso.id,
            "curso_nome": curso.nome,

            "disciplina_id": disciplina.id,
            "disciplina_nome": disciplina.nome,

            "assunto_nome": assunto.nome,

            "questao_id": questao.id,
            "enunciado": questao.enunciado,
            "gabarito": questao.gabarito,
            "comentario": questao.comentario,

            "mensagens": [
                {
                    "id": m.id,
                    "autor": m.autor,
                    "texto": m.texto,
                    "criada_em": m.criada_em
                }
                for m in mensagens
            ],

            "criado_em": conversa.criado_em
        })

    return resultado

@app.post("/admin/mensagens-questoes/{conversa_id}/responder")
def responder_mensagem_questao(
    conversa_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    if not usuario_atual.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito"
        )

    texto = (payload.get("texto") or "").strip()

    if not texto:
        raise HTTPException(
            status_code=400,
            detail="Informe a resposta"
        )

    conversa = (
        db.query(ConversaQuestaoProfessor)
        .filter(
            ConversaQuestaoProfessor.id == conversa_id
        )
        .first()
    )

    if not conversa:
        raise HTTPException(
            status_code=404,
            detail="Conversa não encontrada"
        )

    mensagens_prof = (
        db.query(MensagemConversaQuestao)
        .filter(
            MensagemConversaQuestao.conversa_id == conversa.id,
            MensagemConversaQuestao.autor == "PROFESSOR"
        )
        .count()
    )

    nova = MensagemConversaQuestao(
        conversa_id=conversa.id,
        autor="PROFESSOR",
        texto=texto
    )

    db.add(nova)

    if mensagens_prof + 1 >= 3:
        conversa.status = "ENCERRADA"
    else:
        conversa.status = "ABERTA"

    conversa.atualizado_em = datetime.utcnow()

    db.commit()
    db.refresh(nova)

    return {
        "mensagem_id": nova.id,
        "status_conversa": conversa.status
    }

@app.post("/me/mensagens-prof/{conversa_id}/responder")
def aluno_responder_professor(
    conversa_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    texto = (payload.get("texto") or "").strip()

    if not texto:
        raise HTTPException(status_code=400, detail="Informe a mensagem")

    if len(texto.split()) > 300:
        raise HTTPException(
            status_code=400,
            detail="A mensagem deve ter no máximo 300 palavras"
        )

    conversa = (
        db.query(ConversaQuestaoProfessor)
        .filter(
            ConversaQuestaoProfessor.id == conversa_id,
            ConversaQuestaoProfessor.usuario_id == usuario_atual.id
        )
        .first()
    )

    if not conversa:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")

    if conversa.status == "ENCERRADA":
        raise HTTPException(status_code=400, detail="Interação concluída")

    mensagens = (
        db.query(MensagemConversaQuestao)
        .filter(MensagemConversaQuestao.conversa_id == conversa.id)
        .order_by(MensagemConversaQuestao.criada_em.asc())
        .all()
    )

    if not mensagens:
        raise HTTPException(
            status_code=400,
            detail="Conversa ainda não iniciada"
        )

    ultima = mensagens[-1]

    if ultima.autor != "PROFESSOR":
        raise HTTPException(
            status_code=400,
            detail="Aguarde a resposta do professor antes de enviar nova mensagem"
        )

    mensagens_aluno = [
        m for m in mensagens
        if m.autor == "ALUNO"
    ]

    if len(mensagens_aluno) >= 3:
        raise HTTPException(
            status_code=400,
            detail="Limite de mensagens atingido"
        )

    nova = MensagemConversaQuestao(
        conversa_id=conversa.id,
        autor="ALUNO",
        texto=texto
    )

    db.add(nova)

    conversa.status = "ABERTA"
    conversa.atualizado_em = datetime.utcnow()

    db.commit()
    db.refresh(nova)

    return {
        "mensagem_id": nova.id,
        "status": conversa.status
    }

@app.post(
    "/questoes-pratica/{questao_id}/marcacao",
    response_model=schemas.QuestaoPraticaMarcacaoAlunoResponse
)
def salvar_marcacao_questao_pratica(
    questao_id: int,
    dados: schemas.QuestaoPraticaMarcacaoAlunoCreate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(get_usuario_atual)
):
    questao = db.query(models.QuestaoPraticaAssunto).filter(
        models.QuestaoPraticaAssunto.id == questao_id,
        models.QuestaoPraticaAssunto.ativo == True
    ).first()

    if not questao:
        raise HTTPException(status_code=404, detail="Questão não encontrada.")

    marcacao = db.query(models.QuestaoPraticaMarcacaoAluno).filter(
        models.QuestaoPraticaMarcacaoAluno.usuario_id == usuario.id,
        models.QuestaoPraticaMarcacaoAluno.questao_id == questao_id
    ).first()

    if marcacao:
        marcacao.dificuldade_marcada = dados.dificuldade_marcada
        marcacao.acertou = dados.acertou
    else:
        marcacao = models.QuestaoPraticaMarcacaoAluno(
            usuario_id=usuario.id,
            questao_id=questao_id,
            dificuldade_marcada=dados.dificuldade_marcada,
            acertou=dados.acertou
        )
        db.add(marcacao)

    db.commit()
    db.refresh(marcacao)

    return marcacao

@app.post("/curso-assuntos-proprios/{curso_assunto_proprio_id}/questoes-pratica/proxima")
def obter_proxima_questao_pratica(
    curso_assunto_proprio_id: int,
    dados: schemas.ProximaQuestaoPraticaRequest,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(get_usuario_atual)
):
    filtros = dados.filtros or ["TODAS"]

    ids_sessao = dados.ids_questoes_sessao or []

    if "TODAS" in filtros:
        filtro_chave = "TODAS"
    else:
        filtro_chave = "_".join(sorted(filtros))

    query_questoes = db.query(models.QuestaoPraticaAssunto).filter(
        models.QuestaoPraticaAssunto.curso_assunto_proprio_id == curso_assunto_proprio_id,
        models.QuestaoPraticaAssunto.ativo == True
    )

    if "TODAS" not in filtros:
        query_questoes = query_questoes.join(
            models.QuestaoPraticaMarcacaoAluno,
            models.QuestaoPraticaMarcacaoAluno.questao_id == models.QuestaoPraticaAssunto.id
        ).filter(
            models.QuestaoPraticaMarcacaoAluno.usuario_id == usuario.id
        )

        condicoes = []

        if "DIFICIL" in filtros:
            condicoes.append(models.QuestaoPraticaMarcacaoAluno.dificuldade_marcada == "DIFICIL")

        if "MEDIA" in filtros:
            condicoes.append(models.QuestaoPraticaMarcacaoAluno.dificuldade_marcada == "MEDIA")

        if "FACIL" in filtros:
            condicoes.append(models.QuestaoPraticaMarcacaoAluno.dificuldade_marcada == "FACIL")

        if "ERREI" in filtros:
            condicoes.append(models.QuestaoPraticaMarcacaoAluno.acertou == False)

        if "REVER" in filtros:
            condicoes.append(models.QuestaoPraticaMarcacaoAluno.rever == True)

        if condicoes:
            from sqlalchemy import or_
            query_questoes = query_questoes.filter(or_(*condicoes))

    if ids_sessao:
        ids_questoes_possiveis = ids_sessao
    else:
        ids_questoes_possiveis = [q.id for q in query_questoes.all()]

    if not ids_questoes_possiveis:
        raise HTTPException(status_code=404, detail="Nenhuma questão disponível.")

    ciclo_atual = db.query(func.max(models.QuestaoPraticaRotatividadeAluno.ciclo)).filter(
        models.QuestaoPraticaRotatividadeAluno.usuario_id == usuario.id,
        models.QuestaoPraticaRotatividadeAluno.curso_assunto_proprio_id == curso_assunto_proprio_id,
        models.QuestaoPraticaRotatividadeAluno.filtro == filtro_chave
    ).scalar() or 1

    ids_ja_respondidas = [
        r.questao_id
        for r in db.query(models.QuestaoPraticaRotatividadeAluno.questao_id).filter(
            models.QuestaoPraticaRotatividadeAluno.usuario_id == usuario.id,
            models.QuestaoPraticaRotatividadeAluno.curso_assunto_proprio_id == curso_assunto_proprio_id,
            models.QuestaoPraticaRotatividadeAluno.filtro == filtro_chave,
            models.QuestaoPraticaRotatividadeAluno.ciclo == ciclo_atual
        ).all()
    ]

    ids_disponiveis = [
        qid for qid in ids_questoes_possiveis
        if qid not in ids_ja_respondidas
    ]

    if not ids_disponiveis:
        ciclo_atual += 1
        ids_disponiveis = ids_questoes_possiveis

    questao = db.query(models.QuestaoPraticaAssunto).filter(
        models.QuestaoPraticaAssunto.id.in_(ids_disponiveis)
    ).order_by(func.random()).first()

    numero_questao = db.query(models.QuestaoPraticaRotatividadeAluno).filter(
        models.QuestaoPraticaRotatividadeAluno.usuario_id == usuario.id,
        models.QuestaoPraticaRotatividadeAluno.curso_assunto_proprio_id == curso_assunto_proprio_id,
        models.QuestaoPraticaRotatividadeAluno.filtro == filtro_chave,
        models.QuestaoPraticaRotatividadeAluno.ciclo == ciclo_atual
    ).count() + 1

    alternativas = db.query(models.QuestaoPraticaAlternativa).filter(
        models.QuestaoPraticaAlternativa.questao_pratica_id == questao.id
    ).order_by(
        models.QuestaoPraticaAlternativa.letra.asc()
    ).all()

    return {
        "numero_questao": numero_questao,
        "ciclo": ciclo_atual,
        "filtro": filtro_chave,
        "ids_questoes_sessao": ids_questoes_possiveis,
        "questao": {
            "id": questao.id,
            "curso_assunto_proprio_id": questao.curso_assunto_proprio_id,
            "tipo": questao.tipo,
            "enunciado": questao.enunciado,
            "gabarito": questao.gabarito,
            "comentario": questao.comentario,
            "alternativas": [
                {
                    "id": alt.id,
                    "letra": alt.letra,
                    "texto": alt.texto,
                    "correta": alt.correta
                }
                for alt in alternativas
            ]
        }
    }

@app.post("/questoes-pratica/{questao_id}/responder")
def responder_questao_pratica(
    questao_id: int,
    dados: schemas.ResponderQuestaoPraticaRequest,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(get_usuario_atual)
):
    questao = db.query(models.QuestaoPraticaAssunto).filter(
        models.QuestaoPraticaAssunto.id == questao_id,
        models.QuestaoPraticaAssunto.ativo == True
    ).first()

    if not questao:
        raise HTTPException(status_code=404, detail="Questão não encontrada.")

    filtros = dados.filtros or ["TODAS"]

    if "TODAS" in filtros:
        filtro_chave = "TODAS"
    else:
        filtro_chave = "_".join(sorted(filtros))

    marcacao = db.query(models.QuestaoPraticaMarcacaoAluno).filter(
        models.QuestaoPraticaMarcacaoAluno.usuario_id == usuario.id,
        models.QuestaoPraticaMarcacaoAluno.questao_id == questao_id
    ).first()

    if marcacao:
        marcacao.dificuldade_marcada = dados.dificuldade_marcada
        marcacao.acertou = dados.acertou
        marcacao.rever = dados.rever
        marcacao.nao_soube = dados.nao_soube
    else:
        marcacao = models.QuestaoPraticaMarcacaoAluno(
            usuario_id=usuario.id,
            questao_id=questao_id,
            dificuldade_marcada=dados.dificuldade_marcada,
            acertou=dados.acertou,
            rever=dados.rever,
            nao_soube=dados.nao_soube
        )
        db.add(marcacao)

    ciclo_atual = db.query(func.max(models.QuestaoPraticaRotatividadeAluno.ciclo)).filter(
        models.QuestaoPraticaRotatividadeAluno.usuario_id == usuario.id,
        models.QuestaoPraticaRotatividadeAluno.curso_assunto_proprio_id == questao.curso_assunto_proprio_id,
        models.QuestaoPraticaRotatividadeAluno.filtro == filtro_chave
    ).scalar() or 1

    ids_questoes_possiveis = [
        q.id for q in db.query(models.QuestaoPraticaAssunto).filter(
            models.QuestaoPraticaAssunto.curso_assunto_proprio_id == questao.curso_assunto_proprio_id,
            models.QuestaoPraticaAssunto.ativo == True
        ).all()
    ]

    ids_ja_respondidas = [
        r.questao_id
        for r in db.query(models.QuestaoPraticaRotatividadeAluno.questao_id).filter(
            models.QuestaoPraticaRotatividadeAluno.usuario_id == usuario.id,
            models.QuestaoPraticaRotatividadeAluno.curso_assunto_proprio_id == questao.curso_assunto_proprio_id,
            models.QuestaoPraticaRotatividadeAluno.filtro == filtro_chave,
            models.QuestaoPraticaRotatividadeAluno.ciclo == ciclo_atual
        ).all()
    ]

    if set(ids_questoes_possiveis).issubset(set(ids_ja_respondidas)):
        ciclo_atual += 1

    ja_registrada = db.query(models.QuestaoPraticaRotatividadeAluno).filter(
        models.QuestaoPraticaRotatividadeAluno.usuario_id == usuario.id,
        models.QuestaoPraticaRotatividadeAluno.curso_assunto_proprio_id == questao.curso_assunto_proprio_id,
        models.QuestaoPraticaRotatividadeAluno.questao_id == questao_id,
        models.QuestaoPraticaRotatividadeAluno.filtro == filtro_chave,
        models.QuestaoPraticaRotatividadeAluno.ciclo == ciclo_atual
    ).first()

    if not ja_registrada:
        rotatividade = models.QuestaoPraticaRotatividadeAluno(
            usuario_id=usuario.id,
            curso_assunto_proprio_id=questao.curso_assunto_proprio_id,
            questao_id=questao_id,
            filtro=filtro_chave,
            ciclo=ciclo_atual
        )
        db.add(rotatividade)

    db.commit()

    return {
        "mensagem": "Resposta registrada com sucesso.",
        "questao_id": questao_id,
        "acertou": dados.acertou,
        "dificuldade_marcada": dados.dificuldade_marcada,
        "filtro": filtro_chave,
        "ciclo": ciclo_atual
    }

@app.get("/curso-assuntos-proprios/{curso_assunto_proprio_id}/questoes-pratica/filtros")
def obter_filtros_questoes_pratica(
    curso_assunto_proprio_id: int,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(get_usuario_atual)
):
    # 1. Busca as marcações do aluno para esse assunto
    marcacoes = (
        db.query(models.QuestaoPraticaMarcacaoAluno)
        .join(
            models.QuestaoPraticaAssunto,
            models.QuestaoPraticaAssunto.id ==
            models.QuestaoPraticaMarcacaoAluno.questao_id
        )
        .filter(
            models.QuestaoPraticaMarcacaoAluno.usuario_id == usuario.id,
            models.QuestaoPraticaAssunto.curso_assunto_proprio_id == curso_assunto_proprio_id
        )
        .all()
    )

    # 2. Monta quais filtros devem ficar habilitados
    total_questoes = db.query(models.QuestaoPraticaAssunto).filter(
    models.QuestaoPraticaAssunto.curso_assunto_proprio_id == curso_assunto_proprio_id,
    models.QuestaoPraticaAssunto.ativo == True
    ).count()

    return {
        "TODAS": {
            "habilitado": True,
            "quantidade": total_questoes
        },

        "DIFICIL": {
            "habilitado": any(m.dificuldade_marcada == "DIFICIL" for m in marcacoes),
            "quantidade": sum(1 for m in marcacoes if m.dificuldade_marcada == "DIFICIL")
        },

        "MEDIA": {
            "habilitado": any(m.dificuldade_marcada == "MEDIA" for m in marcacoes),
            "quantidade": sum(1 for m in marcacoes if m.dificuldade_marcada == "MEDIA")
        },

        "FACIL": {
            "habilitado": any(m.dificuldade_marcada == "FACIL" for m in marcacoes),
            "quantidade": sum(1 for m in marcacoes if m.dificuldade_marcada == "FACIL")
        },

        "ERREI": {
            "habilitado": any(m.acertou is False for m in marcacoes),
            "quantidade": sum(1 for m in marcacoes if m.acertou is False)
        },

        "REVER": {
            "habilitado": any(m.rever for m in marcacoes),
            "quantidade": sum(1 for m in marcacoes if m.rever)
        }
    }

@app.post("/admin/questoes-pratica")
def criar_questao_pratica_admin(
    dados: schemas.QuestaoPraticaAdminCreate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas administrador.")

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

    letras_validas = ["A", "B", "C", "D", "E"]

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
    ).first()

    if not questao:
        raise HTTPException(status_code=404, detail="Questão não encontrada.")

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

    letras_validas = ["A", "B", "C", "D", "E"]

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
    ).first()

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

@app.get("/admin/cursos")
def listar_cursos_admin(
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas administrador.")

    cursos = db.query(models.Curso).order_by(models.Curso.nome.asc()).all()

    return [
        {
            "id": c.id,
            "nome": c.nome,
            "ativo": c.ativo
        }
        for c in cursos
    ]


@app.get("/admin/cursos/{curso_id}/disciplinas")
def listar_disciplinas_do_curso_admin(
    curso_id: int,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas administrador.")

    curso = db.query(models.Curso).filter(
        models.Curso.id == curso_id
    ).first()

    if not curso:
        raise HTTPException(status_code=404, detail="Curso não encontrado.")

    disciplinas = db.query(models.CursoDisciplinaPropria).filter(
        models.CursoDisciplinaPropria.curso_id == curso_id
    ).order_by(
        models.CursoDisciplinaPropria.nome.asc()
    ).all()

    return [
        {
            "id": d.id,
            "nome": d.nome,
            "ativo": d.ativo,
            "disponivel_demonstracao": d.disponivel_demonstracao
        }
        for d in disciplinas
    ]


@app.get("/admin/cursos/{curso_id}/disciplinas/{disciplina_id}/assuntos")
def listar_assuntos_da_disciplina_no_curso_admin(
    curso_id: int,
    disciplina_id: int,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas administrador.")

    disciplina = db.query(models.CursoDisciplinaPropria).filter(
        models.CursoDisciplinaPropria.id == disciplina_id,
        models.CursoDisciplinaPropria.curso_id == curso_id
    ).first()

    if not disciplina:
        raise HTTPException(status_code=404, detail="Disciplina do curso não encontrada.")

    assuntos = db.query(models.CursoAssuntoProprio).filter(
        models.CursoAssuntoProprio.curso_disciplina_propria_id == disciplina_id
    ).order_by(
        models.CursoAssuntoProprio.nome.asc()
    ).all()

    return [
        {
            "id": a.id,
            "nome": a.nome,
            "ativo": a.ativo
        }
        for a in assuntos
    ]

@app.get("/me/cursos-expirados/disciplinas/{disciplina_id}/assuntos")
def listar_assuntos_disciplina_expirada(
    disciplina_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    disciplina = (
        db.query(CursoDisciplinaPropria)
        .filter(CursoDisciplinaPropria.id == disciplina_id)
        .first()
    )

    if not disciplina:
        raise HTTPException(status_code=404, detail="Disciplina não encontrada")

    acesso_expirado = db.query(AcessoCurso).filter(
        AcessoCurso.usuario_id == usuario.id,
        AcessoCurso.curso_id == disciplina.curso_id,
        AcessoCurso.ativo == False
    ).first()

    if not acesso_expirado:
        raise HTTPException(
            status_code=403,
            detail="Sem histórico de acesso a este curso"
        )

    assuntos = (
        db.query(CursoAssuntoProprio)
        .filter(
            CursoAssuntoProprio.curso_disciplina_propria_id == disciplina_id,
            CursoAssuntoProprio.ativo == True
        )
        .order_by(CursoAssuntoProprio.ordem.asc())
        .all()
    )

    return [
        {
            "id": a.id,
            "disciplina_id": a.curso_disciplina_propria_id,
            "nome": a.nome,
            "ativo": a.ativo,
            "ordem": a.ordem
        }
        for a in assuntos
    ]

@app.get("/me/cursos-expirados/{curso_id}/anotacoes")
def listar_anotacoes_curso_expirado(
    curso_id: int,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    acesso_expirado = db.query(AcessoCurso).filter(
        AcessoCurso.usuario_id == usuario_atual.id,
        AcessoCurso.curso_id == curso_id,
        AcessoCurso.ativo == False
    ).first()

    if not acesso_expirado:
        raise HTTPException(
            status_code=403,
            detail="Sem histórico de acesso a este curso"
        )

    registros = (
        db.query(
            AnotacaoAlunoQuestao,
            Questao,
            Bateria,
            Aula,
            Pasta,
            CursoAssuntoProprio,
            CursoDisciplinaPropria
        )
        .join(Questao, Questao.id == AnotacaoAlunoQuestao.questao_id)
        .join(Bateria, Bateria.id == Questao.bateria_id)
        .join(Aula, Aula.id == Bateria.aula_id)
        .join(Pasta, Pasta.id == Aula.pasta_id)
        .join(CursoAssuntoProprio, CursoAssuntoProprio.id == Pasta.curso_assunto_proprio_id)
        .join(CursoDisciplinaPropria, CursoDisciplinaPropria.id == CursoAssuntoProprio.curso_disciplina_propria_id)
        .filter(
            AnotacaoAlunoQuestao.usuario_id == usuario_atual.id,
            CursoDisciplinaPropria.curso_id == curso_id
        )
        .order_by(
            CursoDisciplinaPropria.ordem.asc(),
            CursoAssuntoProprio.ordem.asc(),
            Questao.ordem.asc(),
            AnotacaoAlunoQuestao.criado_em.desc()
        )
        .all()
    )

    resultado = []

    for anotacao, questao, bateria, aula, pasta, assunto, disciplina in registros:
        resultado.append({
            "anotacao_id": anotacao.id,
            "disciplina_nome": disciplina.nome,
            "assunto_nome": assunto.nome,
            "questao_id": questao.id,
            "enunciado": questao.enunciado,
            "comentario": questao.comentario,
            "bateria_titulo": bateria.titulo,
            "anotacao": anotacao.texto,
            "texto": anotacao.texto,
            "criado_em": anotacao.criado_em,
            "atualizado_em": anotacao.atualizado_em
        })

    return resultado

@app.get("/me/cursos-expirados/{curso_id}/mensagens-prof")
def listar_mensagens_prof_curso_expirado(
    curso_id: int,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual)
):
    acesso_expirado = db.query(AcessoCurso).filter(
        AcessoCurso.usuario_id == usuario_atual.id,
        AcessoCurso.curso_id == curso_id,
        AcessoCurso.ativo == False
    ).first()

    if not acesso_expirado:
        raise HTTPException(
            status_code=403,
            detail="Sem histórico de acesso a este curso"
        )

    conversas = (
        db.query(
            ConversaQuestaoProfessor,
            Questao,
            Bateria,
            Aula,
            Pasta,
            CursoAssuntoProprio,
            CursoDisciplinaPropria
        )
        .join(Questao, Questao.id == ConversaQuestaoProfessor.questao_id)
        .join(Bateria, Bateria.id == ConversaQuestaoProfessor.bateria_id)
        .join(Aula, Aula.id == Bateria.aula_id)
        .join(Pasta, Pasta.id == Aula.pasta_id)
        .join(CursoAssuntoProprio, CursoAssuntoProprio.id == Pasta.curso_assunto_proprio_id)
        .join(CursoDisciplinaPropria, CursoDisciplinaPropria.id == CursoAssuntoProprio.curso_disciplina_propria_id)
        .filter(
            ConversaQuestaoProfessor.usuario_id == usuario_atual.id,
            CursoDisciplinaPropria.curso_id == curso_id
        )
        .order_by(
            CursoDisciplinaPropria.ordem.asc(),
            CursoAssuntoProprio.ordem.asc(),
            ConversaQuestaoProfessor.criado_em.desc()
        )
        .all()
    )

    resultado = []

    for conversa, questao, bateria, aula, pasta, assunto, disciplina in conversas:
        mensagens = (
            db.query(MensagemConversaQuestao)
            .filter(MensagemConversaQuestao.conversa_id == conversa.id)
            .order_by(MensagemConversaQuestao.criada_em.asc())
            .all()
        )

        resultado.append({
            "conversa_id": conversa.id,
            "status": conversa.status,
            "disciplina_nome": disciplina.nome,
            "assunto_nome": assunto.nome,
            "questao_id": questao.id,
            "enunciado": questao.enunciado,
            "comentario": questao.comentario,
            "bateria_titulo": bateria.titulo,
            "mensagens": [
                {
                    "id": m.id,
                    "autor": m.autor,
                    "texto": m.texto,
                    "criada_em": m.criada_em
                }
                for m in mensagens
            ],
            "criado_em": conversa.criado_em,
            "atualizado_em": conversa.atualizado_em
        })

    return resultado

@app.get("/admin/cursos/{curso_id}/tempos-acesso")
def listar_tempos_acesso(
    curso_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas administrador.")

    registros = (
        db.query(TempoAcessoCurso)
        .filter(
            TempoAcessoCurso.curso_id == curso_id
        )
        .order_by(TempoAcessoCurso.meses.asc())
        .all()
    )

    return [
        {
            "id": r.id,
            "meses": r.meses,
            "valor_cents": r.valor_cents,
            "ativo": r.ativo
        }
        for r in registros
    ]

@app.post("/admin/cursos/{curso_id}/tempos-acesso")
def salvar_tempos_acesso(
    curso_id: int,
    payload: list,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas administrador.")

    curso = db.query(Curso).filter(Curso.id == curso_id).first()

    if not curso:
        raise HTTPException(status_code=404, detail="Curso não encontrado.")

    meses_validos = {4, 8, 12}

    for item in payload:

        meses = int(item["meses"])
        valor = int(item["valor_cents"])

        if meses not in meses_validos:
            raise HTTPException(
                status_code=400,
                detail=f"Tempo de acesso inválido: {meses} meses."
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

            registro.valor_cents = valor
            registro.ativo = True

        else:

            db.add(
                TempoAcessoCurso(
                    curso_id=curso_id,
                    meses=meses,
                    valor_cents=valor,
                    ativo=True
                )
            )

    db.commit()

    return {"ok": True}

@app.get("/admin/cursos/{curso_id}/config-publica")
def obter_config_publica_curso(
    curso_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Apenas administrador.")

    curso = db.query(Curso).filter(Curso.id == curso_id).first()

    if not curso:
        raise HTTPException(status_code=404, detail="Curso não encontrado.")

    tempos = (
        db.query(TempoAcessoCurso)
        .filter(TempoAcessoCurso.curso_id == curso_id)
        .order_by(TempoAcessoCurso.meses.asc())
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
        raise HTTPException(status_code=403, detail="Apenas administrador.")

    curso = db.query(Curso).filter(Curso.id == curso_id).first()

    if not curso:
        raise HTTPException(status_code=404, detail="Curso não encontrado.")

    curso.descricao_publica = payload.get("descricao_publica") or ""

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
        raise HTTPException(status_code=404, detail="Curso não encontrado.")

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

    data_fim = agora + timedelta(days=1)
    liberado_novamente_em = agora + timedelta(days=30)

    demo = DemonstracaoCurso(
        usuario_id=usuario.id,
        curso_id=curso_id,
        data_inicio=agora,
        data_fim=data_fim,
        liberado_novamente_em=liberado_novamente_em,
        ativo=True
    )

    db.add(demo)

    db.execute(text("""
        INSERT INTO acessos_curso (usuario_id, curso_id, ativo, data_inicio, data_fim)
        VALUES (:u, :c, TRUE, :inicio, :fim)
        ON CONFLICT (usuario_id, curso_id)
        DO UPDATE SET
            ativo = TRUE,
            data_inicio = :inicio,
            data_fim = :fim
    """), {
        "u": usuario.id,
        "c": curso_id,
        "inicio": agora,
        "fim": data_fim
    })

    db.commit()

    return {
        "ok": True,
        "tipo": "DEMONSTRACAO",
        "curso_id": curso_id,
        "data_inicio": agora,
        "data_fim": data_fim,
        "liberado_novamente_em": liberado_novamente_em
    }

@app.get("/me/cursos/{curso_id}/tipo-acesso")
def obter_tipo_acesso_curso(
    curso_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    acesso = db.query(AcessoCurso).filter(
        AcessoCurso.usuario_id == usuario.id,
        AcessoCurso.curso_id == curso_id,
        AcessoCurso.ativo == True
    ).first()

    if not acesso:
        raise HTTPException(status_code=403, detail="Sem acesso ativo ao curso.")

    agora = datetime.utcnow()

    if acesso.data_fim and acesso.data_fim < agora:
        acesso.ativo = False
        db.commit()

        raise HTTPException(status_code=403, detail="Acesso expirado.")

    demo = db.query(DemonstracaoCurso).filter(
        DemonstracaoCurso.usuario_id == usuario.id,
        DemonstracaoCurso.curso_id == curso_id,
        DemonstracaoCurso.ativo == True,
        DemonstracaoCurso.data_fim >= agora
    ).order_by(DemonstracaoCurso.id.desc()).first()

    if demo:
        return {
            "tipo": "DEMONSTRACAO",
            "curso_id": curso_id,
            "data_inicio": demo.data_inicio,
            "data_fim": demo.data_fim
        }

    return {
        "tipo": "NORMAL",
        "curso_id": curso_id,
        "data_inicio": acesso.data_inicio,
        "data_fim": acesso.data_fim
    }

@app.get("/public/cursos/{curso_id}/checkout")
def obter_dados_checkout_publico(
    curso_id: int,
    db: Session = Depends(get_db)
):
    curso = db.query(Curso).filter(
        Curso.id == curso_id,
        Curso.ativo == True
    ).first()

    if not curso:
        raise HTTPException(status_code=404, detail="Curso não encontrado.")

    tempos = (
        db.query(TempoAcessoCurso)
        .filter(
            TempoAcessoCurso.curso_id == curso_id,
            TempoAcessoCurso.ativo == True,
            TempoAcessoCurso.meses.in_([4, 8, 12])
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
        .order_by(CursoDisciplinaPropria.ordem.asc())
        .all()
    )

    disciplinas_resultado = []

    for d in disciplinas:
        assuntos = (
            db.query(CursoAssuntoProprio)
            .filter(
                CursoAssuntoProprio.curso_disciplina_propria_id == d.id,
                CursoAssuntoProprio.ativo == True
            )
            .order_by(CursoAssuntoProprio.ordem.asc())
            .all()
        )

        disciplinas_resultado.append({
            "id": d.id,
            "nome": d.nome,
            "ordem": d.ordem,
            "assuntos": [
                {
                    "id": a.id,
                    "nome": a.nome,
                    "ordem": a.ordem
                }
                for a in assuntos
            ]
        })

    return {
        "id": curso.id,
        "nome": curso.nome,
        "descricao_publica": curso.descricao_publica or "",
        "tempos_acesso": [
            {
                "id": t.id,
                "meses": t.meses,
                "valor_cents": t.valor_cents
            }
            for t in tempos
        ],
        "disciplinas": disciplinas_resultado
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

@app.put("/admin/cursos/{curso_id}/retirar-venda")
def retirar_curso_da_venda(
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

    curso.publicado = False

    db.commit()
    db.refresh(curso)

    return {
        "ok": True,
        "curso_id": curso.id,
        "publicado": curso.publicado,
        "mensagem": "Curso retirado da venda com sucesso."
    }

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

    novo_nome = (dados.novo_nome or "").strip()

    if not novo_nome:
        raise HTTPException(
            status_code=400,
            detail="Informe o nome do novo curso."
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

    curso_nome_existente = (
        db.query(models.Curso)
        .filter(
            models.Curso.nome == novo_nome
        )
        .first()
    )

    if curso_nome_existente:
        raise HTTPException(
            status_code=400,
            detail="Já existe um curso com este nome."
        )

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

            nova_disciplina = models.CursoDisciplinaPropria(
                curso_id=novo_curso.id,
                nome=disciplina_origem.nome,
                ativo=disciplina_origem.ativo,
                ordem=disciplina_origem.ordem,
                disponivel_demonstracao=
                    disciplina_origem.disponivel_demonstracao
            )

            db.add(nova_disciplina)
            db.flush()

            # -----------------------------------------------------
            # 4. ASSUNTOS PRÓPRIOS
            # -----------------------------------------------------

            assuntos_origem = (
                db.query(models.CursoAssuntoProprio)
                .filter(
                    models.CursoAssuntoProprio.curso_disciplina_propria_id
                    == disciplina_origem.id
                )
                .order_by(
                    models.CursoAssuntoProprio.ordem.asc(),
                    models.CursoAssuntoProprio.id.asc()
                )
                .all()
            )

            for assunto_origem in assuntos_origem:

                novo_assunto = models.CursoAssuntoProprio(
                    curso_disciplina_propria_id=nova_disciplina.id,
                    nome=assunto_origem.nome,
                    descricao=assunto_origem.descricao,
                    ativo=assunto_origem.ativo,
                    ordem=assunto_origem.ordem
                )

                db.add(novo_assunto)
                db.flush()

                # -------------------------------------------------
                # 5. PASTAS DA ESTRUTURA NOVA
                # -------------------------------------------------

                pastas_origem = (
                    db.query(models.Pasta)
                    .filter(
                        models.Pasta.curso_assunto_proprio_id
                        == assunto_origem.id
                    )
                    .all()
                )

                for pasta_origem in pastas_origem:

                    nova_pasta = models.Pasta(
                        assunto_id=None,
                        curso_assunto_proprio_id=novo_assunto.id,
                        tipo=pasta_origem.tipo,
                        nome=pasta_origem.nome
                    )

                    db.add(nova_pasta)
                    db.flush()

                    # ---------------------------------------------
                    # 6. AULAS
                    # ---------------------------------------------

                    aulas_origem = (
                        db.query(models.Aula)
                        .filter(
                            models.Aula.pasta_id
                            == pasta_origem.id
                        )
                        .order_by(
                            models.Aula.ordem.asc(),
                            models.Aula.id.asc()
                        )
                        .all()
                    )

                    for aula_origem in aulas_origem:

                        nova_aula = models.Aula(
                            pasta_id=nova_pasta.id,
                            titulo=aula_origem.titulo,
                            descricao=aula_origem.descricao,
                            ordem=aula_origem.ordem,
                            ativo=aula_origem.ativo
                        )

                        db.add(nova_aula)
                        db.flush()

                        # -----------------------------------------
                        # 7. VÍDEOS
                        # -----------------------------------------

                        videos_origem = (
                            db.query(models.Video)
                            .filter(
                                models.Video.aula_id
                                == aula_origem.id
                            )
                            .order_by(
                                models.Video.ordem.asc(),
                                models.Video.id.asc()
                            )
                            .all()
                        )

                        for video_origem in videos_origem:
                            db.add(
                                models.Video(
                                    aula_id=nova_aula.id,
                                    titulo=video_origem.titulo,
                                    url=video_origem.url,
                                    duracao_segundos=
                                        video_origem.duracao_segundos,
                                    transcricao=
                                        video_origem.transcricao,
                                    ordem=video_origem.ordem,
                                    ativo=video_origem.ativo
                                )
                            )

                        # -----------------------------------------
                        # 8. MATERIAIS
                        # -----------------------------------------

                        materiais_origem = (
                            db.query(models.Material)
                            .filter(
                                models.Material.aula_id
                                == aula_origem.id
                            )
                            .order_by(
                                models.Material.ordem.asc(),
                                models.Material.id.asc()
                            )
                            .all()
                        )

                        for material_origem in materiais_origem:
                            db.add(
                                models.Material(
                                    aula_id=nova_aula.id,
                                    tipo=material_origem.tipo,
                                    titulo=material_origem.titulo,
                                    url=material_origem.url,
                                    conteudo=material_origem.conteudo,
                                    ordem=material_origem.ordem,
                                    ativo=material_origem.ativo
                                )
                            )

                        # -----------------------------------------
                        # 9. BATERIAS
                        # -----------------------------------------

                        baterias_origem = (
                            db.query(models.Bateria)
                            .filter(
                                models.Bateria.aula_id
                                == aula_origem.id
                            )
                            .order_by(
                                models.Bateria.ordem.asc(),
                                models.Bateria.id.asc()
                            )
                            .all()
                        )

                        for bateria_origem in baterias_origem:

                            nova_bateria = models.Bateria(
                                aula_id=nova_aula.id,
                                titulo=bateria_origem.titulo,
                                ordem=bateria_origem.ordem,
                                status=bateria_origem.status,
                                ativo=bateria_origem.ativo
                            )

                            db.add(nova_bateria)
                            db.flush()

                            # -------------------------------------
                            # 10. QUESTÕES DA BATERIA
                            # -------------------------------------

                            questoes_origem = (
                                db.query(models.Questao)
                                .filter(
                                    models.Questao.bateria_id
                                    == bateria_origem.id
                                )
                                .order_by(
                                    models.Questao.ordem.asc(),
                                    models.Questao.id.asc()
                                )
                                .all()
                            )

                            for questao_origem in questoes_origem:

                                nova_questao = models.Questao(
                                    bateria_id=nova_bateria.id,
                                    enunciado=questao_origem.enunciado,
                                    tipo=questao_origem.tipo,
                                    ordem=questao_origem.ordem,
                                    ativo=questao_origem.ativo,
                                    tipo_questao=
                                        questao_origem.tipo_questao,
                                    quantidade_alternativas=
                                        questao_origem.quantidade_alternativas,
                                    gabarito=
                                        questao_origem.gabarito,
                                    comentario=
                                        questao_origem.comentario
                                )

                                db.add(nova_questao)
                                db.flush()

                                # ---------------------------------
                                # 11. ALTERNATIVAS
                                # ---------------------------------

                                alternativas_origem = (
                                    db.query(models.Alternativa)
                                    .filter(
                                        models.Alternativa.questao_id
                                        == questao_origem.id
                                    )
                                    .all()
                                )

                                mapa_alternativas = {}

                                for alternativa_origem in alternativas_origem:

                                    nova_alternativa = models.Alternativa(
                                        questao_id=nova_questao.id,
                                        letra=alternativa_origem.letra,
                                        texto=alternativa_origem.texto
                                    )

                                    db.add(nova_alternativa)
                                    db.flush()

                                    mapa_alternativas[
                                        alternativa_origem.id
                                    ] = nova_alternativa.id

                                # ---------------------------------
                                # 12. COMENTÁRIOS
                                # ---------------------------------

                                comentarios_origem = (
                                    db.query(models.Comentario)
                                    .filter(
                                        models.Comentario.questao_id
                                        == questao_origem.id
                                    )
                                    .all()
                                )

                                for comentario_origem in comentarios_origem:

                                    nova_alternativa_id = None

                                    if comentario_origem.alternativa_id:
                                        nova_alternativa_id = (
                                            mapa_alternativas.get(
                                                comentario_origem.alternativa_id
                                            )
                                        )

                                    db.add(
                                        models.Comentario(
                                            questao_id=nova_questao.id,
                                            alternativa_id=
                                                nova_alternativa_id,
                                            texto=comentario_origem.texto
                                        )
                                    )

                # -------------------------------------------------
                # 13. QUESTÕES PRÁTICAS DO ASSUNTO
                # -------------------------------------------------

                questoes_praticas_origem = (
                    db.query(models.QuestaoPraticaAssunto)
                    .filter(
                        models.QuestaoPraticaAssunto.curso_assunto_proprio_id
                        == assunto_origem.id
                    )
                    .order_by(
                        models.QuestaoPraticaAssunto.id.asc()
                    )
                    .all()
                )

                for questao_pratica_origem in questoes_praticas_origem:

                    nova_questao_pratica = (
                        models.QuestaoPraticaAssunto(
                            curso_assunto_proprio_id=
                                novo_assunto.id,
                            tipo=
                                questao_pratica_origem.tipo,
                            enunciado=
                                questao_pratica_origem.enunciado,
                            gabarito=
                                questao_pratica_origem.gabarito,
                            comentario=
                                questao_pratica_origem.comentario,
                            ativo=
                                questao_pratica_origem.ativo
                        )
                    )

                    db.add(nova_questao_pratica)
                    db.flush()

                    alternativas_praticas_origem = (
                        db.query(models.QuestaoPraticaAlternativa)
                        .filter(
                            models.QuestaoPraticaAlternativa.questao_pratica_id
                            == questao_pratica_origem.id
                        )
                        .order_by(
                            models.QuestaoPraticaAlternativa.letra.asc()
                        )
                        .all()
                    )

                    for alternativa_pratica_origem in (
                        alternativas_praticas_origem
                    ):
                        db.add(
                            models.QuestaoPraticaAlternativa(
                                questao_pratica_id=
                                    nova_questao_pratica.id,
                                letra=
                                    alternativa_pratica_origem.letra,
                                texto=
                                    alternativa_pratica_origem.texto,
                                correta=
                                    alternativa_pratica_origem.correta
                            )
                        )

        db.commit()

        return {
            "ok": True,
            "curso_origem_id": curso_origem.id,
            "novo_curso_id": novo_curso.id,
            "novo_curso_nome": novo_curso.nome,
            "publicado": novo_curso.publicado
        }

    except Exception as err:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Erro ao duplicar curso: {str(err)}"
        )

@app.post(
    "/admin/disciplinas/{disciplina_id}/copiar",
    tags=["Admin"]
)
def copiar_disciplina_entre_cursos(
    disciplina_id: int,
    dados: schemas.CopiarDisciplinaRequest,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito ao administrador."
        )

    disciplina_origem = (
        db.query(models.CursoDisciplinaPropria)
        .filter(
            models.CursoDisciplinaPropria.id == disciplina_id
        )
        .first()
    )

    if not disciplina_origem:
        raise HTTPException(
            status_code=404,
            detail="Disciplina de origem não encontrada."
        )

    curso_destino = (
        db.query(models.Curso)
        .filter(
            models.Curso.id == dados.curso_destino_id
        )
        .first()
    )

    if not curso_destino:
        raise HTTPException(
            status_code=404,
            detail="Curso de destino não encontrado."
        )

    if disciplina_origem.curso_id == curso_destino.id:
        raise HTTPException(
            status_code=400,
            detail="O curso de destino deve ser diferente do curso de origem."
        )

    try:
        maior_ordem = (
            db.query(
                func.max(
                    models.CursoDisciplinaPropria.ordem
                )
            )
            .filter(
                models.CursoDisciplinaPropria.curso_id
                == curso_destino.id
            )
            .scalar()
        )

        proxima_ordem = (
            maior_ordem + 1
            if maior_ordem is not None
            else 1
        )

        nova_disciplina = models.CursoDisciplinaPropria(
            curso_id=curso_destino.id,
            nome=disciplina_origem.nome,
            ativo=disciplina_origem.ativo,
            ordem=proxima_ordem,
            disponivel_demonstracao=
                disciplina_origem.disponivel_demonstracao
        )

        db.add(nova_disciplina)
        db.flush()

        assuntos_origem = (
            db.query(models.CursoAssuntoProprio)
            .filter(
                models.CursoAssuntoProprio.curso_disciplina_propria_id
                == disciplina_origem.id
            )
            .order_by(
                models.CursoAssuntoProprio.ordem.asc(),
                models.CursoAssuntoProprio.id.asc()
            )
            .all()
        )

        for assunto_origem in assuntos_origem:

            novo_assunto = models.CursoAssuntoProprio(
                curso_disciplina_propria_id=
                    nova_disciplina.id,
                nome=assunto_origem.nome,
                descricao=assunto_origem.descricao,
                ativo=assunto_origem.ativo,
                ordem=assunto_origem.ordem
            )

            db.add(novo_assunto)
            db.flush()

            # -----------------------------------
            # PASTAS
            # -----------------------------------

            pastas_origem = (
                db.query(models.Pasta)
                .filter(
                    models.Pasta.curso_assunto_proprio_id
                    == assunto_origem.id
                )
                .all()
            )

            for pasta_origem in pastas_origem:

                nova_pasta = models.Pasta(
                    assunto_id=None,
                    curso_assunto_proprio_id=
                        novo_assunto.id,
                    tipo=pasta_origem.tipo,
                    nome=pasta_origem.nome
                )

                db.add(nova_pasta)
                db.flush()

                # -------------------------------
                # AULAS
                # -------------------------------

                aulas_origem = (
                    db.query(models.Aula)
                    .filter(
                        models.Aula.pasta_id
                        == pasta_origem.id
                    )
                    .order_by(
                        models.Aula.ordem.asc(),
                        models.Aula.id.asc()
                    )
                    .all()
                )

                for aula_origem in aulas_origem:

                    nova_aula = models.Aula(
                        pasta_id=nova_pasta.id,
                        titulo=aula_origem.titulo,
                        descricao=aula_origem.descricao,
                        ordem=aula_origem.ordem,
                        ativo=aula_origem.ativo
                    )

                    db.add(nova_aula)
                    db.flush()

                    # ---------------------------
                    # VÍDEOS
                    # ---------------------------

                    videos_origem = (
                        db.query(models.Video)
                        .filter(
                            models.Video.aula_id
                            == aula_origem.id
                        )
                        .order_by(
                            models.Video.ordem.asc(),
                            models.Video.id.asc()
                        )
                        .all()
                    )

                    for video_origem in videos_origem:
                        db.add(
                            models.Video(
                                aula_id=nova_aula.id,
                                titulo=video_origem.titulo,
                                url=video_origem.url,
                                duracao_segundos=
                                    video_origem.duracao_segundos,
                                transcricao=
                                    video_origem.transcricao,
                                ordem=video_origem.ordem,
                                ativo=video_origem.ativo
                            )
                        )

                    # ---------------------------
                    # MATERIAIS
                    # ---------------------------

                    materiais_origem = (
                        db.query(models.Material)
                        .filter(
                            models.Material.aula_id
                            == aula_origem.id
                        )
                        .order_by(
                            models.Material.ordem.asc(),
                            models.Material.id.asc()
                        )
                        .all()
                    )

                    for material_origem in materiais_origem:
                        db.add(
                            models.Material(
                                aula_id=nova_aula.id,
                                tipo=material_origem.tipo,
                                titulo=material_origem.titulo,
                                url=material_origem.url,
                                conteudo=material_origem.conteudo,
                                ordem=material_origem.ordem,
                                ativo=material_origem.ativo
                            )
                        )

                    # ---------------------------
                    # BATERIAS
                    # ---------------------------

                    baterias_origem = (
                        db.query(models.Bateria)
                        .filter(
                            models.Bateria.aula_id
                            == aula_origem.id
                        )
                        .order_by(
                            models.Bateria.ordem.asc(),
                            models.Bateria.id.asc()
                        )
                        .all()
                    )

                    for bateria_origem in baterias_origem:

                        nova_bateria = models.Bateria(
                            aula_id=nova_aula.id,
                            titulo=bateria_origem.titulo,
                            ordem=bateria_origem.ordem,
                            status=bateria_origem.status,
                            ativo=bateria_origem.ativo
                        )

                        db.add(nova_bateria)
                        db.flush()

                        # -----------------------
                        # QUESTÕES
                        # -----------------------

                        questoes_origem = (
                            db.query(models.Questao)
                            .filter(
                                models.Questao.bateria_id
                                == bateria_origem.id
                            )
                            .order_by(
                                models.Questao.ordem.asc(),
                                models.Questao.id.asc()
                            )
                            .all()
                        )

                        for questao_origem in questoes_origem:

                            nova_questao = models.Questao(
                                bateria_id=nova_bateria.id,
                                enunciado=
                                    questao_origem.enunciado,
                                tipo=
                                    questao_origem.tipo,
                                ordem=
                                    questao_origem.ordem,
                                ativo=
                                    questao_origem.ativo,
                                tipo_questao=
                                    questao_origem.tipo_questao,
                                quantidade_alternativas=
                                    questao_origem.quantidade_alternativas,
                                gabarito=
                                    questao_origem.gabarito,
                                comentario=
                                    questao_origem.comentario
                            )

                            db.add(nova_questao)
                            db.flush()

                            # -------------------
                            # ALTERNATIVAS
                            # -------------------

                            alternativas_origem = (
                                db.query(models.Alternativa)
                                .filter(
                                    models.Alternativa.questao_id
                                    == questao_origem.id
                                )
                                .all()
                            )

                            mapa_alternativas = {}

                            for alternativa_origem in alternativas_origem:

                                nova_alternativa = models.Alternativa(
                                    questao_id=nova_questao.id,
                                    letra=alternativa_origem.letra,
                                    texto=alternativa_origem.texto
                                )

                                db.add(nova_alternativa)
                                db.flush()

                                mapa_alternativas[
                                    alternativa_origem.id
                                ] = nova_alternativa.id

                            # -------------------
                            # COMENTÁRIOS
                            # -------------------

                            comentarios_origem = (
                                db.query(models.Comentario)
                                .filter(
                                    models.Comentario.questao_id
                                    == questao_origem.id
                                )
                                .all()
                            )

                            for comentario_origem in comentarios_origem:

                                nova_alternativa_id = None

                                if comentario_origem.alternativa_id:
                                    nova_alternativa_id = (
                                        mapa_alternativas.get(
                                            comentario_origem.alternativa_id
                                        )
                                    )

                                db.add(
                                    models.Comentario(
                                        questao_id=nova_questao.id,
                                        alternativa_id=
                                            nova_alternativa_id,
                                        texto=
                                            comentario_origem.texto
                                    )
                                )

            # -----------------------------------
            # QUESTÕES PRÁTICAS DO ASSUNTO
            # -----------------------------------

            questoes_praticas_origem = (
                db.query(models.QuestaoPraticaAssunto)
                .filter(
                    models.QuestaoPraticaAssunto.curso_assunto_proprio_id
                    == assunto_origem.id
                )
                .order_by(
                    models.QuestaoPraticaAssunto.id.asc()
                )
                .all()
            )

            for questao_pratica_origem in questoes_praticas_origem:

                nova_questao_pratica = (
                    models.QuestaoPraticaAssunto(
                        curso_assunto_proprio_id=
                            novo_assunto.id,
                        tipo=
                            questao_pratica_origem.tipo,
                        enunciado=
                            questao_pratica_origem.enunciado,
                        gabarito=
                            questao_pratica_origem.gabarito,
                        comentario=
                            questao_pratica_origem.comentario,
                        ativo=
                            questao_pratica_origem.ativo
                    )
                )

                db.add(nova_questao_pratica)
                db.flush()

                alternativas_praticas_origem = (
                    db.query(
                        models.QuestaoPraticaAlternativa
                    )
                    .filter(
                        models.QuestaoPraticaAlternativa.questao_pratica_id
                        == questao_pratica_origem.id
                    )
                    .order_by(
                        models.QuestaoPraticaAlternativa.letra.asc()
                    )
                    .all()
                )

                for alternativa_origem in (
                    alternativas_praticas_origem
                ):
                    db.add(
                        models.QuestaoPraticaAlternativa(
                            questao_pratica_id=
                                nova_questao_pratica.id,
                            letra=
                                alternativa_origem.letra,
                            texto=
                                alternativa_origem.texto,
                            correta=
                                alternativa_origem.correta
                        )
                    )

        db.commit()

        return {
            "ok": True,
            "disciplina_origem_id":
                disciplina_origem.id,
            "nova_disciplina_id":
                nova_disciplina.id,
            "nova_disciplina_nome":
                nova_disciplina.nome,
            "curso_destino_id":
                curso_destino.id,
            "curso_destino_nome":
                curso_destino.nome
        }

    except Exception as err:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=
                f"Erro ao copiar disciplina: {str(err)}"
        )

def gerar_codigo_cupom_unico(db: Session) -> str:
    while True:
        letras = "".join(
            random.choices(
                string.ascii_uppercase,
                k=2
            )
        )

        numeros = "".join(
            random.choices(
                string.digits,
                k=3
            )
        )

        codigo = letras + numeros

        existe = (
            db.query(models.CupomDesconto)
            .filter(
                models.CupomDesconto.codigo == codigo
            )
            .first()
        )

        if not existe:
            return codigo

@app.post(
    "/admin/assuntos/{assunto_id}/copiar",
    tags=["Admin"]
)
def copiar_assunto_entre_disciplinas(
    assunto_id: int,
    dados: schemas.CopiarAssuntoRequest,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito ao administrador."
        )

    assunto_origem = (
        db.query(models.CursoAssuntoProprio)
        .filter(
            models.CursoAssuntoProprio.id == assunto_id
        )
        .first()
    )

    if not assunto_origem:
        raise HTTPException(
            status_code=404,
            detail="Assunto de origem não encontrado."
        )

    disciplina_destino = (
        db.query(models.CursoDisciplinaPropria)
        .filter(
            models.CursoDisciplinaPropria.id
            == dados.disciplina_destino_id
        )
        .first()
    )

    if not disciplina_destino:
        raise HTTPException(
            status_code=404,
            detail="Disciplina de destino não encontrada."
        )

    if (
        assunto_origem.curso_disciplina_propria_id
        == disciplina_destino.id
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "A disciplina de destino deve ser diferente "
                "da disciplina de origem."
            )
        )

    try:
        maior_ordem = (
            db.query(
                func.max(
                    models.CursoAssuntoProprio.ordem
                )
            )
            .filter(
                models.CursoAssuntoProprio.curso_disciplina_propria_id
                == disciplina_destino.id
            )
            .scalar()
        )

        proxima_ordem = (
            maior_ordem + 1
            if maior_ordem is not None
            else 1
        )

        novo_assunto = models.CursoAssuntoProprio(
            curso_disciplina_propria_id=
                disciplina_destino.id,
            nome=assunto_origem.nome,
            descricao=assunto_origem.descricao,
            ativo=assunto_origem.ativo,
            ordem=proxima_ordem
        )

        db.add(novo_assunto)
        db.flush()

        # -----------------------------------
        # PASTAS
        # -----------------------------------

        pastas_origem = (
            db.query(models.Pasta)
            .filter(
                models.Pasta.curso_assunto_proprio_id
                == assunto_origem.id
            )
            .all()
        )

        for pasta_origem in pastas_origem:

            nova_pasta = models.Pasta(
                assunto_id=None,
                curso_assunto_proprio_id=
                    novo_assunto.id,
                tipo=pasta_origem.tipo,
                nome=pasta_origem.nome
            )

            db.add(nova_pasta)
            db.flush()

            # -------------------------------
            # AULAS
            # -------------------------------

            aulas_origem = (
                db.query(models.Aula)
                .filter(
                    models.Aula.pasta_id
                    == pasta_origem.id
                )
                .order_by(
                    models.Aula.ordem.asc(),
                    models.Aula.id.asc()
                )
                .all()
            )

            for aula_origem in aulas_origem:

                nova_aula = models.Aula(
                    pasta_id=nova_pasta.id,
                    titulo=aula_origem.titulo,
                    descricao=aula_origem.descricao,
                    ordem=aula_origem.ordem,
                    ativo=aula_origem.ativo
                )

                db.add(nova_aula)
                db.flush()

                # ---------------------------
                # VÍDEOS
                # ---------------------------

                videos_origem = (
                    db.query(models.Video)
                    .filter(
                        models.Video.aula_id
                        == aula_origem.id
                    )
                    .order_by(
                        models.Video.ordem.asc(),
                        models.Video.id.asc()
                    )
                    .all()
                )

                for video_origem in videos_origem:
                    db.add(
                        models.Video(
                            aula_id=nova_aula.id,
                            titulo=video_origem.titulo,
                            url=video_origem.url,
                            duracao_segundos=
                                video_origem.duracao_segundos,
                            transcricao=
                                video_origem.transcricao,
                            ordem=video_origem.ordem,
                            ativo=video_origem.ativo
                        )
                    )

                # ---------------------------
                # MATERIAIS
                # ---------------------------

                materiais_origem = (
                    db.query(models.Material)
                    .filter(
                        models.Material.aula_id
                        == aula_origem.id
                    )
                    .order_by(
                        models.Material.ordem.asc(),
                        models.Material.id.asc()
                    )
                    .all()
                )

                for material_origem in materiais_origem:
                    db.add(
                        models.Material(
                            aula_id=nova_aula.id,
                            tipo=material_origem.tipo,
                            titulo=material_origem.titulo,
                            url=material_origem.url,
                            conteudo=material_origem.conteudo,
                            ordem=material_origem.ordem,
                            ativo=material_origem.ativo
                        )
                    )

                # ---------------------------
                # BATERIAS
                # ---------------------------

                baterias_origem = (
                    db.query(models.Bateria)
                    .filter(
                        models.Bateria.aula_id
                        == aula_origem.id
                    )
                    .order_by(
                        models.Bateria.ordem.asc(),
                        models.Bateria.id.asc()
                    )
                    .all()
                )

                for bateria_origem in baterias_origem:

                    nova_bateria = models.Bateria(
                        aula_id=nova_aula.id,
                        titulo=bateria_origem.titulo,
                        ordem=bateria_origem.ordem,
                        status=bateria_origem.status,
                        ativo=bateria_origem.ativo
                    )

                    db.add(nova_bateria)
                    db.flush()

                    # -----------------------
                    # QUESTÕES
                    # -----------------------

                    questoes_origem = (
                        db.query(models.Questao)
                        .filter(
                            models.Questao.bateria_id
                            == bateria_origem.id
                        )
                        .order_by(
                            models.Questao.ordem.asc(),
                            models.Questao.id.asc()
                        )
                        .all()
                    )

                    for questao_origem in questoes_origem:

                        nova_questao = models.Questao(
                            bateria_id=nova_bateria.id,
                            enunciado=questao_origem.enunciado,
                            tipo=questao_origem.tipo,
                            ordem=questao_origem.ordem,
                            ativo=questao_origem.ativo,
                            tipo_questao=
                                questao_origem.tipo_questao,
                            quantidade_alternativas=
                                questao_origem.quantidade_alternativas,
                            gabarito=questao_origem.gabarito,
                            comentario=questao_origem.comentario
                        )

                        db.add(nova_questao)
                        db.flush()

                        alternativas_origem = (
                            db.query(models.Alternativa)
                            .filter(
                                models.Alternativa.questao_id
                                == questao_origem.id
                            )
                            .all()
                        )

                        mapa_alternativas = {}

                        for alternativa_origem in alternativas_origem:

                            nova_alternativa = models.Alternativa(
                                questao_id=nova_questao.id,
                                letra=alternativa_origem.letra,
                                texto=alternativa_origem.texto
                            )

                            db.add(nova_alternativa)
                            db.flush()

                            mapa_alternativas[
                                alternativa_origem.id
                            ] = nova_alternativa.id

                        comentarios_origem = (
                            db.query(models.Comentario)
                            .filter(
                                models.Comentario.questao_id
                                == questao_origem.id
                            )
                            .all()
                        )

                        for comentario_origem in comentarios_origem:

                            nova_alternativa_id = None

                            if comentario_origem.alternativa_id:
                                nova_alternativa_id = (
                                    mapa_alternativas.get(
                                        comentario_origem.alternativa_id
                                    )
                                )

                            db.add(
                                models.Comentario(
                                    questao_id=nova_questao.id,
                                    alternativa_id=
                                        nova_alternativa_id,
                                    texto=
                                        comentario_origem.texto
                                )
                            )

        # -----------------------------------
        # QUESTÕES PRÁTICAS DO ASSUNTO
        # -----------------------------------

        questoes_praticas_origem = (
            db.query(models.QuestaoPraticaAssunto)
            .filter(
                models.QuestaoPraticaAssunto.curso_assunto_proprio_id
                == assunto_origem.id
            )
            .order_by(
                models.QuestaoPraticaAssunto.id.asc()
            )
            .all()
        )

        for questao_pratica_origem in questoes_praticas_origem:

            nova_questao_pratica = (
                models.QuestaoPraticaAssunto(
                    curso_assunto_proprio_id=
                        novo_assunto.id,
                    tipo=questao_pratica_origem.tipo,
                    enunciado=
                        questao_pratica_origem.enunciado,
                    gabarito=
                        questao_pratica_origem.gabarito,
                    comentario=
                        questao_pratica_origem.comentario,
                    ativo=
                        questao_pratica_origem.ativo
                )
            )

            db.add(nova_questao_pratica)
            db.flush()

            alternativas_praticas_origem = (
                db.query(
                    models.QuestaoPraticaAlternativa
                )
                .filter(
                    models.QuestaoPraticaAlternativa.questao_pratica_id
                    == questao_pratica_origem.id
                )
                .order_by(
                    models.QuestaoPraticaAlternativa.letra.asc()
                )
                .all()
            )

            for alternativa_origem in (
                alternativas_praticas_origem
            ):
                db.add(
                    models.QuestaoPraticaAlternativa(
                        questao_pratica_id=
                            nova_questao_pratica.id,
                        letra=
                            alternativa_origem.letra,
                        texto=
                            alternativa_origem.texto,
                        correta=
                            alternativa_origem.correta
                    )
                )

        db.commit()

        return {
            "ok": True,
            "assunto_origem_id":
                assunto_origem.id,
            "novo_assunto_id":
                novo_assunto.id,
            "novo_assunto_nome":
                novo_assunto.nome,
            "disciplina_destino_id":
                disciplina_destino.id,
            "disciplina_destino_nome":
                disciplina_destino.nome,
            "curso_destino_id":
                disciplina_destino.curso_id
        }

    except Exception as err:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=
                f"Erro ao copiar assunto: {str(err)}"
        )

@app.post(
    "/admin/cupons-desconto/gerar",
    response_model=list[schemas.CupomDescontoResponse],
    tags=["Admin"]
)
def gerar_cupons_desconto(
    dados: schemas.CupomDescontoGerarRequest,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito ao administrador."
        )

    if dados.quantidade < 1 or dados.quantidade > 100:
        raise HTTPException(
            status_code=400,
            detail="A quantidade deve estar entre 1 e 100."
        )

    novos_cupons = []

    codigos_gerados_nesta_execucao = set()

    for _ in range(dados.quantidade):

        while True:
            codigo = gerar_codigo_cupom_unico(db)

            if codigo not in codigos_gerados_nesta_execucao:
                codigos_gerados_nesta_execucao.add(
                    codigo
                )
                break

        cupom = models.CupomDesconto(
            codigo=codigo,
            vendedor_id=None,
            percentual_desconto=12,
            ativo=True
        )

        db.add(cupom)

        novos_cupons.append(cupom)

    db.commit()

    for cupom in novos_cupons:
        db.refresh(cupom)

    return novos_cupons


@app.get(
    "/admin/cupons-desconto",
    response_model=list[schemas.CupomDescontoResponse],
    tags=["Admin"]
)
def listar_cupons_desconto(
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito ao administrador."
        )

    return (
        db.query(models.CupomDesconto)
        .order_by(
            models.CupomDesconto.id.desc()
        )
        .all()
    )

@app.put(
    "/admin/cupons-desconto/{cupom_id}/vendedor",
    response_model=schemas.CupomDescontoResponse,
    tags=["Admin"]
)
def vincular_vendedor_cupom(
    cupom_id: int,
    dados: schemas.CupomDescontoVincularVendedorRequest,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito ao administrador."
        )

    cupom = (
        db.query(models.CupomDesconto)
        .filter(
            models.CupomDesconto.id == cupom_id
        )
        .first()
    )

    if not cupom:
        raise HTTPException(
            status_code=404,
            detail="Cupom não encontrado."
        )

    if dados.vendedor_id is not None:
        vendedor = (
            db.query(models.Vendedor)
            .filter(
                models.Vendedor.id
                == dados.vendedor_id
            )
            .first()
        )

        if not vendedor:
            raise HTTPException(
                status_code=404,
                detail="Parceiro/vendedor não encontrado."
            )

        if not vendedor.ativo:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Não é possível vincular "
                    "um parceiro/vendedor inativo."
                )
            )

    cupom.vendedor_id = dados.vendedor_id

    cupom.atualizado_em = datetime.utcnow()

    db.commit()
    db.refresh(cupom)

    return cupom

@app.put(
    "/admin/cupons-desconto/{cupom_id}/status",
    response_model=schemas.CupomDescontoResponse,
    tags=["Admin"]
)
def alterar_status_cupom(
    cupom_id: int,
    ativo: bool,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito ao administrador."
        )

    cupom = (
        db.query(models.CupomDesconto)
        .filter(
            models.CupomDesconto.id == cupom_id
        )
        .first()
    )

    if not cupom:
        raise HTTPException(
            status_code=404,
            detail="Cupom não encontrado."
        )

    cupom.ativo = ativo
    cupom.atualizado_em = datetime.utcnow()

    db.commit()
    db.refresh(cupom)

    return cupom

@app.post(
    "/admin/vendedores",
    response_model=schemas.VendedorResponse,
    tags=["Admin"]
)
def criar_vendedor(
    dados: schemas.VendedorCreate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito ao administrador."
        )

    nome = dados.nome.strip()

    email = (
        dados.email.strip().lower()
        if dados.email
        else None
    )

    telefone = (
        dados.telefone.strip()
        if dados.telefone
        else None
    )

    cpf_cnpj = (
        dados.cpf_cnpj.strip()
        if dados.cpf_cnpj
        else None
    )

    estado_uf = (
        dados.estado_uf.strip().upper()
        if dados.estado_uf
        else None
    )

    cidade = (
        dados.cidade.strip()
        if dados.cidade
        else None
    )

    # Verifica se já existe conta com o mesmo e-mail.
    if email:
        usuario_email_existente = (
            db.query(models.Usuario)
            .filter(
                models.Usuario.email == email
            )
            .first()
        )

        if usuario_email_existente:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Já existe usuário cadastrado "
                    "com esse e-mail."
                )
            )

    # Para criar a conta de acesso, precisamos de CPF.
    # Se for informado CNPJ, não poderá ser usado como CPF do usuário.
    cpf_usuario = re.sub(
        r"\D",
        "",
        cpf_cnpj or ""
    )

    if len(cpf_usuario) != 11:
        raise HTTPException(
            status_code=400,
            detail=(
                "Para criar a conta de acesso do vendedor, "
                "informe um CPF válido."
            )
        )

    usuario_cpf_existente = (
        db.query(models.Usuario)
        .filter(
            models.Usuario.cpf == cpf_usuario
        )
        .first()
    )

    if usuario_cpf_existente:
        raise HTTPException(
            status_code=409,
            detail=(
                "Já existe usuário cadastrado "
                "com esse CPF."
            )
        )

    try:
        # 1. Cria a conta de usuário do vendedor.
        novo_usuario = models.Usuario(
            nome=nome,
            email=email,
            cpf=cpf_usuario,
            telefone=telefone,
            data_nascimento=dados.data_nascimento,
            senha_hash=hash_senha(
                dados.senha
            ),
            ativo=True,
            is_admin=False,
            perfil_inicial="VENDEDOR"
        )

        db.add(novo_usuario)

        # Envia o INSERT sem confirmar a transação ainda.
        # Isso permite obter novo_usuario.id.
        db.flush()

        # 2. Cria o cadastro de vendedor já vinculado à conta.
        vendedor = models.Vendedor(
            nome=nome,
            email=email,
            telefone=telefone,
            cpf_cnpj=cpf_cnpj,
            data_nascimento=dados.data_nascimento,
            estado_uf=estado_uf,
            cidade=cidade,
            ativo=True,
            usuario_id=novo_usuario.id
        )

        db.add(vendedor)

        # Confirma Usuario + Vendedor juntos.
        db.commit()

        db.refresh(vendedor)

        return vendedor

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=400,
            detail=(
                "Não foi possível cadastrar o vendedor. "
                "Verifique se o e-mail ou CPF já estão cadastrados."
            )
        )

    except Exception:
        db.rollback()
        raise

@app.get(
    "/admin/vendedores",
    response_model=list[schemas.VendedorResponse],
    tags=["Admin"]
)
def listar_vendedores(
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito ao administrador."
        )

    return (
        db.query(models.Vendedor)
        .order_by(
            models.Vendedor.ativo.desc(),
            models.Vendedor.nome.asc()
        )
        .all()
    )

@app.put(
    "/admin/vendedores/{vendedor_id}",
    response_model=schemas.VendedorResponse,
    tags=["Admin"]
)
def atualizar_vendedor(
    vendedor_id: int,
    dados: schemas.VendedorUpdate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(
        get_usuario_atual
    )
):
    if not usuario.is_admin:
        raise HTTPException(
            status_code=403,
            detail=(
                "Acesso restrito ao administrador."
            )
        )

    vendedor = (
        db.query(models.Vendedor)
        .filter(
            models.Vendedor.id
            == vendedor_id
        )
        .first()
    )

    if not vendedor:
        raise HTTPException(
            status_code=404,
            detail="Vendedor não encontrado."
        )

    campos = dados.model_dump(
        exclude_unset=True
    )

    if "ativo" in campos:
        novo_status = campos["ativo"]

        if novo_status is False:
            vendedor.descredenciado_em = (
                datetime.utcnow()
            )

        elif novo_status is True:
            vendedor.descredenciado_em = None

    for campo, valor in campos.items():
        if isinstance(valor, str):
            valor = valor.strip()

        if campo == "email" and valor:
            valor = valor.lower()

        if campo == "estado_uf" and valor:
            valor = valor.upper()

        setattr(
            vendedor,
            campo,
            valor
        )

    vendedor.atualizado_em = (
        datetime.utcnow()
    )

    db.commit()
    db.refresh(vendedor)

    return vendedor

@app.put(
    "/admin/vendedores/{vendedor_id}/usuario",
    tags=["Admin"]
)
def vincular_usuario_vendedor(
    vendedor_id: int,
    dados: schemas.VendedorVincularUsuarioRequest,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(
        get_usuario_atual
    )
):
    if not usuario.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito ao administrador."
        )

    vendedor = (
        db.query(models.Vendedor)
        .filter(
            models.Vendedor.id == vendedor_id
        )
        .first()
    )

    if not vendedor:
        raise HTTPException(
            status_code=404,
            detail="Parceiro/vendedor não encontrado."
        )

    # REMOVER VÍNCULO
    if dados.usuario_id is None:
        vendedor.usuario_id = None
        vendedor.atualizado_em = datetime.utcnow()

        db.commit()
        db.refresh(vendedor)

        return {
            "ok": True,
            "mensagem": (
                "Vínculo do usuário removido "
                "do parceiro/vendedor com sucesso."
            ),
            "vendedor_id": vendedor.id,
            "usuario_id": None
        }

    # LOCALIZAR NOVO USUÁRIO
    usuario_vinculado = (
        db.query(models.Usuario)
        .filter(
            models.Usuario.id == dados.usuario_id
        )
        .first()
    )

    if not usuario_vinculado:
        raise HTTPException(
            status_code=404,
            detail="Usuário não encontrado."
        )

    # GARANTIR QUE A CONTA NÃO ESTEJA EM OUTRO VENDEDOR
    outro_vendedor = (
        db.query(models.Vendedor)
        .filter(
            models.Vendedor.usuario_id == dados.usuario_id,
            models.Vendedor.id != vendedor_id
        )
        .first()
    )

    if outro_vendedor:
        raise HTTPException(
            status_code=400,
            detail=(
                "Este usuário já está vinculado "
                "a outro parceiro/vendedor."
            )
        )

    # VINCULAR OU TROCAR
    vendedor.usuario_id = usuario_vinculado.id
    vendedor.atualizado_em = datetime.utcnow()

    db.commit()
    db.refresh(vendedor)

    return {
        "ok": True,
        "mensagem": (
            "Usuário vinculado ao "
            "parceiro/vendedor com sucesso."
        ),
        "vendedor_id": vendedor.id,
        "usuario_id": usuario_vinculado.id,
        "usuario_nome": usuario_vinculado.nome
    }

@app.post(
    "/admin/qr-codes",
    response_model=list[schemas.QRCodeResponse],
    tags=["Admin"]
)
def criar_qr_codes(
    dados: schemas.QRCodeCreate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Acesso restrito ao administrador.")

    if dados.quantidade < 1 or dados.quantidade > 500:
        raise HTTPException(
            status_code=400,
            detail="A quantidade deve estar entre 1 e 500."
        )

    novos_qr_codes = []

    for _ in range(dados.quantidade):

        while True:
            codigo = secrets.token_urlsafe(12)

            existe = (
                db.query(models.QRCode)
                .filter(models.QRCode.codigo == codigo)
                .first()
            )

            if not existe:
                break

        qr_code = models.QRCode(
            codigo=codigo,
            vendedor_id=None,
            ativo=True
        )

        db.add(qr_code)
        novos_qr_codes.append(qr_code)

    db.commit()

    for qr_code in novos_qr_codes:
        db.refresh(qr_code)

    return novos_qr_codes

@app.get(
    "/admin/qr-codes",
    response_model=list[schemas.QRCodeResponse],
    tags=["Admin"]
)
def listar_qr_codes(
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Acesso restrito ao administrador.")

    return (
        db.query(models.QRCode)
        .order_by(models.QRCode.id.desc())
        .all()
    )

@app.put(
    "/admin/qr-codes/{qr_code_id}/vendedor",
    response_model=schemas.QRCodeResponse,
    tags=["Admin"]
)
def vincular_vendedor_qr_code(
    qr_code_id: int,
    dados: schemas.QRCodeVincularVendedorRequest,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(get_usuario_atual)
):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Acesso restrito ao administrador.")

    qr_code = (
        db.query(models.QRCode)
        .filter(models.QRCode.id == qr_code_id)
        .first()
    )

    if not qr_code:
        raise HTTPException(status_code=404, detail="QR Code não encontrado.")

    if dados.vendedor_id is not None:
        vendedor = (
            db.query(models.Vendedor)
            .filter(models.Vendedor.id == dados.vendedor_id)
            .first()
        )

        if not vendedor:
            raise HTTPException(
                status_code=404,
                detail="Vendedor não encontrado."
            )

        if not vendedor.ativo:
            raise HTTPException(
                status_code=400,
                detail="Não é possível vincular um vendedor inativo."
            )

    qr_code.vendedor_id = dados.vendedor_id
    qr_code.atualizado_em = datetime.utcnow()

    db.commit()
    db.refresh(qr_code)

    return qr_code

@app.post(
    "/cupons-desconto/validar",
    response_model=schemas.ValidarCupomResponse
)
def validar_cupom_desconto(
    dados: schemas.ValidarCupomRequest,
    db: Session = Depends(get_db)
):
    codigo = dados.codigo_cupom.strip().upper()

    cupom = (
        db.query(models.CupomDesconto)
        .filter(
            models.CupomDesconto.codigo == codigo,
            models.CupomDesconto.ativo == True
        )
        .first()
    )

    if not cupom:
        raise HTTPException(
            status_code=404,
            detail="Cupom de desconto inválido ou inativo."
        )

    if cupom.vendedor_id is None:
        raise HTTPException(
            status_code=400,
            detail="Este cupom ainda não está vinculado a um parceiro/vendedor."
        )

    vendedor = (
        db.query(models.Vendedor)
        .filter(
            models.Vendedor.id == cupom.vendedor_id,
            models.Vendedor.ativo == True
        )
        .first()
    )

    if not vendedor:
        raise HTTPException(
            status_code=400,
            detail="O parceiro/vendedor vinculado a este cupom está inativo."
        )

    return schemas.ValidarCupomResponse(
        valido=True,
        codigo_cupom=cupom.codigo,
        percentual_desconto=cupom.percentual_desconto,
        vendedor_id=cupom.vendedor_id
    )

@app.get("/")
def raiz():
    return {
        "status": "ok",
        "mensagem": "Backend da Plataforma Quality Estudos em funcionamento."
    }

@app.get(
    "/me/vendedor",
    tags=["Parceiro/Vendedor"]
)
def obter_vendedor_logado(
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(
        get_usuario_atual
    )
):
    vendedor = (
        db.query(models.Vendedor)
        .filter(
            models.Vendedor.usuario_id
            == usuario.id
        )
        .first()
    )

    if not vendedor:
        raise HTTPException(
            status_code=404,
            detail=(
                "Este usuário não está vinculado "
                "a um parceiro/vendedor."
            )
        )

    return {
        "id": vendedor.id,
        "nome": vendedor.nome,
        "email": vendedor.email,
        "ativo": vendedor.ativo
    }

@app.get(
    "/me/vendedor/vendas",
    tags=["Parceiro/Vendedor"]
)
def obter_vendas_vendedor_logado(
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(
        get_usuario_atual
    )
):
    vendedor = (
        db.query(models.Vendedor)
        .filter(
            models.Vendedor.usuario_id
            == usuario.id,
            models.Vendedor.ativo
            == True
        )
        .first()
    )

    if not vendedor:
        raise HTTPException(
            status_code=403,
            detail=(
                "Usuário não autorizado "
                "como parceiro/vendedor."
            )
        )

    pagamentos = (
        db.query(models.Pagamento)
        .filter(
            models.Pagamento.vendedor_id
            == vendedor.id,
            models.Pagamento.status
            == "APPROVED"
        )
        .order_by(
            models.Pagamento.criado_em.desc()
        )
        .all()
    )

    # Busca todos os cupons vinculados
    # ao vendedor, mesmo sem vendas.
    cupons_vendedor = (
        db.query(models.CupomDesconto)
        .filter(
            models.CupomDesconto.vendedor_id
            == vendedor.id
        )
        .order_by(
            models.CupomDesconto.codigo.asc()
        )
        .all()
    )

    # Inicializa todos os cupons do vendedor
    # com seus indicadores zerados.
    cupons = {}

    for cupom in cupons_vendedor:
        codigo = (
            cupom.codigo
            or ""
        ).strip().upper()

        if not codigo:
            continue

        cupons[codigo] = {
            "codigo_cupom":
                codigo,

            "total_vendas":
                0,

            "vendas_efetivas":
                0,

            "vendas_a_confirmar":
                0,

            "valor_vendas_efetivas_cents":
                0,

            "valor_vendas_a_confirmar_cents":
                0,

            # Cursos vendidos com este cupom,
            # considerando todas as vendas.
            "cursos_total":
                {},

            # Cursos das vendas já confirmadas.
            "cursos_efetivos":
                {},

            # Cursos das vendas ainda
            # dentro do prazo de confirmação.
            "cursos_a_confirmar":
                {},

            "ativo":
                cupom.ativo
        }

    agora = datetime.utcnow()

    vendas_efetivas = []
    vendas_a_confirmar = []

    valor_vendas_efetivas_cents = 0
    valor_vendas_a_confirmar_cents = 0


    # Função auxiliar para agrupar
    # as vendas por curso.
    def acumular_curso(
        destino,
        curso_id,
        nome_curso,
        valor_cents
    ):
        # A chave considera o curso e o valor
        # efetivamente pago.
        #
        # Assim, caso o mesmo curso tenha sido
        # vendido pelo mesmo cupom por valores
        # diferentes, as vendas não serão
        # misturadas em uma única linha.
        chave = (
            f"{curso_id}_"
            f"{valor_cents}"
        )

        if chave not in destino:
            destino[chave] = {
                "curso_id":
                    curso_id,

                "nome_curso":
                    nome_curso,

                "valor_cents":
                    valor_cents,

                "quantidade":
                    0
            }

        destino[chave][
            "quantidade"
        ] += 1


    for pagamento in pagamentos:
        codigo_cupom = (
            pagamento.codigo_cupom
            or ""
        ).strip().upper()

        # Venda de vendedor só é contabilizada
        # quando possui cupom válido vinculado a ele.
        if not codigo_cupom:
            continue

        if codigo_cupom not in cupons:
            continue

        data_referencia = (
            pagamento.aprovado_em
            or pagamento.criado_em
        )

        limite = (
            data_referencia
            + timedelta(days=7)
        )

        # Este é o valor efetivamente pago
        # pelo comprador, já considerando
        # eventual desconto aplicado.
        valor_cents = (
            pagamento.valor_cents
            or 0
        )

        curso_id = (
            pagamento.curso_id
        )

        nome_curso = (
            pagamento.curso.nome
            if pagamento.curso
            else "Curso não identificado"
        )

        item = {
            "pagamento_id":
                pagamento.id,

            "codigo_cupom":
                codigo_cupom,

            "curso_id":
                curso_id,

            "nome_curso":
                nome_curso,

            "valor_cents":
                valor_cents,

            "data_pagamento":
                data_referencia
        }


        # -------------------------------------------------
        # TOTAL DE VENDAS
        # -------------------------------------------------

        cupons[codigo_cupom][
            "total_vendas"
        ] += 1

        acumular_curso(
            cupons[codigo_cupom][
                "cursos_total"
            ],
            curso_id,
            nome_curso,
            valor_cents
        )


        # -------------------------------------------------
        # VENDAS CONFIRMADAS
        # -------------------------------------------------

        if agora >= limite:
            vendas_efetivas.append(
                item
            )

            valor_vendas_efetivas_cents += (
                valor_cents
            )

            cupons[codigo_cupom][
                "vendas_efetivas"
            ] += 1

            cupons[codigo_cupom][
                "valor_vendas_efetivas_cents"
            ] += valor_cents

            acumular_curso(
                cupons[codigo_cupom][
                    "cursos_efetivos"
                ],
                curso_id,
                nome_curso,
                valor_cents
            )


        # -------------------------------------------------
        # VENDAS A CONFIRMAR
        # -------------------------------------------------

        else:
            vendas_a_confirmar.append(
                item
            )

            valor_vendas_a_confirmar_cents += (
                valor_cents
            )

            cupons[codigo_cupom][
                "vendas_a_confirmar"
            ] += 1

            cupons[codigo_cupom][
                "valor_vendas_a_confirmar_cents"
            ] += valor_cents

            acumular_curso(
                cupons[codigo_cupom][
                    "cursos_a_confirmar"
                ],
                curso_id,
                nome_curso,
                valor_cents
            )


    # Converte os dicionários usados
    # para agrupamento em listas,
    # facilitando o consumo pelo frontend.
    for dados_cupom in cupons.values():

        dados_cupom[
            "cursos_total"
        ] = list(
            dados_cupom[
                "cursos_total"
            ].values()
        )

        dados_cupom[
            "cursos_efetivos"
        ] = list(
            dados_cupom[
                "cursos_efetivos"
            ].values()
        )

        dados_cupom[
            "cursos_a_confirmar"
        ] = list(
            dados_cupom[
                "cursos_a_confirmar"
            ].values()
        )


    return {
        "vendedor": {
            "id":
                vendedor.id,

            "nome":
                vendedor.nome
        },

        "total_vendas":
            (
                len(vendas_efetivas)
                + len(vendas_a_confirmar)
            ),

        "total_vendas_efetivas":
            len(vendas_efetivas),

        "total_vendas_a_confirmar":
            len(vendas_a_confirmar),

        "valor_vendas_efetivas_cents":
            valor_vendas_efetivas_cents,

        "valor_vendas_a_confirmar_cents":
            valor_vendas_a_confirmar_cents,

        "vendas_efetivas":
            vendas_efetivas,

        "vendas_a_confirmar":
            vendas_a_confirmar,

        "cupons":
            list(cupons.values())
    }
    
@app.post(
    "/admin/usuarios/{usuario_id}/tornar-vendedor",
    response_model=schemas.VendedorResponse,
    tags=["Admin"]
)
def tornar_usuario_vendedor(
    usuario_id: int,
    dados: schemas.VendedorExistenteCreate,
    db: Session = Depends(get_db),
    admin: models.Usuario = Depends(
        get_usuario_atual
    )
):
    if not admin.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito ao administrador."
        )

    usuario_existente = (
        db.query(models.Usuario)
        .filter(
            models.Usuario.id == usuario_id
        )
        .first()
    )

    if not usuario_existente:
        raise HTTPException(
            status_code=404,
            detail="Usuário não encontrado."
        )

    vendedor_existente = (
        db.query(models.Vendedor)
        .filter(
            models.Vendedor.usuario_id
            == usuario_id
        )
        .first()
    )

    if vendedor_existente:
        raise HTTPException(
            status_code=409,
            detail=(
                "Este usuário já possui "
                "perfil de vendedor."
            )
        )

    cpf_cnpj = (
        dados.cpf_cnpj.strip()
        if dados.cpf_cnpj
        else usuario_existente.cpf
    )

    telefone = (
        dados.telefone.strip()
        if dados.telefone
        else usuario_existente.telefone
    )

    data_nascimento = (
        dados.data_nascimento
        if dados.data_nascimento
        else usuario_existente.data_nascimento
    )

    vendedor = models.Vendedor(
        nome=usuario_existente.nome,
        email=usuario_existente.email,
        telefone=telefone,
        cpf_cnpj=cpf_cnpj,
        data_nascimento=data_nascimento,
        estado_uf=(
            dados.estado_uf.strip().upper()
            if dados.estado_uf
            else None
        ),
        cidade=(
            dados.cidade.strip()
            if dados.cidade
            else None
        ),
        ativo=True,
        usuario_id=usuario_existente.id,
        descredenciado_em=None
    )

    db.add(vendedor)

    try:
        db.commit()
        db.refresh(vendedor)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=400,
            detail=(
                "Não foi possível conceder "
                "o perfil de vendedor."
            )
        )

    return vendedor

@app.get(
    "/admin/usuarios/perfis",
    tags=["Admin"]
)
def listar_usuarios_com_perfis(
    q: str = Query(default=""),
    db: Session = Depends(get_db),
    admin: models.Usuario = Depends(
        get_usuario_atual
    )
):
    if not admin.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito ao administrador."
        )

    termo = (
        q or ""
    ).strip()

    query = db.query(
        models.Usuario
    )

    if termo:
        termo_like = f"%{termo}%"

        query = query.filter(
            or_(
                models.Usuario.nome.ilike(
                    termo_like
                ),
                models.Usuario.email.ilike(
                    termo_like
                ),
                models.Usuario.cpf.ilike(
                    termo_like
                )
            )
        )

    usuarios = (
        query
        .order_by(
            models.Usuario.nome.asc()
        )
        .limit(100)
        .all()
    )

    resultado = []

    for usuario in usuarios:

        vendedor = (
            db.query(
                models.Vendedor
            )
            .filter(
                models.Vendedor.usuario_id
                == usuario.id
            )
            .first()
        )

        tem_cursos = (
            db.query(
                models.AcessoCurso
            )
            .filter(
                models.AcessoCurso.usuario_id
                == usuario.id,
                models.AcessoCurso.ativo
                == True
            )
            .first()
            is not None
        )

        is_aluno = (
            usuario.perfil_inicial == "ALUNO"
            or tem_cursos
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

        resultado.append({
            "id":
                usuario.id,

            "nome":
                usuario.nome,

            "email":
                usuario.email,

            "cpf":
                usuario.cpf,

            "ativo":
                usuario.ativo,

            "is_admin":
                usuario.is_admin,

            "is_aluno":
                is_aluno,

            "is_vendedor":
                is_vendedor,

            "vendedor_id":
                vendedor.id
                if vendedor
                else None,

            "vendedor_ativo":
                vendedor.ativo
                if vendedor
                else False,

            "descredenciado_em":
                vendedor.descredenciado_em
                if vendedor
                else None,

            "tem_cursos":
                tem_cursos,

            "perfil_inicial":
                usuario.perfil_inicial
        })

    return resultado

@app.put(
    "/admin/usuarios/{usuario_id}/conceder-admin",
    tags=["Admin"]
)
def conceder_perfil_admin(
    usuario_id: int,
    db: Session = Depends(get_db),
    admin: models.Usuario = Depends(
        get_usuario_atual
    )
):
    if not admin.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito ao administrador."
        )

    usuario = (
        db.query(models.Usuario)
        .filter(
            models.Usuario.id == usuario_id
        )
        .first()
    )

    if not usuario:
        raise HTTPException(
            status_code=404,
            detail="Usuário não encontrado."
        )

    if usuario.is_admin:
        raise HTTPException(
            status_code=400,
            detail="Este usuário já possui perfil Admin."
        )

    usuario.is_admin = True

    db.commit()
    db.refresh(usuario)

    return {
        "ok": True,
        "mensagem": (
            "Perfil Admin concedido com sucesso."
        ),
        "usuario_id": usuario.id,
        "is_admin": usuario.is_admin
    }

@app.put(
    "/admin/usuarios/{usuario_id}/retirar-admin",
    tags=["Admin"]
)
def retirar_perfil_admin(
    usuario_id: int,
    db: Session = Depends(get_db),
    admin: models.Usuario = Depends(
        get_usuario_atual
    )
):
    if not admin.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito ao administrador."
        )

    usuario = (
        db.query(models.Usuario)
        .filter(
            models.Usuario.id == usuario_id
        )
        .first()
    )

    if not usuario:
        raise HTTPException(
            status_code=404,
            detail="Usuário não encontrado."
        )

    if not usuario.is_admin:
        raise HTTPException(
            status_code=400,
            detail=(
                "Este usuário não possui perfil Admin."
            )
        )

    if usuario.id == admin.id:
        raise HTTPException(
            status_code=400,
            detail=(
                "Você não pode retirar o seu próprio "
                "perfil Admin."
            )
        )

    usuario.is_admin = False

    db.commit()
    db.refresh(usuario)

    return {
        "ok": True,
        "mensagem": (
            "Perfil Admin retirado com sucesso."
        ),
        "usuario_id": usuario.id,
        "is_admin": usuario.is_admin
    }

@app.put(
    "/admin/vendedores/{vendedor_id}/descredenciar",
    tags=["Admin"]
)
def descredenciar_vendedor(
    vendedor_id: int,
    db: Session = Depends(get_db),
    admin: models.Usuario = Depends(
        get_usuario_atual
    )
):
    if not admin.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito ao administrador."
        )

    vendedor = (
        db.query(models.Vendedor)
        .filter(
            models.Vendedor.id == vendedor_id
        )
        .first()
    )

    if not vendedor:
        raise HTTPException(
            status_code=404,
            detail="Vendedor não encontrado."
        )

    if not vendedor.ativo:
        raise HTTPException(
            status_code=400,
            detail="Este vendedor já está descredenciado."
        )

    vendedor.ativo = False
    vendedor.descredenciado_em = datetime.utcnow()
    vendedor.atualizado_em = datetime.utcnow()

    db.commit()
    db.refresh(vendedor)

    return {
        "ok": True,
        "mensagem": "Vendedor descredenciado com sucesso.",
        "vendedor_id": vendedor.id,
        "ativo": vendedor.ativo,
        "descredenciado_em": vendedor.descredenciado_em
    }

@app.put(
    "/admin/vendedores/{vendedor_id}/reativar",
    tags=["Admin"]
)
def reativar_vendedor(
    vendedor_id: int,
    db: Session = Depends(get_db),
    admin: models.Usuario = Depends(
        get_usuario_atual
    )
):
    if not admin.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito ao administrador."
        )

    vendedor = (
        db.query(models.Vendedor)
        .filter(
            models.Vendedor.id == vendedor_id
        )
        .first()
    )

    if not vendedor:
        raise HTTPException(
            status_code=404,
            detail="Vendedor não encontrado."
        )

    if vendedor.ativo:
        raise HTTPException(
            status_code=400,
            detail="Este vendedor já está ativo."
        )

    vendedor.ativo = True
    vendedor.descredenciado_em = None
    vendedor.atualizado_em = datetime.utcnow()

    db.commit()
    db.refresh(vendedor)

    return {
        "ok": True,
        "mensagem": "Vendedor reativado com sucesso.",
        "vendedor_id": vendedor.id,
        "ativo": vendedor.ativo
    }