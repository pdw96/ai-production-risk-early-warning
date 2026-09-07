#!/bin/sh
set -eu

# 시드 판단 근거가 「DB 파일이 없으면」에서 세 조건으로 바뀌었다.
#
# PostgreSQL 에는 그 파일이 없다. 그리고 파일이 사라지면 「지우고 다시」라는
# 탈출구도 함께 사라지므로, 반쯤 채워진 상태를 만들지 않는 것이 유일한 방어다.
# 세 조건을 모두 통과할 때만 시드한다.

# ── 0. SQLite 로 떨어질 때는 파일이 앉을 자리를 먼저 만든다 ──────────────
# 상위 디렉터리가 없으면 첫 접속이 `unable to open database file` 로 죽고,
# 기동은 마이그레이션까지 가지도 못한다.
#
# 길이 둘이다. `DATABASE_URL` 이 없으면 `DATABASE_PATH`(또는 기본값)로 떨어지고
# (app.core.config), 있으면서 `sqlite:` 로 시작하면 **그 주소 안에 경로가 있다.**
# 앞의 것만 보면 `sqlite:////data/new/db.sqlite` 같은 주소가 그냥 죽는다.
if [ -z "${DATABASE_URL:-}" ]; then
  database_path="${DATABASE_PATH:-/app/production_risk.db}"
  mkdir -p "$(dirname "$database_path")"
else
  case "${DATABASE_URL}" in
    sqlite:*)
      # 슬래시 셋과 넷이 **다른 뜻**이다. `sqlite:///data/x.db` 는 작업
      # 디렉터리 기준 상대경로(`data/x.db`)이고, `sqlite:////data/x.db` 는
      # 절대경로(`/data/x.db`)다. `://` 까지만 걷어내면 앞의 것이 `/data/x.db`
      # 로 보여 컨테이너 루트에 `/data` 를 만들고, 정작 열리는 `/app/data` 는
      # 없는 채로 남는다.
      #
      # 그래서 `://` 뒤에 남는 슬래시를 **정확히 하나** 더 걷어낸다. 그러면
      # 셋은 상대경로가, 넷은 절대경로가 그대로 남는다. 방언 접미
      # (`sqlite+pysqlite:`)와 `?mode=ro` 같은 질의 문자열도 함께 걷어낸다.
      database_path="${DATABASE_URL#*://}"
      database_path="${database_path%%\?*}"
      database_path="${database_path#/}"
      # 메모리 데이터베이스에는 앉을 자리가 없다.
      if [ -n "$database_path" ]; then
        mkdir -p "$(dirname "$database_path")"
      fi
      ;;
  esac
fi

# ── 0.5 옛 데이터베이스인지 먼저 본다 ───────────────────────────────────
# 표는 있는데 Alembic 버전 표가 없으면 이전 판이 `create_all` 로 만든 것이다.
# 그대로 마이그레이션을 돌리면 이미 있는 표에서 죽는데, 그 메시지로는 무엇을
# 해야 하는지 알 수 없다. 먼저 알아보고 고를 수 있는 길을 알려 준다.
python -m app.db.preflight

# ── 1. 표를 먼저 맞춘다 ──────────────────────────────────────────────────
# 판단이 아니라 **전제**다. 항상 돌린다 — 표가 없으면 「비어 있는지」를 물어볼
# 수조차 없다.
echo "마이그레이션을 적용합니다."
python -m alembic upgrade head

# ── 2. 스위치가 켜져 있어야 한다 ─────────────────────────────────────────
# 개발과 시연에서만 켠다. 운영에서 자동 시드는 편의가 아니라 사고다.
if [ "${SEED_SAMPLE_DATA:-0}" = "1" ]; then
  # ── 3. 품목 표가 비어 있어야 한다 ──────────────────────────────────────
  # 「표가 있는가」는 아무것도 말해 주지 않는다. 마이그레이션이 항상 만들어 두기
  # 때문이다. 물어야 할 것은 내용의 유무이며, 그 판단과 잠금은 app.seed 가 한다.
  python -m app.seed --if-empty
else
  echo "SEED_SAMPLE_DATA 가 꺼져 있어 합성 데이터를 넣지 않습니다."
fi

exec python -m uvicorn app.main:app \
  --host "${UVICORN_HOST:-0.0.0.0}" \
  --port "${UVICORN_PORT:-8000}"
