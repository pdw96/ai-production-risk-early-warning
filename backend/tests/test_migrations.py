"""마이그레이션이 모델과 같은 표를 만드는지 지킨다.

엔진만 옮기고 마이그레이션 도구를 넣지 않으면 문제는 그대로 남고 이사만 한
셈이 된다 — 스키마를 바꿀 때 재시드가 유일한 길인 상태로 되돌아가기 때문이다.
그리고 도구가 있어도 **마이그레이션이 모델과 어긋나면** 더 나쁘다: 개발자는
모델을 보고 코드를 쓰는데 실제 표는 다른 모양이 된다.

이 파일은 그 어긋남을 잡는다. 자동 생성이 구워 낸 SQL 이 한 엔진의 문법으로
굳는 자리도 여기서 걸린다.
"""

from __future__ import annotations

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
        assert "char(9)" not in source, f"{name} 에 SQLite 문법이 박혀 있다"
        assert "chr(9)" not in source, f"{name} 에 PostgreSQL 문법이 박혀 있다"


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
