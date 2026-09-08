#!/usr/bin/env bash
set -euo pipefail

# 각 백그라운드 서버를 독립 프로세스 그룹으로 띄워야 자식 프로세스까지 한 번에 정리할 수 있다.
set -m

# 준비가 PostgreSQL 로 끝났는데 서버만 SQLite 로 뜨면 화면이 빈 데이터베이스를
# 그린다. 준비가 남긴 주소를 먼저 읽고, 없을 때만 직접 세운다.
if [ -z "${DATABASE_URL:-}" ]; then
  __database_environment_file="$(dirname "${BASH_SOURCE[0]}")/database.env"
  if [ -f "$__database_environment_file" ]; then
    . "$__database_environment_file"
  else
    DATABASE_URL="$(bash "$(dirname "${BASH_SOURCE[0]}")/database.sh")"
    export DATABASE_URL
  fi
fi

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
