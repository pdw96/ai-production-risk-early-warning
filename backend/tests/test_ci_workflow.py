"""CI 가 운영과 같은 엔진을 보고 있는지 지킨다.

여기 있는 규칙들은 **저장소의 다른 파일에 적힌 값과 짝을 이룬다** — 워크플로의
접속 주소와 서비스 컨테이너의 비밀번호, CI 의 엔진 판과 compose 의 엔진 판.
짝이 어긋나도 편집한 사람에게는 아무 일도 일어나지 않는다: 접속이 죽거나(주소)
검증되는 엔진이 배포되는 엔진과 달라진다(판). 둘 다 **다음 사람의 문제**가 되고,
방언 결함은 그렇게 CI 를 빠져나간다.

산문으로 적어 두면 한쪽을 고칠 때 나머지가 조용히 거짓이 되므로, 짝을 여기서
기계가 본다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from sqlalchemy.engine import make_url


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "cloud-validation.yml"
COMPOSE_PATH = REPOSITORY_ROOT / "compose.yaml"


@pytest.fixture(scope="module")
def validate_job() -> dict:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    return workflow["jobs"]["validate"]


@pytest.fixture(scope="module")
def database_service(validate_job: dict) -> dict:
    services = validate_job.get("services") or {}
    assert "database" in services, (
        "CI 에 PostgreSQL 서비스 컨테이너가 없다 — 그러면 CI 는 배포되지 않는"
        " 엔진만 검증한다"
    )
    return services["database"]


def _steps(job: dict) -> list[dict]:
    return job["steps"]


def _step_named(job: dict, fragment: str) -> dict:
    matches = [
        step
        for step in _steps(job)
        if fragment in (step.get("name") or "")
    ]
    assert len(matches) == 1, f"'{fragment}' 를 이름에 담은 단계가 하나여야 한다"
    return matches[0]


def test_the_job_talks_to_the_engine_that_ships(
    validate_job: dict, database_service: dict
) -> None:
    """접속 주소와 서비스가 **같은 값**을 보아야 한다.

    사용자 · 비밀번호 · 데이터베이스 이름 중 하나만 어긋나도 첫 접속에서 죽는다.
    같은 값을 두 곳에 적는 것을 사람의 주의에 맡기지 않는다.
    """
    url = make_url(validate_job["env"]["DATABASE_URL"])
    service_environment = database_service["env"]

    assert url.get_backend_name() == "postgresql"
    assert url.username == service_environment["POSTGRES_USER"]
    assert url.password == service_environment["POSTGRES_PASSWORD"]
    assert url.database == service_environment["POSTGRES_DB"]
    assert f"{url.port}:5432" in [str(port) for port in database_service["ports"]]


def test_the_ci_password_is_not_the_deployed_one(database_service: dict) -> None:
    """서비스 컨테이너의 비밀번호는 이 잡에서만 사는 값이어야 한다.

    compose 는 비밀번호를 저장소에 두지 않고 `.env` 에서 받는다(`:?` 로 없으면
    기동이 멈춘다). CI 는 그럴 수 없으므로 값을 적되, **적어도 되는 값**을 적는다 —
    잡 안에서만 닿는 컨테이너의 일회용 비밀번호다. 운영 비밀번호를 여기 옮겨
    적는 순간 그것은 저장소에 적힌 비밀번호가 된다.
    """
    compose_source = COMPOSE_PATH.read_text(encoding="utf-8")

    password = database_service["env"]["POSTGRES_PASSWORD"]
    assert "${{" not in str(password), (
        "CI 전용 일회용 값이므로 비밀에서 끌어올 것이 없다"
    )
    assert password not in compose_source
    assert "POSTGRES_PASSWORD:?" in compose_source, (
        "compose 는 여전히 비밀번호를 저장소 밖(.env)에서 받아야 한다"
    )


def test_ci_validates_the_same_engine_release_that_compose_deploys(
    database_service: dict,
) -> None:
    """CI 의 엔진 판과 compose 의 엔진 판이 같아야 한다.

    한쪽만 올리면 검증하는 엔진과 배포하는 엔진이 갈린다 — 그리고 그때 CI 는
    초록이다.
    """
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))

    def major(image: str) -> str:
        matched = re.search(r":(\d+)", image)
        assert matched, f"이미지 태그에서 판을 읽을 수 없다: {image}"
        return matched.group(1)

    assert major(database_service["image"]) == major(
        compose["services"]["database"]["image"]
    )


def test_ci_walks_the_path_the_container_actually_takes(validate_job: dict) -> None:
    """마이그레이션 → 조건부 시드. `docker-entrypoint.sh` 와 같은 차례다.

    `python -m app.seed`(인자 없음)는 `drop_all`/`create_all` 로 표를 직접 만든다.
    그 길만 돌리면 **운영이 타는 길인 `alembic upgrade head` 는 한 번도 검증되지
    않는다** — 그리고 표를 만들지 않는 `--if-empty` 쪽에서만 나는 고장이 있다.
    """
    migration = _step_named(validate_job, "마이그레이션")
    seeding = _step_named(validate_job, "시드")

    assert "alembic upgrade head" in migration["run"]
    assert "app.db.preflight" in migration["run"]
    assert "app.seed --if-empty" in seeding["run"]
    assert _steps(validate_job).index(migration) < _steps(validate_job).index(seeding)


def test_the_backend_suite_runs_on_both_engines(validate_job: dict) -> None:
    """두 엔진 모두에서 돈다.

    PostgreSQL 만 돌리면 함께 배포되는 SQLite 경로(설정 기본값 · 외래키 PRAGMA ·
    기존 검사 대부분이 붙는 엔진)가 검증 없이 나간다. SQLite 만 돌리면 방언
    결함이 CI 를 빠져나간다 — 지금까지가 그랬다.
    """
    postgres_step = _step_named(validate_job, "백엔드 검사 — PostgreSQL")
    sqlite_step = _step_named(validate_job, "백엔드 검사 — SQLite")

    for step in (postgres_step, sqlite_step):
        assert "pytest tests" in step["run"]

    # PostgreSQL 쪽은 잡의 주소를 그대로 물려받는다.
    assert "DATABASE_URL" not in (postgres_step.get("env") or {})
    # SQLite 쪽은 그 주소를 비워 설정이 파일로 떨어지게 한다.
    assert (sqlite_step.get("env") or {})["DATABASE_URL"] == ""
