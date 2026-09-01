#!/bin/sh
set -eu

database_path="${DATABASE_PATH:-/app/production_risk.db}"
mkdir -p "$(dirname "$database_path")"

# app.seed의 reset_database()는 drop_all → create_all이므로 기동할 때마다 실행하면
# 리스크 상태를 포함한 기존 데이터가 사라진다. DB 파일이 없을 때만 시드한다.
if [ ! -f "$database_path" ]; then
  echo "합성 샘플 SQLite 데이터를 생성합니다: $database_path"
  python -m app.seed
else
  echo "기존 SQLite 데이터를 사용합니다: $database_path"
fi

exec python -m uvicorn app.main:app \
  --host "${UVICORN_HOST:-0.0.0.0}" \
  --port "${UVICORN_PORT:-8000}"
