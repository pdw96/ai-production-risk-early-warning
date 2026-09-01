from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import DATABASE_URL


class Base(DeclarativeBase):
    """모든 ORM 모델의 공통 베이스 클래스."""


engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def create_all() -> None:
    """등록된 모든 ORM 테이블을 생성한다."""
    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_session() -> Generator[Session, None, None]:
    """요청 단위 SQLite 세션을 제공한다."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
