import os
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./belavista.db")

if DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://"):
    raise RuntimeError(
        "Este deploy está configurado para usar apenas SQLite. "
        "Ajuste DATABASE_URL para algo como sqlite:////var/data/belavista.db (Render) "
        "ou sqlite:///./belavista.db (local)."
    )

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


@contextmanager
def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
