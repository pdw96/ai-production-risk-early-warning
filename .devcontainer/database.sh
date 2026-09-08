#!/usr/bin/env bash
# 개발 세션에 PostgreSQL 을 세우고 접속 주소를 **표준출력으로 한 줄** 돌려준다.
# 세우지 못하면 아무것도 내지 않는다 — 부르는 쪽은 그때 SQLite 로 떨어진다.
#
# 왜 필요한가. 운영과 컨테이너는 PostgreSQL 로 돌고 CI 도 이제 그렇다. 그런데
# 개발 세션만 SQLite 로 남으면, 두 엔진에서 뜻이 갈리는 것들(`LIKE` 대소문자 ·
# 불리언 칸의 정수 · `trim`/`btrim`)을 **사람이 손으로 고치는 동안에는 아무도
# 보지 못한다.** 손에서 초록이던 것이 CI 에서 빨개지는 것은 그 다음이다.
#
# 비밀번호를 만들지 않는다. 유닉스 소켓 + peer 인증이라 운영체제 사용자가 곧
# 데이터베이스 역할이고, 그러면 저장소에도 환경에도 적어 둘 비밀번호가 없다.
# compose 가 비밀번호를 저장소에 두지 않는 것과 같은 이유다.
#
# **이 파일은 실패해도 죽지 않는다.** 부르는 쪽이 `set -e` 아래에서 명령 치환으로
# 받으므로, 여기서 나가는 0 아닌 종료는 setup 전체를 끌고 내려간다. 권한이 없어
# PostgreSQL 을 못 세우는 것은 「고장」이 아니라 **SQLite 로 가는 길**이다.
set -euo pipefail

# 안내 문구는 표준오류로 보낸다. 표준출력은 주소 한 줄만 나가는 자리다.
log() { echo "$@" >&2; }

DATABASE_NAME="production_risk"
SOCKET_DIRECTORY="/var/run/postgresql"

# 못 세우고 물러나는 단 하나의 출구. 표준출력에 아무것도 남기지 않는다.
fall_back_to_sqlite() {
  log "$1"
  log "  SQLite 로 진행합니다 — 두 엔진에서 갈리는 결함은 CI 의 PostgreSQL 검사가 잡습니다."
  exit 0
}

# 권한을 올리는 **단 한 곳**. root 면 그대로 쓰고, 아니면 비대화형 sudo 를 쓴다.
#
# `su` 는 비root 에게 비밀번호를 묻는다 — 스크립트에는 그것을 줄 사람이 없어
# `Authentication failure` 로 끝난다. 그 실패를 그대로 두면 역할 조회가 「역할이
# 없다」로 읽히고, 이어지는 생성이 `set -e` 아래에서 setup 을 통째로 죽인다.
run_as() {
  local target="$1"
  shift
  if [ "$(id -u)" = "0" ]; then
    if [ "$target" = "root" ]; then
      sh -c "$*"
    else
      su "$target" -c "$*"
    fi
  elif command -v sudo > /dev/null 2>&1 && sudo -n true 2> /dev/null; then
    if [ "$target" = "root" ]; then
      sudo -n sh -c "$*"
    else
      sudo -n -u "$target" sh -c "$*"
    fi
  else
    return 1
  fi
}

# 이미 정해 준 주소가 있으면 그것이 이긴다. 세션을 다른 데이터베이스에 붙이는
# 유일한 길이다.
if [ -n "${DATABASE_URL:-}" ]; then
  log "DATABASE_URL 이 이미 정해져 있어 그대로 씁니다."
  echo "$DATABASE_URL"
  exit 0
fi

if ! command -v pg_isready > /dev/null 2>&1; then
  fall_back_to_sqlite "이 환경에는 PostgreSQL 이 없습니다."
fi

if ! pg_isready --quiet 2>/dev/null; then
  if ! command -v pg_ctlcluster > /dev/null 2>&1; then
    fall_back_to_sqlite "PostgreSQL 클러스터를 기동할 도구가 없습니다."
  fi
  version="$(pg_lsclusters --no-header 2>/dev/null | awk 'NR==1 {print $1}')"
  cluster="$(pg_lsclusters --no-header 2>/dev/null | awk 'NR==1 {print $2}')"
  if [ -z "$version" ] || [ -z "$cluster" ]; then
    fall_back_to_sqlite "기동할 PostgreSQL 클러스터가 없습니다."
  fi

  log "PostgreSQL ${version}/${cluster} 를 기동합니다."
  # 기동은 root 권한이 필요하다. 못 올리면 그것이 곧 SQLite 로 가는 이유다.
  if ! run_as root "pg_ctlcluster ${version} ${cluster} start" > /dev/null 2>&1; then
    log "클러스터 기동에 필요한 권한을 얻지 못했습니다."
  fi

  # 기동에는 시간이 걸린다. 곧바로 붙으면 첫 접속이 서버보다 앞서 죽는다.
  # 기다리는 것은 **기동을 시도했을 때뿐**이다 — 시도하지도 않고 30초를 세면
  # PostgreSQL 이 없는 환경에서 세션이 그만큼 늦게 뜬다.
  for _ in $(seq 1 30); do
    pg_isready --quiet 2>/dev/null && break
    sleep 1
  done

  if ! pg_isready --quiet 2>/dev/null; then
    fall_back_to_sqlite "PostgreSQL 을 기동하지 못했습니다."
  fi
fi

# peer 인증은 **운영체제 사용자와 같은 이름의 역할**을 요구한다. 그 역할이
# 없으면 소켓 접속이 그 자리에서 거부된다.
role="$(id -un)"
if ! psql -d postgres -qtAc "SELECT 1 FROM pg_roles WHERE rolname = '${role}'" \
  2>/dev/null | grep -q 1; then
  log "역할 ${role} 을 만듭니다."
  if ! run_as postgres "psql -qc \"CREATE ROLE \\\"${role}\\\" LOGIN SUPERUSER\"" \
    > /dev/null 2>&1; then
    fall_back_to_sqlite "역할 ${role} 을 만들 권한을 얻지 못했습니다."
  fi
fi

# 유지보수용 데이터베이스를 **명시한다.** 생략하면 psql 이 사용자 이름과 같은
# 데이터베이스에 붙으려 하고, 그런 것은 없으므로 검사가 늘 「없음」으로 답한다.
if ! psql -d postgres -qtAc \
  "SELECT 1 FROM pg_database WHERE datname = '${DATABASE_NAME}'" \
  2>/dev/null | grep -q 1; then
  log "데이터베이스 ${DATABASE_NAME} 을 만듭니다."
  if ! createdb "$DATABASE_NAME" 2>/dev/null; then
    fall_back_to_sqlite "데이터베이스 ${DATABASE_NAME} 을 만들지 못했습니다."
  fi
fi

# 비밀번호가 들어갈 자리가 아예 없는 주소다.
echo "postgresql+psycopg:///${DATABASE_NAME}?host=${SOCKET_DIRECTORY}"
