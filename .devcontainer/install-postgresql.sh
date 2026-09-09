#!/usr/bin/env bash
# 개발 컨테이너에 **PostgreSQL 을 실제로 놓는다.**
#
# 왜 이 파일이 생겼는가. `database.sh` 는 「있으면 세우고 없으면 SQLite 로
# 물러난다」로 지어졌는데, **이 저장소의 devcontainer 에는 없었다.**
# `devcontainer.json` 이 쓰는 이미지는 `mcr.microsoft.com/devcontainers/python`
# 이고 붙은 기능은 Node 하나뿐이며, 저장소 어디에도 설치 단계가 없다(실측).
# 그러면 새로 만든 Codespace 에서는 `command -v pg_isready` 가 늘 실패해
# **언제나 SQLite 로 물러난다** — 이 PR 이 세우려던 「개발 세션도 운영과 같은
# 엔진」이 정작 서지 않는다. CI 는 서 있으므로 아무도 알아채지 못한다.
#
# **판을 못 박는 이유.** 운영과 CI 가 16 이다. 데비안 bookworm 이 기본으로 주는
# 것은 15 라, 배포판 것을 그냥 깔면 개발만 한 판 뒤처진다 — 이 PR 이 없애려던
# 그 어긋남이 판 번호로 되돌아온다. 그래서 PGDG 저장소에서 16 을 받는다.
#
# **여기서 실패하는 것은 고장이 아니다.** 못 깔면 `database.sh` 가 예전처럼
# SQLite 로 물러나고, 그것이 이 저장소가 실패에 대해 약속한 자리다. 그래서 이
# 파일은 **무슨 일이 있어도 0 으로 끝난다** — 부르는 쪽이 `set -e` 아래이므로
# 여기서 나가는 0 아닌 값은 준비 전체를 끌고 내려간다.
set -uo pipefail

# 판 번호는 `postgresql-version.sh` 한 곳에만 있다 — 고르는 쪽도 같은 숫자를 본다.
#
# 자리를 찾는 데 **바깥 명령을 쓰지 않는다.** `$(dirname ...)` 로 적었더니,
# `dirname` 이 없는 좁은 PATH 에서 소스가 실패하고 곧바로 변수가 없어
# `unbound variable` 로 죽었다 — 이 파일이 「무슨 일이 있어도 0 으로 끝난다」고
# 약속한 자리에서. 껍데기 안의 매개변수 확장은 아무것도 부르지 않는다.
# shellcheck source=.devcontainer/postgresql-version.sh
. "${BASH_SOURCE[0]%/*}/postgresql-version.sh" 2> /dev/null || true
if [ -z "${PRODUCTION_RISK_POSTGRESQL_MAJOR:-}" ]; then
  log() { echo "$@" >&2; }
  log "놓을 PostgreSQL 판을 알 수 없습니다 — SQLite 로 진행합니다."
  exit 0
fi
MAJOR_VERSION="$PRODUCTION_RISK_POSTGRESQL_MAJOR"
DATABASE_PORT="5432"

log() { echo "$@" >&2; }

# 이미 있으면 아무것도 하지 않는다. 개발자의 호스트에 이미 깔려 있을 수도 있고,
# 컨테이너를 다시 띄운 것일 수도 있다.
#
# **묻는 것은 「이 판의 서버가 있는가」다.** 예전에는 `command -v pg_isready` 로
# 물었는데, 그것은 서버가 아니라 **클라이언트**의 존재다. 실측(2026-09-09):
# `pg_isready` 를 주는 꾸러미는 `postgresql-client-common` 이고,
# `postgresql-client-16` 이 의존하는 것도 그것뿐 — 서버 꾸러미 `postgresql-16` 은
# 그 사슬에 없다. 클라이언트만 깔린 PATH 로 이 파일을 돌리니 **종료코드 0** 으로
# 아무것도 하지 않고 끝났고, 그 뒤 `pg_ctlcluster` 는 없었다. 그러면
# `database.sh` 는 89·94번째 줄에서 SQLite 로 물러난다 — 이 파일이 세우려던
# 보장이 정작 서지 않고, 아무도 알아채지 못한다.
#
# 판까지 함께 묻는 이유. `database.sh` 는 클러스터를 **판이 아니라 포트로**
# 고른다(104번째 줄). 그래서 15가 5432를 지키고 있으면 그것을 기동해 쓰고,
# 개발만 한 판 뒤처진 채로 돈다 — 이 파일이 PGDG 에서 16을 받아 오는 이유가
# 바로 그 어긋남이다. 그러니 `pg_isready` 가 있다는 것으로는 건너뛸 수 없다.
#
# 데비안·PGDG 는 서버를 `/usr/lib/postgresql/<판>/bin/postgres` 에 둔다. 그것과
# `pg_ctlcluster`(`postgresql-common`) 둘 다 있어야 `database.sh` 가 실제로 세운다.
#
# **그리고 바이너리가 있다는 것으로도 모자란다.** 데비안에서 판을 올리면 옛
# 클러스터가 5432를 그대로 쥔 채 새 판이 5433으로 밀리는 것이 정상 상태다. 그때
# 16 바이너리는 분명히 있는데 `database.sh` 가 붙는 자리는 15다. 실측
# (2026-09-09, 가짜 `pg_lsclusters` 로 `15 main 5432 down` 을 놓고): 이 파일은
# 아무 말 없이 0 으로 끝났고, 곧바로 `database.sh` 는 **"PostgreSQL 15/main 를
# 기동합니다"** 라고 답했다. 개발만 한 판 뒤처진 채로 도는 것 — 이 파일이 PGDG
# 에서 16을 받아 오는 이유가 바로 그 어긋남이다.
#
# 그러니 묻는 것은 **「우리가 붙을 포트를 지키는 클러스터가 이 판인가」**다.
# 아니면 건너뛰지 않고 아래로 내려가 놓기를 시도한다. 놓아도 그 포트를 못 잡는
# 배치라면 `database.sh` 가 판을 견주어 SQLite 로 물러난다 — 조용히 옛 판에
# 붙는 것보다 낫다.
cluster_version_on_port() {
  command -v pg_lsclusters > /dev/null 2>&1 || return 1
  pg_lsclusters --no-header 2> /dev/null \
    | awk -v port="$DATABASE_PORT" '$3 == port { print $1; exit }'
}

if [ -x "/usr/lib/postgresql/${MAJOR_VERSION}/bin/postgres" ] \
  && command -v pg_ctlcluster > /dev/null 2>&1 \
  && [ "$(cluster_version_on_port)" = "$MAJOR_VERSION" ]; then
  exit 0
fi

# 권한을 올리는 규칙은 `privilege.sh` 한 곳에 있다. 자리를 찾는 데 바깥 명령을
# 쓰지 않는 것은 위와 같은 이유다. 못 읽으면 아래 `run_as_root` 가 없어 이 파일이
# 죽으므로, 그때는 조용히 끝난다 — 이 파일은 무슨 일이 있어도 0 으로 끝난다.
# shellcheck source=.devcontainer/privilege.sh
. "${BASH_SOURCE[0]%/*}/privilege.sh" 2> /dev/null || true
if ! command -v run_as_root > /dev/null 2>&1; then
  log "권한을 올리는 방법을 읽지 못했습니다 — SQLite 로 진행합니다."
  exit 0
fi

if ! command -v apt-get > /dev/null 2>&1; then
  log "PostgreSQL 을 놓을 방법을 모르는 환경입니다 — SQLite 로 진행합니다."
  exit 0
fi

if ! run_as_root true 2> /dev/null; then
  log "PostgreSQL 을 놓을 권한이 없습니다 — SQLite 로 진행합니다."
  exit 0
fi

# shellcheck disable=SC1091  # 컨테이너 안에서만 존재하는 파일이다.
codename="$(. /etc/os-release 2>/dev/null && echo "${VERSION_CODENAME:-}")"
if [ -z "$codename" ]; then
  log "배포판을 알 수 없어 PostgreSQL 을 놓지 못했습니다 — SQLite 로 진행합니다."
  exit 0
fi

# **`export` 로는 apt 에 닿지 않는다.** `run_as_root` 는 root 가 아닐 때
# `sudo -n` 을 쓰고, sudoers 의 기본값은 `env_reset` 이라 우리 환경을 지운다.
# 실측(2026-09-09, NOPASSWD sudo 를 가진 비root 계정):
#
#   우리 셸: [noninteractive]
#   sudo 안: [<비어있음>]
#
# root 로 도는 길에서는 그대로 넘어가므로, 이 결함은 **개발 컨테이너의 보통
# 사용자에게만** 나타난다 — 거기서 apt 는 사람에게 물을 수 있는 프런트엔드로
# 돈다. 그래서 값을 환경에 두지 말고 **명령의 일부로** 넘긴다.
apt_get() {
  run_as_root env DEBIAN_FRONTEND=noninteractive apt-get "$@"
}

# 우리가 apt 자리에 무엇을 더했는지 기억한다 — 실패하면 되돌리기 위해서다.
# 이미 있던 것은 우리 것이 아니므로 건드리지 않는다.
PGDG_LIST="/etc/apt/sources.list.d/pgdg.list"
PGDG_KEYRING="/usr/share/keyrings/pgdg.gpg"
pgdg_list_was_ours=0
pgdg_keyring_was_ours=0

install_postgresql() {
  apt_get update -qq || return 1
  apt_get install -y -qq --no-install-recommends \
    ca-certificates curl gnupg lsb-release || return 1

  # 열쇠는 **키링 파일**로 둔다. `apt-key` 는 폐기됐고, 그 방식은 이 열쇠를
  # 저장소 전체에 대해 믿게 만든다.
  run_as_root install -d -m 0755 /usr/share/keyrings || return 1
  [ -e "$PGDG_KEYRING" ] || pgdg_keyring_was_ours=1
  curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    | run_as_root gpg --dearmor --yes -o "$PGDG_KEYRING" || return 1
  [ -e "$PGDG_LIST" ] || pgdg_list_was_ours=1
  printf 'deb [signed-by=%s] https://apt.postgresql.org/pub/repos/apt %s-pgdg main\n' \
    "$PGDG_KEYRING" "$codename" | run_as_root tee "$PGDG_LIST" > /dev/null || return 1

  apt_get update -qq || return 1
  apt_get install -y -qq --no-install-recommends \
    "postgresql-${MAJOR_VERSION}" "postgresql-client-${MAJOR_VERSION}" || return 1
}

# **실패하면 우리가 더한 apt 자리를 되돌린다.**
#
# 남겨 두면 그 목록은 닿지 않는 저장소를 가리킨 채 남고, 그때부터 이 컨테이너에서
# 도는 **모든** `apt-get update` 가 그것을 함께 긁는다. 실측(2026-09-09, 닿을 수는
# 있는데 색인이 없는 저장소로): `apt-get update` 가 **종료코드 100** 이었다
# (`E: Failed to fetch ...`). 우리 실패는 「SQLite 로 물러난다」로 끝나기로 되어
# 있는데, 그 자국이 남으면 이 저장소와 무관한 도구까지 함께 넘어진다.
#
# 이미 있던 것은 지우지 않는다 — 남이 놓아 둔 PGDG 를 우리 실패로 걷어내는 것은
# 고치려던 것보다 나쁘다.
undo_our_apt_changes() {
  [ "$pgdg_list_was_ours" = "1" ] && run_as_root rm -f "$PGDG_LIST" 2> /dev/null
  [ "$pgdg_keyring_was_ours" = "1" ] && run_as_root rm -f "$PGDG_KEYRING" 2> /dev/null
  return 0
}

log "PostgreSQL ${MAJOR_VERSION} 을 놓습니다 (처음 한 번, 몇 분 걸립니다)."
if ! install_postgresql; then
  undo_our_apt_changes
  log "PostgreSQL 을 놓지 못했습니다 — SQLite 로 진행합니다."
  exit 0
fi

log "PostgreSQL ${MAJOR_VERSION} 을 놓았습니다. 기동과 데이터베이스 준비는 database.sh 가 합니다."
exit 0
