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
# `?password=...` · `?sslpassword=...` 도 **동작하는 주소**다.
#
# 그리고 그 키는 **한 가지 철자로만 오지 않는다.** URI 는 퍼센트 인코딩을
# 허용하고 SQLAlchemy 는 그것을 풀어서 넘기므로, `?pass%77ord=s3cr3t` 는
# psycopg 에 `password=s3cr3t` 로 도착하는 **동작하는 주소**다.
# 실측(2026-09-08, SQLAlchemy 2.x): `make_url("...?pass%77ord=s3cr3t")` 의
# `create_connect_args` 가 `{'password': 's3cr3t'}` 를 냈고, 그때의 가림은
# 글자가 다르다는 이유로 그 값을 그대로 통과시켰다.
#
# 그래서 **방향을 뒤집는다.** 가릴 것을 나열하지 않고, **보여도 되는 것만**
# 나열한다. 나열은 늘 한 철자 뒤에 있지만 허용 목록은 그렇지 않다 — 모르는
# 열쇠는 가려지고, 그 실패는 「로그가 덜 친절하다」이지 「비밀이 샌다」가 아니다.
# 사람이 로그에서 알아야 하는 것은 어느 엔진의 어느 데이터베이스인가뿐이고,
# 그것은 아래 목록으로 충분하다.
#
# 사용자 정보 쪽은 인코딩으로 숨을 수 없다. 실측: `://u%3Apw@` 는 비밀번호가
# 아니라 `u:pw` 라는 **사용자 이름**으로 풀린다 — 구분자인 `:` 는 인코딩되면
# 구분자이기를 그만둔다.
SAFE_QUERY_KEYS="host port dbname sslmode application_name connect_timeout"

redact_url() {
  local url="$1" base query pair key redacted=""
  case "$url" in
    *\?*)
      base="${url%%\?*}"
      query="${url#*\?}"
      ;;
    *)
      base="$url"
      query=""
      ;;
  esac
  # 사용자 이름은 **없을 수도 있다.** `postgresql+psycopg://:s3cr3t@h/db` 는
  # 동작하는 주소이고, SQLAlchemy 는 그것을 사용자 이름 `''` · 비밀번호
  # `s3cr3t` 로 읽어 psycopg 에 넘긴다(실측 2026-09-08, SQLAlchemy 2.0.52).
  # 한 글자 이상을 요구하면 바로 그 형태만 가려지지 않는다.
  #
  # 비밀번호 쪽에서 `/` 를 뺀 이유는 따로 있다. URI 에서 사용자 정보는 `/` 앞에서
  # 끝나므로 비밀번호에 날 `/` 가 올 수 없고(온다면 `%2F` 로 온다), 허용해 두면
  # `://h:5432/db?options=@x` 같은 주소에서 **포트를 비밀번호로 잘못 읽는다.**
  base="$(printf '%s' "$base" | sed -E 's#://([^:/@]*):[^@/]*@#://\1:***@#')"
  if [ -z "$query" ]; then
    printf '%s' "$base"
    return
  fi
  while IFS= read -r pair; do
    key="${pair%%=*}"
    case " $SAFE_QUERY_KEYS " in
      *" $key "*) : ;;
      *) pair="${key}=***" ;;
    esac
    redacted="${redacted:+${redacted}&}${pair}"
  done <<< "${query//&/$'\n'}"
  printf '%s?%s' "$base" "$redacted"
}

# 의존성 설치는 **여기서부터 잠근다.** 백엔드도 프론트도 「보고 나서 고치는」
# 구간이고, 준비와 세션 시작 훅이 겹치면 둘 다 고친다.
#
# 실측(2026-09-08): 아래 세 줄을 0.4초 차이로 겹쳐 돌리니 **두 번 다** 한쪽이
# 종료코드 1 로 죽었다 — `ModuleNotFoundError: No module named
# 'pip._internal.utils'` · `No module named 'pip._vendor.rich'`. 한쪽의
# `pip install --upgrade pip` 이 다른 쪽이 쓰고 있는 pip 을 갈아 끼운 것이다.
# `python -m venv` 만 겹쳤을 때는 세 번 다 무사했으므로, 무는 것은 venv 가
# 아니라 **pip** 이다.
#
# 잠금은 `lock.sh` 한 곳에 있다. 저장소마다 따로 잠근다 — 다른 체크아웃의
# 설치를 기다릴 이유가 없다.
# shellcheck source=.devcontainer/lock.sh
. "$REPOSITORY_ROOT/.devcontainer/lock.sh"

repository_key="$(printf '%s' "$REPOSITORY_ROOT" | sha256sum | cut -d' ' -f1 | cut -c1-16)"

# 실패를 **값으로 받는다.** `set -e` 아래에서 0 아닌 값이 그대로 나가면 잠글
# 자리가 없는 것만으로 준비 전체가 죽는다.
install_lock_status=0
open_production_risk_lock "install-${repository_key}" 8 || install_lock_status=$?
production_risk_lock_note "$install_lock_status"

python -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
backend/.venv/bin/python -m pip install -r backend/requirements.txt

# 잠금 파일 그대로 받는 `npm ci` 는 node_modules 를 지우고 처음부터 받는다.
# 다시 부를 수 있어야 하는 자리(세션 재개)에서 그것을 매번 하면 몇 분이 그냥
# 사라진다. 그렇다고 **디렉터리가 있는지**로 거르면 안 된다 — 세션을 재개하며
# 잠금 파일이 바뀐 리비전을 받아 와도 그 조건은 「있다」이므로 설치를 건너뛰고,
# 프론트 검사가 옛 의존성 위에서 돈다. 물어야 할 것은 **지금 깔린 것이 지금
# 잠금 파일에서 나왔는가**이므로, 잠금 파일의 해시를 남겨 두고 그것을 견준다.
#
# **이 구간도 겹쳐 돌면 서로를 밟는다.** 「해시가 다른가」를 보고 나서 고치는
# 구간이고, 준비와 세션 시작 훅이 겹치면 둘 다 「다르다」를 보고 둘 다 `npm ci`
# 로 들어간다. `npm ci` 는 그 이름대로 **node_modules 를 지우고 다시 만드는**
# 명령이라(`npm ci --help`: "Clean install a project"), 한쪽이 지우는 동안
# 다른 쪽이 쓴다.
#
# 실측(2026-09-08): 사본에서 1.5초 차이로 겹쳐 돌리니 세 번 중 **두 번** 양쪽이
# 다 실패했고 `node_modules` 가 **0개**로 남았다 —
# `npm error code ENOTEMPTY / syscall rmdir / path .../node_modules/ws/lib` 와
# `.../node_modules/esbuild` 의 설치 실패. 한쪽만 실패하는 것이 아니라 **둘 다**다.
#
FRONTEND_LOCK_HASH_FILE="frontend/node_modules/.package-lock-sha256"
frontend_lock_hash="$(sha256sum frontend/package-lock.json | cut -d' ' -f1)"

# **잠근 뒤에 다시 본다.** 앞 사람이 방금 설치를 끝냈다면 해시가 이미 맞다.
if [ "$(cat "$FRONTEND_LOCK_HASH_FILE" 2>/dev/null || true)" != "$frontend_lock_hash" ]; then
  npm --prefix frontend ci
  # `npm ci` 가 node_modules 를 지우고 다시 만드므로 **끝난 뒤에** 적는다.
  printf '%s' "$frontend_lock_hash" > "$FRONTEND_LOCK_HASH_FILE"
fi

# 여기까지가 잠글 구간이다. 준비 차례는 자기 잠금을 따로 든다.
close_production_risk_lock 8

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
  # **고르기 전에 놓는다.** `database.sh` 는 「있으면 세우고 없으면 물러난다」인데,
  # 이 저장소의 devcontainer 이미지에는 PostgreSQL 이 **없었다** — 그래서 새로 만든
  # Codespace 에서는 늘 SQLite 로 물러났고, 이 PR 이 세우려던 「개발 세션도 운영과
  # 같은 엔진」이 정작 서지 않았다. 못 놓으면 예전 그대로 SQLite 다.
  #
  # **그리고 여기 안에서만 놓는다.** 사람이 `DATABASE_URL` 을 손수 준 경우 —
  # 바깥 PostgreSQL 서비스든 명시한 SQLite 파일이든 — 아래 갈래는 그 값을 그대로
  # 지키므로, 여기서 깐 서버는 **한 번도 쓰이지 않는다.** 쓰이지도 않을 것을 위해
  # PGDG 저장소를 더하고 apt 로 서버를 앉히는 것은 남의 컨테이너에 몇 분과
  # 영구적인 시스템 변경을 남기는 일이다. 놓는 이유는 「우리가 고를 것이기
  # 때문」이고, 고르지 않을 때는 이유가 없다.
  bash "$REPOSITORY_ROOT/.devcontainer/install-postgresql.sh"

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
#
# **적는 것은 준비가 끝난 뒤다.** 이 줄이 준비보다 앞에 있으면, 기동 전 검사나
# 마이그레이션이나 시드가 실패했을 때 `set -e` 가 여기서 스크립트를 끊는데
# **파일은 이미 적혀 있다.** 그러면 다음 셸이 그 주소를 내보내고, 훅이 묻는
# 것은 접속과 권한뿐이라 「표가 없거나 반쯤 올라간 데이터베이스」는 통과한다 —
# 사람은 준비가 실패한 줄 모른 채 `no such table` 을 본다.
#
# 그래서 적는 것은 파일 맨 아래, 준비가 성공한 뒤다.
#
# **그렇다고 여기서 지우면 안 된다.** 10차에서 이 자리에 `rm -f` 를 두었는데,
# 그러면 준비가 도는 동안 파일이 **없는 구간**이 생긴다. 실측(2026-09-08):
# 준비 차례만으로 **3.4~5.3초**다. 그 사이에 열린 셸은 훅이 읽을 파일을 못 보고
# SQLite 로 시작하며, 훅은 셸이 뜰 때 한 번만 도므로 **그 셸은 수명 내내 SQLite**다.
# 짧은 구간이지만 결과가 오래간다 — 같은 시각에 한 사람의 두 창이 서로 다른
# 엔진으로 돈다.
#
# 그래서 **마지막으로 쓸 수 있던 파일을 준비가 끝날 때까지 그대로 둔다.** 그것이
# 가리키는 데이터베이스가 이미 사라졌다면 훅의 판정이 실패해 어차피 안 읽힌다 —
# 스스로 고쳐지는 쪽이다.
#
# 지우는 것은 **SQLite 로 물러날 때뿐**이다. 그때는 옛 파일이 곧 틀린 값이고,
# 지운 뒤에 열린 셸은 우리가 가려는 자리(SQLite)로 간다.
if [ "$database_url_is_ours" != "1" ] || [ -z "${DATABASE_URL:-}" ]; then
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
# 묻는 것은 **서버가 사는지가 아니라 쓸 수 있는지**다. 셋은 다른 질문이고,
# `pg_isready` 는 앞의 것에만 답한다 — 그 문서가 「올바른 사용자·비밀번호·
# 데이터베이스 값은 필요하지 않다」고 못 박는다. 실측(2026-09-08): 없는
# 데이터베이스를 향해 `pg_isready` 는 종료코드 0, 같은 자리로 붙인 `psql` 은
# `FATAL: database "..." does not exist` 로 2. 그러면 `production_risk` 가
# 지워졌거나 이 역할이 권한을 잃은 뒤에도 이 줄은 그 주소를 내보내고, 사람이
# 곧바로 치는 명령이 약속된 SQLite 대신 그 자리에서 죽는다.
#
# 그래서 `database.sh` 가 엔진을 고를 때 쓰는 **그 판정**을 그대로 부른다
# (`database-usable.sh`). 둘이 같은 질문에 다르게 답하면, 준비는 PostgreSQL 을
# 고르고 셸은 SQLite 로 도는 일이 생긴다. 실측(2026-09-08): 접속 한 번이라
# 35밀리초 — 셸이 뜨는 데 얹히지 않는다.
#
# 쓸 수 없으면 아무것도 내보내지 않고, 그러면 예전처럼 SQLite 파일로 돈다 —
# 죽은 주소를 들고 있는 것보다 낫다. 서버를 세우는 것은 여전히 `database.sh`
# 하나뿐이고, 그것을 부르는 것은 `setup.sh` 와 `start.sh` 다.
database_host="$(printf '%s' "${DATABASE_URL:-}" | sed -n 's/.*[?&]host=\([^&]*\).*/\1/p')"
database_port="$(printf '%s' "${DATABASE_URL:-}" | sed -n 's/.*[?&]port=\([^&]*\).*/\1/p')"
# 이름은 **두 자리**에 있을 수 있다. `database.sh` 는 경로에 적어 내주지만,
# psycopg 는 질의의 `dbname` 도 받고 그쪽이 경로를 이긴다.
database_name="$(printf '%s' "${DATABASE_URL:-}" | sed -n 's/.*[?&]dbname=\([^&]*\).*/\1/p')"
if [ -z "$database_name" ]; then
  database_name="$(printf '%s' "${DATABASE_URL:-}" |
    sed -n 's|^[^:]*://[^/]*/\([^?]*\).*|\1|p')"
fi

# **몸통은 프로파일이 아니라 파일에 적는다.** 예전에는 조건까지 프로파일에
# 구워 넣고 「표식이 있으면 건너뛴다」로 두 번 적히는 것을 막았는데, 표식이
# 있다는 것은 **몸통이 최신이라는 뜻이 아니다.** 실측(2026-09-08): 처음 준비가
# SQLite 로 물러나면 파싱할 값이 없어 판정 없는 줄이 적히고, 나중 준비가
# PostgreSQL 을 세워도 표식이 이미 있어 건너뛰어, 프로파일에는 끝까지
# **아무것도 확인하지 않고 `database.env` 를 읽는 줄**이 남았다.
#
# 그래서 프로파일에 적히는 줄은 **영영 바뀌지 않는 한 줄**로 두고, 엔진에 따라
# 달라지는 것은 이 파일에 적어 매번 다시 쓴다. 낡을 수 있는 자리를 없앤다.
SHELL_HOOK_FILE="$REPOSITORY_ROOT/.devcontainer/shell-hook.sh"
#
# **읽지 않는 것으로는 모자란다.** 이미 주소를 읽은 셸에서 새 셸을 열면 그 값이
# `export` 로 **물려받아진다.** 그 사이에 서버가 내려갔으면 판정은 실패하는데,
# 훅이 「읽지 않는다」로 끝나면 물려받은 죽은 주소가 그대로 남는다 — 사람은
# 약속된 SQLite 가 아니라 붙지 않는 PostgreSQL 을 향해 명령을 친다.
# 실측(2026-09-08): 부모가 읽은 뒤 판정이 실패하는 상황을 만드니 자식 셸의
# `DATABASE_URL` 이 그대로였다.
#
# 그래서 실패했을 때 **지운다.** 다만 아무것이나 지우지 않는다 — 사람이 직접
# `export DATABASE_URL` 로 고른 주소는 남겨야 한다. 「우리가 고른 것인가」의
# 정의는 `autoselected.sh` 한 곳에 있으므로 그것을 그대로 쓴다.
{
  printf '# %s 가 준비할 때마다 다시 씁니다. 손으로 고치지 마세요.\n' \
    ".devcontainer/setup.sh"
  printf 'if [ -f %q ]' "$DATABASE_ENVIRONMENT_FILE"
  if [ -n "$database_host" ] && [ -n "$database_port" ] &&
    [ -n "$database_name" ]; then
    printf ' \\\n   && bash %q %q %q %q > /dev/null 2>&1' \
      "$REPOSITORY_ROOT/.devcontainer/database-usable.sh" \
      "$database_host" "$database_port" "$database_name"
  fi
  printf '\nthen\n  . %q\n' "$DATABASE_ENVIRONMENT_FILE"
  printf 'else\n'
  printf '  . %q\n' "$REPOSITORY_ROOT/.devcontainer/autoselected.sh"
  printf '  if production_risk_url_is_inherited_ours; then\n'
  printf '    unset DATABASE_URL PRODUCTION_RISK_DATABASE_AUTOSELECTED\n'
  printf '  fi\n'
  # 남의 셸에 우리 함수를 두고 나오지 않는다.
  printf '  unset -f production_risk_url_is_inherited_ours\n'
  printf 'fi\n'
} > "${SHELL_HOOK_FILE}.$$"
# **한 순간에 갈아 끼운다.** 위의 리다이렉션은 파일을 먼저 자르고 `printf` 를
# 여러 번 부르므로, 그 사이에 뜬 셸이 **반쯤 쓰인 파일**을 읽는다 — 문법 오류가
# 나거나 엔진 판단의 절반만 돈다. 실측(2026-09-08): 쓰는 쪽과 읽는 쪽을 8초 동안
# 겹쳐 돌리니 2,895번 중 **95번**(빈 파일 46 · 반쯤 46+)이 완성되지 않은 파일을
# 봤다. 이름에 프로세스 번호를 넣는 것은 준비 둘이 겹쳐도 서로를 밟지 않게
# 하려는 것이다.
mv "${SHELL_HOOK_FILE}.$$" "$SHELL_HOOK_FILE"

SHELL_HOOK_MARKER="# ai-production-risk(${REPOSITORY_ROOT}): 개발 세션의 데이터베이스 주소"

# **프로파일도 잠근다 — 여기가 남의 파일을 고치는 유일한 자리다.**
#
# 겹쳐 돌면 둘이 같은 임시 파일을 쓰고, 한쪽이 그것을 읽는 동안 다른 쪽이
# 잘라 버린다. 그러면 사람의 셸 설정이 **영구히 사라진다.**
# 실측(2026-09-08): 30만 줄짜리 프로파일에 0.12초 차이로 겹쳐 돌리니 네 번 중
# 한 번 **9,144줄이 없어졌다**(290,856/300,000 남음). 우리 토막이 아니라
# 그 사람의 줄이다.
#
# 잠금 열쇠는 저장소가 아니라 **집**이다 — 두 체크아웃이 같은 `$HOME/.bashrc` 를
# 고치므로, 저장소마다 잠그면 서로를 못 본다.
home_key="$(printf '%s' "$HOME" | sha256sum | cut -d' ' -f1 | cut -c1-16)"
profile_lock_status=0
open_production_risk_lock "profile-${home_key}" 7 || profile_lock_status=$?
production_risk_lock_note "$profile_lock_status"

for profile in "$HOME/.bashrc" "$HOME/.zshrc"; do
  [ -f "$profile" ] || continue
  # **심볼릭 링크는 따라간다.** dotfiles 저장소를 링크로 걸어 두는 것이 흔한데,
  # 아래에서 `mv` 로 갈아 끼우면 **링크 자체가 일반 파일로 바뀐다** — 내용은
  # 남지만 그 뒤로 dotfiles 의 갱신이 이 프로파일에 닿지 않는다. 실측
  # (2026-09-08): 링크를 걸어 두고 돌리니 `lrwxrwxrwx ... -> dotfiles/bashrc` 가
  # `-rw-r--r--` 로 바뀌었고, 우리 토막은 원본과 사본 양쪽에 남았다.
  #
  # 링크가 가리키는 **그 파일**을 고친다. 사람이 링크를 건 뜻이 그것이다.
  if [ -L "$profile" ]; then
    profile="$(readlink -f "$profile")" || continue
    [ -f "$profile" ] || continue
  fi
  # **살아 있는 프로파일에는 한 번도 쓰지 않는다.** 옆에 완성한 뒤 `mv` 로 한
  # 순간에 갈아 끼운다 — 표식이 있든 없든 **같은 길**이다.
  #
  # 예전에는 표식이 있을 때만 그랬고, 첫 설치는 `>> "$profile"` 로 살아 있는
  # 파일에 곧장 붙였다. 실측(2026-09-09, strace): 그 토막은 **write 7번**으로
  # 나갔고, 그 중간 상태 8가지 중 **4가지가 `syntax error: unexpected end of
  # file`** 이었다 — `case` 는 열렸는데 `esac` 이 아직 안 온 자리다. 하필 그때
  # 셸이 이 프로파일을 읽으면 그 오류를 내고 우리 토막을 싣지 못한다.
  #
  # 창은 좁다(실측: 살아 있는 읽기 2,139회 중 0회). 그럼에도 고치는 이유는 두
  # 갈래가 **서로 다른 약속 위에 서 있던 것** 자체가 위험이기 때문이다 — 한쪽만
  # 원자적이면, 다음에 이 토막을 파일 가운데로 옮기는 사람은 그 차이를 모른다.
  scratch="${profile}.production-risk.$$"
  # `cp -p` 로 먼저 권한과 소유를 그대로 가져온다(자르기는 모드와 소유를
  # 건드리지 않는다). 그래야 `mv` 로 옮긴 뒤에도 그 집 사람의 파일 그대로다 —
  # 준비 스크립트가 정할 것이 아니다. 이름에 **이 프로세스의 번호**를 넣는 것은
  # 잠금이 서지 않는 환경에서도 둘이 같은 파일을 밟지 않게 하는 마지막 방어다.
  cp -p "$profile" "$scratch"
  # 예전 형태로 적힌 것이 남아 있을 수 있다. 표식부터 그 토막의 `esac` 까지를
  # 걷어내고 새로 적는다 — 이 줄은 이제 늘 같으므로 결과는 안정된다.
  if grep -qF "$SHELL_HOOK_MARKER" "$profile"; then
    awk -v marker="$SHELL_HOOK_MARKER" '
      $0 == "" && !dropping { blanks++; next }
      $0 == marker { dropping = 1; blanks = 0; next }
      dropping && $0 == "esac" { dropping = 0; next }
      dropping { next }
      { for (; blanks > 0; blanks--) print ""; print }
      END { for (; blanks > 0; blanks--) print "" }
    ' "$profile" > "$scratch"
  fi
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
    printf '  if [ -f %q ]; then\n    . %q\n  fi ;;\nesac\n' \
      "$SHELL_HOOK_FILE" "$SHELL_HOOK_FILE"
  } >> "$scratch"
  # **한 순간에** 갈아 끼운다. `cat` 이나 `>>` 는 쓰는 동안 파일이 반쯤인 상태가
  # 있고, 하필 그때 셸이 읽으면 그 사람의 설정이 반만 실린다.
  mv "$scratch" "$profile"
done

close_production_risk_lock 7

# 고른 엔진을 쓸 수 있는 상태로 만든다. 차례는 `prepare-database.sh` 한 곳에만
# 적혀 있고, 엔진을 고르는 곳(`setup.sh` · `start.sh`)이 둘 다 그것을 부른다.
# 실패하면 **여기서 지운다.** 준비가 끝나지 않은 주소를 들고 있는 것보다 SQLite 가
# 낫고, 그것이 이 저장소가 실패에 대해 약속한 자리다. `set -e` 에 맡기면 옛 파일이
# 남으므로 갈래를 직접 적는다 — 그리고 종료 코드는 그대로 내보낸다.
if ! bash "$REPOSITORY_ROOT/.devcontainer/prepare-database.sh"; then
  rm -f "$DATABASE_ENVIRONMENT_FILE"
  exit 1
fi

# **이제 알린다.** 여기까지 왔다는 것은 표가 서 있고 기준정보가 들어 있다는 뜻이다.
#
# 값은 `printf %q` 로 적는다 — 주소에 작은따옴표가 들어갈 수 있고(URI 사용자
# 정보에 허용된다), 따옴표 사이에 그대로 끼워 넣으면 그 줄이 다른 뜻이 되거나
# 아예 읽히지 않는다.
#
# **우리가 고른 주소만 적는다.** 사람이 준 주소에는 비밀번호가 들어 있을 수 있고,
# 그것을 파일로 옮기면 저장소 곁에 평문 자격증명이 하나 생긴다 — 그 사람의 셸에는
# 이미 그 값이 있으므로 옮겨 적을 이유도 없다. 우리가 고르는 주소는 유닉스 소켓
# + peer 인증이라 비밀번호가 아예 없다.
#
# 그럼에도 파일 권한을 좁힌다. 여러 사람이 쓰는 개발 호스트에서 기본 umask 는
# 흔히 022 라 남이 읽을 수 있다.
#
# **갈아 끼우는 것은 한 순간이어야 한다.** 곧바로 `>` 로 쓰면 그 파일이 비어 있는
# 찰나가 있고, 하필 그때 셸이 읽으면 주소 없이 시작한다. 옆에 다 쓴 뒤 `mv` 로
# 옮긴다 — 같은 디렉터리라 이름 바꾸기 하나로 끝난다.
#
# **옆에 두는 이름에는 이 프로세스의 번호를 넣는다.** 이 자리는 잠금 밖이다 —
# 설치 잠금은 위에서 이미 놓았고 준비 잠금은 `prepare-database.sh` 안에서 끝났다.
# 겹쳐 돌면 둘이 **같은 임시 이름**을 쓰고, 한쪽이 그것을 `mv` 로 옮긴 뒤에도
# 다른 쪽은 그 파일을 **연 채로** 남아 이어지는 write 가 옮겨진 목적지로 새어
# 들어간다. 실측(2026-09-09, 0.02초 어긋나게 40회): 40회 모두
# `mv: cannot stat ...: No such file or directory` 로 죽었고, 40회 모두 발행된
# 파일이 `DATABASE_URL` 은 이쪽 주소, 표식은 저쪽 주소인 **섞인 상태**로 남았다 —
# 표식이 자기가 표시하는 값과 어긋나는 것은 `autoselected.sh` 가 딛고 선 바로 그
# 약속이 깨지는 것이다. 셸 훅 파일은 이미 `.$$` 로 옮기고 있었다.
if [ "$database_url_is_ours" = "1" ] && [ -n "${DATABASE_URL:-}" ]; then
  (
    umask 077
    {
      printf 'export DATABASE_URL=%q\n' "$DATABASE_URL"
      # 표식은 `1` 이 아니라 **자기가 표시하는 그 값**을 들고 다닌다.
      printf 'export PRODUCTION_RISK_DATABASE_AUTOSELECTED=%q\n' "$DATABASE_URL"
    } > "${DATABASE_ENVIRONMENT_FILE}.$$"
  )
  mv "${DATABASE_ENVIRONMENT_FILE}.$$" "$DATABASE_ENVIRONMENT_FILE"
fi

if [ -n "${DATABASE_URL:-}" ]; then
  # 주소를 그대로 찍지 않는다. 이 스크립트는 세션 시작 훅이 부르고 그 출력은
  # 로그로 남으므로, 사람이 준 주소에 비밀번호가 있으면 그것이 로그에 박힌다.
  echo "PostgreSQL 을 씁니다: $(redact_url "$DATABASE_URL")"
else
  echo "SQLite 파일로 진행합니다."
fi

echo "준비 완료: bash .devcontainer/start.sh 를 실행하세요."
