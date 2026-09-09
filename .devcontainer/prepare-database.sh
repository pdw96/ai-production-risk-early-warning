#!/usr/bin/env bash
# 고른 엔진을 **쓸 수 있는 상태로** 만든다 — 기동 전 검사 → 마이그레이션 → 비었을 때만 시드.
#
# **엔진과 무관하게 같은 길로 간다.** 컨테이너가 오는 길이 그것이고
# (`docker-entrypoint.sh`), 개발 세션도 같다.
#
# 예전에는 SQLite 갈래만 `app.seed`(인자 없음)로 **표를 지우고 다시 만들었다.**
# 「그 파일에는 지울 수 없는 데이터가 없다」는 전제였는데, 세션 시작 훅이 준비를
# **재개할 때마다** 부르면서 그 전제가 깨졌다 — 화면에서 기록한 리스크 상태가 재개
# 한 번에 사라진다. 실측으로 재현했다: 행 1개 → 재개 → 0개.
#
# 남아 있던 파일이 옛 스키마일 위험은 `preflight` 가 본다. 그것이 이 순서의 첫
# 줄에 있는 이유이며, 지우는 것보다 **멈추고 사람에게 묻는 쪽**이 옳다.
#
# **이 파일이 따로 있는 이유.** 준비(`setup.sh`)만 이 차례를 밟고 기동(`start.sh`)은
# 밟지 않았다. 그런데 기동도 엔진을 **다시 고른다** — 호스트가 다시 뜨면 소켓 뒤의
# 서버가 내려가 있어 그 자리를 지나가야 하기 때문이다. 그 사이 데이터베이스가
# 사라졌거나 SQLite 로 물러났으면 기동은 **표가 없는 엔진을 향해 서버를 띄우고**,
# 화면은 「기동 성공」이라 적힌 채 요청마다 「표가 없다」로 죽는다. 그래서 엔진을
# 고르는 곳은 둘 다 이 차례를 밟고, 차례는 **한 곳에만** 적는다.
#
# 두 번 **이어서** 돌아도 안전하다 — `upgrade head` 는 이미 맞으면 아무것도 하지
# 않고 `--if-empty` 는 비어 있을 때만 채운다. 그러나 **겹쳐서** 도는 것은 다른
# 이야기다. 「이미 맞는가」와 「비어 있는가」는 둘 다 보고 나서 고치는 일이고, 두
# 프로세스가 사이에 끼어들면 둘 다 「아직 아니다」를 본다.
#
# 실측(2026-09-08):
#
#   PostgreSQL 에서 `alembic upgrade head` 둘을 겹쳐 돌림
#     → 진 쪽 종료코드 1,
#       `duplicate key value violates unique constraint "pg_type_typname_nsp_index"`
#   SQLite 에서 `app.seed --if-empty` 둘을 겹쳐 돌림
#     → 진 쪽 종료코드 1,
#       `UNIQUE constraint failed: code_groups.group_code`
#
# 시드에는 이미 잠금이 있지만 그것은 `pg_advisory_xact_lock` 이라 **PostgreSQL
# 에서만** 선다. SQLite 갈래는 「파일 하나에 쓰는 것은 어차피 줄을 선다」에 기대고
# 있었는데, 줄을 서는 것은 쓰기이지 **읽고-보고-쓰기** 전체가 아니다.
#
# 그리고 이 실패는 조용하지 않다. 부르는 쪽이 `set -e` 아래에 있으므로 준비
# 전체가 그 자리에서 끊긴다 — 겹쳐 도는 것을 `database.sh` 는 이미 견디게
# 고쳐 두었는데, 정작 그 다음 차례가 못 견디고 있었다.
#
# 그래서 차례 전체를 **하나씩 지나가게** 한다. 잠금은 고른 데이터베이스마다
# 따로 둔다 — 서로 다른 데이터베이스를 준비하는 둘은 기다릴 이유가 없다.
set -euo pipefail

# **경로는 `cd` 하기 전에 잡는다.** 아래에서 `backend` 로 옮겨 가므로, 그 뒤에
# `${BASH_SOURCE[0]}` 의 상대 경로를 다시 풀면 엉뚱한 곳을 가리킨다.
DEVCONTAINER_DIRECTORY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$DEVCONTAINER_DIRECTORY/../backend"

prepare() {
  .venv/bin/python -m app.db.preflight
  .venv/bin/python -m alembic upgrade head
  .venv/bin/python -m app.seed --if-empty
}

# 잠금은 `lock.sh` 한 곳에 있다 — 준비 차례와 의존성 설치가 같은 규칙을 쓴다.
# 데이터베이스마다 따로 잠근다: 서로 다른 것을 준비하는 둘은 기다릴 이유가 없다.
# shellcheck source=.devcontainer/lock.sh
. "$DEVCONTAINER_DIRECTORY/lock.sh"

key="$(printf '%s' "${DATABASE_URL:-sqlite}" | sha256sum | cut -c1-16)"

# **실패를 값으로 받는다.** `set -e` 아래에서 이 호출이 0 아닌 값으로 끝나면
# 스크립트가 그 자리에서 죽는데, 잠글 자리가 없는 것은 「고장」이 아니라
# 「잠금 없이 진행」이다. 같은 형태를 5차 리뷰에서 한 번 맞았다.
lock_status=0
open_production_risk_lock "prepare-${key}" 9 || lock_status=$?
production_risk_lock_permits "$lock_status" "데이터베이스 준비" || exit 1

prepare
