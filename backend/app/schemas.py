from pydantic import BaseModel

class CursoCreate(BaseModel):
    nome: str
    ativo: bool = True

class CursoResponse(BaseModel):
    id: int
    nome: str
    ativo: bool

    class Config:
        from_attributes = True

class DisciplinaCreate(BaseModel):
    nome: str
    ativo: bool = True

class DisciplinaResponse(BaseModel):
    id: int
    nome: str
    ativo: bool

    class Config:
        from_attributes = True

class AssuntoCreate(BaseModel):
    disciplina_id: int
    nome: str
    descricao: str | None = None
    ativo: bool = True

class AssuntoResponse(BaseModel):
    id: int
    disciplina_id: int
    nome: str
    descricao: str | None
    ativo: bool

class PastaResponse(BaseModel):
    id: int
    assunto_id: int
    tipo: str
    nome: str

class AulaCreate(BaseModel):
    pasta_id: int
    titulo: str
    descricao: str | None = None
    ordem: int = 0
    ativo: bool = True

class AulaResponse(BaseModel):
    id: int
    pasta_id: int
    titulo: str
    descricao: str | None
    ordem: int
    ativo: bool

class VideoCreate(BaseModel):
    aula_id: int
    titulo: str
    url: str
    duracao_segundos: int = 0
    transcricao: str | None = None
    ordem: int = 1
    ativo: bool = True


class VideoResponse(BaseModel):
    id: int
    aula_id: int
    titulo: str
    url: str
    duracao_segundos: int
    transcricao: str | None
    ordem: int
    ativo: bool

class BateriaCreate(BaseModel):
    aula_id: int
    titulo: str
    ordem: int = 1
    ativo: bool = True

class BateriaResponse(BaseModel):
    id: int
    aula_id: int
    titulo: str
    ordem: int
    ativo: bool

class QuestaoCreate(BaseModel):
    bateria_id: int
    enunciado: str
    tipo: str  # "MULTIPLA" ou "CERTO_ERRADO"
    ordem: int = 1
    ativo: bool = True


class AlternativaCreate(BaseModel):
    letra: str  # "A"..."E"
    texto: str
    comentario: str | None = None  # comentário por alternativa (opcional)


class ComentarioGeralCreate(BaseModel):
    texto: str


from typing import Optional

class Sprint10Create(BaseModel):
    bateria_id: Optional[int] = None
    tipo: str  # "MULTIPLA" ou "CERTO_ERRADO"
    enunciados: Optional[list[str]] = None


class MaterialCreate(BaseModel):
    aula_id: int
    tipo: str  # "PDF", "LINK", "TEXTO"
    titulo: str
    url: str | None = None
    conteudo: str | None = None
    ordem: int = 1
    ativo: bool = True


from pydantic import BaseModel, EmailStr, Field

class UsuarioCreate(BaseModel):
    nome: str
    email: EmailStr
    cpf: str
    telefone: str
    senha: str = Field(min_length=8, max_length=64)

class UsuarioResponse(BaseModel):
    id: int
    nome: str
    email: EmailStr
    ativo: bool
    is_admin: bool

    class Config:
        from_attributes = True

class UsuarioUpdateMe(BaseModel):
    nome: str
    email: EmailStr
    cpf: str
    telefone: str
    senha: str | None = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

from datetime import datetime
from typing import Optional

class AcessoCursoCreate(BaseModel):
    usuario_id: int
    curso_id: int
    ativo: bool = True

class AcessoCursoResponse(BaseModel):
    id: int
    curso_id: int
    nome_curso: str
    ativo: bool
    data_inicio: datetime
    data_fim: Optional[datetime] = None

class ProgressoAulaResponse(BaseModel):
    id: int
    usuario_id: int
    pasta_id: int
    aula_id: int
    concluida: bool
    data_conclusao: datetime

    class Config:
        from_attributes = True

class RecuperarSenhaRequest(BaseModel):
    login: str