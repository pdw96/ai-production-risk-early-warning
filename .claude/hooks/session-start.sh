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

# 데이터베이스를 먼저 세워 주소를 얻는다. 세우지 못하는 환경이면 빈 값이다.
DATABASE_URL="$(bash .devcontainer/database.sh || true)"

if [ -n "$DATABASE_URL" ]; then
  export DATABASE_URL
  # 세션의 모든 명령이 같은 엔진을 보게 한다. 이것을 남기지 않으면 준비만
  # PostgreSQL 로 해 두고 정작 pytest 는 SQLite 로 돌아, 세션과 CI 가 다시 갈린다.
  if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
    echo "export DATABASE_URL='${DATABASE_URL}'" >> "$CLAUDE_ENV_FILE"
  fi
fi

bash .devcontainer/setup.sh
