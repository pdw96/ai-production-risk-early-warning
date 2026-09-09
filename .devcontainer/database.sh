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

SOCKET_DIRECTORY="/var/run/postgresql"
DATABASE_PORT="5432"

DEVCONTAINER_DIRECTORY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "$DEVCONTAINER_DIRECTORY/.." && pwd)"

# 판 번호는 `postgresql-version.sh` 한 곳에만 있다 — 놓는 쪽도 같은 숫자를 본다.
# shellcheck source=.devcontainer/postgresql-version.sh
. "$DEVCONTAINER_DIRECTORY/postgresql-version.sh"

# **이름은 체크아웃마다 다르다.**
#
# 예전에는 `production_risk` 한 이름이었다. 그러면 워크트리 둘이나 나란한 체크아웃
# 둘이 같은 클러스터에서 **같은 데이터베이스**를 준비하고 검사한다 — 파일과
# 마이그레이션은 서로 다른데.
#
# 실측(2026-09-09): 다른 가지가 남긴 리비전 `deadbeefcafe` 가 `alembic_version` 에
# 든 데이터베이스에 이 체크아웃이 `alembic upgrade head` 를 돌리니
# `Can't locate revision identified by 'deadbeefcafe'` 로 죽었다. 가지가 서로
# 맞더라도 시드 데이터와 손으로 고친 값을 말없이 나눠 쓴다.
#
# 그래서 잠금이 이미 쓰는 것과 **같은 열쇠**(저장소 뿌리의 해시)를 이름에 붙인다.
# `production_risk_` 16자 + 해시 16자 = 32자로, PostgreSQL 의 이름 한계인
# `NAMEDATALEN-1`(63) 안에 넉넉히 든다.
DATABASE_NAME="production_risk_$(printf '%s' "$REPOSITORY_ROOT" | sha256sum | cut -d' ' -f1 | cut -c1-16)"

# 관례대로 늘 있는 데이터베이스들. **한 곳에만 적는다** — 붙을 자리를 고르는 쪽과
# 판을 묻는 쪽이 다른 목록을 보면, 붙기는 되는데 판은 못 묻는 틈이 생긴다.
MAINTENANCE_DATABASES="postgres template1"

# 목적지를 **못 박는다.** 환경에 내보내져 있던 libpq 변수를 지우고(목록은
# `libpq.sh` 한 곳에 있다) 우리가 약속하는 자리만 다시 세운다. 여기 없는
# 클러스터라면 아래 검사가 실패하고 SQLite 로 물러난다 — 그것이 맞다. 엉뚱한
# 곳에 데이터베이스를 만들어 놓고 성공했다고 말하는 것보다 낫다.
# shellcheck source=.devcontainer/libpq.sh
. "$DEVCONTAINER_DIRECTORY/libpq.sh"
clear_ambient_libpq_environment
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
  # **첫 줄이 아니라 그 포트를 지키는 클러스터**를 고른다. 개발 호스트에 클러스터가
  # 둘 이상이면 첫 줄은 우리가 보는 자리와 무관할 수 있고, 그러면 엉뚱한 클러스터를
  # 기동한 뒤 30초를 기다렸다가 물러난다 — **정작 내려가 있는 5432 는 손도 대지
  # 않은 채**로. 실측(2026-09-08): `16/aaa`(5433)와 `16/main`(5432, down)이 있을 때
  # 이름 순으로 앞선 `aaa` 를 기동하려 했고, 31초 뒤 SQLite 로 물러났으며 `main` 은
  # 그대로 내려가 있었다.
  clusters="$(pg_lsclusters --no-header 2>/dev/null)"
  version="$(echo "$clusters" | awk -v port="$DATABASE_PORT" '$3 == port {print $1; exit}')"
  cluster="$(echo "$clusters" | awk -v port="$DATABASE_PORT" '$3 == port {print $2; exit}')"
  if [ -z "$version" ] || [ -z "$cluster" ]; then
    fall_back_to_sqlite "포트 ${DATABASE_PORT} 을 지키는 PostgreSQL 클러스터가 없습니다."
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

# **판을 견준다.** 여기까지 오면 포트 ${DATABASE_PORT} 에 서버가 하나 서 있는데,
# 그것이 우리가 약속한 판이라는 보장은 아직 없다 — 위의 갈래는 포트로 고르고,
# 이미 돌고 있었다면 그 갈래조차 지나친다. 데비안에서 판을 올리면 옛 클러스터가
# 5432를 그대로 쥐는 것이 정상 상태이므로, 16을 깔아 두고도 15에 붙는 일이
# 생긴다(실측 2026-09-09). 그것이 이 PR 이 없애려던 어긋남이고, **조용하다는
# 점에서 더 나쁘다** — CI 는 16이라 아무도 알아채지 못한다.
#
# `server_version_num` 은 `160013`(16.13) 같은 정수다. 뒤 네 자리가 부판이므로
# 앞을 떼어 견준다.
#
# **못 읽었으면 버리지 않는다.** 물음이 실패했거나 답이 이 꼴이 아니면 우리가
# 아는 것은 「판을 모른다」이지 「판이 다르다」가 아니다. 모른다는 이유로 멀쩡한
# PostgreSQL 을 버리면, 이 검사가 막으려던 것보다 큰 것을 막는다 — 확실히 읽힌
# 값이 어긋날 때만 문다.
# 실패를 **값으로 받는다.** `|| true` 가 없으면 `set -euo pipefail` 아래에서 이
# 대입이 곧 종료가 된다 — 역할이 없어 `psql` 이 거부당하는 것은 흔한 상태이고,
# 그때 이 파일은 SQLite 로 물러나야지 죽으면 안 된다. 같은 결함을 5차에 고쳤고
# `test_a_failing_role_probe_does_not_kill_the_script` 가 그것을 지킨다.
# **한 이름이 아니라 정비 데이터베이스 후보들에게 묻는다.** 관례대로 있는
# `postgres` 가 지워진 호스트가 있고, 그러면 이 물음만 빈 값으로 돌아온다 —
# 그런데 아래의 관리자 갈래는 `template1` 로 붙어 역할과 데이터베이스를 만들어
# 낸다. 즉 붙을 수는 있는데 판만 못 물어보고 지나가는 자리가 생긴다. 나중에
# 붙는 그 후보들에게 지금 묻는다.
server_version=""
for maintenance in $MAINTENANCE_DATABASES; do
  [ -n "$server_version" ] && break
  server_version="$($PSQL -d "$maintenance" -qtAc "SHOW server_version_num" 2> /dev/null \
    | tr -d '[:space:]' || true)"
done

# **못 물었으면 관리자로 다시 묻는다.** 위의 물음은 지금 이 역할로 간다. 그런데
# 이 자리는 아직 역할을 만들기 **전**이다 — 첫 준비에서는 운영체제 사용자와 같은
# 이름의 역할이 없어 peer 접속이 그 자리에서 거부되고, 답은 빈 값으로 온다.
# 그러면 위의 「모르면 버리지 않는다」가 그대로 통과시키고, 곧이어 관리자 계정으로
# 역할을 만든 뒤 **판이 다른 서버를 골라 준비까지 마친다.** 판을 견주려고 둔 검사가
# 정작 첫 준비에서만 비어 있는 셈이다.
#
# 그래서 같은 물음을 관리자로 한 번 더 한다 — `probe_as_postgres` 가 이미 쓰는
# 길이다. 그것마저 안 되면 그때는 정말 「판을 모른다」이고, 모른다는 이유로
# 버리지는 않는다.
for maintenance in $MAINTENANCE_DATABASES; do
  [ -n "$server_version" ] && break
  server_version="$(run_as postgres "$PSQL -d $(printf '%q' "$maintenance") -qtAc 'SHOW server_version_num'" 2> /dev/null \
    | tr -d '[:space:]' || true)"
done
case "$server_version" in
  [0-9][0-9][0-9][0-9][0-9] | [0-9][0-9][0-9][0-9][0-9][0-9])
    server_major="${server_version%????}"
    if [ "$server_major" != "$PRODUCTION_RISK_POSTGRESQL_MAJOR" ]; then
      fall_back_to_sqlite \
        "포트 ${DATABASE_PORT} 의 PostgreSQL 이 ${server_major} 판입니다 — 운영·CI 는 ${PRODUCTION_RISK_POSTGRESQL_MAJOR} 판입니다."
    fi
    ;;
esac

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
#
# **역할을 고치는 명령에도 같은 것이 필요하다.** `psql` 에 `-d` 를 주지 않으면
# 접속 사용자와 같은 이름의 데이터베이스를 찾는다. 권한을 올려 `postgres` 역할로
# 도는 명령은 그래서 `postgres` 데이터베이스를 향하는데, 그것은 지울 수 있는
# 데이터베이스다. 지워져 있으면 이 명령만 실패하고, 쓸 수 있는 클러스터를 통째로
# 버린 채 SQLite 로 물러난다. 실측(2026-09-08, PostgreSQL 16.13): 같은 이름의
# 데이터베이스가 없는 역할로 `psql -w -qc "SELECT 1"` 을 돌리니
# `FATAL: database "pgadmin8" does not exist`, `-d template1` 을 주니 `1`.
#
# 그래서 고르는 규칙은 하나로 두고 **누구로 붙어 보는지만** 바꾼다.
probe_as_current_role() {
  $PSQL -d "$1" -qtAc "SELECT 1" > /dev/null 2>&1
}

probe_as_postgres() {
  run_as postgres "$PSQL -d $(printf '%q' "$1") -qtAc 'SELECT 1'" > /dev/null 2>&1
}

select_database_with() {
  local probe="$1"
  local candidate
  for candidate in "$DATABASE_NAME" $MAINTENANCE_DATABASES; do
    if "$probe" "$candidate"; then
      echo "$candidate"
      return 0
    fi
  done
}

select_maintenance_database() {
  select_database_with probe_as_current_role
}

role="$(id -un)"

# 「이 역할이 데이터베이스를 만들 수 있는가」를 묻는 한 곳. `t` · `f` · 빈 값
# (역할이 없거나 물어볼 데가 없다)을 그대로 돌려준다.
probe_role_privilege() {
  local database
  database="$(select_maintenance_database)"
  if [ -z "$database" ]; then
    return 0
  fi
  $PSQL -d "$database" -qtAc \
    "SELECT rolcreatedb OR rolsuper FROM pg_roles WHERE rolname = '${role}'" \
    2>/dev/null | tr -d '[:space:]' || true
}

maintenance_database="$(select_maintenance_database)"
role_can_create="$(probe_role_privilege)"

# 권한을 올려 도는 명령이 붙을 곳. 위의 것과 후보는 같고 **붙어 보는 역할이**
# 다르다 — 지금 역할이 못 붙는 데이터베이스에 `postgres` 는 붙을 수 있고, 그
# 반대도 있다.
administrative_database=""
if [ "$role_can_create" = "f" ] || [ -z "$role_can_create" ]; then
  administrative_database="$(select_database_with probe_as_postgres)"
  if [ -z "$administrative_database" ]; then
    fall_back_to_sqlite "권한을 올려 붙을 수 있는 데이터베이스가 없습니다."
  fi
fi

if [ "$role_can_create" = "f" ]; then
  log "역할 ${role} 에 데이터베이스 생성 권한이 없습니다. 권한을 더합니다."
  if ! run_as postgres \
    "$PSQL -d $(printf '%q' "$administrative_database") -qc \"ALTER ROLE \\\"${role}\\\" CREATEDB\"" \
    > /dev/null 2>&1 && [ "$(probe_role_privilege)" != "t" ]; then
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
  #
  # **만들기가 실패해도 「없다」는 뜻이 아니다.** 데이터베이스 생성과 똑같이,
  # 준비와 세션 시작 훅이 겹쳐 돌면 둘 다 「역할이 없다」를 보고 한쪽만 만든다.
  # 실측(2026-09-08, PostgreSQL 16.13): `CREATE ROLE` 둘을 겹쳐 돌리니 진 쪽이
  # `duplicate key value violates unique constraint "pg_authid_rolname_index"`
  # 로 끝났고, 역할은 `rolcreatedb = t` 로 멀쩡히 있었다.
  #
  # 진 쪽이 그것을 「권한을 얻지 못했다」로 읽으면 SQLite 로 물러나고, 그러면
  # 이긴 쪽이 고른 PostgreSQL 을 **지운다.** 그래서 한 번 더 묻는다.
  if ! run_as postgres \
    "$PSQL -d $(printf '%q' "$administrative_database") -qc \"CREATE ROLE \\\"${role}\\\" LOGIN CREATEDB\"" \
    > /dev/null 2>&1 && [ "$(probe_role_privilege)" != "t" ]; then
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
database_exists() {
  $PSQL -d "$maintenance_database" -qtAc \
    "SELECT 1 FROM pg_database WHERE datname = '${DATABASE_NAME}'" \
    2>/dev/null | grep -q 1
}

if ! database_exists; then
  log "데이터베이스 ${DATABASE_NAME} 을 만듭니다."
  # **만들기는 실패해도 「없다」는 뜻이 아니다.** 이 파일은 준비와 세션 시작 훅
  # 양쪽에서 불리고 둘이 겹쳐 돌 수 있다. 그러면 둘 다 위의 검사에서 「없다」를
  # 보고, 한쪽이 만들고, **다른 쪽은 여기서 실패한다** — `CREATE DATABASE` 에는
  # `IF NOT EXISTS` 가 없어서 그렇다(실측: `syntax error at or near "NOT"`).
  #
  # 실측(2026-09-08, PostgreSQL 16.13): `createdb` 둘을 실제로 겹쳐 돌리니 진
  # 쪽이 `duplicate key value violates unique constraint
  # "pg_database_datname_index"` 로 끝났고, 데이터베이스는 멀쩡히 있었다.
  #
  # 진 쪽이 그것을 「못 만들었다」로 읽으면 SQLite 로 물러나고, 그러면 이긴 쪽이
  # 적어 둔 `database.env` 를 **지운다**(`setup.sh` 의 else 갈래). 두 세션이 서로
  # 다른 엔진을 들고 도는 것보다 나쁜 결과다.
  #
  # 그래서 실패했을 때 한 번 더 **있는지 묻는다.** 있으면 이긴 쪽이 만든 것이니
  # 그대로 간다 — 쓸 수 있는지는 어차피 아래 판정이 마지막에 묻는다.
  #
  # **붙을 곳을 여기에도 적는다.** 위의 권한 명령들과 같은 이유다 — 다만 이쪽은
  # 지금 당장 깨지는 자리가 아니라 **약속되지 않은 동작에 기대고 있던** 자리다.
  # 실측(2026-09-08, createdb 16.13): `postgres` 는 있는데 이 역할의 `CONNECT` 이
  # 없고 `template1` 은 되는 상태를 만들어 돌리니 `createdb` 는 **세 번 다
  # 성공**했다 — 접속이 거부되면 스스로 `template1` 로 물러난다. 그런데 문서가
  # 약속하는 것은 「`postgres` 가 **없거나** 대상 자신일 때 `template1` 을 쓴다」
  # 뿐이고, 접속 실패 시의 대체는 적혀 있지 않다. 우리가 이미 고른 값이 있는데
  # 구현의 습관에 기댈 이유가 없다.
  if ! $CREATEDB --maintenance-db="$maintenance_database" "$DATABASE_NAME" \
    2>/dev/null && ! database_exists; then
    fall_back_to_sqlite "데이터베이스 ${DATABASE_NAME} 을 만들지 못했습니다."
  fi
fi

# **붙을 수 있다는 것과 쓸 수 있다는 것도 다르다.** 위의 카탈로그 조회는 남이
# 만들어 둔 `production_risk` 도 「있다」로 답한다. 그 데이터베이스에 이 역할이
# 표를 만들지 못하면 생성을 건너뛴 채 멀쩡한 주소를 내밀게 되고, 그러면
# `setup.sh` 가 약속된 SQLite 로 물러나는 대신 `set -e` 아래 기동 전 검사나
# Alembic 에서 죽는다.
#
# 그 판정은 **`database-usable.sh` 한 곳**에 있다. 여기와 프로파일 훅이 같은
# 질문에 다르게 답하면, 준비는 PostgreSQL 을 고르고 셸은 SQLite 로 도는 일이
# 생긴다. 근거와 실측은 그 파일에 적혀 있다.
if ! bash "$DEVCONTAINER_DIRECTORY/database-usable.sh" \
  "$SOCKET_DIRECTORY" "$DATABASE_PORT" "$DATABASE_NAME"; then
  fall_back_to_sqlite "데이터베이스 ${DATABASE_NAME} 에 표를 만들 수 없습니다."
fi

# 비밀번호가 들어갈 자리가 아예 없는 주소다. 소켓과 포트는 위에서 못 박은 그
# 값이다 — 조사하고 만든 자리와 알려 주는 자리가 같아야 한다.
echo "postgresql+psycopg:///${DATABASE_NAME}?host=${SOCKET_DIRECTORY}&port=${DATABASE_PORT}"
