from pydantic import BaseModel, Field

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
    disponivel_demonstracao: bool

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
    status: str = "EM_ANDAMENTO"
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
    tipo: str
    ordem: int = 1
    ativo: bool = True

    tipo_questao: str | None = None
    quantidade_alternativas: int | None = None
    gabarito: str | None = None
    comentario: str | None = None


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
    senha: str = Field(
        min_length=8,
        max_length=64
    )

class UsuarioResponse(BaseModel):
    id: int
    nome: str
    email: EmailStr
    ativo: bool
    is_admin: bool

    perfil_inicial: str
    is_vendedor: bool = False
    is_aluno: bool = False
    tem_cursos: bool = False

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

from datetime import datetime, date
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

class AtendimentoCreate(BaseModel):
    assunto: str
    mensagem: str

class AtendimentoResponse(BaseModel):
    id: int
    usuario_id: int
    assunto: str
    mensagem: str
    status: str
    resposta_admin: str | None = None
    criado_em: datetime

    class Config:
        from_attributes = True

class CursoDisciplinaPropriaCreate(BaseModel):
    curso_id: int
    nome: str
    ativo: bool = True
    ordem: int = 1


class CursoDisciplinaPropriaUpdate(BaseModel):
    nome: str | None = None
    ativo: bool | None = None
    ordem: int | None = None


class CursoDisciplinaPropriaResponse(BaseModel):
    id: int
    curso_id: int
    nome: str
    ativo: bool
    ordem: int
    bloqueada: bool = False

    class Config:
        from_attributes = True

class CursoAssuntoProprioCreate(BaseModel):
    curso_disciplina_propria_id: int
    nome: str
    descricao: str | None = None
    ativo: bool = True
    ordem: int = 1


class CursoAssuntoProprioUpdate(BaseModel):
    nome: str | None = None
    descricao: str | None = None
    ativo: bool | None = None
    ordem: int | None = None


class CursoAssuntoProprioResponse(BaseModel):
    id: int
    curso_disciplina_propria_id: int
    nome: str
    descricao: str | None = None
    ativo: bool
    ordem: int

    class Config:
        from_attributes = True

class AulaUpdate(BaseModel):
    titulo: str | None = None
    descricao: str | None = None
    ordem: int | None = None
    ativo: bool | None = None

class RespostaAlunoQuestaoCreate(BaseModel):
    questao_id: int
    bateria_id: int
    resposta: str | None = None
    dificuldade: str | None = None


class RespostaAlunoQuestaoResponse(BaseModel):
    id: int
    usuario_id: int
    questao_id: int
    bateria_id: int
    resposta: str | None = None
    dificuldade: str | None = None
    respondida: bool
    finalizada: bool
    em_revisao: bool
    acertou: bool | None = None

    class Config:
        from_attributes = True

class RespostaQuestaoAlunoCreate(BaseModel):
    questao_id: int
    resposta_marcada: str
    dificuldade: str | None = None
    rever: bool = False


class ConcluirBateriaCreate(BaseModel):
    bateria_id: int
    respostas: list[RespostaQuestaoAlunoCreate]


class TentativaBateriaResponse(BaseModel):
    id: int
    usuario_id: int
    bateria_id: int
    status: str
    percentual_acerto: int

    class Config:
        from_attributes = True

class QuestaoPraticaMarcacaoAlunoCreate(BaseModel):
    dificuldade_marcada: Optional[str] = None
    acertou: Optional[bool] = None

class QuestaoPraticaMarcacaoAlunoResponse(BaseModel):
    id: int
    usuario_id: int
    questao_id: int
    dificuldade_marcada: Optional[str]
    acertou: Optional[bool]

    class Config:
        from_attributes = True

class ProximaQuestaoPraticaRequest(BaseModel):
    filtros: list[str] = ["TODAS"]
    ids_questoes_sessao: Optional[list[int]] = None

class ResponderQuestaoPraticaRequest(BaseModel):
    dificuldade_marcada: str
    acertou: Optional[bool] = None
    rever: bool = False
    nao_soube: bool = False
    filtros: list[str] = ["TODAS"]

class QuestaoPraticaAlternativaCreate(BaseModel):
    letra: str
    texto: str
    correta: bool = False

class QuestaoPraticaAdminCreate(BaseModel):
    curso_assunto_proprio_id: int
    tipo: str
    enunciado: str
    gabarito: str
    comentario: Optional[str] = None
    ativo: bool = True
    alternativas: Optional[list[QuestaoPraticaAlternativaCreate]] = None

class QuestaoPraticaAdminUpdate(BaseModel):
    tipo: str
    enunciado: str
    gabarito: Optional[str] = None
    comentario: Optional[str] = None
    ativo: bool = True
    alternativas: Optional[list[QuestaoPraticaAlternativaCreate]] = None

class DuplicarCursoRequest(BaseModel):
    novo_nome: str

class CopiarDisciplinaRequest(BaseModel):
    curso_destino_id: int

class CopiarAssuntoRequest(BaseModel):
    disciplina_destino_id: int

class VendedorCreate(BaseModel):
    nome: str
    cpf_cnpj: Optional[str] = None
    data_nascimento: Optional[date] = None
    email: Optional[str] = None
    telefone: Optional[str] = None
    senha: str = Field(
        min_length=8,
        max_length=64
    )
    estado_uf: Optional[str] = None
    cidade: Optional[str] = None


class VendedorUpdate(BaseModel):
    nome: Optional[str] = None
    cpf_cnpj: Optional[str] = None
    data_nascimento: Optional[date] = None
    email: Optional[str] = None
    telefone: Optional[str] = None
    estado_uf: Optional[str] = None
    cidade: Optional[str] = None
    ativo: Optional[bool] = None


class VendedorResponse(BaseModel):
    id: int
    nome: str
    cpf_cnpj: Optional[str] = None
    data_nascimento: Optional[date] = None
    email: Optional[str] = None
    telefone: Optional[str] = None
    estado_uf: Optional[str] = None
    cidade: Optional[str] = None
    ativo: bool
    usuario_id: Optional[int] = None
    descredenciado_em: Optional[datetime] = None

    class Config:
        from_attributes = True

class VendedorVincularUsuarioRequest(BaseModel):
    usuario_id: Optional[int] = None

class QRCodeCreate(BaseModel):
    quantidade: int = 1


class QRCodeVincularVendedorRequest(BaseModel):
    vendedor_id: Optional[int] = None


class QRCodeResponse(BaseModel):
    id: int
    codigo: str
    vendedor_id: Optional[int] = None
    ativo: bool

    class Config:
        from_attributes = True

class CupomDescontoGerarRequest(BaseModel):
    quantidade: int


class CupomDescontoVincularVendedorRequest(BaseModel):
    vendedor_id: Optional[int] = None


class CupomDescontoResponse(BaseModel):
    id: int
    codigo: str
    vendedor_id: Optional[int] = None
    percentual_desconto: int
    ativo: bool

    class Config:
        from_attributes = True

class ValidarCupomRequest(BaseModel):
    codigo_cupom: str


class ValidarCupomResponse(BaseModel):
    valido: bool
    codigo_cupom: str
    percentual_desconto: int
    vendedor_id: Optional[int] = None

class VendedorExistenteCreate(BaseModel):
    telefone: Optional[str] = None
    cpf_cnpj: Optional[str] = None
    data_nascimento: Optional[date] = None
    estado_uf: Optional[str] = None
    cidade: Optional[str] = None

