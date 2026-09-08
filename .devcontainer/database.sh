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
DATABASE_PORT="5432"

# 목적지를 **못 박는다.** `pg_isready` · `psql` · `createdb` 는 모두 환경의
# `PGHOST` · `PGPORT` · `PGUSER` 같은 libpq 변수를 읽는다. 개발자의 셸에 그런
# 것이 하나라도 내보내져 있으면 조사와 생성은 그쪽 클러스터로 가는데, 이 파일이
# 마지막에 내미는 주소는 아래의 소켓과 포트로 **고정**되어 있다. 그러면 만든
# 곳과 알려 준 곳이 갈린다.
#
# 실측(2026-09-08): 같은 호스트에 16/alt(5433)를 띄우고 `PGPORT=5433` 을 내보낸
# 채 이 스크립트를 돌리면 `production_risk` 는 5433 에 생기는데 돌려주는 주소는
# 포트가 없어 5432 를 가리켰다.
#
# 그래서 우리가 약속하는 그 자리만 남기고 나머지는 전부 지운다. 여기 없는
# 클러스터라면 아래 검사가 실패하고 SQLite 로 물러난다 — 그것이 맞다. 엉뚱한
# 곳에 데이터베이스를 만들어 놓고 성공했다고 말하는 것보다 낫다.
unset PGHOSTADDR PGUSER PGDATABASE PGSERVICE PGSERVICEFILE PGPASSFILE \
  PGPASSWORD PGOPTIONS PGSSLMODE PGREQUIRESSL PGCHANNELBINDING \
  PGTARGETSESSIONATTRS PGCLIENTENCODING PGCONNECT_TIMEOUT
export PGHOST="$SOCKET_DIRECTORY"
export PGPORT="$DATABASE_PORT"

# **묻지 않게 한다.** `psql` 과 `createdb` 는 서버가 비밀번호를 요구하면 터미널에
# 대고 물어보고, 답이 올 때까지 기다린다. 이 스크립트를 부르는 것은 사람이 아니라
# 준비(`setup.sh`)와 세션 시작 훅이고 그 자리에는 답할 사람이 없다 — 물러나는 대신
# **영원히 매달린다.** 실측(2026-09-08): 소켓 인증을 `scram-sha-256` 으로 바꾸고
# 가상 터미널을 물려 돌리니 `Password for user root:` 에서 멈춰 20초 제한에 걸렸다.
#
# `-w` 는 「절대 묻지 말라」다. 비밀번호가 필요하면 그 자리에서 실패하고, 실패는
# 이 파일이 이미 아는 것 — SQLite 로 가는 길이다.
PSQL="psql -w"
CREATEDB="createdb -w"

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
#
# 그리고 **있다는 것만으로는 모자란다.** 이미 있는 역할이 평범한 `LOGIN`(=
# `NOCREATEDB`)이면 존재 검사만 하는 코드는 권한 부여를 건너뛰고, 그러면 둘 중
# 하나가 된다 — 데이터베이스가 없을 때는 `createdb` 가 실패해 SQLite 로 물러나고,
# 있을 때는 준비가 성공한 뒤 **검사가 `CREATE DATABASE` 에서 죽는다.**
# 그래서 존재가 아니라 **권한**을 묻는다.
#
# 그리고 이 조회는 **실패할 수 있다.** 역할이 아예 없으면 소켓 접속이 그 자리에서
# 거부되어 `psql` 이 0 아닌 값으로 끝나는데, `set -euo pipefail` 아래에서 그
# 파이프라인을 변수에 담으면 **대입이 곧 종료**가 된다. 그러면 역할을 만들려고
# 둔 아래 갈래에 영영 닿지 못하고, 「실패해도 죽지 않는다」던 이 파일이 0 아닌
# 값으로 나가 부르는 쪽의 `set -e` 까지 끌고 내려간다 — 역할이 없는 바로 그
# 경우에. 실측(2026-09-08): `PGPORT` 로 역할 없는 클러스터를 가리키면 종료코드 2.
#
# 그래서 실패를 **빈 답으로 받는다.** 빈 답은 아래에서 「역할이 없다」로 읽히고,
# 그것이 이 조회가 실패하는 가장 흔한 이유다. 역할이 있는데도 다른 이유로 못
# 붙은 것이었다면 이어지는 생성이 실패하고, 그때는 SQLite 로 물러난다.
# 조회를 받아 줄 데이터베이스를 **고른다.** `postgres` 를 관례로 믿지 않는다 —
# 그 데이터베이스에 이 역할의 `CONNECT` 이 없어도 응용 데이터베이스에는 붙을 수
# 있고, 그러면 아래 조회가 빈 답을 내 「역할이 없다」로 읽힌다. 이어지는 생성은
# 이미 있는 역할을 만들려다 실패하고, **쓸 수 있는 PostgreSQL 이 통째로 버려진다.**
# 실측(2026-09-08): `postgres` 만 거부하는 클러스터를 흉내 내니 정확히 그렇게 됐다.
select_maintenance_database() {
  for candidate in "$DATABASE_NAME" postgres template1; do
    if $PSQL -d "$candidate" -qtAc "SELECT 1" > /dev/null 2>&1; then
      echo "$candidate"
      return 0
    fi
  done
}

role="$(id -un)"
maintenance_database="$(select_maintenance_database)"
role_can_create=""
if [ -n "$maintenance_database" ]; then
  role_can_create="$($PSQL -d "$maintenance_database" -qtAc \
    "SELECT rolcreatedb OR rolsuper FROM pg_roles WHERE rolname = '${role}'" \
    2>/dev/null | tr -d '[:space:]' || true)"
fi

if [ "$role_can_create" = "f" ]; then
  log "역할 ${role} 에 데이터베이스 생성 권한이 없습니다. 권한을 더합니다."
  if ! run_as postgres "$PSQL -qc \"ALTER ROLE \\\"${role}\\\" CREATEDB\"" \
    > /dev/null 2>&1; then
    fall_back_to_sqlite "역할 ${role} 에 CREATEDB 를 줄 권한을 얻지 못했습니다."
  fi
elif [ -z "$role_can_create" ]; then
  log "역할 ${role} 을 만듭니다."
  # `SUPERUSER` 가 아니라 `CREATEDB` 다. 이 역할이 해야 하는 것은 두 가지뿐이다 —
  # `production_risk` 를 만들어 갖는 것과, 검사가 쓰는 일회용 데이터베이스를
  # 만드는 것. `CREATEDB` 가 그 둘을 모두 준다(만든 데이터베이스의 주인이 되므로
  # 지우는 것도 된다).
  #
  # `SUPERUSER` 를 주면 **클러스터의 모든 데이터베이스**에 대한 권한이 이
  # 개발 계정으로 도는 모든 프로세스에 영구히 붙는다 — 이 저장소와 무관한
  # 데이터베이스까지. 준비 스크립트가 조용히 할 일이 아니다.
  if ! run_as postgres "$PSQL -qc \"CREATE ROLE \\\"${role}\\\" LOGIN CREATEDB\"" \
    > /dev/null 2>&1; then
    fall_back_to_sqlite "역할 ${role} 을 만들 권한을 얻지 못했습니다."
  fi
fi
# 세 번째 갈래(`t`)는 아무것도 하지 않는다 — 이미 권한이 있다.

# 역할을 방금 만들었다면 이제는 붙을 곳이 생겼다. 한 번 더 고른다.
if [ -z "$maintenance_database" ]; then
  maintenance_database="$(select_maintenance_database)"
fi
if [ -z "$maintenance_database" ]; then
  fall_back_to_sqlite "붙을 수 있는 데이터베이스가 없습니다."
fi

# 유지보수용 데이터베이스를 **명시한다.** 생략하면 psql 이 사용자 이름과 같은
# 데이터베이스에 붙으려 하고, 그런 것은 없으므로 검사가 늘 「없음」으로 답한다.
if ! $PSQL -d "$maintenance_database" -qtAc \
  "SELECT 1 FROM pg_database WHERE datname = '${DATABASE_NAME}'" \
  2>/dev/null | grep -q 1; then
  log "데이터베이스 ${DATABASE_NAME} 을 만듭니다."
  if ! $CREATEDB "$DATABASE_NAME" 2>/dev/null; then
    fall_back_to_sqlite "데이터베이스 ${DATABASE_NAME} 을 만들지 못했습니다."
  fi
fi

# **있다는 것과 쓸 수 있다는 것은 다르다.** 위의 카탈로그 조회는 남이 만들어 둔
# `production_risk` 도 「있다」로 답한다. 그 데이터베이스에 이 역할의 `CONNECT`
# 이 없으면 생성을 건너뛴 채 멀쩡한 주소를 내밀게 되고, 그러면 `setup.sh` 가
# 약속된 SQLite 로 물러나는 대신 `set -e` 아래 기동 전 검사나 Alembic 에서
# 죽는다. 실측(2026-09-08): `REVOKE CONNECT ON DATABASE ... FROM PUBLIC` 한
# 데이터베이스에 대해 카탈로그 조회는 `1` 을 돌려주고 접속은
# `permission denied for database` 로 거부됐다.
#
# 그래서 내밀기 전에 **그 자리로 한 번 붙어 본다.** 못 붙으면 그것도 SQLite 로
# 가는 길이다.
if ! $PSQL -d "$DATABASE_NAME" -qtAc "SELECT 1" > /dev/null 2>&1; then
  fall_back_to_sqlite "데이터베이스 ${DATABASE_NAME} 에 붙지 못했습니다."
fi

# 비밀번호가 들어갈 자리가 아예 없는 주소다. 소켓과 포트는 위에서 못 박은 그
# 값이다 — 조사하고 만든 자리와 알려 주는 자리가 같아야 한다.
echo "postgresql+psycopg:///${DATABASE_NAME}?host=${SOCKET_DIRECTORY}&port=${DATABASE_PORT}"
