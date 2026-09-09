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

    # 판 번호는 **한 곳**에만 있어야 한다. 놓는 쪽과 고르는 쪽이 각자 숫자를 들고
    # 있으면 언젠가 어긋나고, 그때 16을 깔아 놓고 15에 붙는 상태가 조용히 선다.
    version_file = REPOSITORY_ROOT / ".devcontainer" / "postgresql-version.sh"
    assert version_file.exists(), "판 번호를 둘 한 곳이 없다"
    major = re.search(
        r"^PRODUCTION_RISK_POSTGRESQL_MAJOR=(\d+)$",
        version_file.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert major, "놓을 판이 적혀 있지 않다"

    # compose 가 쓰는 판과 같아야 한다.
    compose = (REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert f"postgres:{major.group(1)}" in compose, (
        f"개발이 놓는 판({major.group(1)})이 compose 의 판과 다르다"
    )

    # 그리고 두 스크립트가 그 한 곳에서 받아 쓴다 — 자기 숫자를 들고 있으면 안 된다.
    for script in (install, REPOSITORY_ROOT / ".devcontainer" / "database.sh"):
        body = script.read_text(encoding="utf-8")
        assert "postgresql-version.sh" in body, f"{script.name} 이 판을 따로 정한다"
        stray = [
            line
            for line in body.splitlines()
            if re.match(r"^\s*(MAJOR_VERSION|POSTGRESQL_MAJOR)=\d+\s*$", line)
        ]
        assert not stray, f"{script.name} 에 판 번호가 따로 박혀 있다: {stray}"

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


def test_the_app_table_list_matches_the_models() -> None:
    """`app-tables.txt` 는 **모델과 한 글자도 다르면 안 된다.**

    셸 판정(`database-usable.sh`)이 「이미 서 있는 표를 이 역할이 만질 수 있는가」를
    물을 때 그 목록이 필요한데, 목록의 출처인 파이썬을 새 셸마다 띄우면 실측
    0.7초가 붙는다. 그래서 값만 미리 꺼내 두었고 — 미리 꺼낸 값은 **낡는다.**

    낡으면 조용히 틀린다. 새 표가 목록에 없으면 남이 소유한 그 표를 판정이 못 보고
    쓸 수 있다고 답하며, 없어진 표가 남아 있으면 없는 이름을 묻는다. 그래서 여기가
    그 파일과 `Base.metadata` 를 견주는 자리다 — `preflight.py` 가 보는 것과 같은
    출처다.
    """
    from app.db.table_names import table_names

    listed = [
        line.strip()
        for line in (REPOSITORY_ROOT / ".devcontainer" / "app-tables.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert listed == table_names(), (
        "`.devcontainer/app-tables.txt` 가 모델과 다릅니다. 다시 만드십시오:\n"
        "  cd backend && .venv/bin/python -m app.db.table_names "
        "> ../.devcontainer/app-tables.txt"
    )


def test_an_unrelated_table_does_not_push_the_session_to_sqlite(
    tmp_path: Path,
) -> None:
    """**남의 표 하나 때문에 SQLite 로 물러나지 않는다.**

    스키마를 나눠 쓰는 곳에는 이 앱과 무관한 표가 함께 산다 — 관리자가 만든 감사
    표 같은 것. `preflight.py` 는 그것을 두고 「보는 것은 이 앱의 표뿐이다. 아무
    표나 있으면 막으면 ... 첫 기동이 영영 마이그레이션을 하지 못한다」고 적어 두었고
    `drop_all` 도 같은 목록을 본다. 판정이 그것과 다른 답을 내면 저장소 안에서 두
    곳이 같은 질문에 다르게 답하는 것이다.

    실측(2026-09-09, PostgreSQL 16.13): 앱의 표는 전부 이 역할 소유인 데이터베이스에
    관리자 소유 `audit_log` 하나를 두니, 앱은 `SELECT count(*) FROM items` 와
    `ALTER TABLE orders` 를 멀쩡히 해내는데 판정만 1(SQLite 로 물러남)이었다.
    """
    usable_script = REPOSITORY_ROOT / ".devcontainer" / "database-usable.sh"

    # 가짜 `psql` 은 질의를 평가하지 않는다. 대신 **질의가 무엇을 묻는지**를 본다 —
    # 앱의 표 이름으로 좁혀 묻고 있으면 그 데이터베이스를 받아들이는 것이 맞다.
    stub = _stub_directory(
        tmp_path,
        {
            "psql": (
                'case "$*" in\n'
                # 앱의 표 이름으로 좁혀 물으면 남의 표는 애초에 걸리지 않는다.
                '  *"c.relname = ANY"*) echo t;;\n'
                # 좁히지 않고 `public` 전체를 묻는 형태에는 남의 표가 걸린다.
                "  *pg_has_role*) echo f;;\n"
                "  *) echo t;;\n"
                "esac"
            )
        },
    )
    result = subprocess.run(
        ["bash", str(usable_script), "/socket", "5432", "production_risk"],
        capture_output=True,
        text=True,
        env=_environment_without_a_url(
            {"PATH": f"{stub}{os.pathsep}{os.environ['PATH']}"}
        ),
        timeout=60,
    )
    assert result.returncode == 0, (
        "앱의 표로 좁혀 묻지 않는다 — 무관한 표 하나에 SQLite 로 물러난다"
    )


def test_a_busy_lock_stops_instead_of_entering(tmp_path: Path) -> None:
    """잠금을 **다른 실행이 쥐고 있으면 들어가지 않는다.**

    상태 셋은 서로 다른 사실이다. 「잠글 자리가 없다」(1)와 「잠그지 못했다」(3)는
    겹쳐 돈다는 증거가 아니므로 알리고 나아가는 것이 맞다. 그런데 「다른 실행이
    쥐고 있다」(2)는 겹쳐 돈다는 증거 **그 자체**이고, 그때 들어가면 잠금이
    막으려던 바로 그 상황에서만 잠금 없이 들어가는 셈이 된다.

    이 잠금들이 지키는 것은 되돌릴 수 없는 것들이다 — `npm ci` 는 `node_modules` 를
    지우고 다시 만들고(실측 2026-09-08: 겹쳐 돌린 세 번 중 두 번 양쪽이 다 실패해
    0개로 남았다), 프로파일 다시 쓰기는 남의 `.bashrc` 를 갈아 끼운다(실측: 30만
    줄 중 9,144줄이 사라졌다).

    규칙은 `lock.sh` 한 곳에 있으므로 여기서 그것을 직접 돌려 본다.
    """
    script = tmp_path / "permits.sh"
    script.write_text(
        "set -uo pipefail\n"
        f". {REPOSITORY_ROOT / '.devcontainer' / 'lock.sh'}\n"
        'for status in 0 1 2 3; do\n'
        '  if production_risk_lock_permits "$status" "무엇" 2> /dev/null; then\n'
        '    echo "$status 들어감"\n'
        '  else\n'
        '    echo "$status 멈춤"\n'
        '  fi\n'
        'done\n',
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == [
        "0", "들어감", "1", "들어감", "2", "멈춤", "3", "들어감",
    ], result.stdout


def test_provisioning_and_selection_share_one_lock() -> None:
    """놓기와 고르기는 **한 잠금 안**에 함께 있다.

    이 둘이 건드리는 것은 저장소 안이 아니라 호스트 전체다 — apt 저장소와 키링,
    꾸러미 데이터베이스, PostgreSQL 클러스터와 그 안의 역할. 위의 설치 잠금은
    저장소 열쇠라 여기서는 쓸 수 없고 그마저 이미 놓았다.

    겹치면 무엇이 나쁜가. 놓기는 **실패해도 0 으로 끝나기로** 되어 있으므로, 한쪽이
    반쯤 놓인 상태를 보고 물러나면 그쪽은 SQLite 를 고르고 다른 쪽은 마저 놓고
    PostgreSQL 을 고른다 — 같은 컨테이너의 두 세션이 서로 다른 엔진 위에서 돈다.

    글자로 「안에 있다」를 확인하는 대신 **줄 번호로 가둔다.**
    """
    lines = [
        line
        for line in SETUP_SCRIPT.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]

    opens = next(
        index
        for index, line in enumerate(lines)
        if "open_production_risk_lock" in line and '"provision"' in line
    )
    closes = next(
        index
        for index, line in enumerate(lines[opens:], opens)
        if line.strip().startswith("close_production_risk_lock")
    )
    installs = next(
        index for index, line in enumerate(lines) if "install-postgresql.sh" in line
    )
    chooses = next(
        index
        for index, line in enumerate(lines)
        if "bash .devcontainer/database.sh" in line
    )

    assert opens < installs < closes, "놓기가 잠금 밖에 있다"
    assert opens < chooses < closes, "고르기가 잠금 밖에 있다"
    # 그리고 그 잠금 열쇠는 저장소가 아니라 호스트여야 한다 — apt 는 하나뿐이다.
    assert "repository_key" not in lines[opens], (
        "놓기 잠금이 저장소마다 따로 걸린다 — 다른 체크아웃과 겹친다"
    )


def test_each_checkout_gets_its_own_database() -> None:
    """체크아웃마다 **다른 데이터베이스**를 고른다.

    워크트리 둘이나 나란한 체크아웃 둘이 같은 클러스터에서 같은 이름을 고르면,
    파일과 마이그레이션은 서로 다른데 데이터베이스는 하나다.

    실측(2026-09-09): 다른 가지가 남긴 리비전 `deadbeefcafe` 가 `alembic_version` 에
    든 데이터베이스에 이 체크아웃이 `alembic upgrade head` 를 돌리니
    `Can't locate revision identified by 'deadbeefcafe'` 로 죽었다.

    이름 규칙을 베끼지 않는다 — **실제 스크립트를 두 자리에서 돌려** 서로 다른
    이름이 나오는지 본다.
    """
    database_script = REPOSITORY_ROOT / ".devcontainer" / "database.sh"
    # 규칙을 베끼지 않는다 — 그 줄을 파일에서 그대로 꺼내 돌린다.
    name_of = next(
        line
        for line in database_script.read_text(encoding="utf-8").splitlines()
        if line.startswith("DATABASE_NAME=")
    )

    names = []
    for root in ("/home/someone/repo-a", "/home/someone/repo-b"):
        script = f'REPOSITORY_ROOT={root}\n{name_of}\nprintf %s "$DATABASE_NAME"\n'
        done = subprocess.run(
            ["bash", "-c", script], capture_output=True, text=True, timeout=60
        )
        assert done.returncode == 0, done.stderr
        names.append(done.stdout)

    assert names[0] != names[1], f"두 체크아웃이 같은 이름을 고른다: {names[0]}"
    for name in names:
        assert name.startswith("production_risk"), name
        # PostgreSQL 의 이름 한계는 `NAMEDATALEN-1` = 63 이다.
        assert len(name) <= 63, f"이름이 {len(name)}자다 — 잘려서 서로 부딪친다"


def test_an_older_server_on_the_port_is_not_used(tmp_path: Path) -> None:
    """포트를 지키는 서버가 **다른 판이면 쓰지 않는다.**

    데비안에서 판을 올리면 옛 클러스터가 5432를 그대로 쥔 채 새 판이 5433으로
    밀리는 것이 정상 상태다. 그때 16 바이너리는 분명히 있는데 붙는 자리는 15다.
    실측(2026-09-09, 가짜 `pg_lsclusters` 로 `15 main 5432 down` 을 놓고):
    `install-postgresql.sh` 는 아무 말 없이 0 으로 끝났고 `database.sh` 는
    **"PostgreSQL 15/main 를 기동합니다"** 라고 답했다. 조용하다는 점에서 더 나쁘다 —
    CI 는 16이라 아무도 알아채지 못한다.

    **못 읽었을 때는 버리지 않는다.** 물음이 실패했거나 답이 그 꼴이 아니면 아는
    것은 「판을 모른다」이지 「판이 다르다」가 아니다. 두 자리를 함께 본다.
    """
    version_file = REPOSITORY_ROOT / ".devcontainer" / "postgresql-version.sh"
    major = re.search(
        r"^PRODUCTION_RISK_POSTGRESQL_MAJOR=(\d+)$",
        version_file.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert major
    ours = int(major.group(1))

    def run(server_version_num: str) -> subprocess.CompletedProcess[str]:
        room = tmp_path / server_version_num
        room.mkdir(parents=True, exist_ok=True)
        stub = _stub_directory(
            room,
            {
                "pg_isready": "exit 0",
                "psql": (
                    'case "$*" in\n'
                    f"  *server_version_num*) echo {server_version_num};;\n"
                    "  *) exit 2;;\n"
                    "esac"
                ),
                "createdb": "exit 1",
                "su": "exit 1",
                "sudo": "exit 1",
            },
        )
        return _run_database_script(stub)

    older = run(f"{ours - 1}0013")
    assert older.returncode == 0, older.stderr
    assert older.stdout.strip() == "", "한 판 뒤처진 서버의 주소를 내밀었다"
    assert f"{ours - 1} 판입니다" in older.stderr, older.stderr

    # 판을 알 수 없을 때는 이 검사 때문에 물러나지 않는다.
    unknown = run("알수없음")
    assert unknown.returncode == 0, unknown.stderr
    assert "판입니다" not in unknown.stderr, (
        f"판을 못 읽었는데 판이 다르다고 말한다: {unknown.stderr!r}"
    )


def test_the_hook_keeps_a_manually_chosen_url(tmp_path: Path) -> None:
    """훅은 **사람이 고른 주소를 덮지 않는다.**

    두 갈래가 어긋나 있었다. 지우는 쪽은 「우리가 고른 것인가」를 물었는데
    **적는 쪽은 묻지 않고 덮었다.** 그래서 사람이 `export DATABASE_URL=...` 로
    다른 데이터베이스를 골라 둔 셸에서 저장소 안으로 들어가 새 셸을 열면, 훅이
    말없이 우리 주소로 되돌려 놓는다 — 표식이 아직 옛 값을 가리켜도 마찬가지다.

    세 자리를 함께 본다. 아무것도 없으면 우리 것을 내주고, 사람이 고른 것이 있으면
    그대로 두고, 우리가 지난번에 내준 것이면 새 값으로 바꾼다.
    """
    repository = tmp_path / "repo"
    (repository / ".devcontainer").mkdir(parents=True, exist_ok=True)
    (repository / ".devcontainer" / "database.env").write_text(
        "export DATABASE_URL=chosen\n"
        "export PRODUCTION_RISK_DATABASE_AUTOSELECTED=chosen\n",
        encoding="utf-8",
    )
    (repository / ".devcontainer" / "database-usable.sh").write_text(
        "#!/usr/bin/env bash\nexit 0\n", encoding="utf-8"
    )
    # 훅은 「우리가 고른 것인가」의 정의를 이 파일에서 읽는다 — 진짜 것을 둔다.
    # 베껴 쓰면 정의가 둘이 되고, 그 둘이 갈라지는 것이 바로 이 검사가 막으려는 것이다.
    (repository / ".devcontainer" / "autoselected.sh").write_text(
        AUTOSELECTED_SCRIPT.read_text(encoding="utf-8"), encoding="utf-8"
    )
    _install_hook(tmp_path, POSTGRESQL_URL)

    def shell_sees(exported: dict[str, str]) -> str:
        runner = tmp_path / "run.sh"
        runner.write_text(
            "".join(f"export {name}={value}\n" for name, value in exported.items())
            + f". {tmp_path / 'home' / '.bashrc'}\n"
            + 'printf \'%s\\n\' "${DATABASE_URL:-<none>}"\n',
            encoding="utf-8",
        )
        done = subprocess.run(
            ["bash", str(runner)],
            capture_output=True,
            text=True,
            cwd=repository,
            env=_environment_without_a_url({"HOME": str(tmp_path / "home")}),
            timeout=60,
        )
        assert done.returncode == 0, done.stderr
        return done.stdout.strip()

    assert shell_sees({}) == "chosen", "아무것도 없을 때 우리 것을 내주지 않는다"
    assert shell_sees({"DATABASE_URL": "theirs"}) == "theirs", (
        "사람이 고른 주소를 훅이 덮었다"
    )
    # 우리가 지난번에 내준 값이면 새 값으로 바꾸는 것이 맞다.
    assert (
        shell_sees(
            {
                "DATABASE_URL": "stale",
                "PRODUCTION_RISK_DATABASE_AUTOSELECTED": "stale",
            }
        )
        == "chosen"
    ), "우리가 내준 낡은 주소를 그대로 뒀다"


def test_the_version_is_checked_even_before_the_role_exists(tmp_path: Path) -> None:
    """역할이 아직 없어도 **판은 확인한다.**

    판 견주기는 지금 이 역할로 묻는데, 그 자리는 아직 역할을 만들기 **전**이다.
    첫 준비에서는 운영체제 사용자와 같은 이름의 역할이 없어 peer 접속이 거부되고
    답이 빈 값으로 온다. 그러면 「모르면 버리지 않는다」가 통과시키고, 곧이어
    관리자로 역할을 만든 뒤 **판이 다른 서버를 골라 준비까지 마친다** — 판을
    견주려고 둔 검사가 정작 첫 준비에서만 비어 있는 셈이다.

    그래서 같은 물음을 관리자로 한 번 더 한다. 여기서는 역할이 없는 상태를
    흉내 내고(현재 역할로는 실패), 관리자로는 한 판 뒤처진 답이 오게 한다.
    """
    version_file = REPOSITORY_ROOT / ".devcontainer" / "postgresql-version.sh"
    major = re.search(
        r"^PRODUCTION_RISK_POSTGRESQL_MAJOR=(\d+)$",
        version_file.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert major
    older = f"{int(major.group(1)) - 1}0013"

    stub = _stub_directory(
        tmp_path,
        {
            "pg_isready": "exit 0",
            # 현재 역할로는 아무것도 못 한다 — 역할이 아직 없는 상태다.
            "psql": 'echo "FATAL: role does not exist" >&2\nexit 2',
            "createdb": "exit 1",
            # 관리자로 가는 길만 열려 있고, 그쪽은 한 판 뒤처진 서버라고 답한다.
            #
            # **두 길을 다 연다.** `run_as` 는 root 면 `su`, 아니면 비대화형 `sudo`
            # 를 쓴다. 한쪽만 열어 두면 검사가 **돌리는 사람에 따라 다른 것을 본다** —
            # 실측(2026-09-09): `su` 만 열어 두었더니 root 인 손에서는 초록이고
            # `ubuntu-latest`(비root + 비밀번호 없는 sudo)에서는 이 검사만 빨갰다.
            # 7차에 같은 자리에서 배운 것을 한 번 더 밟았다.
            "su": f'case "$*" in *server_version_num*) echo {older};; *) exit 1;; esac',
            "sudo": (
                'case "$*" in\n'
                f"  *server_version_num*) echo {older};;\n"
                # `run_as` 는 먼저 `sudo -n true` 로 쓸 수 있는지 본다.
                "  *true*) exit 0;;\n"
                "  *) exit 1;;\n"
                "esac"
            ),
        },
    )

    result = _run_database_script(stub)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", "한 판 뒤처진 서버의 주소를 내밀었다"
    assert "판입니다" in result.stderr, (
        f"역할이 없다는 이유로 판 견주기를 통째로 건너뛰었다: {result.stderr!r}"
    )


def test_the_reported_engine_comes_from_the_url(tmp_path: Path) -> None:
    """무슨 엔진을 쓴다고 말할지는 **주소가 정한다.**

    예전에는 「주소가 있으면 PostgreSQL」이었다. 그래서 사람이
    `DATABASE_URL=sqlite:////tmp/dev.db` 를 준 경우에도 그렇게 말했다 —
    실측(2026-09-09): `PostgreSQL 을 씁니다: sqlite:////tmp/dev.db`.

    이 줄의 존재 이유가 「지금 어느 엔진 위에서 도는가」를 보이게 하는 것인데
    그 자리에서 거짓말을 하면, 사람은 PostgreSQL 에서만 나는 것을 확인했다고
    믿는다. 그 갈래를 파일에서 그대로 꺼내 돌려 본다.
    """
    region = _shell_region(SETUP_SCRIPT, 'case "${DATABASE_URL:-}" in', "esac")
    script = tmp_path / "announce.sh"
    script.write_text(
        "set -uo pipefail\nredact_url() { printf %s \"$1\"; }\n" + region + "\n",
        encoding="utf-8",
    )

    def announced(url: str) -> str:
        done = subprocess.run(
            ["bash", str(script)],
            capture_output=True,
            text=True,
            env=_environment_without_a_url({"DATABASE_URL": url} if url else {}),
            timeout=60,
        )
        assert done.returncode == 0, done.stderr
        return done.stdout.strip()

    assert "SQLite" in announced("sqlite:////tmp/dev.db"), "SQLite 주소를 PostgreSQL 이라 말한다"
    assert "PostgreSQL" not in announced("sqlite:////tmp/dev.db")
    assert "PostgreSQL" in announced("postgresql+psycopg:///x?host=/socket")
    assert announced("") == "SQLite 파일로 진행합니다."
    # 모르는 방식에 아는 이름을 붙이지 않는다 — 그것이 방금 고친 결함이다.
    unknown = announced("mysql://h/x")
    assert "PostgreSQL" not in unknown and "SQLite" not in unknown, unknown


def test_the_readme_describes_postgresql_in_codespaces() -> None:
    """Codespaces 절이 **지금 실제로 벌어지는 일**을 적는다.

    준비는 PostgreSQL 을 놓고 이 체크아웃 전용 데이터베이스를 만들어 시드하는데,
    README 는 「합성 SQLite 데이터가 준비된다」·「SQLite 파일은 Codespace 마다 다시
    생성된다」고 적고 있었다. 그 글을 따라 초기화하려는 사람은 없는 파일을 지우고,
    앱은 그대로 남아 있는 PostgreSQL 데이터를 계속 쓴다.

    산문이 기계보다 뒤처지는 것을 막을 길은 기계가 산문을 읽는 것뿐이다.
    """
    codespaces = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    # 제목을 **줄 통째로** 잡는다. `## GitHub Codespaces` 로 찾으면 Docker 절의
    # `### GitHub Codespaces` 가 먼저 걸린다 — `###` 안에 `##` 가 들어 있다.
    heading = "\n## GitHub Codespaces에서 실행\n"
    start = codespaces.index(heading)
    section = codespaces[start : codespaces.index("\n## ", start + len(heading))]

    # 틀린 주장을 **이름으로 금지한다.** 「PostgreSQL 이 어딘가 적혀 있다」로는
    # 물지 않는다 — 옛 문장과 새 문장이 나란히 있어도 통과하기 때문이다.
    wrong = (
        "합성 SQLite 데이터",          # 준비가 놓는 것은 PostgreSQL 이다
        "SQLite 파일은 Git에 포함되지 않으며",  # 지울 파일이 있다는 안내
    )
    for claim in wrong:
        assert claim not in section, f"Codespaces 절에 낡은 주장이 남아 있다: {claim}"

    assert "PostgreSQL" in section, "Codespaces 절이 PostgreSQL 을 말하지 않는다"
    # SQLite 를 언급하는 것은 좋다 — 다만 **물러나는 자리**로만이어야 한다.
    for line in section.splitlines():
        if "SQLite" not in line:
            continue
        assert "물러" in line or "아니라" in line, (
            f"SQLite 를 기본 경로처럼 적고 있다: {line.strip()}"
        )


def test_a_password_with_a_slash_is_redacted(tmp_path: Path) -> None:
    """날 `/` 가 든 비밀번호도 **가려진다.**

    옛 글자 묶음은 비밀번호에서 `/` 를 뺐고, 그 근거로 「URI 에서 사용자 정보는
    `/` 앞에서 끝나므로 날 `/` 가 올 수 없다」고 적혀 있었다. **우리가 실제로
    쓰는 파서는 그렇게 읽지 않는다.**

    실측(2026-09-09, SQLAlchemy 2.0.52):

        make_url("postgresql+psycopg://u:sec/ret@h/db")
          → username='u' password='sec/ret' host='h' database='db'

    그래서 그 주소는 동작하는 주소이고, 그때의 가림은 입력을 **그대로** 내보냈다 —
    비밀번호가 세션 시작 로그에 통째로 박힌다.

    근거로 삼았던 반례도 반대였다. `://h:5432/db?options=@x` 를 같은 파서에 넣으면
    username='h' password='5432/db?options=' host='x' 다 — 파서가 이미 비밀번호로
    읽고 있었으므로 가리는 것이 맞다.

    글자를 베끼지 않고 **그 함수를 파일에서 꺼내 돌린다.**
    """
    region = _shell_region(SETUP_SCRIPT, "redact_url() {", "}")
    # 한 줄짜리는 `_shell_region` 의 두 앵커에 맞지 않는다 — 그 줄을 그대로 꺼낸다.
    keys = next(
        line
        for line in SETUP_SCRIPT.read_text(encoding="utf-8").splitlines()
        if line.startswith("SAFE_QUERY_KEYS=")
    )
    script = tmp_path / "redact.sh"
    script.write_text(
        f"{keys}\n{region}\nredact_url \"$1\"\n", encoding="utf-8"
    )

    def redacted(url: str) -> str:
        done = subprocess.run(
            ["bash", str(script), url], capture_output=True, text=True, timeout=60
        )
        assert done.returncode == 0, done.stderr
        return done.stdout

    leaky = "postgresql+psycopg://u:sec/ret@h/db"
    assert "sec/ret" not in redacted(leaky), "날 `/` 가 든 비밀번호가 그대로 나갔다"
    assert "***" in redacted(leaky)

    # 사용자 정보 안의 `?` 도 마찬가지다 — 질의로 자르기 전에 가려야 한다.
    tricky = "postgresql+psycopg://h:5432/db?options=@x"
    assert "5432/db" not in redacted(tricky), redacted(tricky)

    # 그러면서 가릴 것이 없는 주소는 그대로 읽혀야 한다.
    plain = "postgresql+psycopg:///production_risk?host=/var/run/postgresql&port=5432"
    assert redacted(plain).strip() == plain
    # 질의 쪽 자격증명은 이미 가리고 있었다 — 함께 지킨다.
    assert "s3cr3t" not in redacted("postgresql+psycopg://h/db?pass%77ord=s3cr3t")


def test_the_provisioning_lock_is_shared_across_users(tmp_path: Path) -> None:
    """놓기 잠금은 **집이 아니라 호스트**에 있다.

    사람마다 다른 파일을 잠그면 잠근 것이 아니다. 한 호스트를 두 사람이 쓰면 둘 다
    자기 캐시의 자기 파일을 잠그고 나란히 apt 를 돌린다 — 진 쪽의 설치는 「놓기
    실패」로 삼켜져 SQLite 를 고르고 이긴 쪽은 PostgreSQL 을 고른다.

    그리고 **누구나 쓸 수 있는 디렉터리에 두어서도 안 된다.** 실측(2026-09-09,
    이 컨테이너는 `fs.protected_symlinks = 0`): `/run/lock` 은 `drwxrwxrwt` 라
    다른 사용자가 잠금 이름으로 `/etc/shadow` 를 가리키는 링크를 걸 수 있었고,
    root 로 그 이름에 붙으니 그대로 따라갔다. 고치려던 것보다 나쁜 것을 만드는
    자리다 — 디렉터리는 0755, 파일만 0666 이어야 한다.

    집을 바꿔 가며 **실제로 열어** 같은 자리가 나오는지 본다.
    """
    lock_script = REPOSITORY_ROOT / ".devcontainer" / "lock.sh"

    def where(home: Path, scope: str) -> str:
        home.mkdir(parents=True, exist_ok=True)
        runner = tmp_path / f"open-{home.name}-{scope}.sh"
        runner.write_text(
            f". {lock_script}\n"
            f'open_production_risk_lock provision-test 9 {scope} || exit 1\n'
            'readlink -f /proc/self/fd/9\n'
            "close_production_risk_lock 9\n",
            encoding="utf-8",
        )
        environment = _environment_without_a_url({"HOME": str(home)})
        environment.pop("XDG_CACHE_HOME", None)
        done = subprocess.run(
            ["bash", str(runner)], capture_output=True, text=True, timeout=120
        , env=environment)
        assert done.returncode == 0, done.stderr
        return done.stdout.strip()

    host_a = where(tmp_path / "home-a", "host")
    host_b = where(tmp_path / "home-b", "host")
    assert host_a == host_b, f"집마다 다른 잠금 파일을 쓴다: {host_a} vs {host_b}"
    assert str(tmp_path) not in host_a, f"호스트 잠금이 집 안에 있다: {host_a}"

    # 그 자리는 남이 링크를 심을 수 없어야 한다.
    directory = Path(host_a).parent
    assert not (directory.stat().st_mode & 0o002), (
        f"잠금 디렉터리가 누구나 쓸 수 있다 — 링크를 심을 수 있다: {directory}"
    )

    # 반대로 사람마다 따로 잠가야 하는 것은 여전히 따로다.
    user_a = where(tmp_path / "home-a", "user")
    user_b = where(tmp_path / "home-b", "user")
    assert user_a != user_b, "집마다 따로 잠가야 할 것이 함께 잠긴다"

    # **그리고 준비가 실제로 그 범위를 쓴다.** 위까지는 `lock.sh` 가 그런 범위를
    # 줄 수 있다는 것뿐이고, 부르는 쪽이 쓰지 않으면 아무 소용이 없다.
    lines = [
        line
        for line in SETUP_SCRIPT.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]
    provision = next(
        line
        for line in lines
        if "open_production_risk_lock" in line and '"provision"' in line
    )
    assert provision.split()[-1].rstrip("|") == "host" or " host " in provision, (
        f"놓기 잠금이 호스트 범위를 쓰지 않는다: {provision.strip()}"
    )


def test_the_session_hook_cleans_up_even_when_setup_fails(tmp_path: Path) -> None:
    """준비가 실패해도 **환경 정리는 한다.**

    준비가 실패하면 그것은 `database.env` 를 지우고 0 아닌 값으로 끝난다. 그런데
    `set -e` 가 그 자리에서 훅을 끊으면 아래의 `unset` 을 적는 갈래에 닿지 못하고,
    물려받은 주소를 들고 다시 뜬 세션이 **준비가 방금 거부한 그 데이터베이스를
    계속 쓴다** — 준비가 「이 주소는 못 쓴다」고 말한 바로 그 순간에.

    가짜 `setup.sh` 로 실패를 만들어 놓고 두 가지를 함께 본다: 정리가 적혔는가,
    그리고 실패가 그대로 나갔는가.
    """
    project = tmp_path / "project"
    (project / ".devcontainer").mkdir(parents=True)
    (project / ".claude" / "hooks").mkdir(parents=True)
    (project / ".claude" / "hooks" / "session-start.sh").write_text(
        (REPOSITORY_ROOT / ".claude" / "hooks" / "session-start.sh").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (project / ".devcontainer" / "autoselected.sh").write_text(
        AUTOSELECTED_SCRIPT.read_text(encoding="utf-8"), encoding="utf-8"
    )
    # 준비는 실패한다 — 그리고 실패한 준비는 `database.env` 를 남기지 않는다.
    (project / ".devcontainer" / "setup.sh").write_text(
        "#!/usr/bin/env bash\nexit 1\n", encoding="utf-8"
    )

    environment_file = tmp_path / "session.env"
    environment_file.write_text("", encoding="utf-8")
    chosen = "postgresql+psycopg:///x?host=/socket"
    done = subprocess.run(
        ["bash", str(project / ".claude" / "hooks" / "session-start.sh")],
        capture_output=True,
        text=True,
        timeout=120,
        env={
            **_environment_without_a_url({}),
            "CLAUDE_CODE_REMOTE": "true",
            "CLAUDE_PROJECT_DIR": str(project),
            "CLAUDE_ENV_FILE": str(environment_file),
            "DATABASE_URL": chosen,
            "PRODUCTION_RISK_DATABASE_AUTOSELECTED": chosen,
        },
    )

    written = environment_file.read_text(encoding="utf-8")
    assert "unset DATABASE_URL" in written, (
        "준비가 실패했는데 물려받은 주소를 그대로 뒀다"
    )
    assert done.returncode != 0, "준비의 실패가 훅 밖으로 나가지 않는다"


def test_the_version_is_probed_through_a_reachable_maintenance_database(
    tmp_path: Path,
) -> None:
    """판은 **붙을 수 있는 정비 데이터베이스**에게 묻는다.

    관례대로 있는 `postgres` 가 지워진 호스트가 있다. 그때 그 이름으로만 물으면
    답이 빈 값이고 「모르면 버리지 않는다」가 통과시키는데, 정작 아래의 관리자
    갈래는 `template1` 로 붙어 역할과 데이터베이스를 만들어 낸다 — 붙을 수는
    있는데 판만 못 물어보고 지나가는 자리다.

    `postgres` 는 없고 `template1` 만 있는 서버를 만들어 본다.
    """
    version_file = REPOSITORY_ROOT / ".devcontainer" / "postgresql-version.sh"
    major = re.search(
        r"^PRODUCTION_RISK_POSTGRESQL_MAJOR=(\d+)$",
        version_file.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert major
    older = f"{int(major.group(1)) - 1}0013"

    answer = (
        'case "$*" in\n'
        '  *"-d postgres"*) echo "FATAL: database \\"postgres\\" does not exist" >&2; exit 2;;\n'
        f'  *server_version_num*) echo {older};;\n'
        "  *) exit 2;;\n"
        "esac"
    )
    stub = _stub_directory(
        tmp_path,
        {
            "pg_isready": "exit 0",
            "psql": answer,
            "createdb": "exit 1",
            "su": f'case "$*" in *"-d postgres"*) exit 2;; *server_version_num*) echo {older};; *) exit 1;; esac',
            "sudo": (
                'case "$*" in\n'
                '  *"-d postgres"*) exit 2;;\n'
                f"  *server_version_num*) echo {older};;\n"
                "  *true*) exit 0;;\n"
                "  *) exit 1;;\n"
                "esac"
            ),
        },
    )

    result = _run_database_script(stub)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", "한 판 뒤처진 서버의 주소를 내밀었다"
    assert "판입니다" in result.stderr, (
        f"`postgres` 가 없다는 이유로 판 견주기를 건너뛰었다: {result.stderr!r}"
    )


def test_the_host_lock_refuses_an_untrusted_directory(tmp_path: Path) -> None:
    """호스트 잠금 자리는 **믿을 수 있어야** 연다.

    17차에 잠금을 호스트 공용으로 옮기며 「디렉터리 0755, 파일 0666」으로 두었는데,
    **그 디렉터리를 누가 만드느냐**를 묻지 않았다. 공격자가 먼저 자기 것으로
    만들어 두면 그 안은 그 사람이 정한다.

    실측(2026-09-09, 이 환경은 `fs.protected_symlinks = 0`): 다른 사용자가
    `/run/lock/production-risk` 를 자기 0755 디렉터리로 만들고 **매달린 링크**
    `provision.lock -> /tmp/attack-target` 을 심으니, `[ -e ]` 는 거짓이라 통과했고
    이어지는 `: >` 가 `umask 0000` 아래에서 그것을 따라가
    **`-rw-rw-rw- root root /tmp/attack-target`** 을 만들었다. 잠금을 고치려다
    root 가 남이 고른 경로에 세계쓰기 파일을 만드는 길을 낸 셈이다.

    그래서 소유자·모드·링크 셋을 함께 본다. 여기서는 **그 판정을 직접 돌린다** —
    실제 `/run/lock` 을 건드리지 않고도 규칙을 물을 수 있다.
    """
    lock_script = REPOSITORY_ROOT / ".devcontainer" / "lock.sh"

    def trusted(directory: Path) -> bool:
        runner = tmp_path / "ask.sh"
        runner.write_text(
            f". {lock_script}\n"
            f'production_risk_directory_is_trusted {shlex.quote(str(directory))}\n',
            encoding="utf-8",
        )
        return (
            subprocess.run(
                ["bash", str(runner)], capture_output=True, text=True, timeout=60
            ).returncode
            == 0
        )

    # 우리가 만든 0755 는 믿는다.
    ours = tmp_path / "ours"
    ours.mkdir(mode=0o755)
    assert trusted(ours), "우리 소유의 0755 를 믿지 않는다"

    # 누구나 쓸 수 있으면 안 된다 — 그러면 지금도 링크를 심을 수 있다.
    loose = tmp_path / "loose"
    loose.mkdir(mode=0o777)
    loose.chmod(0o777)
    assert not trusted(loose), "세계쓰기 디렉터리를 믿는다 — 링크를 심을 수 있다"

    # 링크는 따라가지 않는다.
    linked = tmp_path / "linked"
    linked.symlink_to(ours)
    assert not trusted(linked), "링크된 디렉터리를 믿는다"

    # 그리고 잠금 파일을 여는 자리도 링크를 거부해야 한다.
    dangling = ours / "victim.lock"
    dangling.symlink_to(tmp_path / "never-created")
    runner = tmp_path / "open.sh"
    runner.write_text(
        f". {lock_script}\n"
        'candidate="$1"\n'
        'if [ ! -e "$candidate" ] && [ ! -L "$candidate" ]; then\n'
        '  (set -C; umask 0000; : > "$candidate") 2> /dev/null || true\n'
        "fi\n"
        '[ -L "$candidate" ] && exit 1\n'
        '[ -f "$candidate" ] || exit 1\n',
        encoding="utf-8",
    )
    done = subprocess.run(
        ["bash", str(runner), str(dangling)], capture_output=True, text=True, timeout=60
    )
    assert done.returncode != 0, "매달린 링크를 잠금 파일로 받아들였다"
    assert not (tmp_path / "never-created").exists(), (
        "매달린 링크를 따라가 공격자가 고른 경로에 파일을 만들었다"
    )


def test_a_username_with_an_at_sign_is_redacted(tmp_path: Path) -> None:
    """`@` 가 든 사용자 이름 뒤의 비밀번호도 **가려진다.**

    파서는 **마지막 `@`** 로 사용자 정보와 호스트를 가른다. 실측(2026-09-09,
    SQLAlchemy 2.0.52):

        make_url("postgresql+psycopg://a@b:secret@host/db")
          → username='a@b' password='secret' host='host'

    그런데 옛 사용자 이름 묶음 `[^:/@]*` 는 첫 `@` 에서 막혀 이 주소를 통째로
    통과시켰다 — 비밀번호가 세션 시작 로그에 그대로 박힌다.
    """
    region = _shell_region(SETUP_SCRIPT, "redact_url() {", "}")
    keys = next(
        line
        for line in SETUP_SCRIPT.read_text(encoding="utf-8").splitlines()
        if line.startswith("SAFE_QUERY_KEYS=")
    )
    script = tmp_path / "redact.sh"
    script.write_text(f"{keys}\n{region}\nredact_url \"$1\"\n", encoding="utf-8")

    def redacted(url: str) -> str:
        done = subprocess.run(
            ["bash", str(script), url], capture_output=True, text=True, timeout=60
        )
        assert done.returncode == 0, done.stderr
        return done.stdout

    assert "secret" not in redacted("postgresql+psycopg://a@b:secret@host/db")
    # 사용자 이름 자체는 남겨 둔다 — 비밀이 아니고, 사람이 보아야 하는 값이다.
    assert "a@b" in redacted("postgresql+psycopg://a@b:secret@host/db")
    # 그러면서 앞서 고친 것들이 그대로여야 한다.
    assert "sec/ret" not in redacted("postgresql+psycopg://u:sec/ret@h/db")
    assert "5432/db" not in redacted("postgresql+psycopg://h:5432/db?options=@x")
    plain = "postgresql+psycopg:///production_risk?host=/var/run/postgresql&port=5432"
    assert redacted(plain).strip() == plain


def test_the_session_hook_does_not_publish_a_stale_url(tmp_path: Path) -> None:
    """준비가 **일찍** 실패해도 낡은 주소를 싣지 않는다.

    준비는 데이터베이스를 다시 보기 훨씬 전에 죽을 수 있다 — venv · pip · npm ·
    잠금. 그때는 옛 `database.env` 가 그대로 남아 있고, 상태를 보지 않으면 그
    파일을 세션에 그대로 실어 보낸다. 컨테이너를 다시 띄워 PostgreSQL 이 내려간
    채로 pip 이 실패하면, 엔진을 고르지도 않았는데 죽은 주소를 물려받는다.

    파일이 **남아 있는데도** 싣지 않는지를 본다 — 앞선 검사(파일이 지워진 경우)와
    다른 자리다.
    """
    project = tmp_path / "project"
    (project / ".devcontainer").mkdir(parents=True)
    (project / ".claude" / "hooks").mkdir(parents=True)
    (project / ".claude" / "hooks" / "session-start.sh").write_text(
        (REPOSITORY_ROOT / ".claude" / "hooks" / "session-start.sh").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (project / ".devcontainer" / "autoselected.sh").write_text(
        AUTOSELECTED_SCRIPT.read_text(encoding="utf-8"), encoding="utf-8"
    )
    # 의존성 설치에서 죽는다 — 데이터베이스는 보지도 못했다.
    (project / ".devcontainer" / "setup.sh").write_text(
        "#!/usr/bin/env bash\nexit 1\n", encoding="utf-8"
    )
    # 그래서 지난번 주소가 그대로 남아 있다.
    (project / ".devcontainer" / "database.env").write_text(
        "export DATABASE_URL=stale\n", encoding="utf-8"
    )

    environment_file = tmp_path / "session.env"
    environment_file.write_text("", encoding="utf-8")
    done = subprocess.run(
        ["bash", str(project / ".claude" / "hooks" / "session-start.sh")],
        capture_output=True,
        text=True,
        timeout=120,
        env={
            **_environment_without_a_url({}),
            "CLAUDE_CODE_REMOTE": "true",
            "CLAUDE_PROJECT_DIR": str(project),
            "CLAUDE_ENV_FILE": str(environment_file),
        },
    )

    written = environment_file.read_text(encoding="utf-8")
    assert "stale" not in written, "준비가 실패했는데 낡은 주소를 세션에 실었다"
    assert done.returncode != 0, "준비의 실패가 훅 밖으로 나가지 않는다"


def test_a_foreign_owned_sequence_is_not_advertised(tmp_path: Path) -> None:
    """표가 기대는 **시퀀스**도 함께 묻는다.

    생성 ID 한 줄을 넣는 데 필요한 것은 표 권한만이 아니다. 실측(2026-09-09):
    이 앱이 만드는 시퀀스는 표에 묶여 있어(`OWNED BY`) PostgreSQL 이 소유자 분리를
    거부하지만(`Sequence "items_id_seq" is linked to table "items"`), **묶이지 않은
    시퀀스**는 다르다 — 남이 소유한 `loose_seq` 를 `DEFAULT nextval` 로 부르게 두니
    판정은 0 이었고 다음 `INSERT` 는 `permission denied for sequence loose_seq` 였다.

    질의가 시퀀스를 **이름이 아니라 의존으로** 찾는지 본다.
    """
    usable_script = REPOSITORY_ROOT / ".devcontainer" / "database-usable.sh"
    stub = _stub_directory(
        tmp_path,
        {
            "psql": (
                'case "$*" in\n'
                # 시퀀스를 의존으로 찾는 형태면 남의 시퀀스가 걸린다.
                "  *pg_attrdef*) echo f;;\n"
                "  *) echo t;;\n"
                "esac"
            )
        },
    )
    result = subprocess.run(
        ["bash", str(usable_script), "/socket", "5432", "production_risk"],
        capture_output=True,
        text=True,
        env=_environment_without_a_url(
            {"PATH": f"{stub}{os.pathsep}{os.environ['PATH']}"}
        ),
        timeout=60,
    )
    assert result.returncode != 0, (
        "표가 기대는 시퀀스를 묻지 않는다 — 시드가 첫 insert 에서 죽는다"
    )
