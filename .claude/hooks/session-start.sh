#!/usr/bin/env bash
# 웹 세션이 저장소의 검사를 곧바로 돌릴 수 있게 만든다.
#
# **새로 쓰는 것이 아니라 부르는 것이다.** 의존성 설치와 데이터베이스 준비는
# 이미 `.devcontainer/setup.sh` 가 한다 — 웹 세션이 devcontainer 를 타지 않아
# 그것을 안 쓰고 있었을 뿐이다. 두 벌로 적으면 한쪽을 고칠 때 다른 쪽이 조용히
# 뒤처지고, 그때 「내 손에서는 되는데」가 시작된다.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

PROJECT_DIRECTORY="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$PROJECT_DIRECTORY"

# **실패를 값으로 받는다 — 정리는 그래도 해야 한다.**
#
# 준비가 실패하면 그것은 `database.env` 를 지우고 0 아닌 값으로 끝난다. 그런데
# 여기서 `set -e` 가 그 자리에서 훅을 끊으면, 아래의 `unset` 을 적는 갈래에
# 닿지 못한다 — 물려받은 주소를 들고 다시 뜬 세션이 **준비가 방금 거부한 그
# 데이터베이스를 계속 쓴다.** 준비가 「이 주소는 못 쓴다」고 말한 바로 그 순간에.
#
# 그래서 상태를 들고 있다가, 정리를 마친 뒤에 그대로 내보낸다.
setup_status=0
bash .devcontainer/setup.sh || setup_status=$?

# 준비가 정한 엔진을 세션의 모든 명령이 이어받게 한다. 여기서 다시 판단하지
# 않는다 — 두 곳이 각자 판단하면 준비는 PostgreSQL 로 해 놓고 pytest 는 SQLite 로
# 도는 상태가 만들어진다. 그 줄은 `setup.sh` 가 `printf %q` 로 이미 셸에 안전하게
# 적어 두었으므로 그대로 옮긴다.
DATABASE_ENVIRONMENT_FILE=".devcontainer/database.env"
# 물려받은 주소가 우리 것인지 묻는 판단은 `setup.sh` · `start.sh` 와 **같은
# 정의**를 쓴다.
# shellcheck source=.devcontainer/autoselected.sh
. "$PROJECT_DIRECTORY/.devcontainer/autoselected.sh"
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  # **성공했을 때만 알린다.** 준비는 의존성 설치(venv · pip · npm)나 잠금에서
  # 먼저 죽을 수 있고, 그때는 데이터베이스를 다시 보지도 못했으므로 옛
  # `database.env` 가 그대로 남아 있다. 상태를 보지 않으면 그 낡은 주소를 세션에
  # 그대로 실어 보내게 된다 — 이를테면 컨테이너를 다시 띄워 PostgreSQL 이 내려간
  # 채로 pip 이 실패한 경우, 엔진을 고르지도 않았는데 죽은 주소를 물려받는다.
  if [ "$setup_status" = "0" ] && [ -f "$DATABASE_ENVIRONMENT_FILE" ]; then
    cat "$DATABASE_ENVIRONMENT_FILE" >> "$CLAUDE_ENV_FILE"
  elif production_risk_url_is_inherited_ours; then
    # 지난 세션이 고른 PostgreSQL 주소를 물려받았는데 이번에는 그 서버를 세우지
    # 못해 `setup.sh` 가 SQLite 로 물러난 경우다. `setup.sh` 의 `unset` 은 그
    # 자식 프로세스에서 끝나고 파일도 지워졌으므로, 아무것도 적지 않으면 세션의
    # 이후 명령들이 **죽은 PostgreSQL 주소를 계속 들고 있다** — 준비는 SQLite 로
    # 했는데 검사는 거기에 붙는다. 그 어긋남이 이 PR 이 없애려던 것이다.
    #
    # 사람이 준 주소는 표식의 값과 다르므로 여기 걸리지 않는다.
    printf 'unset DATABASE_URL PRODUCTION_RISK_DATABASE_AUTOSELECTED\n' \
      >> "$CLAUDE_ENV_FILE"
  fi
fi

# 준비의 판정은 여기서 나간다.
exit "$setup_status"
