"""Apenas emula BTRIM de PostgreSQL nas fixtures SQLite. Nenhum patch de negócio."""
import sqlite3
from sqlalchemy import event
from sqlalchemy.engine import Engine
import pytest
import sys
@event.listens_for(Engine,'connect')
def suporte(conexao,_):
    if isinstance(conexao,sqlite3.Connection):
        conexao.create_function('BTRIM',1,lambda v:v.strip() if v is not None else None)
raise SystemExit(pytest.main(sys.argv[1:]))
