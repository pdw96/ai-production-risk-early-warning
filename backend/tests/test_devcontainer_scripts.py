"""개발 세션을 세우는 셸 스크립트가 **약속한 대로 물러나는지** 본다.

`database.sh` 머리에는 「이 파일은 실패해도 죽지 않는다」고 적혀 있다. 그것은
설명이 아니라 계약이다 — 부르는 쪽이 `set -e` 아래에서 명령 치환으로 받으므로,
여기서 0 아닌 값이 나가면 준비 전체가, 그리고 그것을 부르는 세션 시작 훅이 함께
내려간다. 글로만 적힌 계약은 지켜지지 않는다. 실제로 그 상황을 만들어 본다.

PostgreSQL 을 진짜로 세우지 않는다. 이 검사가 묻는 것은 「PostgreSQL 이 이러이러
하게 답할 때 이 스크립트가 무엇을 하는가」이므로, 그 답을 내는 **가짜 명령**을
`PATH` 앞에 둔다. 그러면 CI 든 개발자의 손이든, PostgreSQL 이 있든 없든 같은
결론이 나온다.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATABASE_SCRIPT = REPOSITORY_ROOT / ".devcontainer" / "database.sh"
AUTOSELECTED_SCRIPT = REPOSITORY_ROOT / ".devcontainer" / "autoselected.sh"
SETTINGS_FILE = REPOSITORY_ROOT / ".claude" / "settings.json"


def _stub_directory(tmp_path: Path, commands: dict[str, str]) -> Path:
    """`PATH` 앞에 둘 가짜 명령들을 만든다."""
    directory = tmp_path / "stub-bin"
    directory.mkdir(exist_ok=True)
    for name, body in commands.items():
        script = directory / name
        script.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        script.chmod(0o755)
    return directory


def _run_database_script(
    stub: Path, extra_environment: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    # 이미 정해진 주소가 있으면 이 스크립트는 곧바로 그것을 돌려주고 끝난다.
    environment.pop("DATABASE_URL", None)
    environment["PATH"] = f"{stub}{os.pathsep}{environment['PATH']}"
    environment.update(extra_environment or {})
    return subprocess.run(
        ["bash", str(DATABASE_SCRIPT)],
        capture_output=True,
        text=True,
        env=environment,
        cwd=REPOSITORY_ROOT,
        timeout=120,
    )


# 역할 조회가 성공하는 평범한 클러스터. `1` 하나로 세 번의 조회를 모두 만족한다 —
# 권한 조회는 `f` 도 빈 값도 아니므로 손대지 않고, 존재 조회는 있다고 답하며,
# 접속 조회는 0 으로 끝난다.
HEALTHY_PSQL = 'echo 1'


def test_a_failing_role_probe_does_not_kill_the_script(tmp_path: Path) -> None:
    """역할이 없어 조회가 실패해도 0 으로 끝나고 아무 주소도 내지 않는다.

    peer 인증은 운영체제 사용자와 같은 이름의 역할을 요구하고, 그것이 없으면
    소켓 접속이 그 자리에서 거부된다 — 즉 조회가 **0 아닌 값으로** 끝난다.
    `set -euo pipefail` 아래에서 그 파이프라인을 변수에 담으면 대입이 곧 종료가
    되어, 역할을 만들려고 둔 갈래에 닿지도 못한 채 스크립트가 죽는다.
    """
    stub = _stub_directory(
        tmp_path,
        {
            "pg_isready": "exit 0",
            "psql": 'echo "FATAL: role does not exist" >&2\nexit 2',
            "createdb": "exit 1",
            # 권한을 올리는 길을 막아 SQLite 로 물러나게 한다.
            "su": "exit 1",
            "sudo": "exit 1",
        },
    )

    result = _run_database_script(stub)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_an_unreachable_database_is_not_advertised(tmp_path: Path) -> None:
    """이미 있지만 붙지 못하는 데이터베이스의 주소를 내밀지 않는다.

    카탈로그 조회는 남이 만들어 둔 것도 「있다」로 답한다. 그 데이터베이스에
    이 역할의 `CONNECT` 이 없으면, 생성을 건너뛴 채 멀쩡해 보이는 주소가 나가고
    준비는 약속된 SQLite 대신 기동 전 검사에서 죽는다.
    """
    stub = _stub_directory(
        tmp_path,
        {
            "pg_isready": "exit 0",
            "psql": (
                'for argument in "$@"; do\n'
                '  case "$argument" in\n'
                "    production_risk)\n"
                '      echo "FATAL: permission denied for database" >&2\n'
                "      exit 2;;\n"
                "  esac\n"
                "done\n"
                "echo 1"
            ),
            "createdb": "exit 1",
            "su": "exit 1",
            "sudo": "exit 1",
        },
    )

    result = _run_database_script(stub)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""
    assert "붙지 못했습니다" in result.stderr


def test_ambient_libpq_variables_do_not_steer_the_script(tmp_path: Path) -> None:
    """조사하고 만든 자리와 알려 주는 자리가 같다.

    `psql` · `createdb` · `pg_isready` 는 모두 환경의 `PGHOST` · `PGPORT` ·
    `PGUSER` 를 읽는다. 개발자의 셸에 그런 것이 내보내져 있으면 준비는 그쪽
    클러스터에 데이터베이스를 만들고, 그러고는 소켓 주소를 돌려준다.
    """
    recording = tmp_path / "seen.json"
    record = (
        'printf \'{"PGHOST":"%s","PGPORT":"%s","PGUSER":"%s"}\\n\''
        f' "${{PGHOST:-}}" "${{PGPORT:-}}" "${{PGUSER:-}}" >> {recording}'
    )
    stub = _stub_directory(
        tmp_path,
        {
            "pg_isready": f"{record}\nexit 0",
            "psql": f"{record}\n{HEALTHY_PSQL}",
            "createdb": f"{record}\nexit 0",
        },
    )

    result = _run_database_script(
        stub,
        {"PGHOST": "db.example.internal", "PGPORT": "15432", "PGUSER": "someone-else"},
    )

    assert result.returncode == 0, result.stderr
    url = result.stdout.strip()
    assert url, result.stderr

    seen = [json.loads(line) for line in recording.read_text(encoding="utf-8").splitlines()]
    assert seen, "가짜 명령이 한 번도 불리지 않았다"
    for call in seen:
        # 밖에서 준 값이 하나라도 살아남으면 만든 곳과 알려 준 곳이 갈린다.
        assert call["PGHOST"] != "db.example.internal"
        assert call["PGPORT"] != "15432"
        assert call["PGUSER"] != "someone-else"
        # 그리고 실제로 본 자리가 주소에 적힌 그 자리여야 한다.
        assert f"host={call['PGHOST']}" in url
        assert f"port={call['PGPORT']}" in url


@pytest.mark.parametrize(
    ("marker", "current", "expected"),
    [
        # 지난 세션이 물려준 우리 주소 — 서버가 내려가 있을 수 있으니 다시 고른다.
        ("postgresql+psycopg:///production_risk", "postgresql+psycopg:///production_risk", True),
        # 개발자가 갈아 끼운 주소 — 표식이 남아 있어도 우리 것이 아니다.
        ("postgresql+psycopg:///production_risk", "postgresql+psycopg://me@host/staging", False),
        # 사람이 처음부터 준 주소.
        ("", "postgresql+psycopg://me@host/staging", False),
        # 아무것도 없다.
        ("", "", False),
    ],
)
def test_only_our_own_inherited_url_is_discarded(
    marker: str, current: str, expected: bool
) -> None:
    """표식이 그 둘을 가른다 — `1` 이 아니라 **값**으로.

    표식이 「자동으로 골랐다」는 사실만 들고 있으면, 지난 세션의 파일을 읽은 셸에서
    개발자가 `export DATABASE_URL=...` 로 다른 데이터베이스를 고른 순간 그 선택이
    조용히 버려진다. `setup.sh` 는 로컬 데이터베이스를 세우고, `start.sh` 는
    엉뚱한 곳을 향해 서버를 띄운다.
    """
    result = subprocess.run(
        [
            "bash",
            "-c",
            f'. "{AUTOSELECTED_SCRIPT}"\n'
            "if production_risk_url_is_inherited_ours; then echo ours; else echo theirs; fi",
        ],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "DATABASE_URL": current,
            "PRODUCTION_RISK_DATABASE_AUTOSELECTED": marker,
        },
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ("ours" if expected else "theirs")


def test_the_session_start_hook_survives_a_path_with_spaces(tmp_path: Path) -> None:
    """공백이 든 경로에 체크아웃해도 훅이 돈다.

    훅 명령은 셸이 읽는다. 저장소가 공백이 든 디렉터리 아래에 있으면 따옴표 없는
    경로는 여러 낱말로 쪼개지고, 훅은 **조용히 실행되지 않는다** — 의존성도
    데이터베이스도 준비되지 않은 채 세션이 시작된다.
    """
    command = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))["hooks"][
        "SessionStart"
    ][0]["hooks"][0]["command"]

    project = tmp_path / "my project"
    (project / ".claude" / "hooks").mkdir(parents=True)
    hook = project / ".claude" / "hooks" / "session-start.sh"
    hook.write_text("#!/usr/bin/env bash\necho ran\n", encoding="utf-8")
    hook.chmod(0o755)

    result = subprocess.run(
        ["sh", "-c", command],
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project)},
        timeout=60,
    )

    assert result.stdout.strip() == "ran", result.stderr
