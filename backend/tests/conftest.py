"""검사가 **설정이 가리키는 엔진**에서 돌게 하는 공용 픽스처.

## 왜 이 파일이 생겼나

CI 는 백엔드 검사를 두 번 돌린다 — `DATABASE_URL` 에 PostgreSQL 을 물려 한 번,
빈 값으로 주어 SQLite 로 한 번. 그런데 검사의 큰 몫이 **그 설정을 보지 않는다.**
스스로 SQLite 엔진을 만들어 `db_base` 에 물리므로, 두 번 돌려도 그 검사들은
**같은 엔진을 두 번** 볼 뿐이다. 실측(2026-09-09, `main` `c6ebb4e`,
`pytest --collect-only -q`): 286개 중 178개(62%)가 그랬다.

`test_live_engine.py` 의 주석이 그 값을 이미 적어 두었다 — PR #15 리뷰에서
엔드포인트에 PostgreSQL 전용 결함을 심었는데 PostgreSQL 묶음이 전부 초록이었다.

## 왜 monkeypatch 를 그냥 걷어내면 안 되나

그 검사들이 설정을 무시하는 것은 실수가 아니다. 그것은 동시에 **개발자의
데이터베이스를 지키는 장치**다 — 그 검사들은 표를 지웠다 다시 만들므로, 설정이
가리키는 곳에 그대로 붙으면 로컬에서 한 번 돌리는 것만으로 데이터가 사라진다.

그래서 옳은 수는 안전장치를 **걷어내는 것이 아니라 옮기는 것**이다. 엔진은
설정이 가리키는 그것을 쓰되, 데이터베이스는 이번 실행에만 있는 것을 새로 만들어
거기에 붙는다. `test_live_engine.py` 가 이미 그렇게 돌고 있었고, 그 장치를
`tests/engines.py` 로 끌어올려 여기서 픽스처로 낸다.

`tests/factories.py` 와 같은 자리다 — 여러 검사가 나눠 쓰는 것은 모듈에 두고,
픽스처만 이 파일에 둔다. 픽스처가 아닌 것을 conftest 에 두면 다른 검사가
`from tests.conftest import ...` 로 끌어다 쓰게 되는데, 그때 pytest 가 이미
불러 둔 것과 **모듈이 둘이 된다.**
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import DATABASE_URL, is_sqlite
from app.db import base as db_base
from tests.engines import (
    drop_throwaway_database,
    make_throwaway_database,
    with_the_database_in_one_place,
)


@pytest.fixture(scope="module")
def throwaway_engine(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[sa.Engine]:
    """`DATABASE_URL` 의 **엔진**에 붙되, 데이터베이스는 이번 실행만의 것.

    표는 만들지 않는다. 표를 어떻게 세우는가는 검사마다 다르고(마이그레이션 ·
    `create_all` · 시드), 그 선택은 부르는 쪽의 것이다.

    모듈마다 하나씩 만든다. 실행마다 하나로 줄이면 `create_all` 로 표를 세우는
    검사와 마이그레이션으로 세우는 검사가 **같은 데이터베이스를 서로 지운다.**
    검사 하나마다 만들면 PostgreSQL 에서 `CREATE DATABASE` 가 그만큼 늘어난다.
    """
    sqlite = is_sqlite(DATABASE_URL)
    source = None
    if sqlite:
        # SQLite 의 일회용은 파일 하나다. 인메모리로 하지 않는 것은 이 픽스처를
        # 쓰는 검사가 접속을 여럿 열기 때문이다 — 인메모리는 접속마다 다른
        # 데이터베이스라 표를 만든 쪽과 읽는 쪽이 갈린다.
        path = tmp_path_factory.mktemp("throwaway") / "throwaway.db"
        url = make_url(f"sqlite:///{path.as_posix()}")
    else:
        source = with_the_database_in_one_place(make_url(DATABASE_URL))
        url = make_throwaway_database(source)

    # `db_base.engine` 과 같은 모양으로 만든다. 이 엔진에 `db_base` 를 물리는
    # 검사가 앱과 다른 접속 성질을 갖지 않게 하기 위해서다 — `check_same_thread`
    # 는 SQLite 드라이버에만 있는 인자이고, PostgreSQL 에 넘기면 접속이 아예
    # 열리지 않는다.
    engine = sa.create_engine(
        url,
        connect_args={"check_same_thread": False} if sqlite else {},
    )
    try:
        yield engine
    finally:
        # 만든 것을 **여기서** 치운다. 다음 실행의 앞머리에서 치우면 그 사이에
        # 남아 있고, 이름이 고정되어야만 찾을 수 있어서 이름을 고정하지 않기로
        # 한 이유가 되돌아온다.
        engine.dispose()
        if source is not None:
            drop_throwaway_database(source, url.database)


@pytest.fixture
def bound_engine(
    throwaway_engine: sa.Engine, monkeypatch: pytest.MonkeyPatch
) -> sa.Engine:
    """앱이 보는 엔진을 위의 일회용으로 갈아 끼운다.

    `db_base.engine` 과 `db_base.SessionLocal` 을 함께 건다. 하나만 걸면
    `drop_all`/`create_all` 과 세션이 **다른 데이터베이스**를 보게 된다.

    갈아 끼우는 행위 자체는 지금까지 각 검사가 하던 것과 같다. 달라진 것은
    갈아 끼우는 **대상**이다 — 손으로 만든 SQLite 가 아니라 설정이 가리키는
    엔진 위의 일회용이다. 안전장치는 그대로 서 있고, 엔진만 진짜가 된다.
    """
    monkeypatch.setattr(db_base, "engine", throwaway_engine)
    monkeypatch.setattr(
        db_base,
        "SessionLocal",
        sessionmaker(bind=throwaway_engine, autoflush=False, autocommit=False),
    )
    return throwaway_engine


@pytest.fixture
def bound_session_factory(bound_engine: sa.Engine) -> sessionmaker[Session]:
    """갈아 끼운 엔진에 붙는 세션 공장. 검사가 직접 읽을 때 쓴다."""
    return sessionmaker(bind=bound_engine)
