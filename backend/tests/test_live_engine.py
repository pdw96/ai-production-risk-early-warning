"""제약이 **무는지**를 실제 엔진에서 본다.

이 저장소의 다른 검사는 제약이 **서 있는지**를 본다 — `test_migrations.py` 는
방언별로 구워 낸 SQL 문자열을 견주고, `test_sql_portability.py` 는 기준정보
SQL 을 글자로 읽는다. 둘 다 데이터베이스를 열지 않는다.

서 있는 것과 무는 것은 다른 문제다. 문자열이 옳게 그려져도 그 문법이 그 엔진에
실제로 있는지, 그 표현이 그 엔진에서 같은 값을 내는지는 **돌려 봐야** 안다.
PR #10 에서 걸린 방언 결함 셋(`LIKE` 대소문자 · 불리언 칸의 `1` · `trim`/`btrim`)
이 전부 그 자리에서 나왔고, 셋 다 사람이 직접 컨테이너를 띄워서 잡았다.

그래서 이 파일만은 `DATABASE_URL` 이 가리키는 **그 엔진**에서 돈다. CI 가
PostgreSQL 을 물려 한 번, 아무것도 물리지 않아 SQLite 로 한 번 돌린다.

건드리는 데이터베이스는 **따로 만든 일회용**이다. 이 파일이 표를 지우고 다시
만들므로, 설정이 가리키는 데이터베이스를 그대로 쓰면 로컬에서 한 번 돌리는
것만으로 개발자의 데이터가 사라진다.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.config import (
    BACKEND_DIRECTORY,
    DATABASE_URL,
    FINISHED_ITEM,
    MASS_PRODUCTION_PHASE,
    QC_FAILED,
    QC_PASSED,
    is_sqlite,
)
from app.core import codes
from app.db.base import Base, register_models
from app.db.master_data_loader import load_master_data
from app.db.models import failure_reason_is_present


# 일회용 데이터베이스 이름의 앞부분. 뒤에는 **이번 실행에만 있는 값**이 붙는다.
THROWAWAY_PREFIX = "live_engine_"

# PostgreSQL 식별자의 상한. `NAMEDATALEN - 1` 이고, 넘기면 **조용히 잘린다.**
MAXIMUM_IDENTIFIER_BYTES = 63


def _throwaway_name(source: str | None) -> str:
    """상한 안에서 만들되, 이번 실행에만 있는 값은 **반드시 남긴다.**

    이름을 그냥 이어 붙이면 63바이트에서 잘리는데, 잘려 나가는 쪽이 하필 뒤에
    붙인 그 값이다. 설정된 데이터베이스 이름이 38바이트를 넘으면 고유한 꼬리가
    깎이기 시작하고, 63바이트짜리 이름이면 **잘린 결과가 원본 이름 그 자체**가
    되어 `CREATE DATABASE` 가 늘 「이미 있다」로 끝난다. 그보다 조금 짧으면 더
    나쁘다 — 나란히 도는 두 실행이 같은 이름을 얻고, 한쪽의 뒷정리가 다른 쪽이
    쓰고 있는 데이터베이스를 `WITH (FORCE)` 로 지운다.

    실측(2026-09-08, PostgreSQL 16.13): 63바이트 이름 뒤에 꼬리를 붙여 만들려
    하면 `NOTICE: identifier ... will be truncated` 에 이어
    `ERROR: database "aaa…" already exists` 가 났다.

    그래서 깎는 쪽을 **앞부분으로 바꾼다.** 앞부분은 읽는 사람을 위한 것이고,
    뒤의 값은 안전을 위한 것이다. 바이트로 자르므로 다중바이트 글자가 반 토막
    날 수 있어, 깨진 조각은 버린다.

    **앞부분은 없을 수도 있다.** `postgresql+psycopg://user@localhost` 처럼
    데이터베이스를 적지 않은 주소도 동작하는 주소이고(libpq 가 기본값으로 붙는다),
    그때 `url.database` 는 `None` 이다. 이름의 앞부분은 읽는 사람을 위한 것이므로
    없으면 없는 대로 짓는다 — 뒤의 값만 있으면 이 파일이 필요한 성질은 다 선다.
    """
    suffix = f"_{THROWAWAY_PREFIX}{uuid.uuid4().hex[:12]}"
    if not source:
        return suffix
    room = MAXIMUM_IDENTIFIER_BYTES - len(suffix.encode("utf-8"))
    stem = source.encode("utf-8")[:room].decode("utf-8", "ignore")
    return f"{stem}{suffix}"


def _with_the_database_in_one_place(url: sa.engine.URL) -> sa.engine.URL:
    """이름이 적힐 수 있는 두 자리를 **하나로 모은다.**

    psycopg 는 데이터베이스를 경로로도 받고 질의의 `dbname` 으로도 받는데,
    **질의 쪽이 이긴다.** 그래서 `url.set(database=...)` 로 갈아 끼운 이름은
    질의에 `dbname` 이 남아 있으면 아무 일도 하지 않는다 — 일회용 데이터베이스는
    만들어지되 엔진은 설정이 가리키는 **진짜 데이터베이스**에 붙고, 이 파일이
    표를 지우고 다시 만드는 동안 개발자의 데이터가 사라진다. 뒷정리는 쓰이지도
    않은 일회용 쪽을 지우므로 흔적조차 남지 않는다.

    실측(2026-09-08, SQLAlchemy 2.x · psycopg 3.3.5):
    `postgresql+psycopg:///?dbname=repro_real&host=...` 에 `set(database=...)` 를
    걸어도 `create_connect_args` 가 내는 `dbname` 은 `repro_real` 이었고, 그
    엔진으로 붙어 `current_database()` 를 물으니 `repro_real` 이었다. 그 자리에서
    남의 표가 보였고, 지워졌다.

    앞선 「경로가 빈 주소」 고침은 이 경우를 덮지 못한다. 그쪽은 이름이 **없는**
    주소였고, 이쪽은 이름이 **다른 자리에 있는** 주소다.

    그래서 붙기 전에 질의의 `dbname` 을 경로로 옮긴다. 이 뒤로는 이름이 한
    자리에만 있으므로, 갈아 끼우는 것도 읽는 것도 그 한 자리를 보면 된다.
    """
    dbname = url.query.get("dbname")
    if dbname is None:
        return url
    # 같은 열쇠가 여러 번 오면 SQLAlchemy 는 튜플로 준다. libpq 는 마지막 것을
    # 쓰므로 여기서도 마지막 것을 택한다.
    if isinstance(dbname, tuple):
        dbname = dbname[-1]
    query = {key: value for key, value in url.query.items() if key != "dbname"}
    return url.set(query=query, database=dbname)


def _admin_engine(url: sa.engine.URL) -> sa.Engine:
    """일회용 데이터베이스를 만들고 지울 때 붙는 관리용 접속.

    **설정이 가리키는 데이터베이스에 그대로 붙는다.** 관례를 믿고 `postgres` 로
    갈아타지 않는다 — 그 데이터베이스는 지워졌을 수도, 이 역할의 `CONNECT` 가
    회수됐을 수도 있다. 그러면 앱 주소는 멀쩡한데 이 검사만 시작조차 못 한다.
    만들려는 것은 **다른 이름**이므로 여기 붙어 있어도 부딪히지 않는다.
    """
    return sa.create_engine(url, isolation_level="AUTOCOMMIT")


def _quoted(engine: sa.Engine, identifier: str) -> str:
    """식별자를 그 방언의 규칙으로 감싼다.

    이름은 **밖에서 오는 값**이다(설정 주소에서 왔다). 큰따옴표가 들어 있으면
    따옴표 사이에 그대로 끼워 넣은 SQL 이 깨져, 마이그레이션에 닿기도 전에
    이 픽스처가 죽는다. 이미 안전한 것으로 다루지 않는다.
    """
    return engine.dialect.identifier_preparer.quote(identifier)


def _make_throwaway_database(url: sa.engine.URL) -> sa.engine.URL:
    """이번 실행만의 데이터베이스를 새로 만든다.

    이름을 **고정하지 않는다.** 고정하면 그 이름은 설정 주소에서 기계적으로
    나오므로 미리 알 수 있고, 그러면 이 검사가 남의 것을 지울 수 있다 —
    같은 이름의 데이터베이스가 이미 있었다면 그것을, 옆에서 돌던 또 다른 실행이
    쓰고 있었다면 그 접속까지 끊어서. 로컬 준비가 역할에 `SUPERUSER` 를 주므로
    막아 줄 권한 경계도 없다.

    그래서 이름에 이번 실행에만 있는 값을 붙이고, **만들기만 한다** —
    `DROP ... IF EXISTS` 로 앞길을 치우지 않는다. 부딪히면 지우는 것이 아니라
    거기서 터지는 것이 맞다.
    """
    throwaway = _throwaway_name(url.database)
    admin = _admin_engine(url)
    try:
        with admin.connect() as connection:
            connection.execute(
                sa.text(f"CREATE DATABASE {_quoted(admin, throwaway)}")
            )
    finally:
        admin.dispose()
    # 주소를 **객체로** 돌려준다. `str(URL)` 은 비밀번호를 `***` 로 가리므로,
    # 문자열로 만들어 넘기면 그 별표가 그대로 비밀번호가 되어 접속이 거부된다.
    return url.set(database=throwaway)


def _drop_throwaway_database(source: sa.engine.URL, throwaway: str) -> None:
    """이번 실행이 만든 것만 지운다.

    `WITH (FORCE)` 를 쓰는 것은 여기서는 안전하다 — 지우는 대상이 방금 이
    실행이 만든 이름이라 남의 접속이 붙어 있을 수 없다.
    """
    admin = _admin_engine(source)
    try:
        with admin.connect() as connection:
            connection.execute(
                sa.text(
                    f"DROP DATABASE IF EXISTS {_quoted(admin, throwaway)} WITH (FORCE)"
                )
            )
    finally:
        admin.dispose()


@pytest.fixture(scope="module")
def live_engine(tmp_path_factory: pytest.TempPathFactory) -> sa.Engine:
    """운영이 실제로 타는 길 그대로 만든 데이터베이스에 붙는다.

    `create_all` 이 아니라 **마이그레이션**으로 표를 만든다. 운영과 컨테이너가
    오는 길이 그쪽이고, 지금까지 CI 는 그 길을 한 번도 밟지 않았다 —
    `create_all` 로 만든 표가 옳다고 해서 마이그레이션이 만든 표가 옳은 것은
    아니다. 여기서 마이그레이션이 이 엔진의 문법으로 서지 못하면 그 자리에서
    터진다.
    """
    register_models()
    sqlite = is_sqlite(DATABASE_URL)
    source = None
    if sqlite:
        path = tmp_path_factory.mktemp("live-engine") / "throwaway.db"
        url = make_url(f"sqlite:///{path.as_posix()}")
    else:
        source = _with_the_database_in_one_place(make_url(DATABASE_URL))
        url = _make_throwaway_database(source)
    engine = sa.create_engine(url)

    # **만든 직후부터** 치우는 약속 안에 있어야 한다. 마이그레이션을 밖에 두면
    # 그것이 터질 때 데이터베이스가 남는데, 하필 **그 실패가 이 픽스처가 드러내려는
    # 것**이다 — 한 엔진의 문법이 마이그레이션에 굳으면 여기서 터진다. 실패할수록
    # 고아가 쌓이는 구조였다.
    try:
        config = Config(str(BACKEND_DIRECTORY / "alembic.ini"))
        config.set_main_option(
            "script_location", str(BACKEND_DIRECTORY / "migrations")
        )
        # 주소가 아니라 연결을 넘긴다. 주소만 넘기면 `env.py` 가 설정의
        # `DATABASE_URL` 로 새 엔진을 열어 **진짜 데이터베이스**를 고친다.
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        yield engine
    finally:
        # 만든 것을 **여기서** 치운다. 다음 실행의 앞머리에서 치우면 그 사이에
        # 남아 있고, 이름이 고정되어야만 찾을 수 있어서 위의 위험이 되돌아온다.
        engine.dispose()
        if source is not None:
            _drop_throwaway_database(source, url.database)


@pytest.fixture(scope="module")
def seeded_engine(live_engine: sa.Engine) -> sa.Engine:
    """기준정보 SQL 을 **이 엔진에 실제로 넣은** 상태.

    `test_sql_portability.py` 는 같은 파일을 글자로 읽는다. 글자 검사가 통과해도
    엔진이 받아 준다는 보장은 없다 — 컬럼 목록 없는 `INSERT` 처럼 그 검사가
    아예 보지 못하는 모양이 있고, SQLite 는 불리언 칸의 정수를 받고 PostgreSQL 은
    거부한다. 넣어 보는 것만이 그 차이를 드러낸다.
    """
    from sqlalchemy.orm import Session

    with Session(live_engine) as session:
        load_master_data(session)
        session.commit()
    return live_engine


def _insert_item(connection: sa.Connection, code: str, item_type: str) -> None:
    connection.execute(
        sa.insert(Base.metadata.tables["items"]).values(
            code=code,
            name="일회용 품목",
            item_type=item_type,
            process=None,
            process_group=codes.PROCESS,
            stock_uom="EA",
            stock_uom_group=codes.UOM,
            phase=MASS_PRODUCTION_PHASE,
            safety_stock=1.0,
        )
    )


def test_the_migration_path_builds_every_table_on_this_engine(
    live_engine: sa.Engine,
) -> None:
    """운영이 오는 길로 만든 표가 모델의 표를 모두 갖고 있어야 한다.

    지금까지 CI 는 `python -m app.seed`(= `drop_all`/`create_all`)만 돌렸다.
    그 길이 초록이어도 `alembic upgrade head` 는 다른 SQL 을 낸다 — 한 엔진의
    문법이 마이그레이션에 굳어 있으면 여기서 표가 서지 않는다.
    """
    register_models()
    present = set(sa.inspect(live_engine).get_table_names())

    assert set(Base.metadata.tables) <= present
    assert "alembic_version" in present


def test_the_master_data_files_load_into_this_engine(seeded_engine: sa.Engine) -> None:
    """기준정보가 이 엔진에 실제로 들어가야 한다.

    불리언 칸에 `1` 이 들어 있으면 PostgreSQL 이 여기서 거부한다. 시드 전체가
    트랜잭션 하나라 그때 실패하는 것은 그 문장 하나가 아니라 **기준정보 전부**다.
    """
    with seeded_engine.connect() as connection:
        code_groups = connection.execute(
            sa.select(sa.func.count()).select_from(
                Base.metadata.tables["code_groups"]
            )
        ).scalar_one()
        items = connection.execute(
            sa.select(sa.func.count()).select_from(Base.metadata.tables["items"])
        ).scalar_one()

    assert code_groups > 0
    assert items > 0


def test_an_endpoint_reads_this_engine_through_the_application_query_path(
    seeded_engine: sa.Engine,
) -> None:
    """엔드포인트 하나가 **이 엔진에** 실제로 질의한다.

    이 파일의 나머지는 제약과 표현을 SQL 로 직접 견준다. 그런데 화면이 타는
    길은 **라우터 → ORM** 이고, PR #10 에서 걸린 방언 결함 셋(`LIKE` 대소문자 ·
    불리언 칸의 정수 · `trim`/`btrim`)은 전부 그 길에서 났다.

    그 길이 PostgreSQL 에서 밟히지 않고 있었다. `test_api.py` 는 스스로
    `sqlite://` 엔진을 만들어 `db_base` 에 물리므로 `DATABASE_URL` 을 무엇으로
    주든 SQLite 로 돈다 — 두 엔진에서 각각 돌려도 그 51개는 **같은 엔진을 두 번**
    본다. 여기서 **한 자리**를 밟아 둔다.

    기준정보만 들어 있는 엔진이므로 기준정보를 읽는 엔드포인트를 고른다.
    나머지 엔드포인트까지 두 엔진에서 돌리는 일은 픽스처를 한곳으로 모으는
    별건이다 — 진단 「파이프라인 조기경보」의 `engine-pinned-tests` 항목이다.
    """
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app.db import base as db_base
    from app.main import app

    session_factory = sessionmaker(bind=seeded_engine)

    def override_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[db_base.get_session] = override_session
    try:
        with TestClient(app) as client:
            response = client.get("/api/master-data")
    finally:
        app.dependency_overrides.pop(db_base.get_session, None)

    assert response.status_code == 200, response.text
    items = response.json()["data"]["items"]
    assert items, "기준정보를 넣은 엔진인데 품목이 비어 있다"


def test_a_boolean_column_holds_a_boolean_on_this_engine(
    seeded_engine: sa.Engine,
) -> None:
    """읽어 온 값이 `1` 이 아니라 참·거짓이어야 한다.

    SQLite 는 불리언 칸에 넣은 정수를 정수 그대로 돌려준다. 그 값을 `is True` 로
    보는 코드는 한 엔진에서만 맞는다.
    """
    with seeded_engine.connect() as connection:
        values = connection.execute(
            sa.select(Base.metadata.tables["code_groups"].c.value_fixed)
        ).scalars().all()

    assert values
    assert all(isinstance(value, bool) for value in values)


def test_a_lowercase_item_code_is_rejected_by_this_engine(
    seeded_engine: sa.Engine,
) -> None:
    """`fg-01` 은 완제품 접두를 만족하지 않는다 — 두 엔진 모두에서.

    이 제약을 `LIKE` 로 적으면 SQLite 는 ASCII 대소문자를 가리지 않아 **받아
    준다.** 개발과 테스트는 통과하고 운영만 거부하는 행이 그렇게 생긴다.
    제약이 서 있는지가 아니라 **무는지**를 여기서 본다.
    """
    with pytest.raises(IntegrityError):
        with seeded_engine.begin() as connection:
            _insert_item(connection, "fg-01", FINISHED_ITEM)


def test_a_matching_item_code_is_accepted_by_this_engine(
    seeded_engine: sa.Engine,
) -> None:
    """물기만 하고 통과시키지 못하면 제약이 아니라 고장이다."""
    with seeded_engine.begin() as connection:
        _insert_item(connection, "FG-99", FINISHED_ITEM)
        connection.execute(
            sa.delete(Base.metadata.tables["items"]).where(
                Base.metadata.tables["items"].c.code == "FG-99"
            )
        )


@pytest.mark.parametrize(
    ("result", "reason", "expected"),
    [
        (QC_FAILED, "표면 광택 편차", True),
        (QC_FAILED, "", False),
        (QC_FAILED, " ", False),
        # 1인자 `trim()` 은 공백(0x20)만 지운다. 탭·개행만 담긴 사유가 통과하면
        # 화면에는 사유 없는 불합격 행이 그려진다.
        (QC_FAILED, "\t\n\r", False),
        (QC_PASSED, None, True),
    ],
)
def test_the_blank_reason_expression_means_the_same_thing_on_this_engine(
    live_engine: sa.Engine, result: str, reason: str | None, expected: bool
) -> None:
    """식을 이 엔진이 **실제로 계산해** 같은 답을 내야 한다.

    지울 문자를 명시하는 형태의 이름이 엔진마다 다르다 — SQLite 는 `trim(x, y)`,
    PostgreSQL 은 `btrim(x, y)` 이고 문자 코드 함수도 `char` 과 `chr` 로 갈린다.
    `test_migrations.py` 는 그려진 문자열이 서로 다른지까지만 본다. 그 문법이
    그 엔진에 실제로 있는지, 두 표기가 같은 값을 내는지는 돌려 봐야 안다.
    """
    rendered = str(
        failure_reason_is_present().compile(
            dialect=live_engine.dialect, compile_kwargs={"literal_binds": True}
        )
    )
    with live_engine.connect() as connection:
        actual = connection.execute(
            sa.text(
                f"SELECT CASE WHEN ({rendered}) THEN 1 ELSE 0 END"
                " FROM (SELECT :result AS result, :reason AS reason) AS sample"
            ),
            {"result": result, "reason": reason},
        ).scalar_one()

    assert bool(actual) is expected


@pytest.mark.skipif(
    is_sqlite(DATABASE_URL),
    reason="SQLite 는 불리언 칸의 정수를 받는다 — 이 검사가 물 수 있는 엔진이 아니다",
)
def test_this_engine_refuses_an_integer_written_into_a_boolean_column(
    seeded_engine: sa.Engine,
) -> None:
    """SQLite 가 왜 대역이 될 수 없는지를 못박는 자리.

    이 검사가 통과한다는 것은 기준정보 SQL 의 불리언 리터럴을 **엔진이 직접**
    지키고 있다는 뜻이다. SQLite 로만 CI 를 돌리면 이 자리에 아무도 서지 않고,
    글자 검사가 보지 못하는 모양(컬럼 목록 없는 `INSERT` 등)이 그대로 새어
    나간다.
    """
    with pytest.raises(DBAPIError):
        with seeded_engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO code_groups (group_code, name, value_fixed, description)"
                    " VALUES ('ZZZ', '일회용', 1, '일회용')"
                )
            )


def test_the_throwaway_name_stays_inside_the_identifier_limit() -> None:
    """긴 데이터베이스 이름에서도 고유한 꼬리가 살아남는다.

    이 검사는 데이터베이스를 열지 않는다. 이름을 짓는 규칙만 묻는다 — 63바이트를
    넘겨 잘리는 순간 이 파일의 격리가 통째로 무너지기 때문이다.
    """
    for length in (1, 37, 38, 39, 50, 63):
        source = "a" * length
        first = _throwaway_name(source)
        second = _throwaway_name(source)

        assert len(first.encode("utf-8")) <= MAXIMUM_IDENTIFIER_BYTES, source
        # 잘린 결과가 원본 이름이 되면 `CREATE DATABASE` 가 늘 「이미 있다」다.
        assert first != source
        # 나란히 도는 두 실행이 같은 이름을 얻으면 한쪽이 다른 쪽을 지운다.
        assert first != second
        assert THROWAWAY_PREFIX in first


def test_the_throwaway_name_never_splits_a_multibyte_character() -> None:
    """바이트로 자르므로 글자가 반 토막 날 수 있다. 깨진 조각은 남기지 않는다."""
    name = _throwaway_name("한" * 40)

    assert len(name.encode("utf-8")) <= MAXIMUM_IDENTIFIER_BYTES
    # 되감아 인코딩해도 같아야 한다 = 깨진 조각이 없다.
    assert name.encode("utf-8").decode("utf-8") == name


def test_the_throwaway_name_survives_a_url_without_a_database() -> None:
    """데이터베이스를 적지 않은 주소에서도 이름이 지어진다.

    `postgresql+psycopg://user@localhost` 는 동작하는 주소다 — libpq 가 기본
    데이터베이스로 붙는다. 그런데 SQLAlchemy 는 그 자리를 `None` 으로 내주므로,
    이름 짓기가 그것을 그대로 받으면 이 파일 전체가 시작조차 못 한다.
    """
    assert make_url("postgresql+psycopg://user@localhost").database is None

    for source in (None, ""):
        name = _throwaway_name(source)

        assert name
        assert THROWAWAY_PREFIX in name
        assert len(name.encode("utf-8")) <= MAXIMUM_IDENTIFIER_BYTES
        assert _throwaway_name(source) != name


def test_the_throwaway_engine_never_reaches_the_configured_database() -> None:
    """일회용으로 갈아 끼운 이름이 **실제 접속에도 닿는지** 본다.

    psycopg 는 데이터베이스를 경로로도 질의의 `dbname` 으로도 받고, **질의 쪽이
    이긴다.** 그래서 `dbname` 이 남아 있으면 `set(database=...)` 는 아무 일도 하지
    않는다 — 일회용 데이터베이스는 만들어지되 엔진은 설정이 가리키는 진짜
    데이터베이스에 붙고, 이 파일이 표를 지우고 다시 만드는 동안 개발자의 데이터가
    사라진다. 뒷정리는 쓰이지도 않은 쪽을 지우므로 흔적조차 남지 않는다.

    그래서 이름을 보는 것으로는 모자란다. **드라이버에 실제로 넘어가는 값**을
    본다 — 위험이 사는 자리가 거기다.
    """
    for source in (
        "postgresql+psycopg:///?dbname=production_risk&host=/tmp&port=5432",
        "postgresql+psycopg://user@localhost/production_risk?dbname=elsewhere",
        "postgresql+psycopg:///production_risk?host=/tmp&port=5432",
    ):
        url = _with_the_database_in_one_place(make_url(source))
        throwaway = url.set(database=_throwaway_name(url.database))
        _, arguments = throwaway.get_dialect()().create_connect_args(throwaway)

        assert arguments["dbname"] == throwaway.database
        assert THROWAWAY_PREFIX in arguments["dbname"]
        assert "production_risk" != arguments["dbname"]


def test_the_readable_stem_survives_a_database_named_in_the_query() -> None:
    """이름을 모으고 나면 읽는 사람을 위한 앞부분도 되돌아온다.

    질의에만 이름이 있는 주소에서 `url.database` 는 `None` 이라, 모으지 않으면
    일회용 이름은 꼬리만 남는다. 안전에는 문제가 없지만 `\\dl` 로 들여다본 사람이
    그것이 무엇인지 알 수 없다.
    """
    url = _with_the_database_in_one_place(
        make_url("postgresql+psycopg:///?dbname=production_risk&host=/tmp")
    )

    assert url.database == "production_risk"
    assert "dbname" not in url.query
    assert _throwaway_name(url.database).startswith("production_risk_")
