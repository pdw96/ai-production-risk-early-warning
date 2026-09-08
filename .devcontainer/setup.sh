#!/usr/bin/env bash
set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPOSITORY_ROOT"

python -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
backend/.venv/bin/python -m pip install -r backend/requirements.txt

# 잠금 파일 그대로 받는 `npm ci` 는 node_modules 를 지우고 처음부터 받는다.
# 다시 부를 수 있어야 하는 자리(세션 재개)에서 그것을 매번 하면 몇 분이 그냥
# 사라지므로, 받아 둔 것이 없을 때만 부른다.
if [ ! -d frontend/node_modules ]; then
  npm --prefix frontend ci
fi

# 개발 세션도 운영과 같은 엔진을 본다. 세우지 못하는 환경이면 빈 값이 오고,
# 그때는 예전처럼 SQLite 파일 하나로 돈다.
if [ -z "${DATABASE_URL:-}" ]; then
  DATABASE_URL="$(bash .devcontainer/database.sh)"
  export DATABASE_URL
fi

cd backend
if [ -n "${DATABASE_URL:-}" ]; then
  # 운영과 컨테이너가 오는 길 그대로다 — 마이그레이션으로 표를 맞추고, 품목 표가
  # 비어 있을 때만 채운다. 표를 지우는 길(`app.seed` 인자 없음)로 오지 않는 이유는
  # 그쪽이 세션을 다시 열 때마다 사람이 넣어 둔 것을 지우기 때문이다.
  .venv/bin/python -m app.db.preflight
  .venv/bin/python -m alembic upgrade head
  .venv/bin/python -m app.seed --if-empty
  echo "PostgreSQL 을 씁니다: ${DATABASE_URL}"
else
  # SQLite 파일은 세션마다 새로 만드는 것이 안전하다 — 남아 있던 파일이 옛
  # 스키마일 수 있고, 그 파일에는 지울 수 없는 데이터가 없다.
  .venv/bin/python -m app.seed
  echo "SQLite 파일로 진행합니다."
fi

echo "준비 완료: bash .devcontainer/start.sh 를 실행하세요."
