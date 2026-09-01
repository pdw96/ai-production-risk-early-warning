#!/usr/bin/env bash
set -euo pipefail

python -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
backend/.venv/bin/python -m pip install -r backend/requirements.txt
npm --prefix frontend ci

(
  cd backend
  .venv/bin/python -m app.seed
)

echo "Codespace 준비 완료: bash .devcontainer/start.sh 를 실행하세요."
