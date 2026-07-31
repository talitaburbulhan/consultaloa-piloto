from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings
from .database import Base
from .models import AuditLog, Feedback, SavedQuery


settings = get_settings()
database_url = settings.feedback_database_url or settings.database_url
if database_url.startswith("postgresql://"):
    database_url = "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
elif database_url.startswith("postgres://"):
    database_url = "postgresql+psycopg://" + database_url.removeprefix("postgres://")
connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
engine = create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def create_feedback_schema() -> None:
    Base.metadata.create_all(
        engine,
        tables=[Feedback.__table__, AuditLog.__table__, SavedQuery.__table__],
    )


def get_feedback_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
