#!/usr/bin/env bash
set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPOSITORY_ROOT"

# 정해진 엔진을 이후 명령들이 이어받는 자리. 이 파일 하나가 유일한 대응표다.
DATABASE_ENVIRONMENT_FILE="$REPOSITORY_ROOT/.devcontainer/database.env"

# 물려받은 주소가 우리 것인지 묻는 판단. `start.sh` · 세션 시작 훅과 **같은
# 정의**를 쓴다.
# shellcheck source=.devcontainer/autoselected.sh
. "$REPOSITORY_ROOT/.devcontainer/autoselected.sh"

# 주소에서 비밀번호만 가린다. 어느 엔진·어느 데이터베이스인지는 사람이 봐야
# 하므로 통째로 숨기지 않는다.
#
# 자격증명이 들어오는 자리가 **둘**이다. `://사용자:비밀번호@` 만 가리면 부족한데,
# SQLAlchemy 는 질의 문자열의 키를 psycopg 에 그대로 접속 인자로 넘기므로
# `?password=...` · `?sslpassword=...` 도 **동작하는 주소**다. 잘못된 입력이
# 아니라 다른 표기이며, 가리지 않으면 그대로 로그에 박힌다.
redact_url() {
  printf '%s' "$1" | sed -E \
    -e 's#://([^:/@]+):[^@]*@#://\1:***@#' \
    -e 's#([?&](password|sslpassword)=)[^&]*#\1***#g'
}

python -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
backend/.venv/bin/python -m pip install -r backend/requirements.txt

# 잠금 파일 그대로 받는 `npm ci` 는 node_modules 를 지우고 처음부터 받는다.
# 다시 부를 수 있어야 하는 자리(세션 재개)에서 그것을 매번 하면 몇 분이 그냥
# 사라진다. 그렇다고 **디렉터리가 있는지**로 거르면 안 된다 — 세션을 재개하며
# 잠금 파일이 바뀐 리비전을 받아 와도 그 조건은 「있다」이므로 설치를 건너뛰고,
# 프론트 검사가 옛 의존성 위에서 돈다. 물어야 할 것은 **지금 깔린 것이 지금
# 잠금 파일에서 나왔는가**이므로, 잠금 파일의 해시를 남겨 두고 그것을 견준다.
FRONTEND_LOCK_HASH_FILE="frontend/node_modules/.package-lock-sha256"
frontend_lock_hash="$(sha256sum frontend/package-lock.json | cut -d' ' -f1)"
if [ "$(cat "$FRONTEND_LOCK_HASH_FILE" 2>/dev/null || true)" != "$frontend_lock_hash" ]; then
  npm --prefix frontend ci
  # `npm ci` 가 node_modules 를 지우고 다시 만드므로 **끝난 뒤에** 적는다.
  printf '%s' "$frontend_lock_hash" > "$FRONTEND_LOCK_HASH_FILE"
fi

# 지난 세션이 **우리가 고른** 주소를 물려줬다면 그것을 믿지 않는다. 왜 그런지와
# 왜 값까지 견주는지는 `autoselected.sh` 에 적혀 있다.
if production_risk_url_is_inherited_ours; then
  unset DATABASE_URL
fi
# 표식은 여기서 끝난다. 남겨 두면 아래에서 다시 적는 값과 어긋날 수 있다.
unset PRODUCTION_RISK_DATABASE_AUTOSELECTED

# 개발 세션도 운영과 같은 엔진을 본다. 세우지 못하는 환경이면 빈 값이 오고,
# 그때는 예전처럼 SQLite 파일 하나로 돈다.
database_url_is_ours=0
if [ -z "${DATABASE_URL:-}" ]; then
  DATABASE_URL="$(bash .devcontainer/database.sh)"
  export DATABASE_URL
  database_url_is_ours=1
fi

# 여기서 export 한 값은 **이 프로세스와 함께 사라진다.** 이 스크립트는
# `postCreateCommand` 나 세션 시작 훅으로 한 번 돌고 끝나므로, 그 뒤 사람이 치는
# `cd backend && .venv/bin/python -m pytest` 에는 `DATABASE_URL` 이 없다 —
# 마이그레이션과 시드는 PostgreSQL 에 해 놓고 정작 검사는 SQLite 로 도는,
# 이 PR 이 없애려던 바로 그 어긋남이 개발자의 손 안에서 다시 생긴다.
#
# 그래서 파일로 남긴다. 값은 `printf %q` 로 적는다 — 주소에 작은따옴표가 들어갈
# 수 있고(URI 사용자 정보에 허용된다), 따옴표 사이에 그대로 끼워 넣으면 그 줄이
# 다른 뜻이 되거나 아예 읽히지 않는다.
#
# **우리가 고른 주소만 적는다.** 사람이 준 주소에는 비밀번호가 들어 있을 수 있고,
# 그것을 파일로 옮기면 저장소 곁에 평문 자격증명이 하나 생긴다 — 그 사람의 셸에는
# 이미 그 값이 있으므로 옮겨 적을 이유도 없다. 우리가 고르는 주소는 유닉스 소켓
# + peer 인증이라 비밀번호가 아예 없다.
#
# 그럼에도 파일 권한을 좁힌다. 여러 사람이 쓰는 개발 호스트에서 기본 umask 는
# 흔히 022 라 남이 읽을 수 있다.
if [ "$database_url_is_ours" = "1" ] && [ -n "${DATABASE_URL:-}" ]; then
  (
    umask 077
    {
      printf 'export DATABASE_URL=%q\n' "$DATABASE_URL"
      # 표식은 `1` 이 아니라 **자기가 표시하는 그 값**을 들고 다닌다.
      printf 'export PRODUCTION_RISK_DATABASE_AUTOSELECTED=%q\n' "$DATABASE_URL"
    } > "$DATABASE_ENVIRONMENT_FILE"
  )
else
  # 빈 파일이 아니라 **없는 파일**이어야 한다. 남아 있으면 지난 세션의 주소가
  # 이번 세션의 엔진 판단을 이긴다.
  rm -f "$DATABASE_ENVIRONMENT_FILE"
fi

# 대화형 셸이 그 파일을 읽게 한다. **이 저장소 안에서 연 셸만** 읽는다.
#
# 조건 없이 걸면 이 집의 모든 셸에 `DATABASE_URL` 이 export 되고, 그러면 그
# 관용 변수를 보는 **다른 프로그램이 production_risk 에 붙어 고칠 수 있다.**
# 표식에 저장소 경로를 넣는 것도 같은 이유다 — 고정 표식이면 같은 집의 두 번째
# 체크아웃이 자기 줄을 영영 넣지 못한다.
#
# `cd` 로 들어온 뒤에는 다시 평가되지 않는다. 그 값을 얻는 정확한 방법은 셸
# 훅(direnv 류)인데, 준비 스크립트가 의존성을 하나 늘릴 자리는 아니다 —
# `bash .devcontainer/start.sh` 와 `setup.sh` 는 스스로 주소를 정하므로
# 이 줄이 없어도 돈다.
#
# **그리고 읽기 전에 살아 있는지 본다.** devcontainer 가 다시 뜰 때 도는 것은
# `postStartCommand`(= `docker-gc.sh`) 하나뿐이라 `setup.sh` 도 `start.sh` 도
# 돌지 않는다. 그 상태에서 이 줄이 지난 세션의 주소를 그대로 내보내면, 사람이
# 곧바로 치는 `cd backend && .venv/bin/python -m pytest` 가 **내려가 있는 서버를
# 향해** 돈다. 실측(2026-09-08): 클러스터를 내린 뒤 그 파일을 읽은 셸에서
# `connection to server on socket ... failed`.
#
# `pg_isready` 는 접속 한 번이라 셸이 뜨는 데 얹히지 않는다. 죽어 있으면 아무것도
# 내보내지 않고, 그러면 예전처럼 SQLite 파일로 돈다 — 죽은 주소를 들고 있는 것보다
# 낫다. 서버를 세우는 것은 여전히 `database.sh` 하나뿐이고, 그것을 부르는 것은
# `setup.sh` 와 `start.sh` 다.
database_host="$(printf '%s' "${DATABASE_URL:-}" | sed -n 's/.*[?&]host=\([^&]*\).*/\1/p')"
database_port="$(printf '%s' "${DATABASE_URL:-}" | sed -n 's/.*[?&]port=\([^&]*\).*/\1/p')"

SHELL_HOOK_MARKER="# ai-production-risk(${REPOSITORY_ROOT}): 개발 세션의 데이터베이스 주소"
for profile in "$HOME/.bashrc" "$HOME/.zshrc"; do
  [ -f "$profile" ] || continue
  grep -qF "$SHELL_HOOK_MARKER" "$profile" && continue
  {
    printf '\n%s\n' "$SHELL_HOOK_MARKER"
    # `$PWD` 는 **여기서 펴지면 안 된다.** 프로파일에 적히는 줄이고, 그 줄이
    # 읽히는 시점의 작업 디렉터리를 봐야 한다. 지금 값을 구워 넣으면 준비를
    # 돌린 자리에서만 발동한다.
    # `&&` 사슬이 아니라 `if` 다. 사슬은 마지막 조건이 거짓일 때 **0 아닌 값을
    # 남기고**, 그 값이 프로파일의 마지막 종료 상태가 되어 새 셸의 `$?` 가
    # 더럽혀진다(실측: 파일이 없으면 1, 서버가 죽어 있으면 2). `if` 는 조건이
    # 거짓이어도 0 이다.
    # shellcheck disable=SC2016
    printf 'case "$PWD/" in %q*)\n' "$REPOSITORY_ROOT/"
    printf '  if [ -f %q ]' "$DATABASE_ENVIRONMENT_FILE"
    if [ -n "$database_host" ] && [ -n "$database_port" ]; then
      printf ' \\\n     && command -v pg_isready > /dev/null 2>&1'
      printf ' \\\n     && pg_isready -q -h %q -p %q > /dev/null 2>&1' \
        "$database_host" "$database_port"
    fi
    printf '\n  then\n    . %q\n  fi ;;\nesac\n' "$DATABASE_ENVIRONMENT_FILE"
  } >> "$profile"
done

# 고른 엔진을 쓸 수 있는 상태로 만든다. 차례는 `prepare-database.sh` 한 곳에만
# 적혀 있고, 엔진을 고르는 곳(`setup.sh` · `start.sh`)이 둘 다 그것을 부른다.
bash "$REPOSITORY_ROOT/.devcontainer/prepare-database.sh"

if [ -n "${DATABASE_URL:-}" ]; then
  # 주소를 그대로 찍지 않는다. 이 스크립트는 세션 시작 훅이 부르고 그 출력은
  # 로그로 남으므로, 사람이 준 주소에 비밀번호가 있으면 그것이 로그에 박힌다.
  echo "PostgreSQL 을 씁니다: $(redact_url "$DATABASE_URL")"
else
  echo "SQLite 파일로 진행합니다."
fi

echo "준비 완료: bash .devcontainer/start.sh 를 실행하세요."
