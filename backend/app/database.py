import os
from urllib.parse import quote_plus, urlparse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base

# 1. Busca a URL da nuvem injetada pelo GitHub
ENV_DATABASE_URL = os.environ.get("DATABASE_URL")

is_cloud = False

if ENV_DATABASE_URL:
    is_cloud = True
    # Corrige o prefixo exigido pelo SQLAlchemy moderno
    if ENV_DATABASE_URL.startswith("postgres://"):
        ENV_DATABASE_URL = ENV_DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    try:
        # Remove parâmetros conflitantes com o driver Psycopg3
        if "?pgbouncer=true" in ENV_DATABASE_URL:
            ENV_DATABASE_URL = ENV_DATABASE_URL.replace("?pgbouncer=true", "")
        elif "&pgbouncer=true" in ENV_DATABASE_URL:
            ENV_DATABASE_URL = ENV_DATABASE_URL.replace("&pgbouncer=true", "")
            
        # Extrai os componentes da URL para codificar a senha com segurança
        parsed_url = urlparse(ENV_DATABASE_URL)
        username = parsed_url.username
        password = parsed_url.password
        
        if password:
            # Codifica caracteres especiais contidos na senha nova
            safe_password = quote_plus(password)
            # Reconstroi o host de forma limpa
            host_port_db = parsed_url.netloc.split('@')[-1]
            path_query = parsed_url.path
            if parsed_url.query:
                path_query += f"?{parsed_url.query}"
                
            DATABASE_URL = f"postgresql+psycopg://{username}:{safe_password}@{host_port_db}{path_query}"
        else:
            DATABASE_URL = ENV_DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
    except Exception:
        DATABASE_URL = ENV_DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
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
        connect_args={"prepare_threshold": None}
    )
else:
    engine = create_engine(DATABASE_URL)

# 3. Configuração da Sessão
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 4. Garante a criação/verificação das tabelas ao iniciar
Base.metadata.create_all(bind=engine)