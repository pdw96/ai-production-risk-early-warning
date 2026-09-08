#!/usr/bin/env bash
set -euo pipefail

# 각 백그라운드 서버를 독립 프로세스 그룹으로 띄워야 자식 프로세스까지 한 번에 정리할 수 있다.
set -m

# 준비가 PostgreSQL 로 끝났는데 서버만 SQLite 로 뜨면 화면이 빈 데이터베이스를
# 그린다. 그렇다고 **지난번에 고른 주소를 그대로 믿어서도 안 된다** — 호스트가
# 다시 뜨면 그 소켓 뒤의 서버는 내려가 있고, 서버를 세우는 것은 `database.sh`
# 하나뿐이라 그 자리를 건너뛰면 백엔드가 죽은 서버를 향해 뜬다.
#
# 그래서 **우리가 고른 주소면 다시 고른다.** 그 판단은 `setup.sh` · 세션 시작
# 훅과 같은 정의를 쓴다 — 셋이 각자 적었더니 셋 다 같은 모양으로 틀렸다.
# shellcheck source=.devcontainer/autoselected.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/autoselected.sh"
if production_risk_url_is_inherited_ours; then
  unset DATABASE_URL
fi
unset PRODUCTION_RISK_DATABASE_AUTOSELECTED
if [ -z "${DATABASE_URL:-}" ]; then
  DATABASE_URL="$(bash "$(dirname "${BASH_SOURCE[0]}")/database.sh")"
  export DATABASE_URL
fi

# **고른 엔진을 준비한다.** 위에서 다시 골랐다면 그것은 준비가 손댄 그 엔진이
# 아닐 수 있다 — 데이터베이스가 사라져 새로 만들어졌을 수도, SQLite 로 물러났을
# 수도 있다. 그대로 서버를 띄우면 기동은 성공했다고 적히고 요청마다 「표가 없다」로
# 죽는다. 차례는 `prepare-database.sh` 한 곳에만 있고 두 번 돌아도 안전하다.
bash "$(dirname "${BASH_SOURCE[0]}")/prepare-database.sh"

server_pids=()

cleanup() {
  trap - EXIT INT TERM
  for pid in "${server_pids[@]:-}"; do
    [[ -n "$pid" ]] || continue
    # 프로세스 그룹 전체를 종료해 npm이 띄운 Next.js 서버까지 함께 내린다.
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  done
  for pid in "${server_pids[@]:-}"; do
    [[ -n "$pid" ]] || continue
    wait "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

(
  cd backend
  exec .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
) < /dev/null &
backend_pid=$!
server_pids+=("$backend_pid")

(
  cd frontend
  exec npm run dev -- --hostname 0.0.0.0 --port 3000
) < /dev/null &
frontend_pid=$!
server_pids+=("$frontend_pid")

echo "FastAPI(8000)와 Next.js(3000)를 실행했습니다. 종료하려면 Ctrl+C를 누르세요."
wait -n "$backend_pid" "$frontend_pid"
