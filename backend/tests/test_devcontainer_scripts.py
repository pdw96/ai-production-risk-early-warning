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
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATABASE_SCRIPT = REPOSITORY_ROOT / ".devcontainer" / "database.sh"
AUTOSELECTED_SCRIPT = REPOSITORY_ROOT / ".devcontainer" / "autoselected.sh"
PREPARE_SCRIPT = REPOSITORY_ROOT / ".devcontainer" / "prepare-database.sh"
START_SCRIPT = REPOSITORY_ROOT / ".devcontainer" / "start.sh"
SETUP_SCRIPT = REPOSITORY_ROOT / ".devcontainer" / "setup.sh"
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


def _environment_without_a_url(overrides: dict[str, str]) -> dict[str, str]:
    """물려받은 `DATABASE_URL` 을 걷어낸 환경.

    이 검사들은 「주소가 정해져 있지 않을 때 무엇을 하는가」를 묻는다. 그런데
    PostgreSQL 실행에서는 `DATABASE_URL` 이 설정되어 있고, 그것을 그대로 물려주면
    묻고 싶은 갈래로 아예 들어가지 못한다 — 검사가 엔진에 따라 다른 것을 보게 된다.
    """
    environment = dict(os.environ)
    environment.pop("DATABASE_URL", None)
    environment.pop("PRODUCTION_RISK_DATABASE_AUTOSELECTED", None)
    environment.update(overrides)
    return environment


def _run_database_script(
    stub: Path, extra_environment: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    environment = _environment_without_a_url(
        {"PATH": f"{stub}{os.pathsep}{os.environ['PATH']}"}
    )
    environment.update(extra_environment or {})
    return subprocess.run(
        ["bash", str(DATABASE_SCRIPT)],
        capture_output=True,
        text=True,
        env=environment,
        cwd=REPOSITORY_ROOT,
        timeout=120,
    )


# 아무 문제 없는 클러스터 흉내. 스키마 권한 질의에는 `t` 를, 나머지에는 `1` 을
# 낸다 — 역할 권한 조회의 `1` 은 `f` 도 빈 값도 아니므로 손대지 않고, 존재 조회는
# 있다고 답한다.
HEALTHY_PSQL = (
    'case "$*" in\n'
    "  *has_schema_privilege*) echo t;;\n"
    "  *) echo 1;;\n"
    "esac"
)


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
    assert "표를 만들 수 없습니다" in result.stderr


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


def test_no_postgres_command_can_stop_and_ask_for_a_password(tmp_path: Path) -> None:
    """이 도우미가 부르는 모든 명령이 「묻지 말라」를 달고 나간다.

    `psql` 과 `createdb` 는 서버가 비밀번호를 요구하면 터미널에 대고 물어보고
    답이 올 때까지 기다린다. 이것을 부르는 것은 준비 스크립트와 세션 시작 훅이고
    그 자리에는 답할 사람이 없으므로, 물러나는 대신 **영원히 매달린다.**
    소켓 인증을 `scram-sha-256` 으로 바꿔 실제로 재현했다 —
    `Password for user root:` 에서 멈춰 시간 제한에 걸렸다.

    이 검사는 서버를 세우지 않는다. 가짜 명령이 자기가 받은 인자를 적게 하고,
    **한 번이라도 `-w` 없이 불린 적이 있는지**를 묻는다.
    """
    # `pg_isready` 는 이 목록에 없다 — 접속을 물어보기만 하고 비밀번호를 묻지
    # 않으며, `-w` 를 받지도 않는다. 묻는 것은 `psql` 과 `createdb` 뿐이다.
    recording = tmp_path / "argv.txt"
    # SQL 이 여러 줄일 수 있으므로 **한 줄로 접어** 적는다. 그러지 않으면 한 번의
    # 호출이 여러 줄로 쪼개져 `-w` 가 없는 것처럼 보인다.
    record = f'printf \'%s\\n\' "$*" | tr \'\\n\' \' \' >> {recording}; printf \'\\n\' >> {recording}'
    stub = _stub_directory(
        tmp_path,
        {
            "pg_isready": "exit 0",
            "psql": f"{record}\n{HEALTHY_PSQL}",
            "createdb": f"{record}\nexit 0",
        },
    )

    result = _run_database_script(stub)

    assert result.returncode == 0, result.stderr
    calls = recording.read_text(encoding="utf-8").splitlines()
    assert calls, "가짜 명령이 한 번도 불리지 않았다"
    asking = [c for c in calls if "-w" not in c.split()]
    assert not asking, f"비밀번호를 물을 수 있는 호출이 있다: {asking}"


def test_an_inaccessible_maintenance_database_does_not_discard_postgresql(
    tmp_path: Path,
) -> None:
    """`postgres` 에 못 붙는다고 쓸 수 있는 PostgreSQL 을 버리지 않는다.

    관례상 쓰는 `postgres` 데이터베이스에 이 역할의 `CONNECT` 이 없어도 응용
    데이터베이스에는 붙을 수 있다. 그때 역할 조회가 빈 답을 내면 「역할이 없다」로
    읽히고, 이어지는 생성이 이미 있는 역할을 만들려다 실패해 **멀쩡한 엔진이
    통째로 버려진다.**
    """
    stub = _stub_directory(
        tmp_path,
        {
            "pg_isready": "exit 0",
            "psql": (
                "database=''\nwant=0\n"
                'for argument in "$@"; do\n'
                '  if [ "$want" = 1 ]; then database="$argument"; want=0; fi\n'
                '  [ "$argument" = "-d" ] && want=1\n'
                "done\n"
                'case "$database" in\n'
                "  postgres|template1)\n"
                '    echo "FATAL: permission denied for database" >&2\n'
                "    exit 2;;\n"
                "esac\n"
                + HEALTHY_PSQL
            ),
            "createdb": "exit 1",
            # 권한을 올리는 길을 막아 둔다 — 역할을 만들 필요가 없어야 한다.
            "su": "exit 1",
            "sudo": "exit 1",
        },
    )

    result = _run_database_script(stub)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), f"쓸 수 있는 엔진을 버렸다: {result.stderr}"


def test_both_engine_selectors_prepare_what_they_selected() -> None:
    """엔진을 고르는 곳은 둘 다 준비 차례를 밟는다.

    준비(`setup.sh`)만 밟고 기동(`start.sh`)이 밟지 않으면, 기동이 다시 고른
    엔진에 표가 없을 수 있다 — 데이터베이스가 사라져 새로 만들어졌거나 SQLite 로
    물러난 경우다. 그대로 서버를 띄우면 **기동은 성공했다고 적히고 요청마다
    「표가 없다」로 죽는다.**

    차례 자체는 `prepare-database.sh` 한 곳에만 적는다 — 두 벌로 적으면 한쪽을
    고칠 때 다른 쪽이 조용히 뒤처진다.
    """
    preparation = PREPARE_SCRIPT.read_text(encoding="utf-8")
    for step in ("app.db.preflight", "alembic upgrade head", "app.seed --if-empty"):
        assert step in preparation, step

    for selector in (SETUP_SCRIPT, START_SCRIPT):
        # **주석은 세지 않는다.** 「`prepare-database.sh` 를 부른다」고 적어 두기만
        # 하고 부르지 않아도 글자 검사는 통과한다 — 이 검사가 한 번 그렇게 통과했다.
        body = "\n".join(
            line
            for line in selector.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        )
        assert "database.sh" in body, f"{selector.name} 이 엔진을 고르지 않는다"
        assert "prepare-database.sh" in body, f"{selector.name} 이 준비를 부르지 않는다"
        # 차례를 여기에 다시 적으면 두 곳이 갈린다.
        assert "alembic upgrade head" not in body, selector.name


def test_only_the_cluster_serving_the_configured_port_is_started(tmp_path: Path) -> None:
    """클러스터가 여럿이면 **우리가 보는 포트를 지키는 것**을 기동한다.

    첫 줄을 무조건 집으면 그것이 우리와 무관한 클러스터일 수 있다. 그러면 엉뚱한
    것을 기동한 뒤 30초를 기다렸다가 물러나고, **정작 내려가 있는 5432 는 손도
    대지 않는다.** 실측으로 재현했다: `16/aaa`(5433, online)와
    `16/main`(5432, down)이 있을 때 이름 순으로 앞선 `aaa` 를 기동하려 했고
    31초 뒤 SQLite 로 물러났다.
    """
    started = tmp_path / "started.txt"
    stub = _stub_directory(
        tmp_path,
        {
            # 처음에는 죽어 있고, 기동한 뒤에는 살아난다.
            "pg_isready": f'[ -f {started} ]',
            "pg_lsclusters": (
                "printf '%s\\n' "
                "'16  aaa  5433 online postgres /var/lib/postgresql/16/aaa  /log/aaa' "
                "'16  main 5432 down   postgres /var/lib/postgresql/16/main /log/main'"
            ),
            "pg_ctlcluster": f'printf \'%s\\n\' "$*" >> {started}',
            "psql": HEALTHY_PSQL,
            "createdb": "exit 0",
            # 기동은 권한을 올려서 한다. root 로 돌 때는 `sh -c` 라 이 자리가
            # 필요 없지만, CI 러너처럼 **root 가 아닐 때**는 `sudo` 를 지난다 —
            # 그러면 진짜 `sudo` 가 `secure_path` 로 `PATH` 를 갈아 끼워 위의
            # 가짜 명령들이 보이지 않는다. 실측으로 CI 가 여기서 빨개졌다.
            # 옵션만 걷어내고 그대로 실행하는 `sudo` 를 둔다.
            "sudo": (
                "while [ $# -gt 0 ]; do\n"
                '  case "$1" in\n'
                "    -n) shift;;\n"
                "    -u) shift 2;;\n"
                "    *) break;;\n"
                "  esac\n"
                "done\n"
                'exec "$@"'
            ),
        },
    )

    result = _run_database_script(stub)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), f"기동에 실패했다: {result.stderr}"
    assert started.exists(), "아무 클러스터도 기동하지 않았다"
    requested = started.read_text(encoding="utf-8")
    assert "main" in requested, f"5432 를 지키는 클러스터가 아니다: {requested}"
    assert "aaa" not in requested, f"무관한 클러스터를 기동했다: {requested}"


def test_a_database_we_cannot_create_tables_in_is_not_advertised(tmp_path: Path) -> None:
    """붙을 수 있다는 것과 **표를 만들 수 있다는 것**은 다르다.

    바로 다음에 오는 것이 `alembic upgrade head` 이고 그것이 하는 일은 `public`
    스키마에 표를 만드는 것이다. PostgreSQL 15 부터 그 스키마의 `CREATE` 가
    `PUBLIC` 에서 회수됐으므로, 남이 만들어 둔 데이터베이스에는 **붙기는 되는데
    표는 못 만드는** 상태가 흔하다. 실측(PostgreSQL 16.13): `SELECT 1` 은 `1` 을
    돌려주고 `CREATE TABLE` 은 `permission denied for schema public` 였다.
    """
    stub = _stub_directory(
        tmp_path,
        {
            "pg_isready": "exit 0",
            # 접속과 카탈로그 조회에는 답하지만, 스키마 권한 질의에는 거짓을 낸다.
            "psql": (
                'case "$*" in\n'
                "  *has_schema_privilege*) echo f;;\n"
                "  *) echo 1;;\n"
                "esac"
            ),
            "createdb": "exit 0",
            "su": "exit 1",
            "sudo": "exit 1",
        },
    )

    result = _run_database_script(stub)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", "표를 만들 수 없는 데이터베이스의 주소를 내밀었다"
    assert "표를 만들 수 없습니다" in result.stderr


def test_the_shell_hook_does_not_export_an_unusable_url() -> None:
    """프로파일 줄은 **쓸 수 있는지 보고 나서** 주소를 내보낸다.

    devcontainer 가 다시 뜰 때 도는 것은 `postStartCommand` 하나뿐이라
    `setup.sh` 도 `start.sh` 도 돌지 않는다. 그 상태에서 이 줄이 지난 세션의 주소를
    그대로 내보내면 사람이 곧바로 치는 `pytest` 가 쓸 수 없는 자리를 향해 돈다.

    묻는 것은 **서버가 사는지가 아니다.** `pg_isready` 는 그 문서가 못 박듯 올바른
    사용자·데이터베이스 값을 요구하지 않으므로, `production_risk` 가 지워졌거나
    이 역할이 권한을 잃어도 초록으로 답한다. 그래서 `database.sh` 가 엔진을 고를
    때 쓰는 **그 판정**을 그대로 부른다 — 둘이 다르게 답하면 준비는 PostgreSQL 을
    고르고 셸은 SQLite 로 돈다.

    그리고 조건이 거짓일 때 **0 으로 끝나야 한다** — `&&` 사슬은 0 아닌 값을
    남기고 그것이 새 셸의 `$?` 가 된다(실측: 파일 없음 1, 서버 죽음 2).
    """
    setup = SETUP_SCRIPT.read_text(encoding="utf-8")
    # **주석을 걷고 본다.** 왜 그렇게 했는지를 적은 글에는 `pg_isready` 가 나오고,
    # 글자만 세면 그 글 때문에 이 검사가 늘 통과한다 — 무는 검사가 아니게 된다.
    code = "\n".join(
        line for line in setup.splitlines() if not line.lstrip().startswith("#")
    )
    assert "database-usable.sh" in code, "프로파일 줄이 쓸 수 있는지 보지 않는다"
    assert "pg_isready" not in code, "살아 있는지만 보는 판정이 남아 있다"
    # 사슬이 아니라 `if` 여야 조건이 거짓일 때 0 으로 끝난다.
    assert "if [ -f %q ]" in code
    assert "[ -f %q ] &&" not in code


def _shell_region(script: Path, first: str, last: str) -> str:
    """`setup.sh` 의 **실제 토막**을 꺼낸다.

    모양을 검사에 손으로 베껴 두면 그것이 낡는다 — 그리고 낡은 줄은 조용히
    통과한다. 9차에 걸린 결함이 정확히 그 자리에서 살았다: 프로파일에 적히는
    몸통이 바뀌었는데 검사는 예전 모양을 돌려 보고 초록이었다.

    그래서 베끼지 않고 **가져다 돌린다.** 앵커를 못 찾으면 그 자리에서 터진다 —
    조용히 통과하는 것보다 낫다.
    """
    lines = script.read_text(encoding="utf-8").splitlines()
    begin = next(i for i, line in enumerate(lines) if line.startswith(first))
    end = next(i for i, line in enumerate(lines[begin:], begin) if line == last)
    return "\n".join(lines[begin : end + 1])


def _install_hook(tmp_path: Path, database_url: str) -> tuple[str, str]:
    """준비가 프로파일과 훅 파일에 적는 것을 그대로 만들어 낸다."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    profile = home / ".bashrc"
    if not profile.exists():
        profile.write_text("export EDITOR=vim\n", encoding="utf-8")

    repository = tmp_path / "repo"
    (repository / ".devcontainer").mkdir(parents=True, exist_ok=True)

    region = _shell_region(
        SETUP_SCRIPT, "database_host=", "close_production_risk_lock 7"
    )
    script = tmp_path / "install.sh"
    script.write_text(
        "set -euo pipefail\n"
        f'REPOSITORY_ROOT={repository}\n'
        f'DATABASE_ENVIRONMENT_FILE={repository}/.devcontainer/database.env\n'
        f'DATABASE_URL={database_url!r}\n'
        # 프로파일 토막이 잠금을 쓴다 — 준비가 그러듯 여기서도 물려 준다.
        f". {REPOSITORY_ROOT / '.devcontainer' / 'lock.sh'}\n" + region + "\n",
        encoding="utf-8",
    )
    environment = _environment_without_a_url({"HOME": str(home)})
    environment.pop("XDG_CACHE_HOME", None)
    result = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        env=environment,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr

    hook_file = repository / ".devcontainer" / "shell-hook.sh"
    return (
        profile.read_text(encoding="utf-8"),
        hook_file.read_text(encoding="utf-8") if hook_file.exists() else "",
    )


def _source_the_profile(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """그 프로파일을 읽은 셸이 무엇을 들고 있는지 본다."""
    repository = tmp_path / "repo"
    runner = tmp_path / "run.sh"
    runner.write_text(
        f". {tmp_path / 'home' / '.bashrc'}\n"
        'printf \'%s\\n\' "${DATABASE_URL:-<none>}"\n',
        encoding="utf-8",
    )
    return subprocess.run(
        ["bash", str(runner)],
        capture_output=True,
        text=True,
        cwd=repository,
        env=_environment_without_a_url({"HOME": str(tmp_path / "home")}),
        timeout=60,
    )


POSTGRESQL_URL = "postgresql+psycopg:///production_risk?host=/socket&port=5432"


@pytest.mark.parametrize("usable", [True, False])
def test_the_generated_shell_hook_behaves(tmp_path: Path, usable: bool) -> None:
    """만들어지는 줄을 **실제로 실행해 본다.**

    글자만 보면 그 줄이 문법에 맞는지도, 조건이 거짓일 때 무엇을 남기는지도
    모른다. 그래서 준비가 적는 것을 그대로 만들어 읽혀 본다.
    """
    repository = tmp_path / "repo"
    (repository / ".devcontainer").mkdir(parents=True, exist_ok=True)
    (repository / ".devcontainer" / "database.env").write_text(
        "export DATABASE_URL=chosen\n", encoding="utf-8"
    )
    usable_script = repository / ".devcontainer" / "database-usable.sh"
    usable_script.write_text(
        "#!/usr/bin/env bash\nexit %d\n" % (0 if usable else 1), encoding="utf-8"
    )

    _install_hook(tmp_path, POSTGRESQL_URL)
    result = _source_the_profile(tmp_path)

    # 조건이 거짓이어도 프로파일은 깨끗하게 끝나야 한다.
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ("chosen" if usable else "<none>")


def test_the_hook_is_refreshed_when_the_engine_changes(tmp_path: Path) -> None:
    """엔진이 바뀌면 프로파일이 읽는 것도 바뀐다.

    처음 준비가 SQLite 로 물러나면 파싱할 값이 없어 **판정 없는** 몸통이 적힌다.
    그 뒤 준비가 PostgreSQL 을 세웠는데 표식이 있다는 이유로 건너뛰면, 프로파일에는
    끝까지 아무것도 확인하지 않고 `database.env` 를 읽는 줄이 남는다 — 그리고
    그것이 하는 일은 **쓸 수 없는 주소를 사람의 셸에 내보내는 것**이다.

    실측(2026-09-08): 그때의 코드로 SQLite → PostgreSQL 순서로 돌리니 프로파일에
    남은 것은 `if [ -f .../database.env ]` 한 줄뿐이었다.

    표식이 있다는 것은 **몸통이 최신이라는 뜻이 아니다.**
    """
    _, sqlite_body = _install_hook(tmp_path, "")
    assert "database-usable.sh" not in sqlite_body

    profile, postgresql_body = _install_hook(tmp_path, POSTGRESQL_URL)

    assert "database-usable.sh" in postgresql_body, "엔진이 바뀌었는데 몸통이 낡았다"
    # 토막은 **하나**여야 한다 — 준비를 여러 번 돌려도 쌓이지 않는다.
    assert profile.count("ai-production-risk(") == 1
    assert profile.count("esac") == 1
    # 그 집 사람의 다른 줄은 건드리지 않는다.
    assert "export EDITOR=vim" in profile


def test_an_older_hook_block_is_replaced(tmp_path: Path) -> None:
    """예전 형태로 적힌 토막도 갈아 끼운다.

    사람의 프로파일에는 이미 지난 판의 줄이 적혀 있다. 표식이 같다는 이유로
    건너뛰면 그 줄은 **영영** 남는다.
    """
    home = tmp_path / "home"
    home.mkdir()
    repository = tmp_path / "repo"
    (home / ".bashrc").write_text(
        "export EDITOR=vim\n"
        "\n"
        f"# ai-production-risk({repository}): 개발 세션의 데이터베이스 주소\n"
        f'case "$PWD/" in {repository}/*)\n'
        f"  if [ -f {repository}/.devcontainer/database.env ]\n"
        "  then\n"
        f"    . {repository}/.devcontainer/database.env\n"
        "  fi ;;\n"
        "esac\n"
        "\n"
        "alias ll='ls -l'\n",
        encoding="utf-8",
    )

    profile, _ = _install_hook(tmp_path, POSTGRESQL_URL)

    assert "shell-hook.sh" in profile
    assert profile.count("ai-production-risk(") == 1
    assert "database.env" not in profile, "검사 없이 읽던 예전 줄이 남았다"
    assert "alias ll='ls -l'" in profile


def test_the_redaction_survives_an_encoded_credential_key(tmp_path: Path) -> None:
    """비밀번호는 **한 가지 철자로만 오지 않는다.**

    URI 는 퍼센트 인코딩을 허용하고 SQLAlchemy 는 그것을 풀어서 psycopg 에
    넘기므로 `?pass%77ord=s3cr3t` 는 **동작하는 주소**다. 실측(2026-09-08,
    SQLAlchemy 2.x): `create_connect_args` 가 `{'password': 's3cr3t'}` 를 냈다.
    가릴 것을 나열하는 방식은 늘 한 철자 뒤에 있으므로, **보여도 되는 것만**
    나열한다.
    """
    region = _shell_region(SETUP_SCRIPT, "SAFE_QUERY_KEYS=", "}")
    script = tmp_path / "redact.sh"
    script.write_text(
        region + '\nfor url in "$@"; do redact_url "$url"; printf "\\n"; done\n',
        encoding="utf-8",
    )

    urls = [
        "postgresql+psycopg://u@h/db?pass%77ord=s3cr3t",
        "postgresql+psycopg://u@h/db?sslpass%77ord=s3cr3t",
        "postgresql+psycopg://u@h/db?password=s3cr3t",
        "postgresql+psycopg://u:pw@h/db?sslmode=require&password=s3cr3t",
    ]
    result = subprocess.run(
        ["bash", str(script), *urls], capture_output=True, text=True, timeout=60
    )

    assert result.returncode == 0, result.stderr
    assert "s3cr3t" not in result.stdout, f"비밀번호가 로그로 샜다: {result.stdout}"
    assert "pw@" not in result.stdout

    # 그러면서도 사람이 알아야 하는 것은 남는다.
    kept = subprocess.run(
        ["bash", str(script), POSTGRESQL_URL], capture_output=True, text=True, timeout=60
    )
    assert kept.stdout.strip() == POSTGRESQL_URL


def test_the_usability_check_asks_for_database_creation(tmp_path: Path) -> None:
    """판정은 **이 저장소가 하려는 일을 다 할 수 있는지**를 묻는다.

    사람이 셸에서 곧바로 치는 것은 `pytest` 이고, 그 안의 `test_live_engine.py` 는
    일회용 데이터베이스를 만들어 쓴다 — `CREATE DATABASE` 다. 역할이 `public` 의
    `CREATE` 는 지녔는데 `CREATEDB` 를 잃은 상태가 실제로 있고, 프로파일 훅은
    `database.sh` 를 거치지 않으므로 **권한을 되돌려 줄 길도 지나친다.**

    실측(2026-09-08, PostgreSQL 16.13): `NOCREATEDB` 역할이 자기 소유
    데이터베이스에서 `has_schema_privilege(..., 'CREATE')` 는 `t` 였고 `createdb` 는
    `permission denied to create database` 였다.
    """
    stub = _stub_directory(
        tmp_path,
        {
            # 표는 만들 수 있고 데이터베이스는 못 만드는 역할 흉내.
            "psql": (
                'case "$*" in\n'
                "  *rolcreatedb*) echo f;;\n"
                "  *) echo t;;\n"
                "esac"
            )
        },
    )
    result = subprocess.run(
        [
            "bash",
            str(REPOSITORY_ROOT / ".devcontainer" / "database-usable.sh"),
            "/socket",
            "5432",
            "production_risk",
        ],
        capture_output=True,
        text=True,
        env=_environment_without_a_url(
            {"PATH": f"{stub}{os.pathsep}{os.environ['PATH']}"}
        ),
        timeout=60,
    )

    assert result.returncode != 0, "데이터베이스를 만들 수 없는데 쓸 수 있다고 답했다"


def test_losing_a_creation_race_does_not_discard_postgresql(tmp_path: Path) -> None:
    """겹쳐 돈 준비 중 **진 쪽**이 멀쩡한 데이터베이스를 버리지 않는다.

    이 파일은 준비와 세션 시작 훅 양쪽에서 불리고 둘이 겹칠 수 있다. 그러면 둘 다
    「없다」를 보고, 한쪽이 만들고, 다른 쪽은 `CREATE DATABASE` 에 `IF NOT EXISTS`
    가 없어 실패한다. 실측(2026-09-08, PostgreSQL 16.13): `createdb` 둘을 실제로
    겹쳐 돌리니 진 쪽이 `duplicate key value violates unique constraint
    "pg_database_datname_index"` 로 끝났고 데이터베이스는 멀쩡히 있었다.

    진 쪽이 그것을 「못 만들었다」로 읽으면 SQLite 로 물러나고, 그러면 이긴 쪽이
    적어 둔 `database.env` 를 **지운다**. 두 세션이 서로 다른 엔진을 드는 것보다
    나쁜 결과다.
    """
    created = tmp_path / "created-by-the-winner"
    stub = _stub_directory(
        tmp_path,
        {
            "pg_isready": "exit 0",
            # 존재 조회는 이긴 쪽이 만들었는지에 따라 답이 달라진다.
            "psql": (
                'case "$*" in\n'
                "  *pg_database*)\n"
                f'    [ -e {created} ] && echo 1\n'
                "    exit 0;;\n"
                "  *has_schema_privilege*) echo t;;\n"
                "  *) echo 1;;\n"
                "esac"
            ),
            # 우리가 만들려는 사이에 이긴 쪽이 이미 만들어 두었다.
            "createdb": f"touch {created}\nexit 1",
            "su": "exit 1",
            "sudo": "exit 1",
        },
    )

    result = _run_database_script(stub)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), (
        f"경합에서 졌다고 쓸 수 있는 엔진을 버렸다: {result.stderr}"
    )


def test_the_redaction_survives_an_empty_username(tmp_path: Path) -> None:
    """사용자 이름은 **없을 수도 있다.**

    `postgresql+psycopg://:s3cr3t@localhost/db` 는 동작하는 주소다.
    실측(2026-09-08, SQLAlchemy 2.0.52): 사용자 이름 `''` · 비밀번호 `s3cr3t` 로
    읽혀 psycopg 에 `password='s3cr3t'` 로 넘어갔고, 한 글자 이상을 요구하던 가림은
    그 값을 그대로 로그에 냈다.
    """
    region = _shell_region(SETUP_SCRIPT, "SAFE_QUERY_KEYS=", "}")
    script = tmp_path / "redact.sh"
    script.write_text(
        region + '\nfor url in "$@"; do redact_url "$url"; printf "\\n"; done\n',
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "bash",
            str(script),
            "postgresql+psycopg://:s3cr3t@localhost/db",
            "postgresql+psycopg://:s3cr3t@h/db?pass%77ord=t0p",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert "s3cr3t" not in result.stdout, f"비밀번호가 로그로 샜다: {result.stdout}"
    assert "t0p" not in result.stdout

    # 그러면서도 **포트를 비밀번호로 잘못 읽지 않는다.** 사용자 정보는 `/` 앞에서
    # 끝나므로 비밀번호에 날 `/` 가 올 수 없고, 허용해 두면 아래가 가려진다.
    kept = subprocess.run(
        ["bash", str(script), "postgresql+psycopg://h:5432/db?host=x"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert kept.stdout.strip() == "postgresql+psycopg://h:5432/db?host=x"


def test_the_selected_url_is_published_only_after_preparation() -> None:
    """준비가 끝나기 전에는 **아무에게도 알리지 않는다.**

    기동 전 검사·마이그레이션·시드 중 하나가 실패하면 `set -e` 가 준비를 그
    자리에서 끊는다. 그때 `database.env` 가 이미 적혀 있으면 다음 셸이 그 주소를
    내보내고, 훅이 묻는 것은 접속과 권한뿐이라 **표가 없거나 반쯤 올라간**
    데이터베이스도 통과한다 — 사람은 준비가 실패한 줄 모른 채 `no such table` 을
    본다.

    없는 파일은 SQLite 로 도는 것이고, 그것이 이 저장소가 실패에 대해 약속한
    자리다.
    """
    # **주석을 걷고 본다.** 왜 그 차례인지를 적은 글에도 `prepare-database.sh` 가
    # 나오고, 글자만 세면 그 글의 위치를 호출의 위치로 착각한다 — 그러면 이 검사는
    # 순서가 뒤집혀도 초록이다(실측: 실제로 그랬다).
    lines = [
        line
        for line in SETUP_SCRIPT.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]
    prepares = next(
        index
        for index, line in enumerate(lines)
        if "prepare-database.sh" in line and "bash " in line
    )
    publishes = next(
        index
        for index, line in enumerate(lines)
        if line.strip() == '} > "${DATABASE_ENVIRONMENT_FILE}.$$"'
    )

    assert publishes > prepares, "준비보다 먼저 주소를 알린다"


def test_the_preparation_sequence_is_serialized(tmp_path: Path) -> None:
    """겹쳐 도는 준비는 **하나씩 지나간다.**

    「이미 맞는가」와 「비어 있는가」는 둘 다 보고 나서 고치는 일이고, 두 프로세스가
    사이에 끼어들면 둘 다 「아직 아니다」를 본다. 실측(2026-09-08): PostgreSQL 에서
    `alembic upgrade head` 둘을 겹치니 진 쪽이 `duplicate key value violates unique
    constraint "pg_type_typname_nsp_index"` 로 1, SQLite 에서 `app.seed --if-empty`
    둘을 겹치니 `UNIQUE constraint failed: code_groups.group_code` 로 1이었다.

    잠금을 **실제로 겹쳐 걸어** 본다 — 글자만 보면 그것이 서는지 알 수 없다.

    겹쳤는지는 「그 순간에 남이 있는가」로 묻지 않는다. 그 물음 자체가 경합이라,
    둘이 나란히 들어오면 둘 다 「아무도 없다」를 본다 — 검사가 검사하려던 그 결함을
    그대로 갖게 된다. 그래서 **드나든 자취를 남기고 나중에 읽는다.** 줄을 섰다면
    한쪽이 다 지나간 뒤 다른 쪽이 지나가므로, 자취에서 주인이 바뀌는 지점은
    한 번뿐이다.
    """
    home = tmp_path / "home"
    home.mkdir()
    trace = tmp_path / "trace"
    stub = _stub_directory(
        tmp_path,
        {
            # 준비 세 줄 대신, 드나든 자취를 남기는 것으로 바꾼다.
            "python": (
                f'printf "%s\\n" "$PPID" >> {trace}\n'
                "sleep 0.3\n"
                f'printf "%s\\n" "$PPID" >> {trace}\n'
            )
        },
    )
    backend = tmp_path / "repo" / "backend"
    (backend / ".venv" / "bin").mkdir(parents=True)
    (backend / ".venv" / "bin" / "python").write_text(
        f'#!/bin/sh\nexec {stub}/python "$@"\n', encoding="utf-8"
    )
    (backend / ".venv" / "bin" / "python").chmod(0o755)
    devcontainer = tmp_path / "repo" / ".devcontainer"
    devcontainer.mkdir(parents=True)
    for name in ("prepare-database.sh", "lock.sh"):
        (devcontainer / name).write_text(
            (REPOSITORY_ROOT / ".devcontainer" / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    environment = _environment_without_a_url(
        {"HOME": str(home), "DATABASE_URL": "postgresql+psycopg:///overlap"}
    )
    environment.pop("XDG_CACHE_HOME", None)
    runs = [
        subprocess.Popen(
            ["bash", str(devcontainer / "prepare-database.sh")],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=environment,
        )
        for _ in range(2)
    ]
    for run in runs:
        assert run.wait(timeout=180) == 0, run.stderr.read()

    owners = trace.read_text(encoding="utf-8").split()
    assert len(set(owners)) == 2, f"두 쪽이 다 돌지 않았다: {owners}"
    changes = sum(1 for before, after in zip(owners, owners[1:]) if before != after)
    assert changes == 1, f"준비가 서로 끼어들었다: {owners}"


def test_losing_a_role_creation_race_does_not_discard_postgresql(
    tmp_path: Path,
) -> None:
    """역할 경합에서 **진 쪽**도 멀쩡한 엔진을 버리지 않는다.

    데이터베이스 생성과 똑같은 자리다. 준비와 세션 시작 훅이 겹쳐 돌면 둘 다
    「역할이 없다」를 보고 한쪽만 만든다. 실측(2026-09-08, PostgreSQL 16.13):
    `CREATE ROLE` 둘을 겹쳐 돌리니 진 쪽이 `duplicate key value violates unique
    constraint "pg_authid_rolname_index"` 로 끝났고, 역할은 `rolcreatedb = t` 로
    멀쩡히 있었다.

    진 쪽이 그것을 「권한을 얻지 못했다」로 읽으면 SQLite 로 물러나고, 그러면
    이긴 쪽이 고른 PostgreSQL 을 지운다.
    """
    created = tmp_path / "role-created-by-the-winner"
    stub = _stub_directory(
        tmp_path,
        {
            "pg_isready": "exit 0",
            "psql": (
                'case "$*" in\n'
                # 역할 조회는 이긴 쪽이 만들었는지에 따라 답이 달라진다.
                "  *rolcreatedb*)\n"
                f'    [ -e {created} ] && echo t\n'
                "    exit 0;;\n"
                "  *has_schema_privilege*) echo t;;\n"
                # 우리가 만들려는 사이에 이긴 쪽이 이미 만들어 두었다.
                "  *CREATE\\ ROLE*)\n"
                f"    touch {created}\n"
                '    echo "ERROR:  duplicate key value violates unique constraint'
                ' \\"pg_authid_rolname_index\\"" >&2\n'
                "    exit 1;;\n"
                "  *) echo 1;;\n"
                "esac"
            ),
            "createdb": "exit 0",
            # 권한 상승은 열어 둔다 — 막으면 이 갈래에 닿지 못한다.
            "su": 'shift\n[ "$1" = "-c" ] && shift\nexec sh -c "$*"',
            "sudo": (
                'while [ "$1" = "-n" ] || [ "$1" = "-u" ]; do\n'
                '  [ "$1" = "-u" ] && shift\n'
                "  shift\n"
                "done\n"
                'exec "$@"'
            ),
        },
    )

    result = _run_database_script(stub)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), (
        f"역할 경합에서 졌다고 쓸 수 있는 엔진을 버렸다: {result.stderr}"
    )


def test_the_hook_clears_an_inherited_dead_url(tmp_path: Path) -> None:
    """읽지 않는 것으로는 **모자란다.**

    이미 주소를 읽은 셸에서 새 셸을 열면 그 값이 `export` 로 물려받아진다. 그
    사이에 서버가 내려갔으면 판정은 실패하는데, 훅이 「읽지 않는다」로 끝나면
    **물려받은 죽은 주소가 그대로 남는다** — 사람은 약속된 SQLite 가 아니라 붙지
    않는 PostgreSQL 을 향해 명령을 친다.

    실측(2026-09-08): 부모가 읽은 뒤 판정이 실패하는 상황을 만드니 자식 셸의
    `DATABASE_URL` 이 그대로였다.

    **그러면서 사람이 직접 고른 주소는 남겨야 한다.** 지울지 말지의 정의는
    `autoselected.sh` 한 곳에 있고, 훅은 그것을 그대로 쓴다.
    """
    repository = tmp_path / "repo"
    devcontainer = repository / ".devcontainer"
    devcontainer.mkdir(parents=True)
    (devcontainer / "autoselected.sh").write_text(
        (REPOSITORY_ROOT / ".devcontainer" / "autoselected.sh").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    chosen = "postgresql+psycopg:///production_risk?host=/socket&port=5432"
    (devcontainer / "database.env").write_text(
        f"export DATABASE_URL={shlex.quote(chosen)}\n"
        f"export PRODUCTION_RISK_DATABASE_AUTOSELECTED={shlex.quote(chosen)}\n",
        encoding="utf-8",
    )

    def _read(usable: bool, environment: dict[str, str]) -> str:
        (devcontainer / "database-usable.sh").write_text(
            "#!/usr/bin/env bash\nexit %d\n" % (0 if usable else 1), encoding="utf-8"
        )
        _install_hook(tmp_path, POSTGRESQL_URL)
        runner = tmp_path / "child.sh"
        runner.write_text(
            f". {devcontainer / 'shell-hook.sh'}\n"
            'printf \'%s\\n\' "${DATABASE_URL:-<none>}"\n',
            encoding="utf-8",
        )
        done = subprocess.run(
            ["bash", str(runner)],
            capture_output=True,
            text=True,
            env=environment,
            timeout=60,
        )
        assert done.returncode == 0, done.stderr
        return done.stdout.strip()

    inherited = _environment_without_a_url(
        {
            "HOME": str(tmp_path / "home"),
            "DATABASE_URL": chosen,
            "PRODUCTION_RISK_DATABASE_AUTOSELECTED": chosen,
        }
    )
    assert _read(usable=False, environment=inherited) == "<none>", (
        "판정이 실패했는데 물려받은 죽은 주소가 남았다"
    )

    # 사람이 직접 고른 주소는 표식이 붙지 않으므로 건드리지 않는다.
    theirs = _environment_without_a_url(
        {"HOME": str(tmp_path / "home"), "DATABASE_URL": "postgresql+psycopg://me@h/db"}
    )
    assert _read(usable=False, environment=theirs) == "postgresql+psycopg://me@h/db"

    # 그리고 쓸 수 있으면 여전히 읽는다.
    assert _read(usable=True, environment=inherited) == chosen


def test_the_last_usable_url_survives_preparation() -> None:
    """준비가 도는 동안 **주소가 사라지는 구간**을 만들지 않는다.

    준비 차례만으로 실측 **3.4~5.3초**다. 그 사이에 열린 셸은 훅이 읽을 파일을 못
    보고 SQLite 로 시작하며, 훅은 셸이 뜰 때 한 번만 도므로 **그 셸은 수명 내내
    SQLite** 다 — 같은 시각에 한 사람의 두 창이 서로 다른 엔진으로 돈다.

    그래서 지우는 것은 **SQLite 로 물러날 때뿐**이고, PostgreSQL 을 고른 경우에는
    마지막으로 쓸 수 있던 파일을 준비가 끝날 때까지 그대로 둔 뒤 **한 순간에**
    갈아 끼운다.
    """
    lines = [
        line
        for line in SETUP_SCRIPT.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]
    body = "\n".join(lines)

    # 조건 없는 삭제가 남아 있으면 그 구간이 다시 생긴다.
    assert '\nrm -f "$DATABASE_ENVIRONMENT_FILE"\n' not in body, (
        "준비 앞에서 조건 없이 지운다"
    )
    assert 'if [ "$database_url_is_ours" != "1" ] || [ -z "${DATABASE_URL:-}" ]' in body

    # 갈아 끼우는 것은 한 순간이어야 한다 — 옆에 쓰고 이름을 바꾼다.
    assert '} > "${DATABASE_ENVIRONMENT_FILE}.$$"' in body
    assert 'mv "${DATABASE_ENVIRONMENT_FILE}.$$" "$DATABASE_ENVIRONMENT_FILE"' in body

    # 준비가 실패하면 그때는 지운다 — 반쯤 올라간 주소를 남기지 않는다.
    prepares = next(
        index
        for index, line in enumerate(lines)
        if line.strip().startswith("if ! bash ") and "prepare-database.sh" in line
    )
    assert 'rm -f "$DATABASE_ENVIRONMENT_FILE"' in lines[prepares + 1]


def test_dependency_installation_is_serialized(tmp_path: Path) -> None:
    """의존성 설치도 **하나씩 지나간다.**

    「해시가 다른가」를 보고 나서 고치는 구간이라, 준비와 세션 시작 훅이 겹치면
    둘 다 「다르다」를 보고 둘 다 `npm ci` 로 들어간다. 그것은 이름대로
    node_modules 를 지우고 다시 만드는 명령이라 한쪽이 지우는 동안 다른 쪽이 쓴다.

    실측(2026-09-08): 1.5초 차이로 겹쳐 돌리니 세 번 중 **두 번** 양쪽이 다
    실패했고 `node_modules` 가 **0개**로 남았다 —
    `npm error code ENOTEMPTY / syscall rmdir / path .../node_modules/ws/lib`.

    잠금은 준비 차례와 **같은 것**을 쓴다. 여기서는 그 잠금이 실제로 서는지를
    `lock.sh` 를 직접 겹쳐 걸어 본다 — 글자만 보면 서는지 알 수 없다.
    """
    assert "open_production_risk_lock" in SETUP_SCRIPT.read_text(encoding="utf-8")

    trace = tmp_path / "trace"
    runner = tmp_path / "run.sh"
    runner.write_text(
        "set -uo pipefail\n"
        f". {REPOSITORY_ROOT / '.devcontainer' / 'lock.sh'}\n"
        'status=0\n'
        'open_production_risk_lock "install-test-$KEY" 8 || status=$?\n'
        '[ "$status" = 0 ] || { echo "잠금 실패 $status" >&2; exit 1; }\n'
        f'printf "%s\\n" "$$" >> {trace}\n'
        "sleep 0.3\n"
        f'printf "%s\\n" "$$" >> {trace}\n',
        encoding="utf-8",
    )

    environment = _environment_without_a_url(
        {"HOME": str(tmp_path), "KEY": tmp_path.name}
    )
    environment.pop("XDG_CACHE_HOME", None)
    runs = [
        subprocess.Popen(
            ["bash", str(runner)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=environment,
        )
        for _ in range(2)
    ]
    for run in runs:
        assert run.wait(timeout=120) == 0, run.stderr.read()

    owners = trace.read_text(encoding="utf-8").split()
    assert len(set(owners)) == 2, f"두 쪽이 다 돌지 않았다: {owners}"
    changes = sum(1 for before, after in zip(owners, owners[1:]) if before != after)
    assert changes == 1, f"설치 구간이 서로 끼어들었다: {owners}"


def test_the_profile_rewrite_never_loses_the_persons_lines(tmp_path: Path) -> None:
    """프로파일은 **남의 파일**이다 — 겹쳐 돌아도 한 줄도 잃지 않는다.

    표식이 이미 있으면 그 토막을 걷어내고 다시 적는데, 겹쳐 돌면 둘이 같은 임시
    파일을 쓰고 한쪽이 그것을 읽는 동안 다른 쪽이 잘라 버린다. 그러면 **그 사람의
    셸 설정이 영구히 사라진다.**

    실측(2026-09-08): 30만 줄짜리 프로파일에 0.12초 차이로 겹쳐 돌리니 네 번 중
    한 번 **9,144줄이 없어졌다**(290,856/300,000 남음). 우리 토막이 아니라 그
    사람의 줄이다.

    그래서 잠그고, 임시 이름에 프로세스 번호를 넣고, `mv` 로 한 순간에 갈아
    끼운다. 잃지 않는 것을 **실제로 겹쳐 돌려** 본다 — 글자만 보면 알 수 없다.
    """
    home = tmp_path / "home"
    home.mkdir()
    repository = tmp_path / "repo"
    (repository / ".devcontainer").mkdir(parents=True)

    marker = f"# ai-production-risk({repository}): 개발 세션의 데이터베이스 주소"
    # 파일이 작으면 겹칠 틈이 없어 이 검사가 무는지 알 수 없다.
    theirs = [f"export THEIRS_{index}=value_long_enough_{index}" for index in range(40000)]
    original = "\n".join(
        theirs
        + [
            "",
            marker,
            f'case "$PWD/" in {repository}/*)',
            "  if [ -f /x ]; then",
            "    . /x",
            "  fi ;;",
            "esac",
            "",
            "alias ll='ls -l'",
        ]
    ) + "\n"

    region = _shell_region(SETUP_SCRIPT, "SHELL_HOOK_MARKER=", "close_production_risk_lock 7")
    script = tmp_path / "rewrite.sh"
    script.write_text(
        "set -uo pipefail\n"
        f"REPOSITORY_ROOT={repository}\n"
        f"SHELL_HOOK_FILE={repository}/.devcontainer/shell-hook.sh\n"
        f". {REPOSITORY_ROOT / '.devcontainer' / 'lock.sh'}\n" + region + "\n",
        encoding="utf-8",
    )

    environment = _environment_without_a_url({"HOME": str(home)})
    environment.pop("XDG_CACHE_HOME", None)

    for _ in range(3):
        (home / ".bashrc").write_text(original, encoding="utf-8")
        runs = [
            subprocess.Popen(
                ["bash", str(script)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=environment,
            )
            for _ in range(2)
        ]
        for run in runs:
            assert run.wait(timeout=180) == 0, run.stderr.read()

        written = (home / ".bashrc").read_text(encoding="utf-8")
        kept = sum(1 for line in written.splitlines() if line.startswith("export THEIRS_"))
        assert kept == len(theirs), f"그 사람의 줄이 {len(theirs) - kept}개 사라졌다"
        assert "alias ll='ls -l'" in written
        # 그러면서 우리 토막은 하나여야 한다 — 겹쳐 돌아도 쌓이지 않는다.
        assert written.count("ai-production-risk(") == 1


def test_the_backend_install_is_inside_the_lock() -> None:
    """백엔드 설치도 **잠금 안**에 있다.

    실측(2026-09-08): `python -m venv` → `pip install --upgrade pip` →
    `pip install -r requirements.txt` 세 줄을 0.4초 차이로 겹쳐 돌리니 두 번 다
    한쪽이 종료코드 1 로 죽었다 —
    `ModuleNotFoundError: No module named 'pip._internal.utils'`.
    한쪽의 pip 갈아 끼우기가 다른 쪽이 쓰고 있는 pip 을 무너뜨린 것이다.
    (`python -m venv` 만 겹쳤을 때는 세 번 다 무사했다 — 무는 것은 venv 가 아니라
    pip 이다.)

    부르는 쪽이 `set -e` 아래이므로 그 종료 1 은 준비 전체를 끊는다.
    """
    lines = [
        line
        for line in SETUP_SCRIPT.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]

    def _line(needle: str) -> int:
        return next(index for index, line in enumerate(lines) if needle in line)

    opens = _line('open_production_risk_lock "install-')
    venv = _line("python -m venv backend/.venv")
    pip = _line("pip install -r backend/requirements.txt")
    npm = _line("npm --prefix frontend ci")
    closes = _line("close_production_risk_lock 8")

    assert opens < venv < pip < npm < closes, (
        "설치 세 갈래가 한 잠금 안에 들어 있지 않다"
    )


def test_createdb_names_the_maintenance_database() -> None:
    """`createdb` 에도 **붙을 곳을 적는다.**

    이 자리는 지금 당장 깨지지 않는다 — 실측(2026-09-08, createdb 16.13):
    `postgres` 는 있는데 이 역할의 `CONNECT` 이 없고 `template1` 은 되는 상태에서
    `createdb` 는 **세 번 다 성공**했다. 접속이 거부되면 스스로 `template1` 로
    물러난다.

    그런데 문서가 약속하는 것은 「`postgres` 가 **없거나** 대상 자신일 때
    `template1` 을 쓴다」뿐이고 접속 실패 시의 대체는 적혀 있지 않다. 우리가 이미
    고른 값이 있는데 **구현의 습관에 기댈 이유가 없다** — 위의 권한 명령들이
    이미 같은 이유로 `-d` 를 명시한다.
    """
    body = "\n".join(
        line
        for line in DATABASE_SCRIPT.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )
    assert '--maintenance-db="$maintenance_database"' in body


def test_the_devcontainer_provisions_postgresql() -> None:
    """개발 컨테이너에 PostgreSQL 이 **실제로 놓인다.**

    `database.sh` 는 「있으면 세우고 없으면 SQLite 로 물러난다」로 지어졌는데,
    이 저장소의 devcontainer 에는 **없었다** — 이미지는
    `mcr.microsoft.com/devcontainers/python` 이고 붙은 기능은 Node 하나뿐이며
    저장소 어디에도 설치 단계가 없었다. 그러면 새로 만든 Codespace 에서는
    `command -v pg_isready` 가 늘 실패해 **언제나 SQLite** 로 물러나고, 이 PR 이
    세우려던 「개발 세션도 운영과 같은 엔진」이 정작 서지 않는다. CI 는 서 있으므로
    아무도 알아채지 못한다.

    판을 못 박는 것도 함께 본다 — 배포판 기본은 15 이고 운영·CI 는 16 이다.
    개발만 한 판 뒤처지면 이 PR 이 없애려던 어긋남이 판 번호로 되돌아온다.
    """
    install = REPOSITORY_ROOT / ".devcontainer" / "install-postgresql.sh"
    assert install.exists(), "devcontainer 가 PostgreSQL 을 놓지 않는다"

    body = install.read_text(encoding="utf-8")
    # compose 가 쓰는 판과 같아야 한다 — 두 곳에 숫자를 적었으면 견준다.
    compose = (REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8")
    major = re.search(r"^MAJOR_VERSION=(\d+)$", body, re.MULTILINE)
    assert major, "놓을 판이 적혀 있지 않다"
    assert f"postgres:{major.group(1)}" in compose, (
        f"개발이 놓는 판({major.group(1)})이 compose 의 판과 다르다"
    )

    # 그리고 준비가 그것을 **엔진을 고르기 전에** 부른다.
    lines = [
        line
        for line in SETUP_SCRIPT.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]
    installs = next(
        index for index, line in enumerate(lines) if "install-postgresql.sh" in line
    )
    chooses = next(
        index for index, line in enumerate(lines) if "bash .devcontainer/database.sh" in line
    )
    assert installs < chooses, "엔진을 고른 뒤에 놓는다"


def test_failing_to_provision_postgresql_is_not_fatal(tmp_path: Path) -> None:
    """못 놓는 것은 **고장이 아니다.**

    부르는 쪽이 `set -e` 아래이므로 여기서 나가는 0 아닌 값은 준비 전체를 끌고
    내려간다. 못 놓으면 `database.sh` 가 예전처럼 SQLite 로 물러나는 것이 맞다 —
    이 저장소가 실패에 대해 약속한 자리다.
    """
    # `pg_isready` 가 보이지 않는 좁은 `PATH` 를 만든다. 스텁으로는 「없음」을
    # 흉내 낼 수 없어(`command -v` 가 찾는다) 필요한 것만 골라 넣는다.
    #
    # **시스템 바이너리를 가리키는 링크는 두지 않는다.** 그 자리에 무언가를
    # 덮어쓰면 링크를 따라가 진짜 명령을 망가뜨린다 — 이 검사를 손으로 만들다
    # 실제로 `/usr/bin/id` 를 날려 본 적이 있다. 필요한 것은 `bash` 하나뿐이고,
    # `id` 는 처음부터 스텁으로 둔다.
    narrow = tmp_path / "bin"
    narrow.mkdir()
    (narrow / "bash").symlink_to(shutil.which("bash"))
    stub_identity = narrow / "id"
    stub_identity.write_text(
        '#!/bin/sh\nif [ "$1" = "-u" ]; then echo 1000; else echo nobody; fi\n',
        encoding="utf-8",
    )
    stub_identity.chmod(0o755)

    install = REPOSITORY_ROOT / ".devcontainer" / "install-postgresql.sh"

    def _run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(narrow / "bash"), str(install)],
            capture_output=True,
            text=True,
            env={"PATH": str(narrow), "HOME": str(tmp_path)},
            timeout=120,
        )

    # ① 놓을 방법을 모르는 환경 (apt-get 없음)
    done = _run()
    assert done.returncode == 0, done.stderr
    assert "SQLite" in done.stderr

    # ② 권한이 없는 환경 (비root · sudo 없음)
    (narrow / "apt-get").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (narrow / "apt-get").chmod(0o755)
    done = _run()
    assert done.returncode == 0, done.stderr
    assert "SQLite" in done.stderr


def test_the_shell_hook_file_is_published_atomically() -> None:
    """훅 파일도 **한 순간에** 갈아 끼운다.

    리다이렉션은 파일을 먼저 자르고 `printf` 를 여러 번 부르므로, 그 사이에 뜬
    셸이 반쯤 쓰인 파일을 읽는다 — 문법 오류가 나거나 엔진 판단의 절반만 돈다.
    실측(2026-09-08): 쓰는 쪽과 읽는 쪽을 8초 동안 겹쳐 돌리니 **2,895번 중
    95번**이 완성되지 않은 파일을 봤다(빈 파일 46 · 반쯤 49).
    """
    body = "\n".join(
        line
        for line in SETUP_SCRIPT.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )
    assert '} > "${SHELL_HOOK_FILE}.$$"' in body, "훅 파일을 곧바로 덮어쓴다"
    assert 'mv "${SHELL_HOOK_FILE}.$$" "$SHELL_HOOK_FILE"' in body
    assert '} > "$SHELL_HOOK_FILE"' not in body


def test_a_symlinked_profile_survives(tmp_path: Path) -> None:
    """프로파일이 **심볼릭 링크**여도 링크가 살아남는다.

    dotfiles 저장소를 링크로 걸어 두는 것이 흔한데, `mv` 로 갈아 끼우면 링크
    자체가 일반 파일로 바뀐다 — 내용은 남지만 그 뒤로 dotfiles 의 갱신이 이
    프로파일에 닿지 않는다. 실측(2026-09-08): `lrwxrwxrwx ... -> dotfiles/bashrc`
    가 `-rw-r--r--` 로 바뀌었고 우리 토막이 원본과 사본 양쪽에 남았다.

    링크가 가리키는 **그 파일**을 고친다 — 사람이 링크를 건 뜻이 그것이다.
    """
    home = tmp_path / "home"
    home.mkdir()
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    repository = tmp_path / "repo"
    (repository / ".devcontainer").mkdir(parents=True)

    marker = f"# ai-production-risk({repository}): 개발 세션의 데이터베이스 주소"
    (dotfiles / "bashrc").write_text(
        "export FROM_DOTFILES=1\n\n"
        + marker
        + "\n"
        + f'case "$PWD/" in {repository}/*)\n  if [ -f /x ]; then\n    . /x\n  fi ;;\nesac\n',
        encoding="utf-8",
    )
    (home / ".bashrc").symlink_to(dotfiles / "bashrc")

    region = _shell_region(
        SETUP_SCRIPT, "SHELL_HOOK_MARKER=", "close_production_risk_lock 7"
    )
    script = tmp_path / "rewrite.sh"
    script.write_text(
        "set -uo pipefail\n"
        f"REPOSITORY_ROOT={repository}\n"
        f"SHELL_HOOK_FILE={repository}/.devcontainer/shell-hook.sh\n"
        f". {REPOSITORY_ROOT / '.devcontainer' / 'lock.sh'}\n" + region + "\n",
        encoding="utf-8",
    )
    environment = _environment_without_a_url({"HOME": str(home)})
    environment.pop("XDG_CACHE_HOME", None)
    done = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, env=environment, timeout=120
    )
    assert done.returncode == 0, done.stderr

    assert (home / ".bashrc").is_symlink(), "링크가 일반 파일로 바뀌었다"
    written = (dotfiles / "bashrc").read_text(encoding="utf-8")
    assert "export FROM_DOTFILES=1" in written
    assert written.count("ai-production-risk(") == 1
    assert "shell-hook.sh" in written


def test_a_database_full_of_someone_elses_tables_is_not_advertised(
    tmp_path: Path,
) -> None:
    """**스키마 권한은 남의 표를 만질 권리가 아니다.**

    여러 사람이 쓰는 개발 호스트에서 `production_risk` 를 먼저 만든 사람이 있으면
    표의 소유자는 그 사람이다. 이쪽이 `public` 의 `USAGE`·`CREATE` 를 받아도 그
    표에는 아무 권한이 없는데, 판정이 스키마만 보면 **쓸 수 있다고 답한다.**

    실측(2026-09-09, PostgreSQL 16.13): `otherdev` 가 소유한 `items` 가 있는
    데이터베이스에 `devprobe` 로 붙으니 판정은 종료코드 0 이었고, 바로 다음 두
    동작은 `permission denied for table items`(preflight·시드가 하는 일)와
    `must be owner of table items`(`alembic upgrade head` 가 하는 일)로 거부됐다.

    진짜 서버를 세우지 않는다. 이 검사가 묻는 것은 「PostgreSQL 이 이렇게 답할 때
    이 파일이 무엇을 하는가」이므로, 그 답을 내는 가짜 `psql` 을 앞에 둔다 —
    그리고 **질의가 무엇을 묻는지**가 아니라 그 답에 따라 무엇을 하는지를 본다.
    """
    usable_script = REPOSITORY_ROOT / ".devcontainer" / "database-usable.sh"

    # 가짜 `psql` 은 질의를 그대로 평가하지 않는다. 대신 「스키마 권한은 있는데
    # 남의 표가 서 있는 데이터베이스」를 흉내 낸다 — 소유를 묻는 질의에만 f 다.
    stub = _stub_directory(
        tmp_path,
        {
            "psql": (
                'case "$*" in\n'
                "  *pg_has_role*) echo f;;\n"
                "  *) echo t;;\n"
                "esac"
            )
        },
    )
    environment = _environment_without_a_url(
        {"PATH": f"{stub}{os.pathsep}{os.environ['PATH']}"}
    )
    result = subprocess.run(
        ["bash", str(usable_script), "/var/run/postgresql", "5432", "production_risk"],
        capture_output=True,
        text=True,
        env=environment,
        timeout=60,
    )
    assert result.returncode != 0, (
        "남의 표가 있는 데이터베이스를 쓸 수 있다고 답했다 — "
        "판정이 이미 서 있는 표의 소유를 묻지 않는다"
    )


def test_an_explicit_database_url_does_not_provision_postgresql() -> None:
    """사람이 준 주소에는 **서버를 깔지 않는다.**

    `DATABASE_URL` 을 손수 준 경우 — 바깥 PostgreSQL 이든 명시한 SQLite 든 —
    아래 갈래는 그 값을 그대로 지키므로 여기서 깐 서버는 한 번도 쓰이지 않는다.
    쓰이지도 않을 것을 위해 PGDG 저장소를 더하고 apt 로 서버를 앉히는 것은 남의
    컨테이너에 몇 분과 영구적인 시스템 변경을 남기는 일이다.

    글자로 「안에 있다」고 적는 대신 **줄 번호로 가둔다** — 부르는 자리가 우리가
    고르는 갈래의 여는 줄과 닫는 줄 사이에 있어야 한다.
    """
    lines = SETUP_SCRIPT.read_text(encoding="utf-8").splitlines()

    opens = next(
        index
        for index, line in enumerate(lines)
        if line == 'if [ -z "${DATABASE_URL:-}" ]; then'
    )
    closes = next(index for index, line in enumerate(lines[opens:], opens) if line == "fi")
    installs = next(
        index
        for index, line in enumerate(lines)
        if "install-postgresql.sh" in line and line.lstrip().startswith("bash ")
    )

    assert opens < installs < closes, (
        "주소가 이미 있어도 PostgreSQL 을 깐다 — "
        f"설치는 {installs + 1}번째 줄, 갈래는 {opens + 1}~{closes + 1}번째 줄"
    )


def test_the_environment_file_is_published_under_a_private_name() -> None:
    """발행에 쓰는 임시 이름은 **프로세스마다 달라야 한다.**

    이 자리는 잠금 밖이다 — 설치 잠금은 위에서 이미 놓았고 준비 잠금은
    `prepare-database.sh` 안에서 끝났다. 둘이 같은 임시 이름을 쓰면, 한쪽이 그것을
    `mv` 로 옮긴 뒤에도 다른 쪽은 그 파일을 **연 채로** 남아 이어지는 write 가
    옮겨진 목적지로 새어 들어간다.

    실측(2026-09-09, 0.02초 어긋나게 40회): 고정된 이름으로는 40회 모두
    `mv: cannot stat ...: No such file or directory` 로 죽었고, 40회 모두 발행된
    파일이 `DATABASE_URL` 은 이쪽 주소, 표식은 저쪽 주소인 섞인 상태로 남았다.
    프로세스 번호를 넣으니 40회 모두 0 이었고 섞인 것은 0회였다.

    이름을 통째로 못 박지 않는다 — 다음에 이름이 바뀌어도 **프로세스마다 다르다**는
    성질만 지키면 된다.
    """
    lines = [
        line
        for line in SETUP_SCRIPT.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]
    writes = next(
        line
        for line in lines
        if line.strip().startswith("} > ") and "DATABASE_ENVIRONMENT_FILE" in line
    )
    renames = next(
        line
        for line in lines
        if line.strip().startswith("mv ") and "DATABASE_ENVIRONMENT_FILE" in line
    )

    for line in (writes, renames):
        assert "$$" in line, f"임시 이름에 프로세스 번호가 없다: {line.strip()}"


def test_the_first_profile_install_never_writes_to_the_live_file(
    tmp_path: Path,
) -> None:
    """**첫 설치도 살아 있는 프로파일에 쓰지 않는다.**

    예전에는 표식이 있을 때만 옆에 쓰고 `mv` 했고, 첫 설치는 `>> "$profile"` 로
    살아 있는 파일에 곧장 붙였다. 실측(2026-09-09, strace): 그 토막은 **write
    7번**으로 나갔고 중간 상태 8가지 중 **4가지가 `syntax error: unexpected end of
    file`** 이었다 — `case` 는 열렸는데 `esac` 이 아직 안 온 자리다.

    창은 좁다(실측: 살아 있는 읽기 2,139회 중 0회). 그럼에도 고치는 이유는 두
    갈래가 서로 다른 약속 위에 서 있던 것 자체가 위험이기 때문이다.

    그래서 **살아 있는 파일로 간 write 를 센다.** 글자를 보지 않고 시스템콜을
    본다 — 0 이어야 한다.
    """
    if shutil.which("strace") is None:
        pytest.skip("strace 가 없다 — 시스템콜을 셀 수 없다")

    home = tmp_path / "home"
    home.mkdir()
    profile = home / ".bashrc"
    # 표식이 **없는** 상태 — 첫 설치 갈래다.
    profile.write_text("export EDITOR=vim\n", encoding="utf-8")

    repository = tmp_path / "repo"
    (repository / ".devcontainer").mkdir(parents=True)

    region = _shell_region(
        SETUP_SCRIPT, "SHELL_HOOK_MARKER=", "close_production_risk_lock 7"
    )
    script = tmp_path / "install.sh"
    script.write_text(
        "set -uo pipefail\n"
        f"REPOSITORY_ROOT={repository}\n"
        f"SHELL_HOOK_FILE={repository}/.devcontainer/shell-hook.sh\n"
        f". {REPOSITORY_ROOT / '.devcontainer' / 'lock.sh'}\n" + region + "\n",
        encoding="utf-8",
    )
    environment = _environment_without_a_url({"HOME": str(home)})
    environment.pop("XDG_CACHE_HOME", None)

    trace = tmp_path / "trace.txt"
    done = subprocess.run(
        [
            "strace", "-f", "-y",           # `-y` 는 fd 옆에 그 파일의 경로를 적어 준다.
            "-e", "trace=write",
            "-o", str(trace),
            "bash", str(script),
        ],
        capture_output=True,
        text=True,
        env=environment,
        timeout=180,
    )
    assert done.returncode == 0, done.stderr

    written_live = [
        line
        for line in trace.read_text(encoding="utf-8", errors="replace").splitlines()
        # `-y` 는 fd 옆에 `<경로>` 를 적는다. **닫는 꺾쇠까지** 함께 본다 —
        # 그냥 부분문자열로 보면 옆에 둔 `.bashrc.production-risk.<번호>` 가
        # 프로파일 경로로 시작하므로 그것까지 물어, 고쳐도 계속 빨갛다.
        if "write(" in line and f"<{profile}>" in line
    ]
    assert not written_live, (
        "살아 있는 프로파일로 write 가 갔다 — 옆에 쓰고 `mv` 하지 않는다:\n"
        + "\n".join(written_live[:5])
    )
    # 그러면서 결과는 제대로 적혀 있어야 한다 — 아무것도 안 하면 위 단언은 공짜다.
    assert "ai-production-risk(" in profile.read_text(encoding="utf-8")


def test_a_client_only_installation_still_provisions_the_server(
    tmp_path: Path,
) -> None:
    """`pg_isready` 가 있다고 **서버가 있는 것이 아니다.**

    실측(2026-09-09): `pg_isready` 를 주는 꾸러미는 `postgresql-client-common`
    이고, `postgresql-client-16` 이 의존하는 것도 그것뿐 — 서버 꾸러미
    `postgresql-16` 은 그 사슬에 없다. 클라이언트만 있는 PATH 로 돌리니 예전
    코드는 종료코드 0 으로 아무것도 하지 않고 끝났고, 그 뒤 `pg_ctlcluster` 는
    없었다. 그러면 `database.sh` 는 SQLite 로 물러난다 — 이 파일이 세우려던 보장이
    정작 서지 않는다.

    건너뛰었는지를 **말로** 본다. 건너뛰면 아무 말이 없고, 건너뛰지 않으면 다음
    관문(`apt-get` 없음)에서 물러나며 그 이유를 적는다.
    """
    install_script = REPOSITORY_ROOT / ".devcontainer" / "install-postgresql.sh"

    # `pg_isready` 는 있고 `pg_ctlcluster` 와 `apt-get` 은 없는 자리.
    stub = _stub_directory(tmp_path, {"pg_isready": "exit 0"})
    for name in ("bash", "sed", "grep", "cat", "id", "printf", "uname", "dirname"):
        found = shutil.which(name)
        if found:
            (stub / name).symlink_to(found)

    result = subprocess.run(
        ["bash", str(install_script)],
        capture_output=True,
        text=True,
        env=_environment_without_a_url({"PATH": str(stub)}),
        timeout=120,
    )
    assert result.returncode == 0, "설치에 실패하는 것은 고장이 아니다 — 0 이어야 한다"
    assert "SQLite" in result.stderr, (
        "클라이언트만 보고 서버가 있다고 여겨 건너뛰었다 — "
        f"아무 말이 없다: {result.stderr!r}"
    )
