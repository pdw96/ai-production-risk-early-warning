"""마이그레이션이 모델과 같은 표를 만드는지 지킨다.

엔진만 옮기고 마이그레이션 도구를 넣지 않으면 문제는 그대로 남고 이사만 한
셈이 된다 — 스키마를 바꿀 때 재시드가 유일한 길인 상태로 되돌아가기 때문이다.
그리고 도구가 있어도 **마이그레이션이 모델과 어긋나면** 더 나쁘다: 개발자는
모델을 보고 코드를 쓰는데 실제 표는 다른 모양이 된다.

이 파일은 그 어긋남을 잡는다. 자동 생성이 구워 낸 SQL 이 한 엔진의 문법으로
굳는 자리도 여기서 걸린다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateTable

from app.db.base import Base, register_models
from app.db.models import QualityInspection, failure_reason_is_present


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]


def _schema_snapshot(engine: sa.Engine) -> dict[str, dict[str, object]]:
    """표의 모양을 비교할 수 있는 형태로 뽑는다.

    이름만 보지 않고 컬럼의 자료형·널 허용, 기본키, 외래키, 유일키, CHECK 까지
    본다. 이 저장소는 **제약으로 규칙을 지키는 구조**이므로, 표 이름만 맞고
    제약이 빠진 마이그레이션은 규칙이 통째로 사라진 것과 같다.
    """
    inspector = sa.inspect(engine)
    snapshot: dict[str, dict[str, object]] = {}
    for table in sorted(inspector.get_table_names()):
        if table == "alembic_version":
            continue
        snapshot[table] = {
            "columns": sorted(
                (column["name"], str(column["type"]), column["nullable"])
                for column in inspector.get_columns(table)
            ),
            "primary_key": sorted(
                inspector.get_pk_constraint(table)["constrained_columns"]
            ),
            "foreign_keys": sorted(
                (
                    tuple(key["constrained_columns"]),
                    key["referred_table"],
                    tuple(key["referred_columns"]),
                )
                for key in inspector.get_foreign_keys(table)
            ),
            "unique_constraints": sorted(
                (constraint["name"], tuple(constraint["column_names"]))
                for constraint in inspector.get_unique_constraints(table)
            ),
            "check_constraints": sorted(
                (constraint["name"], " ".join(constraint["sqltext"].split()))
                for constraint in inspector.get_check_constraints(table)
            ),
        }
    return snapshot


def test_upgrading_from_empty_reproduces_the_model_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """마이그레이션을 끝까지 돌린 표와 모델이 만든 표가 같아야 한다.

    둘이 갈리면 개발자는 모델을 보고 코드를 쓰는데 실제 표는 다른 모양이 된다.

    이 검사가 스스로 엔진을 만드는 것은 **두 스키마를 나란히 놓아야 하기**
    때문이다 — 마이그레이션이 세운 것과 모델이 세운 것을 견주려면 데이터베이스가
    둘 필요한데, 공용 일회용 픽스처는 하나를 준다.

    **그래서 이 대조는 아직 SQLite 에서만 선다 — 여기가 없는 눈이다.** 이
    마이그레이션은 방언마다 다르게 렌더된다(`_BlankTrimmed` 에 SQLite 용과
    PostgreSQL 용 컴파일러가 따로 있다). PostgreSQL 쪽 렌더가 모델과 어긋나도
    이 자리는 두 CI 런에서 모두 SQLite 를 견주므로 초록이다. 메우려면 설정된
    방언 위에 데이터베이스 둘이나 격리된 스키마 둘을 내주는 픽스처가 있어야
    하고, 그것은 이 검사 하나의 사정을 넘는다.
    """
    migrated_path = tmp_path / "migrated.db"
    monkeypatch.setenv("DATABASE_PATH", str(migrated_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{migrated_path.as_posix()}")

    config = Config(str(BACKEND_DIRECTORY / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIRECTORY / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{migrated_path.as_posix()}")
    command.upgrade(config, "head")

    register_models()
    fresh_engine = sa.create_engine(f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}")
    Base.metadata.create_all(fresh_engine)

    migrated_engine = sa.create_engine(f"sqlite:///{migrated_path.as_posix()}")
    assert _schema_snapshot(migrated_engine) == _schema_snapshot(fresh_engine)


def test_the_blank_reason_check_speaks_each_engine_s_own_dialect() -> None:
    """1인자 `trim()` 은 공백만 지운다 — 탭·개행만 담긴 사유가 통과한다.

    지울 문자를 명시하는 형태의 이름이 엔진마다 다르므로(`trim` / `btrim`,
    `char` / `chr`), SQL 을 문자열로 박으면 엔진을 옮길 때 제약이 조용히
    뜻을 잃는다.
    """
    rendered = {
        name: str(
            CreateTable(QualityInspection.__table__).compile(dialect=dialect)
        )
        for name, dialect in (
            ("sqlite", sqlite.dialect()),
            ("postgresql", postgresql.dialect()),
        )
    }

    assert "trim(reason, ' ' || char(9)" in rendered["sqlite"]
    assert "btrim(reason, ' ' || chr(9)" in rendered["postgresql"]
    # 반대쪽 방언의 함수가 새어 들어가면 표가 만들어지지 않는다.
    assert "btrim" not in rendered["sqlite"]
    assert "char(9)" not in rendered["postgresql"]


def test_the_migration_does_not_freeze_one_engine_s_sql() -> None:
    """자동 생성은 실행 시점 방언으로 제약을 구워 문자열로 박아 둔다.

    그 문자열이 마이그레이션에 남으면, 나중에 다른 엔진에서 돌릴 때 표가
    만들어지지 않거나 뜻이 다른 제약이 선다.
    """
    versions = (BACKEND_DIRECTORY / "migrations" / "versions").glob("*.py")
    sources = {path.name: path.read_text(encoding="utf-8") for path in versions}

    assert sources
    for name, source in sources.items():
        # 굳었다는 것은 **한 방언만** 남았다는 뜻이다. 리비전이 방언을 스스로
        # 가르면 둘이 함께 있고(각자의 `@compiles`), 그것은 굳은 것이 아니다.
        # 그래서 「있다/없다」가 아니라 **짝이 맞는가**를 본다.
        assert ("char(9)" in source) == ("chr(9)" in source), (
            f"{name} 에 한 엔진의 문법만 남아 있다 — 다른 엔진에서 규칙이 사라진다"
        )
        # 그리고 어느 쪽도 **제약 문자열 안에** 박혀서는 안 된다. 박히면 그
        # 문자열이 그대로 실행되므로 방언이 끼어들 자리가 없다.
        for frozen in re.findall(r"CheckConstraint\(\s*(['\"].*?['\"])", source):
            assert "char(9)" not in frozen and "chr(9)" not in frozen, (
                f"{name} 의 CHECK 문자열에 한 엔진의 문법이 박혀 있다: {frozen}"
            )


def test_both_engines_render_the_same_constraint_meaning() -> None:
    """식은 하나이고 표기만 둘이다 — 그래서 두 엔진에서 같은 규칙이 선다."""
    expressions = {
        name: str(failure_reason_is_present().compile(dialect=dialect))
        for name, dialect in (
            ("sqlite", sqlite.dialect()),
            ("postgresql", postgresql.dialect()),
        )
    }

    for rendered in expressions.values():
        assert "reason IS NOT NULL" in rendered
        assert "result = " in rendered
    assert expressions["sqlite"] != expressions["postgresql"]


def test_a_database_url_with_percent_encoding_survives_alembic_config() -> None:
    """alembic 의 설정은 ConfigParser 이고 그것은 `%` 를 보간 문법으로 읽는다.

    비밀번호에 `%40`(=`@`) 같은 퍼센트 인코딩이 들어 있으면 접속을 해 보기도
    전에 ValueError 로 죽는다. entrypoint 가 마이그레이션을 **항상 먼저**
    돌리므로, 그 순간 백엔드는 아예 기동하지 못한다.
    """
    url = "postgresql+psycopg://user:p%40ssw0rd@db:5432/prod"
    config = Config()

    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))

    # 읽는 쪽에서 다시 한 글자로 돌아온다 — 주소 자체는 바뀌지 않는다.
    assert config.get_main_option("sqlalchemy.url") == url
    assert config.get_section(config.config_ini_section, {})["sqlalchemy.url"] == url


def test_the_migration_environment_escapes_percent_signs() -> None:
    """위 규칙을 env.py 가 실제로 지키는지 본다."""
    source = (BACKEND_DIRECTORY / "migrations" / "env.py").read_text(encoding="utf-8")

    assert 'replace("%", "%%")' in source
