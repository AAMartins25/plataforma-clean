from urllib.parse import quote_plus
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base

DB_USER = "postgres"
DB_PASSWORD = quote_plus("aROSE@23")  # mantém seguro mesmo com ç, @, etc.
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "plataforma"

DATABASE_URL = f"postgresql+psycopg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

