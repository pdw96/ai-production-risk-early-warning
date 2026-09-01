#!/usr/bin/env bash
set -euo pipefail

# 각 백그라운드 서버를 독립 프로세스 그룹으로 띄워야 자식 프로세스까지 한 번에 정리할 수 있다.
set -m

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
