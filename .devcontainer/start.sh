#!/usr/bin/env bash
set -euo pipefail

cleanup() {
  kill "${backend_pid:-}" "${frontend_pid:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

(
  cd backend
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
) &
backend_pid=$!

(
  cd frontend
  npm run dev -- --hostname 0.0.0.0 --port 3000
) &
frontend_pid=$!

echo "FastAPI(8000)와 Next.js(3000)를 실행했습니다. 종료하려면 Ctrl+C를 누르세요."
wait -n "$backend_pid" "$frontend_pid"
