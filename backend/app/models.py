from sqlalchemy import DateTime
from datetime import datetime 
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Table, ForeignKey, Text
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.postgresql import JSONB 


Base = declarative_base()

# Tabela de associação N:N entre cursos e disciplinas
curso_disciplina = Table(
    "curso_disciplina",
    Base.metadata,
    Column("curso_id", Integer, ForeignKey("cursos.id"), primary_key=True),
    Column("disciplina_id", Integer, ForeignKey("disciplinas.id"), primary_key=True),
)

class Curso(Base):
    __tablename__ = "cursos"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(255), nullable=False)
    ativo = Column(Boolean, default=True)

    disciplinas = relationship(
        "Disciplina",
        secondary=curso_disciplina,
        back_populates="cursos"
    )

class Disciplina(Base):
    __tablename__ = "disciplinas"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(255), nullable=False)
    ativo = Column(Boolean, default=True)

    cursos = relationship(
        "Curso",
        secondary=curso_disciplina,
        back_populates="disciplinas"
    )

from sqlalchemy import Text  # se ainda não tiver

class Assunto(Base):
    __tablename__ = "assuntos"

    id = Column(Integer, primary_key=True, index=True)
    disciplina_id = Column(Integer, ForeignKey("disciplinas.id"), nullable=False)

    nome = Column(String(255), nullable=False)
    descricao = Column(Text, nullable=True)
    ativo = Column(Boolean, default=True)

    disciplina = relationship("Disciplina", backref="assuntos")

class Pasta(Base):
    __tablename__ = "pastas"

    id = Column(Integer, primary_key=True, index=True)
    assunto_id = Column(Integer, ForeignKey("assuntos.id"), nullable=False)

    tipo = Column(String(50), nullable=False)   # TEORIA / INTERATIVIDADE
    nome = Column(String(255), nullable=False)  # "Teoria + Questões" / "Interatividade"

    assunto = relationship("Assunto", backref="pastas")

class Aula(Base):
    __tablename__ = "aulas"

    id = Column(Integer, primary_key=True, index=True)
    pasta_id = Column(Integer, ForeignKey("pastas.id"), nullable=False)

    titulo = Column(String(255), nullable=False)
    descricao = Column(Text, nullable=True)
    ordem = Column(Integer, default=0)
    ativo = Column(Boolean, default=True)

    criado_em = Column(DateTime, default=datetime.utcnow)

    pasta = relationship("Pasta", backref="aulas")

class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, index=True)
    aula_id = Column(Integer, ForeignKey("aulas.id"), nullable=False)

    titulo = Column(String(255), nullable=False)
    url = Column(Text, nullable=False)
    duracao_segundos = Column(Integer, default=0)
    transcricao = Column(Text, nullable=True)

    ordem = Column(Integer, default=1)
    ativo = Column(Boolean, default=True)

    aula = relationship("Aula", backref="videos")

class Bateria(Base):
    __tablename__ = "baterias"

    id = Column(Integer, primary_key=True, index=True)
    aula_id = Column(Integer, ForeignKey("aulas.id"), nullable=False)

    titulo = Column(String(255), nullable=False)
    ordem = Column(Integer, default=1)
    ativo = Column(Boolean, default=True)

    aula = relationship("Aula", backref="baterias")

class Questao(Base):
    __tablename__ = "questoes"

    id = Column(Integer, primary_key=True, index=True)
    bateria_id = Column(Integer, ForeignKey("baterias.id"), nullable=False)

    enunciado = Column(Text, nullable=False)
    tipo = Column(String(20), nullable=False)  # MULTIPLA / CERTO_ERRADO
    ordem = Column(Integer, default=1)
    ativo = Column(Boolean, default=True)

    bateria = relationship("Bateria", backref="questoes")


class Alternativa(Base):
    __tablename__ = "alternativas"

    id = Column(Integer, primary_key=True, index=True)
    questao_id = Column(Integer, ForeignKey("questoes.id"), nullable=False)

    letra = Column(String(1), nullable=False)  # A-E
    texto = Column(Text, nullable=False)

    questao = relationship("Questao", backref="alternativas")


class Comentario(Base):
    __tablename__ = "comentarios"

    id = Column(Integer, primary_key=True, index=True)
    questao_id = Column(Integer, ForeignKey("questoes.id"), nullable=False)
    alternativa_id = Column(Integer, ForeignKey("alternativas.id"), nullable=True)

    texto = Column(Text, nullable=False)

    questao = relationship("Questao", backref="comentarios")
    alternativa = relationship("Alternativa", backref="comentario")

class Material(Base):
    __tablename__ = "materiais"

    id = Column(Integer, primary_key=True, index=True)
    aula_id = Column(Integer, ForeignKey("aulas.id"), nullable=False)

    tipo = Column(String(20), nullable=False)   # PDF / LINK / TEXTO
    titulo = Column(String(255), nullable=False)

    url = Column(Text, nullable=True)
    conteudo = Column(Text, nullable=True)

    ordem = Column(Integer, default=1)
    ativo = Column(Boolean, default=True)

    aula = relationship("Aula", backref="materiais")

class QuizIA(Base):
    __tablename__ = "quiz_ia"

    id = Column(Integer, primary_key=True, index=True)
    pasta_id = Column(Integer, ForeignKey("pastas.id"), nullable=False)
    titulo = Column(String(255), nullable=False)

    pasta = relationship("Pasta", backref="quizzes_ia")


class QuizIAItem(Base):
    __tablename__ = "quiz_ia_itens"

    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quiz_ia.id"), nullable=False)

    pergunta = Column(Text, nullable=False)
    alternativas = Column(JSONB, nullable=False)
    resposta_correta = Column(String(1), nullable=False)
    comentario_curto = Column(Text, nullable=False)
    ordem = Column(Integer, default=1)

    quiz = relationship("QuizIA", backref="itens")


class CartaoIA(Base):
    __tablename__ = "cartoes_ia"

    id = Column(Integer, primary_key=True, index=True)
    pasta_id = Column(Integer, ForeignKey("pastas.id"), nullable=False)

    frente = Column(Text, nullable=False)
    verso = Column(Text, nullable=False)
    ordem = Column(Integer, default=1)

    pasta = relationship("Pasta", backref="cartoes_ia")


class QuestoesIA(Base):
    __tablename__ = "questoes_ia"

    id = Column(Integer, primary_key=True, index=True)
    pasta_id = Column(Integer, ForeignKey("pastas.id"), nullable=False)
    titulo = Column(String(255), nullable=False)

    pasta = relationship("Pasta", backref="questoes_ia")


class QuestoesIAItem(Base):
    __tablename__ = "questoes_ia_itens"

    id = Column(Integer, primary_key=True, index=True)
    questoes_ia_id = Column(Integer, ForeignKey("questoes_ia.id"), nullable=False)

    enunciado = Column(Text, nullable=False)
    tipo = Column(String(20), nullable=False)
    alternativas = Column(JSONB, nullable=True)
    comentario = Column(JSONB, nullable=True)
    ordem = Column(Integer, default=1)

    questoes_ia = relationship("QuestoesIA", backref="itens")

class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    senha_hash = Column(String, nullable=False)
    ativo = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    cpf = Column(String, unique=True, nullable=False)
    telefone = Column(String, nullable=False)

    criado_em = Column(DateTime, default=datetime.utcnow)

from sqlalchemy import DateTime
from datetime import datetime

class AcessoCurso(Base):
    __tablename__ = "acessos_curso"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    curso_id = Column(Integer, ForeignKey("cursos.id"), nullable=False)

    ativo = Column(Boolean, default=True)
    data_inicio = Column(DateTime, default=datetime.utcnow)
    data_fim = Column(DateTime, nullable=True)

    usuario = relationship("Usuario")
    curso = relationship("Curso")

class Pagamento(Base):
    __tablename__ = "pagamentos"

    id = Column(Integer, primary_key=True, index=True)

    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    curso_id = Column(Integer, ForeignKey("cursos.id"), nullable=False)

    status = Column(String(50), nullable=False)
    valor_cents = Column(Integer, nullable=False, default=0)

    provedor = Column(String(50), nullable=True)
    moeda = Column(String(20), nullable=True)

    mp_preference_id = Column(String, nullable=True)
    mp_payment_id = Column(String, nullable=True)

    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow)

    usuario = relationship("Usuario")
    curso = relationship("Curso")

class ProgressoAula(Base):
    __tablename__ = "progresso_aulas"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    pasta_id = Column(Integer, ForeignKey("pastas.id"), nullable=False)
    aula_id = Column(Integer, ForeignKey("aulas.id"), nullable=False)

    concluida = Column(Boolean, default=True)
    data_conclusao = Column(DateTime, default=datetime.utcnow)

    usuario = relationship("Usuario")
    pasta = relationship("Pasta")
    aula = relationship("Aula")
