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

MAJOR_VERSION=16

log() { echo "$@" >&2; }

# 이미 있으면 아무것도 하지 않는다. 개발자의 호스트에 이미 깔려 있을 수도 있고,
# 컨테이너를 다시 띄운 것일 수도 있다.
if command -v pg_isready > /dev/null 2>&1; then
  exit 0
fi

# 권한을 올리는 방법은 `database.sh` 와 같은 규칙을 쓴다 — root 면 그대로,
# 아니면 비대화형 sudo. 둘 다 안 되면 여기서 조용히 끝난다.
run_as_root() {
  if [ "$(id -u)" = "0" ]; then
    "$@"
  elif command -v sudo > /dev/null 2>&1 && sudo -n true 2> /dev/null; then
    sudo -n "$@"
  else
    return 1
  fi
}

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

install_postgresql() {
  export DEBIAN_FRONTEND=noninteractive
  run_as_root apt-get update -qq || return 1
  run_as_root apt-get install -y -qq --no-install-recommends \
    ca-certificates curl gnupg lsb-release || return 1

  # 열쇠는 **키링 파일**로 둔다. `apt-key` 는 폐기됐고, 그 방식은 이 열쇠를
  # 저장소 전체에 대해 믿게 만든다.
  run_as_root install -d -m 0755 /usr/share/keyrings || return 1
  curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    | run_as_root gpg --dearmor --yes -o /usr/share/keyrings/pgdg.gpg || return 1
  printf 'deb [signed-by=/usr/share/keyrings/pgdg.gpg] https://apt.postgresql.org/pub/repos/apt %s-pgdg main\n' \
    "$codename" | run_as_root tee /etc/apt/sources.list.d/pgdg.list > /dev/null || return 1

  run_as_root apt-get update -qq || return 1
  run_as_root apt-get install -y -qq --no-install-recommends \
    "postgresql-${MAJOR_VERSION}" "postgresql-client-${MAJOR_VERSION}" || return 1
}

log "PostgreSQL ${MAJOR_VERSION} 을 놓습니다 (처음 한 번, 몇 분 걸립니다)."
if ! install_postgresql; then
  log "PostgreSQL 을 놓지 못했습니다 — SQLite 로 진행합니다."
  exit 0
fi

log "PostgreSQL ${MAJOR_VERSION} 을 놓았습니다. 기동과 데이터베이스 준비는 database.sh 가 합니다."
exit 0
