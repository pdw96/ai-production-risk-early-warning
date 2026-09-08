import sqlite3
from collections.abc import Generator
from typing import Any

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import DATABASE_URL, is_sqlite


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


# `check_same_thread` 는 SQLite 드라이버에만 있는 인자다. PostgreSQL 에 넘기면
# 연결이 아예 열리지 않는다.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if is_sqlite() else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def register_models() -> None:
    """모든 ORM 모듈을 불러와 메타데이터를 완전하게 만든다.

    기준정보와 거래 표가 서로 다른 모듈에 있으므로 둘 다 불러와야 한다. 하나만
    부르면 메타데이터가 반쪽이 되고, 그 반쪽으로 `drop_all` 을 부르면 **모르는
    표는 지워지지 않는다** — 다음 `create_all` 은 이미 있는 표를 조용히 건너뛰고,
    시드는 남아 있던 옛 행과 부딪힌다.
    """
    from app.db import master_data, models  # noqa: F401


def create_all() -> None:
    """등록된 모든 ORM 테이블을 생성한다."""
    register_models()
    Base.metadata.create_all(bind=engine)


# 이 앱이 예전에 쓰던 표 이름들. 지금 모델은 이 이름을 모르므로 메타데이터만
# 보고 지우면 **살아남는다** — 품목 통합 전의 `products` · `materials` ·
# `bom_requirements` 를 가진 데이터베이스에서 새 표가 그 옆에 생기고, 시드가
# 현재 리비전을 찍어 두므로 Alembic 도 영영 치우지 못한다. 옛 데이터를 든 표가
# 그대로 굳는 것을 막으려면 이름을 여기 적어 두는 수밖에 없다.
#
# 표 이름을 바꿀 때마다 옛 이름이 여기 한 줄 는다.
LEGACY_TABLE_NAMES: tuple[str, ...] = (
    "products",
    "materials",
    "bom_requirements",
)


def drop_all() -> None:
    """**이 앱이 만든 표만** 지운다 — 지금 것과 옛 것.

    데이터베이스 전체를 읽어 지우지 않는다. PostgreSQL 로 옮기면서 스키마를
    다른 것과 나눠 쓸 수 있게 됐고, 보이는 표를 전부 지우면 **옆에 있는 남의
    표까지 사라진다.** 개발용이라고 문서에 적어 두는 것으로는 막지 못한다 —
    한 번 실행하면 되돌릴 수 없기 때문이다.

    그래서 지울 것을 이름으로 정한다. 현재 모델의 표와 위의 옛 이름들, 그리고
    `alembic_version` 이다. 버전 표를 함께 지우는 것은 시드가 곧바로 다시 찍기
    때문이다.
    """
    register_models()
    owned = set(Base.metadata.tables) | set(LEGACY_TABLE_NAMES) | {"alembic_version"}

    existing = MetaData()
    # 이름으로 걸러 반사한다. 여기서 거른 표는 아래 `drop_all` 이 아예 보지 못한다.
    existing.reflect(bind=engine, only=lambda name, _metadata: name in owned)
    existing.drop_all(bind=engine)


def get_session() -> Generator[Session, None, None]:
    """요청 단위 SQLite 세션을 제공한다."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
