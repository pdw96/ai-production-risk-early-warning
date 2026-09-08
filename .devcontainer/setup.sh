#!/usr/bin/env bash
set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPOSITORY_ROOT"

# 정해진 엔진을 이후 명령들이 이어받는 자리. 이 파일 하나가 유일한 대응표다.
DATABASE_ENVIRONMENT_FILE="$REPOSITORY_ROOT/.devcontainer/database.env"

python -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
backend/.venv/bin/python -m pip install -r backend/requirements.txt

# 잠금 파일 그대로 받는 `npm ci` 는 node_modules 를 지우고 처음부터 받는다.
# 다시 부를 수 있어야 하는 자리(세션 재개)에서 그것을 매번 하면 몇 분이 그냥
# 사라진다. 그렇다고 **디렉터리가 있는지**로 거르면 안 된다 — 세션을 재개하며
# 잠금 파일이 바뀐 리비전을 받아 와도 그 조건은 「있다」이므로 설치를 건너뛰고,
# 프론트 검사가 옛 의존성 위에서 돈다. 물어야 할 것은 **지금 깔린 것이 지금
# 잠금 파일에서 나왔는가**이므로, 잠금 파일의 해시를 남겨 두고 그것을 견준다.
FRONTEND_LOCK_HASH_FILE="frontend/node_modules/.package-lock-sha256"
frontend_lock_hash="$(sha256sum frontend/package-lock.json | cut -d' ' -f1)"
if [ "$(cat "$FRONTEND_LOCK_HASH_FILE" 2>/dev/null || true)" != "$frontend_lock_hash" ]; then
  npm --prefix frontend ci
  # `npm ci` 가 node_modules 를 지우고 다시 만드므로 **끝난 뒤에** 적는다.
  printf '%s' "$frontend_lock_hash" > "$FRONTEND_LOCK_HASH_FILE"
fi

# 개발 세션도 운영과 같은 엔진을 본다. 세우지 못하는 환경이면 빈 값이 오고,
# 그때는 예전처럼 SQLite 파일 하나로 돈다.
if [ -z "${DATABASE_URL:-}" ]; then
  DATABASE_URL="$(bash .devcontainer/database.sh)"
  export DATABASE_URL
fi

# 여기서 export 한 값은 **이 프로세스와 함께 사라진다.** 이 스크립트는
# `postCreateCommand` 나 세션 시작 훅으로 한 번 돌고 끝나므로, 그 뒤 사람이 치는
# `cd backend && .venv/bin/python -m pytest` 에는 `DATABASE_URL` 이 없다 —
# 마이그레이션과 시드는 PostgreSQL 에 해 놓고 정작 검사는 SQLite 로 도는,
# 이 PR 이 없애려던 바로 그 어긋남이 개발자의 손 안에서 다시 생긴다.
#
# 그래서 파일로 남긴다. 값은 `printf %q` 로 적는다 — 주소에 작은따옴표가 들어갈
# 수 있고(URI 사용자 정보에 허용된다), 따옴표 사이에 그대로 끼워 넣으면 그 줄이
# 다른 뜻이 되거나 아예 읽히지 않는다.
if [ -n "${DATABASE_URL:-}" ]; then
  printf 'export DATABASE_URL=%q\n' "$DATABASE_URL" > "$DATABASE_ENVIRONMENT_FILE"
else
  # 빈 파일이 아니라 **없는 파일**이어야 한다. 남아 있으면 지난 세션의 주소가
  # 이번 세션의 엔진 판단을 이긴다.
  rm -f "$DATABASE_ENVIRONMENT_FILE"
fi

# 대화형 셸이 그 파일을 읽게 한다. 한 번만 적는다.
SHELL_HOOK_MARKER="# ai-production-risk: 개발 세션의 데이터베이스 주소"
for profile in "$HOME/.bashrc" "$HOME/.zshrc"; do
  [ -f "$profile" ] || continue
  grep -qF "$SHELL_HOOK_MARKER" "$profile" && continue
  {
    printf '\n%s\n' "$SHELL_HOOK_MARKER"
    printf '[ -f %q ] && . %q\n' "$DATABASE_ENVIRONMENT_FILE" "$DATABASE_ENVIRONMENT_FILE"
  } >> "$profile"
done

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
