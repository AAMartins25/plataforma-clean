import os
from urllib.parse import quote_plus
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base

# 1. O Codespaces/GitHub injetará a variável 'DATABASE_URL' automaticamente na nuvem.
#    Se a variável não existir (como na sua máquina local em casa), ele usará None.
ENV_DATABASE_URL = os.environ.get("DATABASE_URL")

if ENV_DATABASE_URL:
    # Configuração para a NUVEM (Supabase + Codespaces)
    
    # O Supabase fornece a URI começando com "postgres://". 
    # O SQLAlchemy moderno exige que comece com "postgresql://"
    if ENV_DATABASE_URL.startswith("postgres://"):
        ENV_DATABASE_URL = ENV_DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    # Se você for usar o driver Psycopg3 na nuvem, adicionamos '+psycopg' à URL
    if "postgresql+psycopg" not in ENV_DATABASE_URL:
        ENV_DATABASE_URL = ENV_DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
        
    DATABASE_URL = ENV_DATABASE_URL
else:
    # Configuração para a sua MÁQUINA LOCAL (Em casa)
    DB_USER = "postgres"
    DB_PASSWORD = quote_plus("aROSE@23")
    DB_HOST = "localhost"
    DB_PORT = "5432"
    DB_NAME = "plataforma"
    
    DATABASE_URL = f"postgresql+psycopg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# 2. Criação do Engine do SQLAlchemy
engine = create_engine(DATABASE_URL)

# 3. Configuração da Sessão
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 4. Garante a criação/verificação das tabelas ao iniciar
Base.metadata.create_all(bind=engine)