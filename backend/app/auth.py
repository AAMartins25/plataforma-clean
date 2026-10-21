from datetime import datetime, timedelta
from typing import Optional
import os
from jose import jwt, JWTError
from passlib.context import CryptContext


def _carregar_secret_key():
    value = os.environ.get("SECRET_KEY")
    # Comprimento não prova entropia: a chave deve ser gerada aleatoriamente.
    if (not value or len(value) < 32 or not value.isascii()
            or any(not 33 <= ord(char) <= 126 for char in value)):
        raise RuntimeError(
            "SECRET_KEY ausente ou inadequada. Configure uma chave aleatória "
            "com pelo menos 32 caracteres ASCII imprimíveis, sem espaços."
        )
    return value


SECRET_KEY = _carregar_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 dia

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def hash_senha(senha: str) -> str:
    return pwd_context.hash(senha)

def verificar_senha(senha: str, senha_hash: str) -> bool:
    return pwd_context.verify(senha, senha_hash)

def criar_token(data: dict, expires_minutes: Optional[int] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes or ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decodificar_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return {}

