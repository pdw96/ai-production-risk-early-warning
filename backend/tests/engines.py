"""검사가 붙을 **일회용 데이터베이스**를 짓는 장치.

`test_live_engine.py` 가 혼자 쓰던 것을 여기로 옮겼다. 옮긴 이유는 이 장치가
그 파일만의 것이 아니기 때문이다 — 검사를 `DATABASE_URL` 이 가리키는 엔진에서
돌리려면 **먼저 안전해야** 하고, 안전을 만드는 것이 이 장치다.

검사 대부분은 스스로 SQLite 엔진을 만들어 `db_base` 에 물린다. 그것은 설정을
무시하는 것이지만 동시에 **개발자의 데이터베이스를 지키는 장치**이기도 하다 —
그 검사들은 표를 지웠다 다시 만들므로, 설정이 가리키는 곳을 그대로 쓰면 로컬에서
한 번 돌리는 것만으로 데이터가 사라진다.

그래서 설정을 따르게 하는 길은 「안전장치를 걷어낸다」가 아니라 **안전장치를
설정된 엔진 위에서 다시 세운다**가 된다. 엔진은 설정이 가리키는 그것을 쓰되,
데이터베이스는 이번 실행에만 있는 것을 새로 만들어 거기에 붙는다.

이름을 짓는 규칙이 왜 이렇게까지 조심스러운지는 아래 각 함수의 주석에 있다.
그 규칙을 지키는지는 `test_live_engine.py` 가 본다.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa


# 일회용임을 이름에 남기는 표식. 뒤에는 **이번 실행에만 있는 값**이 붙는다.
# 파일 이름을 딴 `live_engine_` 이었으나 쓰는 곳이 늘어 중립적인 이름으로 바꿨다 —
# `\dl` 로 들여다본 사람이 골든 케이스가 만든 것을 `live_engine` 것으로 읽지 않도록.
THROWAWAY_PREFIX = "throwaway_"

# PostgreSQL 식별자의 상한. `NAMEDATALEN - 1` 이고, 넘기면 **조용히 잘린다.**
MAXIMUM_IDENTIFIER_BYTES = 63


def throwaway_name(source: str | None) -> str:
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


def with_the_database_in_one_place(url: sa.engine.URL) -> sa.engine.URL:
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


def make_throwaway_database(url: sa.engine.URL) -> sa.engine.URL:
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
    throwaway = throwaway_name(url.database)
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


def drop_throwaway_database(source: sa.engine.URL, throwaway: str) -> None:
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

