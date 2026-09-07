import sqlite3
from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import DATABASE_URL


class Base(DeclarativeBase):
    """모든 ORM 모델의 공통 베이스 클래스."""


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
    """SQLite 연결마다 외래키 강제를 켠다.

    SQLite는 기본적으로 외래키를 검사하지 않는다. 켜지 않으면 모델의
    `ForeignKey` 선언이 문서일 뿐이어서, 존재하지 않는 대상을 가리키는 행이
    그대로 저장된다. 검사 기록처럼 대상이 유형마다 다른 테이블에서는 그런 행이
    조회 시 모든 관계를 `None` 으로 만들어, 대상 표기를 만드는 코드가 터진다.

    엔진 클래스에 걸어 두어 앱 엔진과 테스트가 따로 만드는 엔진에 모두 적용된다.
    SQLite 연결일 때만 실행한다.
    """
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


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
