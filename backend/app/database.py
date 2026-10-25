import os
from urllib.parse import parse_qs, quote_plus, unquote, urlsplit
from app.financeiro_transacional import configuracao_pool
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker
from app.models import Base, TABELAS_JURIDICAS

# 1. Busca a URL da nuvem injetada pelo GitHub
ENV_DATABASE_URL = os.environ.get("DATABASE_URL")

is_cloud = False

def _url_psycopg(valor):
    # urlsplit não decodifica credenciais; URL.create recebe valores já decodificados.
    # Passar o objeto URL evita uma segunda interpretação de %, @, + e outros sinais.
    parsed = urlsplit(valor)
    query = {
        chave: valores[0] if len(valores) == 1 else tuple(valores)
        for chave, valores in parse_qs(parsed.query, keep_blank_values=True).items()
        if chave != "pgbouncer"
    }
    return URL.create(
        "postgresql+psycopg",
        username=unquote(parsed.username) if parsed.username is not None else None,
        password=unquote(parsed.password) if parsed.password is not None else None,
        host=parsed.hostname,
        port=parsed.port,
        database=unquote(parsed.path[1:]),
        query=query,
    )


if ENV_DATABASE_URL:
    is_cloud = True
    DATABASE_URL = _url_psycopg(ENV_DATABASE_URL)
else:
    # Configuração para a sua MÁQUINA LOCAL (Em casa)
    DB_USER = "postgres"
    DB_PASSWORD = quote_plus("aROSE@23")
    DB_HOST = "localhost"
    DB_PORT = "5432"
    DB_NAME = "plataforma"
    
    DATABASE_URL = f"postgresql+psycopg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# 2. Criação do Engine do SQLAlchemy
# Se estiver na nuvem usando PgBouncer, configuramos o driver para não usar prepared statements
if is_cloud:
    engine = create_engine(
        DATABASE_URL,
        **configuracao_pool(),
        connect_args={"prepare_threshold": None, "connect_timeout": 5}
    )
else:
    engine = create_engine(DATABASE_URL)

# 3. Configuração da Sessão
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 4. Garante a criação/verificação das tabelas ao iniciar
if os.getenv("AMBIENTE_TESTE") != "1":
    Base.metadata.create_all(bind=engine, tables=[
        tabela for tabela in Base.metadata.sorted_tables
        if tabela.name not in TABELAS_JURIDICAS
    ])
