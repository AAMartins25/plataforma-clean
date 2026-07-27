from sqlalchemy import DateTime
from sqlalchemy import Date
from datetime import datetime 
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Table, ForeignKey, Text
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.postgresql import JSONB 
from sqlalchemy import UniqueConstraint

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

    publicado = Column(
        Boolean,
        default=False,
        nullable=False
    )

    descricao_publica = Column(Text, nullable=True)

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
        
    disponivel_demonstracao = Column(
        Boolean,
        default=False,
        nullable=False
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
    assunto_id = Column(Integer, ForeignKey("assuntos.id"), nullable=True)

    curso_assunto_proprio_id = Column(
        Integer,
        ForeignKey("curso_assuntos_proprios.id", ondelete="CASCADE"),
        nullable=True
    )

    tipo = Column(String(50), nullable=False)   # TEORIA / INTERATIVIDADE
    nome = Column(String(255), nullable=False)  # "Teoria + Questões" / "Interatividade"

    assunto = relationship("Assunto", backref="pastas")

    curso_assunto_proprio = relationship(
        "CursoAssuntoProprio",
        backref="pastas"
    )

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
    status = Column(String(20), default="EM_ANDAMENTO")
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

    tipo_questao = Column(String, nullable=True)
    quantidade_alternativas = Column(Integer, nullable=True)
    gabarito = Column(String, nullable=True)
    comentario = Column(Text, nullable=True)

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

    tentativas_login = Column(
        Integer,
        nullable=False,
        default=0
    )

    bloqueado_login = Column(
        Boolean,
        nullable=False,
        default=False
    )

    perfil_inicial = Column(
        String(20),
        nullable=False,
        default="ALUNO"
    )

    data_nascimento = Column(
        Date,
        nullable=True
    )

    criado_em = Column(DateTime, default=datetime.utcnow)

from sqlalchemy import DateTime
from datetime import datetime

class TokenRecuperacaoSenha(Base):
    __tablename__ = "tokens_recuperacao_senha"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    usuario_id = Column(
        Integer,
        ForeignKey(
            "usuarios.id",
            ondelete="CASCADE"
        ),
        nullable=False,
        index=True
    )

    token_hash = Column(
        String(64),
        unique=True,
        nullable=False,
        index=True
    )

    expira_em = Column(
        DateTime,
        nullable=False
    )

    usado = Column(
        Boolean,
        nullable=False,
        default=False
    )

    criado_em = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    usado_em = Column(
        DateTime,
        nullable=True
    )

    usuario = relationship(
        "Usuario"
    )

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
    
    atualizado_em = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    aprovado_em = Column(
        DateTime,
        nullable=True
    )

    usuario = relationship("Usuario")
    curso = relationship("Curso")

    tempo_acesso_id = Column(
        Integer,
        ForeignKey("tempo_acesso_curso.id"),
        nullable=True
    )

    qr_code_id = Column(
        Integer,
        ForeignKey("qr_codes.id"),
        nullable=True
    )

    vendedor_id = Column(
        Integer,
        ForeignKey("vendedores.id"),
        nullable=True
    )

    codigo_cupom = Column(
        String(5),
        nullable=True
    )

    tempo_acesso = relationship("TempoAcessoCurso")
    qr_code = relationship("QRCode")
    vendedor = relationship("Vendedor")

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

class Atendimento(Base):
    __tablename__ = "atendimentos"

    id = Column(Integer, primary_key=True, index=True)

    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)

    assunto = Column(Text, nullable=False)

    mensagem = Column(Text, nullable=False)

    status = Column(String, default="ABERTO")

    resposta_admin = Column(Text, nullable=True)

    respondido_em = Column(DateTime, nullable=True)

    criado_em = Column(DateTime, default=datetime.utcnow)


    atualizado_em = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    usuario = relationship("Usuario")

class CursoDisciplinaPropria(Base):
    __tablename__ = "curso_disciplinas_proprias"

    id = Column(Integer, primary_key=True, index=True)

    curso_id = Column(
        Integer,
        ForeignKey("cursos.id", ondelete="CASCADE"),
        nullable=False
    )

    nome = Column(String, nullable=False)

    ativo = Column(Boolean, default=True)

    ordem = Column(Integer, default=1)

    disponivel_demonstracao = Column(
        Boolean,
        default=False,
        nullable=False
    )

    criado_em = Column(DateTime, default=datetime.utcnow)

    atualizado_em = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    
class CursoAssuntoProprio(Base):
    __tablename__ = "curso_assuntos_proprios"

    id = Column(Integer, primary_key=True, index=True)

    curso_disciplina_propria_id = Column(
        Integer,
        ForeignKey("curso_disciplinas_proprias.id", ondelete="CASCADE"),
        nullable=False
    )

    nome = Column(String, nullable=False)

    descricao = Column(Text, nullable=True)

    ativo = Column(Boolean, default=True)

    ordem = Column(Integer, default=1)

    criado_em = Column(DateTime, default=datetime.utcnow)

    atualizado_em = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

class RespostaAlunoQuestao(Base):
    __tablename__ = "respostas_aluno_questoes"

    id = Column(Integer, primary_key=True, index=True)

    tentativa_id = Column(
        Integer,
        ForeignKey("tentativas_bateria.id"),
        nullable=True
    )

    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    questao_id = Column(Integer, ForeignKey("questoes.id"), nullable=False)
    bateria_id = Column(Integer, ForeignKey("baterias.id"), nullable=False)

    resposta_marcada = Column(String, nullable=True)
    gabarito = Column(String, nullable=True)

    dificuldade = Column(String, nullable=True)
    acertou = Column(Boolean, nullable=True)
    pulou = Column(Boolean, default=False)
    rever = Column(Boolean, default=False)

    respondida = Column(Boolean, default=True)
    finalizada = Column(Boolean, default=True)
    em_revisao = Column(Boolean, default=False)

    criada_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow)

    tentativa = relationship("TentativaBateria")
    usuario = relationship("Usuario")
    questao = relationship("Questao")
    bateria = relationship("Bateria")

class TentativaBateria(Base):
    __tablename__ = "tentativas_bateria"

    id = Column(Integer, primary_key=True, index=True)

    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    bateria_id = Column(Integer, ForeignKey("baterias.id"), nullable=False)

    status = Column(String(20), default="EM_ANDAMENTO", nullable=False)
    percentual_acerto = Column(Integer, default=0)

    iniciada_em = Column(DateTime, default=datetime.utcnow)
    concluida_em = Column(DateTime, nullable=True)
    revisao_concluida_em = Column(DateTime, nullable=True)

    ativo = Column(Boolean, default=True)

class RevisaoAluno(Base):
    __tablename__ = "revisoes_aluno"

    id = Column(Integer, primary_key=True, index=True)

    usuario_id = Column(
        Integer,
        ForeignKey("usuarios.id"),
        nullable=False
    )

    aula_id = Column(
        Integer,
        ForeignKey("aulas.id"),
        nullable=False
    )

    pasta_id = Column(
        Integer,
        ForeignKey("pastas.id"),
        nullable=False
    )

    etapa = Column(Integer, default=1)

    data_prevista = Column(DateTime, nullable=False)

    concluida = Column(Boolean, default=False)

    criada_em = Column(DateTime, default=datetime.utcnow)

    usuario = relationship("Usuario")
    aula = relationship("Aula")
    pasta = relationship("Pasta")

class AnotacaoAlunoQuestao(Base):
    __tablename__ = "anotacoes_aluno_questao"

    id = Column(Integer, primary_key=True, index=True)

    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    questao_id = Column(Integer, ForeignKey("questoes.id"), nullable=False)
    bateria_id = Column(Integer, ForeignKey("baterias.id"), nullable=False)

    texto = Column(Text, nullable=False)

    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    usuario = relationship("Usuario")
    questao = relationship("Questao")
    bateria = relationship("Bateria")

class ConversaQuestaoProfessor(Base):
    __tablename__ = "conversas_questao_professor"

    id = Column(Integer, primary_key=True, index=True)

    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    questao_id = Column(Integer, ForeignKey("questoes.id"), nullable=False)
    bateria_id = Column(Integer, ForeignKey("baterias.id"), nullable=False)

    status = Column(String(20), default="ABERTA")  # ABERTA / ENCERRADA

    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    usuario = relationship("Usuario")
    questao = relationship("Questao")
    bateria = relationship("Bateria")


class MensagemConversaQuestao(Base):
    __tablename__ = "mensagens_conversa_questao"

    id = Column(Integer, primary_key=True, index=True)

    conversa_id = Column(
        Integer,
        ForeignKey("conversas_questao_professor.id"),
        nullable=False
    )

    autor = Column(String(20), nullable=False)  # ALUNO / PROFESSOR
    texto = Column(Text, nullable=False)

    criada_em = Column(DateTime, default=datetime.utcnow)

    conversa = relationship("ConversaQuestaoProfessor", backref="mensagens")

class QuestaoPraticaAssunto(Base):
    __tablename__ = "questoes_pratica_assunto"

    id = Column(Integer, primary_key=True, index=True)

    curso_assunto_proprio_id = Column(
        Integer,
        ForeignKey("curso_assuntos_proprios.id", ondelete="CASCADE"),
        nullable=False
    )

    tipo = Column(String(20), nullable=False)
    # MULTIPLA ou CERTO_ERRADO

    enunciado = Column(Text, nullable=False)

    gabarito = Column(String(5), nullable=False)

    comentario = Column(Text, nullable=True)

    ativo = Column(Boolean, default=True)

    criado_em = Column(
        DateTime,
        default=datetime.utcnow
    )

    atualizado_em = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

class AlternativaQuestaoPratica(Base):
    __tablename__ = "alternativas_questao_pratica"

    id = Column(Integer, primary_key=True, index=True)

    questao_pratica_id = Column(
        Integer,
        ForeignKey(
            "questoes_pratica_assunto.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )

    letra = Column(String(1), nullable=False)

    texto = Column(Text, nullable=False)

class RespostaQuestaoPratica(Base):
    __tablename__ = "respostas_questao_pratica"

    id = Column(Integer, primary_key=True, index=True)

    usuario_id = Column(
        Integer,
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False
    )

    questao_pratica_id = Column(
        Integer,
        ForeignKey(
            "questoes_pratica_assunto.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )

    resposta_marcada = Column(
        String(5),
        nullable=True
    )

    acertou = Column(
        Boolean,
        nullable=False
    )

    dificuldade = Column(
        String(20),
        nullable=True
    )
    # FACIL
    # MEDIA
    # DIFICIL

    rever = Column(
        Boolean,
        default=False
    )

    criada_em = Column(
        DateTime,
        default=datetime.utcnow
    )

class QuestaoPraticaMarcacaoAluno(Base):
    __tablename__ = "questoes_pratica_marcacoes_aluno"

    id = Column(Integer, primary_key=True, index=True)

    usuario_id = Column(
        Integer,
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False
    )

    questao_id = Column(
        Integer,
        ForeignKey("questoes_pratica_assunto.id", ondelete="CASCADE"),
        nullable=False
    )

    dificuldade_marcada = Column(String(20), nullable=True)

    acertou = Column(Boolean, nullable=True)

    criado_em = Column(DateTime, default=datetime.utcnow)

    atualizado_em = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    usuario = relationship("Usuario")
    questao = relationship("QuestaoPraticaAssunto")

    rever = Column(Boolean, default=False, nullable=False)
    nao_soube = Column(Boolean, default=False, nullable=False)

class QuestaoPraticaRotatividadeAluno(Base):
    __tablename__ = "questoes_pratica_rotatividade_aluno"

    id = Column(Integer, primary_key=True, index=True)

    usuario_id = Column(
        Integer,
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False
    )

    curso_assunto_proprio_id = Column(
        Integer,
        ForeignKey("curso_assuntos_proprios.id", ondelete="CASCADE"),
        nullable=False
    )

    questao_id = Column(
        Integer,
        ForeignKey("questoes_pratica_assunto.id", ondelete="CASCADE"),
        nullable=False
    )

    filtro = Column(String(20), nullable=False, default="TODAS")

    ciclo = Column(Integer, nullable=False, default=1)

    respondida_em = Column(DateTime, default=datetime.utcnow)

    usuario = relationship("Usuario")
    questao = relationship("QuestaoPraticaAssunto")

class QuestaoPraticaAlternativa(Base):
    __tablename__ = "questoes_pratica_alternativas"

    id = Column(Integer, primary_key=True, index=True)

    questao_pratica_id = Column(
        Integer,
        ForeignKey("questoes_pratica_assunto.id", ondelete="CASCADE"),
        nullable=False
    )

    letra = Column(String(1), nullable=False)

    texto = Column(Text, nullable=False)

    correta = Column(Boolean, default=False, nullable=False)

    criado_em = Column(DateTime, default=datetime.utcnow)

    atualizado_em = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    questao = relationship("QuestaoPraticaAssunto")

class TempoAcessoCurso(Base):
    __tablename__ = "tempo_acesso_curso"

    __table_args__ = (
        UniqueConstraint("curso_id", "meses", name="uq_tempo_acesso_curso"),
    )

    id = Column(Integer, primary_key=True, index=True)

    curso_id = Column(Integer, ForeignKey("cursos.id"), nullable=False)

    meses = Column(Integer, nullable=False)
    valor_cents = Column(Integer, nullable=False)

    ativo = Column(Boolean, default=True)

    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    curso = relationship("Curso")

class DemonstracaoCurso(Base):
    __tablename__ = "demonstracoes_curso"

    id = Column(Integer, primary_key=True, index=True)

    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    curso_id = Column(Integer, ForeignKey("cursos.id"), nullable=False)

    data_inicio = Column(DateTime, default=datetime.utcnow)
    data_fim = Column(DateTime, nullable=False)

    liberado_novamente_em = Column(DateTime, nullable=False)

    ativo = Column(Boolean, default=True)

    criado_em = Column(DateTime, default=datetime.utcnow)

    usuario = relationship("Usuario")
    curso = relationship("Curso")

class Vendedor(Base):
    __tablename__ = "vendedores"

    id = Column(Integer, primary_key=True, index=True)

    nome = Column(String(255), nullable=False)

    email = Column(
        String(255),
        nullable=True,
        index=True
    )

    telefone = Column(
        String(30),
        nullable=True
    )

    cpf_cnpj = Column(
        String(20),
        nullable=True,
        index=True
    )

    estado_uf = Column(
        String(2),
        nullable=True
    )

    cidade = Column(
        String(255),
        nullable=True
    )

    ativo = Column(
        Boolean,
        default=True,
        nullable=False
    )

    criado_em = Column(
        DateTime,
        default=datetime.utcnow
    )

    atualizado_em = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    usuario_id = Column(
        Integer,
        ForeignKey("usuarios.id"),
        nullable=True,
        unique=True
    )

    descredenciado_em = Column(
        DateTime,
        nullable=True
    )

    data_nascimento = Column(
        Date,
        nullable=True
    )

    usuario = relationship("Usuario")

class QRCode(Base):
    __tablename__ = "qr_codes"

    id = Column(Integer, primary_key=True, index=True)

    codigo = Column(
        String(100),
        unique=True,
        nullable=False,
        index=True
    )

    vendedor_id = Column(
        Integer,
        ForeignKey("vendedores.id"),
        nullable=True
    )

    ativo = Column(
        Boolean,
        default=True,
        nullable=False
    )

    criado_em = Column(
        DateTime,
        default=datetime.utcnow
    )

    atualizado_em = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    vendedor = relationship("Vendedor")

class CupomDesconto(Base):
    __tablename__ = "cupons_desconto"

    id = Column(Integer, primary_key=True, index=True)

    codigo = Column(
        String(5),
        unique=True,
        nullable=False,
        index=True
    )

    vendedor_id = Column(
        Integer,
        ForeignKey("vendedores.id"),
        nullable=True
    )

    percentual_desconto = Column(
        Integer,
        nullable=False,
        default=12
    )

    ativo = Column(
        Boolean,
        nullable=False,
        default=True
    )

    criado_em = Column(
        DateTime,
        default=datetime.utcnow
    )

    atualizado_em = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    vendedor = relationship("Vendedor")