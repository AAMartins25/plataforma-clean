from app.models import Curso, Disciplina, Assunto, Pasta, Aula, Video, Bateria   
from datetime import datetime, timedelta
from app.schemas import CursoCreate, CursoResponse, DisciplinaCreate, DisciplinaResponse, AssuntoCreate, AssuntoResponse
from app.models import Questao, Alternativa, Comentario
from app.schemas import QuestaoCreate, AlternativaCreate, ComentarioGeralCreate
from app.schemas import Sprint10Create 
from app.schemas import VideoCreate 
from app.schemas import BateriaCreate 
from app.models import Material
from app.schemas import MaterialCreate 
from sqlalchemy import text
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session 
from app.database import SessionLocal
from app.models import Curso
from app.schemas import CursoCreate, CursoResponse  
from app.models import QuizIA, QuizIAItem, CartaoIA, QuestoesIA, QuestoesIAItem 
from app.schemas import (
    CursoCreate, CursoResponse,
    DisciplinaCreate, DisciplinaResponse,
    AssuntoCreate, AssuntoResponse,
    AulaCreate, AulaResponse
) 
from fastapi import HTTPException
import requests
from sqlalchemy.exc import IntegrityError
from app.models import AcessoCurso, ProgressoAula
from app.schemas import AcessoCursoCreate, AcessoCursoResponse
from app.schemas import RecuperarSenhaRequest
from app.models import Pagamento

from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="Plataforma de Cursos")

from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from app.auth import hash_senha, verificar_senha, criar_token, decodificar_token
from app.models import Usuario
from app.schemas import UsuarioCreate, UsuarioResponse, TokenResponse
from sqlalchemy import or_
from app.schemas import UsuarioUpdateMe

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],  # essencial p/ Authorization: Bearer ...
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
                    "valor_cents": compra_recente.valor_cents,
                    "status": compra_recente.status
                }
            ]
        }

    return {
        "tipo": "nenhuma",
        "compras": []
    }

@app.get("/me/cursos", response_model=list[AcessoCursoResponse], tags=["Acessos"])
def meus_cursos(db: Session = Depends(get_db), usuario: Usuario = Depends(get_usuario_atual)):
    acessos = db.query(AcessoCurso).join(Curso, Curso.id == AcessoCurso.curso_id).filter(
        AcessoCurso.usuario_id == usuario.id,
        AcessoCurso.ativo == True,
        Curso.ativo == True
    ).all()

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
    novo = Curso(nome=curso.nome, ativo=curso.ativo)
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo

# READ: listar cursos
@app.get("/cursos", response_model=list[CursoResponse])
def listar_cursos(db: Session = Depends(get_db)):
    cursos = db.query(Curso).all()
    return cursos

# CREATE: criar disciplina
@app.post("/disciplinas", response_model=DisciplinaResponse)
def criar_disciplina(disciplina: DisciplinaCreate, db: Session = Depends(get_db)):
    nova = Disciplina(nome=disciplina.nome, ativo=disciplina.ativo)
    db.add(nova)
    db.commit()
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
        db.commit()
        db.refresh(existente)
        return existente

    novo = ProgressoAula(
        usuario_id=usuario.id,
        pasta_id=aula.pasta_id,
        aula_id=aula.id,
        concluida=True
    )

    db.add(novo)
    db.commit()
    db.refresh(novo)

    return novo

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
    if total >= 3:
        return {"erro": "Limite de 3 vídeos por aula atingido"}

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

@app.post("/baterias")
def criar_bateria(bateria: BateriaCreate, db: Session = Depends(get_db)):
    aula = db.query(Aula).filter(Aula.id == bateria.aula_id).first()
    if not aula:
        return {"erro": "Aula não encontrada"}

    # checa limite 3 (backend) - além do trigger do banco
    total = db.query(Bateria).filter(Bateria.aula_id == bateria.aula_id).count()
    if total >= 3:
        return {"erro": "Limite de 3 baterias (sprints) por aula atingido"}

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
        {"id": b.id, "aula_id": b.aula_id, "titulo": b.titulo, "ordem": b.ordem, "ativo": b.ativo}
        for b in baterias
    ]

@app.post("/questoes")
def criar_questao(questao: QuestaoCreate, db: Session = Depends(get_db)):
    bateria = db.query(Bateria).filter(Bateria.id == questao.bateria_id).first()
    if not bateria:
        return {"erro": "Bateria (Sprint) não encontrada"}

    # ordem única na bateria (mensagem amigável)
    existe_ordem = db.query(Questao).filter(
        Questao.bateria_id == questao.bateria_id,
        Questao.ordem == questao.ordem
    ).first()
    if existe_ordem:
        return {"erro": f"Já existe questão com ordem {questao.ordem} nesta bateria. Use outra ordem."}

    # valida tipo
    if questao.tipo not in ("MULTIPLA", "CERTO_ERRADO"):
        return {"erro": "Tipo inválido. Use 'MULTIPLA' ou 'CERTO_ERRADO'."}

    nova = Questao(
        bateria_id=questao.bateria_id,
        enunciado=questao.enunciado,
        tipo=questao.tipo,
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
        "ordem": nova.ordem,
        "ativo": nova.ativo
    }

@app.post("/questoes/{questao_id}/alternativas")
def criar_alternativa(questao_id: int, alt: AlternativaCreate, db: Session = Depends(get_db)):
    questao = db.query(Questao).filter(Questao.id == questao_id).first()
    if not questao:
        return {"erro": "Questão não encontrada"}

    if questao.tipo != "MULTIPLA":
        return {"erro": "Alternativas só podem ser adicionadas a questões do tipo MULTIPLA"}

    letra = alt.letra.strip().upper()
    if letra not in ("A", "B", "C", "D", "E"):
        return {"erro": "Letra inválida. Use A, B, C, D ou E."}

    existe = db.query(Alternativa).filter(
        Alternativa.questao_id == questao_id,
        Alternativa.letra == letra
    ).first()
    if existe:
        return {"erro": f"Já existe alternativa {letra} nesta questão."}

    nova_alt = Alternativa(
        questao_id=questao_id,
        letra=letra,
        texto=alt.texto
    )
    db.add(nova_alt)
    db.commit()
    db.refresh(nova_alt)

    # comentário por alternativa (opcional)
    if alt.comentario and alt.comentario.strip():
        db.add(Comentario(
            questao_id=questao_id,
            alternativa_id=nova_alt.id,
            texto=alt.comentario.strip()
        ))
        db.commit()

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
        alts = db.query(Alternativa).filter(Alternativa.questao_id == q.id).order_by(Alternativa.letra.asc()).all()

        # comentários por alternativa (MULTIPLA)
        comentarios_alt = db.query(Comentario).filter(
            Comentario.questao_id == q.id,
            Comentario.alternativa_id.isnot(None)
        ).all()
        mapa_com_alt = {c.alternativa_id: c.texto for c in comentarios_alt}

        # comentário geral (CERTO_ERRADO)
        comentario_geral = db.query(Comentario).filter(
            Comentario.questao_id == q.id,
            Comentario.alternativa_id.is_(None)
        ).first()

        resultado.append({
            "id": q.id,
            "bateria_id": q.bateria_id,
            "enunciado": q.enunciado,
            "tipo": q.tipo,
            "ordem": q.ordem,
            "ativo": q.ativo,
            "alternativas": [
                {
                    "id": a.id,
                    "letra": a.letra,
                    "texto": a.texto,
                    "comentario": mapa_com_alt.get(a.id)
                } for a in alts
            ],
            "comentario_geral": comentario_geral.texto if comentario_geral else None
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
    if total >= 3:
        return {"erro": "Limite de 3 materiais por aula atingido"}

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
def register(dados: UsuarioCreate, db: Session = Depends(get_db)):
    existe_email = db.query(Usuario).filter(Usuario.email == dados.email).first()
    if existe_email:
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")

    existe_cpf = db.query(Usuario).filter(Usuario.cpf == dados.cpf).first()
    if existe_cpf:
        raise HTTPException(status_code=400, detail="CPF já cadastrado")

    novo = Usuario(
        nome=dados.nome,
        email=dados.email,
        cpf=dados.cpf,
        telefone=dados.telefone,
        senha_hash=hash_senha(dados.senha),
        ativo=True,
        is_admin=False
    )

    db.add(novo)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="E-mail ou CPF já cadastrado")

    db.refresh(novo)
    return novo

@app.post("/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    login_digitado = form_data.username.strip()

    usuario = db.query(Usuario).filter(
        or_(
            Usuario.email == login_digitado,
            Usuario.cpf == login_digitado
        )
    ).first()

    if not usuario or not verificar_senha(form_data.password, usuario.senha_hash):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    token = criar_token({"sub": str(usuario.id)})
    return {"access_token": token, "token_type": "bearer"}

@app.get("/me", response_model=UsuarioResponse)
def me(usuario: Usuario = Depends(get_usuario_atual)):
    return usuario

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

import os
from fastapi import HTTPException, Request

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:5500/site-html")

def mp_headers():
    if not MP_ACCESS_TOKEN:
        raise HTTPException(status_code=500, detail="MP_ACCESS_TOKEN não configurado no ambiente.")
    return {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}

@app.post("/checkout/mercadopago")
def criar_checkout_mp(payload: dict, db: Session = Depends(get_db), user=Depends(get_usuario_atual)):
    """
    Body esperado:
    { "curso_id": 1, "valor_cents": 1990 }
    """
    curso_id = payload.get("curso_id")
    valor_cents = payload.get("valor_cents", 0)

    if not curso_id or not isinstance(curso_id, int):
        raise HTTPException(status_code=400, detail="curso_id inválido.")

    if not isinstance(valor_cents, int) or valor_cents <= 0:
        raise HTTPException(status_code=400, detail="valor_cents inválido (inteiro > 0).")

    curso = db.query(Curso).filter(Curso.id == curso_id).first()
    if not curso:
        raise HTTPException(status_code=404, detail="Curso não encontrado.")

    # 1) cria pagamento PENDENTE e pega o id desse pagamento
    pagamento_id = db.execute(text("""
        INSERT INTO pagamentos (usuario_id, curso_id, status, valor_cents)
        VALUES (:u, :c, 'PENDENTE', :v)
        RETURNING id
    """), {"u": user.id, "c": curso_id, "v": int(valor_cents)}).scalar()

    db.commit()

    # 2) monta URLs de retorno (back_urls)
    base = (APP_BASE_URL or "").rstrip("/")
    if not base:
        base = "http://127.0.0.1:5500/site-html"

    success_url = f"{base}/cursos.html"
    failure_url = f"{base}/cursos.html"
    pending_url = f"{base}/cursos.html"

    # 3) monta payload do Mercado Pago (COM items)
    payload_mp = {
        "items": [{
            "title": f"Curso #{curso.id} - {curso.nome}",
            "quantity": 1,
            "unit_price": round(valor_cents / 100, 2),
            "currency_id": "BRL"
        }],
        "payer": {"email": user.email},
        "external_reference": f"user:{user.id}|curso:{curso_id}",
        "back_urls": {
            "success": f"{base}/pagamento_sucesso.html",
            "failure": f"{base}/pagamento_erro.html",
            "pending": f"{base}/pagamento_pendente.html",
        },

        # ✅ em ambiente local/sandbox, deixe sem auto_return para evitar bloqueio
        # "auto_return": "approved", 
        "notification_url": "https://leonora-poriferous-hexagonally.ngrok-free.dev/webhooks/mercadopago", 
    }

    # 4) chama MP para criar a preference
    url = "https://api.mercadopago.com/checkout/preferences"
    headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}", "Content-Type": "application/json"}

    try:
        resp = requests.post(url, headers=headers, json=payload_mp, timeout=20)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Falha de rede ao chamar MP: {e}")

    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Erro MP {resp.status_code}: {resp.text}")

    try:
        data = resp.json()
    except ValueError:
        raise HTTPException(status_code=502, detail=f"MP não retornou JSON: {resp.text[:500]}")

    pref_id = data.get("id")
    init_point = data.get("sandbox_init_point") or data.get("init_point")

    if not pref_id or not init_point:
        raise HTTPException(status_code=502, detail=f"MP retornou sem pref_id/init_point: {data}")

    # 5) salva mp_preference_id no pagamento que acabamos de criar (o PENDENTE certo)
    db.execute(text("""
        UPDATE pagamentos
        SET mp_preference_id = :pid
        WHERE id = :pag_id
    """), {"pid": str(pref_id), "pag_id": int(pagamento_id)})

    db.commit()

    return {
        "preference_id": str(pref_id),
        "pagamento_id": int(pagamento_id),
        "init_point": data.get("init_point"),
        "sandbox_init_point": data.get("sandbox_init_point"),
    }

from fastapi import HTTPException

@app.post("/pagamentos/confirmar")
def confirmar_pagamento(payload: dict, db: Session = Depends(get_db), user=Depends(get_usuario_atual)):
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

    # atualiza pagamento mais recente do usuário/curso
    # 1) Atualiza o pagamento mais recente
    db.execute(text("""
        UPDATE pagamentos
        SET status = :st, mp_payment_id = :pid
        WHERE id = (
            SELECT id
            FROM pagamentos
            WHERE usuario_id = :u AND curso_id = :c
            ORDER BY id DESC
            LIMIT 1
        )
    """), {
        "st": status.upper(),
        "pid": str(payment_id),
        "u": user.id,
        "c": curso_id
    })
    db.commit()

    # 2) Libera acesso ao curso
    liberou = False

    if status == "approved":
        db.execute(text("""
            INSERT INTO acessos_curso (usuario_id, curso_id, ativo, data_inicio, data_fim)
            VALUES (:u, :c, TRUE, NOW(), NULL)
            ON CONFLICT (usuario_id, curso_id)
            DO UPDATE SET
                ativo = TRUE,
                data_inicio = COALESCE(acessos_curso.data_inicio, NOW()),
                data_fim = NULL
        """), {
            "u": user.id,
            "c": curso_id
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

    # MP costuma mandar: {"type":"payment","data":{"id":"123"}}
    payment_id = None
    if isinstance(data, dict):
        payment_id = (data.get("data") or {}).get("id") or data.get("id") or data.get("payment_id")

    if not payment_id:
        return {"ok": True, "ignored": True, "msg": "sem payment_id", "payload": data}

    # 1) Consulta no MP (fonte de verdade)
    r = requests.get(
        f"https://api.mercadopago.com/v1/payments/{payment_id}",
        headers=mp_headers(),
        timeout=20
    )
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"MP erro ao consultar payment: {r.status_code} {r.text}")

    pagamento_mp = r.json()
    status = (pagamento_mp.get("status") or "desconhecido").upper()
    external_reference = pagamento_mp.get("external_reference") or ""

    # external_reference esperado: "user:1|curso:2"
    user_id = None
    curso_id = None
    try:
        for p in external_reference.split("|"):
            if p.startswith("user:"):
                user_id = int(p.split(":", 1)[1])
            elif p.startswith("curso:"):
                curso_id = int(p.split(":", 1)[1])
    except:
        pass

    # 2) Atualiza pagamento (sempre) — salva mp_payment_id e status
    if user_id and curso_id:
        db.execute(text("""
            UPDATE pagamentos
            SET status = :st,
                mp_payment_id = :pid,
                atualizado_em = NOW()
            WHERE id = (
                SELECT id FROM pagamentos
                WHERE usuario_id = :u AND curso_id = :c
                ORDER BY id DESC
                LIMIT 1
            )
        """), {"st": status, "pid": str(payment_id), "u": user_id, "c": curso_id})
        db.commit()
    else:
        # Não conseguiu parsear external_reference: ainda assim registra o payment_id/status no último pendente (se houver)
        db.execute(text("""
            UPDATE pagamentos
            SET status = :st,
                mp_payment_id = :pid,
                atualizado_em = NOW()
            WHERE status = 'PENDENTE'
            ORDER BY id DESC
            LIMIT 1
        """), {"st": status, "pid": str(payment_id)})
        db.commit()
        return {"ok": True, "status": status, "msg": "external_reference não parseável", "payment_id": payment_id}

    # 3) Se aprovado, libera acesso (ativo=true)
    if status == "APPROVED":
        db.execute(text("""
            INSERT INTO acessos_curso (usuario_id, curso_id, ativo, data_inicio, data_fim)
            VALUES (:u, :c, TRUE, NOW(), NULL)
            ON CONFLICT (usuario_id, curso_id)
            DO UPDATE SET
                ativo = TRUE,
                data_inicio = COALESCE(acessos_curso.data_inicio, NOW()),
                data_fim = NULL
        """), {
            "u": user_id,
            "c": curso_id
        })
        db.commit()

    return {
        "ok": True,
        "status": status.upper(),
        "curso_id": curso_id
    }


@app.get("/debug/env")
def debug_env():
    return {
        "tem_mp_token": bool(os.getenv("MP_ACCESS_TOKEN")),
        "app_base_url": os.getenv("APP_BASE_URL", "")
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
        WHERE p.status IN ('REFUND_IN_PROCESS', 'REFUNDED', 'REFUND_ERROR')
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
        raise HTTPException(status_code=403, detail="Apenas admin")

    nome = (payload.get("nome") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    cpf = (payload.get("cpf") or "").strip()
    telefone = (payload.get("telefone") or "").strip()
    senha = (payload.get("senha") or "").strip()

    # ✅ NOVO: lê flag do payload
    is_admin = bool(payload.get("is_admin", False))

    if not nome or not email or not cpf or not telefone or not senha:
        raise HTTPException(status_code=400, detail="Informe nome, email, CPF, telefone e senha")

    existe = db.query(Usuario).filter(Usuario.email == email).first()
    if existe:
        raise HTTPException(status_code=409, detail="Já existe usuário com esse email")

    existe_cpf = db.query(Usuario).filter(Usuario.cpf == cpf).first()
    if existe_cpf:
        raise HTTPException(status_code=409, detail="Já existe usuário com esse CPF")

    senha_hash = hash_senha(senha)

    u = Usuario(
        nome=nome,
        email=email,
        cpf=cpf,
        telefone=telefone,
        senha_hash=senha_hash,
        ativo=True,
        # ✅ AQUI: salva o valor correto
        is_admin=is_admin
    )
    db.add(u)
    db.commit()
    db.refresh(u)

    return {"id": u.id, "nome": u.nome, "email": u.email, "ativo": u.ativo, "is_admin": u.is_admin}


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

    return {
        "ok": True,
        "message": (
            "Processo de recuperação realizado com sucesso! "
            "Verifique seu email para obter a senha."
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
            detail="Este pagamento não está elegível para reembolso"
        )

    limite_reembolso = pagamento.criado_em + timedelta(days=7)

    if datetime.utcnow() > limite_reembolso:
        raise HTTPException(
            status_code=400,
            detail="Prazo de reembolso expirado"
        )

    if not pagamento.mp_payment_id:
        raise HTTPException(
            status_code=400,
            detail="Pagamento sem mp_payment_id. Não foi possível solicitar reembolso automático."
        )

    acesso = db.query(AcessoCurso).filter(
        AcessoCurso.usuario_id == usuario.id,
        AcessoCurso.curso_id == pagamento.curso_id,
        AcessoCurso.ativo == True
    ).first()

    if acesso:
        acesso.ativo = False
        acesso.data_fim = datetime.utcnow()

    pagamento.status = "REFUND_IN_PROCESS"
    pagamento.atualizado_em = datetime.utcnow()
    db.commit()

    try:
        r = requests.post(
            f"https://api.mercadopago.com/v1/payments/{pagamento.mp_payment_id}/refunds",
            headers={
                **mp_headers(),
            },
            json={},
            timeout=20
        )

        if r.status_code not in [200, 201]:
            pagamento.status = "REFUND_ERROR"
            pagamento.atualizado_em = datetime.utcnow()
            db.commit()

            raise HTTPException(
                status_code=502,
                detail=f"Erro ao solicitar reembolso no Mercado Pago: {r.text}"
            )

        dados_mp = r.json()
        status_refund = (dados_mp.get("status") or "").lower()

        if status_refund == "approved":
            pagamento.status = "REFUNDED"
        elif status_refund == "in_process":
            pagamento.status = "REFUND_IN_PROCESS"
        else:
            pagamento.status = "REFUND_IN_PROCESS"

        pagamento.atualizado_em = datetime.utcnow()
        db.commit()

        return {
            "ok": True,
            "message": "Reembolso solicitado com sucesso",
            "status": pagamento.status
        }

    except HTTPException:
        raise

    except Exception as e:
        pagamento.status = "REFUND_ERROR"
        pagamento.atualizado_em = datetime.utcnow()
        db.commit()

        raise HTTPException(
            status_code=500,
            detail=f"Erro inesperado ao solicitar reembolso: {str(e)}"
        )