#!/usr/bin/env bash
# 프로세스 사이의 잠금이 사는 **단 한 곳**.
#
# 준비(`setup.sh`)와 세션 시작 훅과 기동(`start.sh`)은 겹쳐 돌 수 있다. 그때
# 「보고 나서 고치는」 구간은 둘 다 「아직 아니다」를 보고 둘 다 고친다. 실측으로
# 그 자리가 둘 나왔다 — 데이터베이스 준비 차례(마이그레이션·시드)와 의존성 설치.
#
# 잠금 파일은 **그 사람의 자리**에 둔다. 여럿이 쓰는 호스트에서 공용 자리에 두면
# 남이 만든 파일에 막혀 열지 못하고, 그 실패가 준비를 끊는다.
#
# **무한정 기다리지 않는다.** 앞 사람이 멈춰 있으면 세션이 영영 뜨지 않는다.
# 구간이 몇 초에서 몇 분짜리이므로 5분은 넉넉하고, 넘겼다면 기다려서 될 일이
# 아니다 — 답할 사람이 없는 자리에서 매달리지 않는다는 이 저장소의 판단 그대로다.

PRODUCTION_RISK_LOCK_TIMEOUT=300

# 대기 초과를 나타내는 값. `flock` 의 다른 실패와 **구분되어야** 한다 —
# 둘을 뭉뚱그리면 「앞 사람이 오래 걸린다」와 「이 환경에 잠금이 안 선다」가
# 같은 문장으로 나오고, 사람이 무엇을 고쳐야 하는지 알 수 없다.
PRODUCTION_RISK_LOCK_BUSY=77

# open_production_risk_lock <열쇠> <파일서술자> [범위]
#   0 잠갔다 · 1 잠글 자리가 없다 · 2 기다리다 지쳤다 · 3 잠금 자체가 실패했다
#
# 파일서술자는 부르는 쪽이 정한다 — 한 프로세스가 잠금을 둘 들 수 있어야 하고,
# 그러려면 서로 다른 번호를 써야 한다.
#
# **범위가 둘인 이유.** 기본값 `user` 는 잠금 파일을 그 사람의 캐시에 둔다. 의존성
# 설치(`backend/.venv` · `frontend/node_modules`)와 프로파일 고쳐 쓰기는 그 사람의
# 것만 건드리므로 그것이 맞다 — 남의 설치를 기다릴 이유가 없다.
#
# 그런데 **PostgreSQL 을 놓고 고르는 일은 호스트 전체를 건드린다** — apt 저장소와
# 키링, 꾸러미 데이터베이스, 클러스터와 그 안의 역할. 그것을 사람마다 다른 파일로
# 잠그면 잠근 것이 아니다. 한 호스트를 두 사람이 쓰면 둘 다 자기 집에 있는 자기
# 파일을 잠그고 나란히 apt 를 돌린다. 그러면 진 쪽의 설치는 「놓기 실패」로
# 삼켜져(그 파일은 실패해도 0 으로 끝나기로 되어 있다) SQLite 를 고르고, 이긴
# 쪽은 PostgreSQL 을 고른다 — 같은 호스트의 두 세션이 다른 엔진 위에서 돈다.
#
# 그래서 `host` 범위는 **모두가 같은 파일**을 보게 한다. 자리는
# `/run/lock/production-risk` — FHS 가 잠금 파일에 정해 둔 곳 아래다.
#
# **누구나 쓸 수 있는 디렉터리에 두면 안 된다.** `/run/lock` 자체는
# `drwxrwxrwt` 라 아무나 파일을 만들 수 있는데, 그러면 이름이 뻔한 잠금 파일
# 자리에 남이 **심볼릭 링크를 미리 걸어 둘 수 있다.** 실측(2026-09-09, 이
# 컨테이너는 `fs.protected_symlinks = 0`): 다른 사용자가 그 이름으로
# `/etc/shadow` 를 가리키는 링크를 걸었고, root 로 그 이름에 append 하니 **그대로
# 따라갔다.** 사람끼리 잠금이 갈라지는 것을 고치려다 root 가 남이 고른 파일을
# 여는 길을 내는 셈이 된다 — 병보다 약이 나쁘다.
#
# 그래서 **디렉터리는 0755 로 두고 파일만 0666 으로** 만든다. 디렉터리에 쓸 수
# 있는 것은 그것을 만든 쪽(놓기를 할 수 있는, 즉 root 인 쪽)뿐이라 링크를 심을
# 자리가 없고, 파일은 이미 있으므로 다른 사용자도 열어서 겨룰 수 있다.
#
# 처음 만드는 것이 root 가 아니면 여기서 1 이 나가고 부르는 쪽은 「잠글 자리가
# 없다」로 다룬다. 그것으로 충분하다 — 이 잠금이 지키는 일(apt · 클러스터)은
# 어차피 root 여야 할 수 있다.
open_production_risk_lock() {
  local key="$1" descriptor="$2" scope="${3:-user}" directory candidate status
  command -v flock > /dev/null 2>&1 || return 1
  if [ "$scope" = "host" ]; then
    for directory in /run/lock /var/lock /tmp; do
      [ -d "$directory" ] || continue
      directory="$directory/production-risk"
      # 링크를 따라가지 않는다 — 위의 설명이 그 이유다.
      if [ -L "$directory" ]; then
        directory=""
        continue
      fi
      [ -d "$directory" ] || mkdir -m 0755 "$directory" 2> /dev/null || directory=""
      [ -n "$directory" ] && break
    done
    [ -n "$directory" ] || return 1
    candidate="$directory/${key}.lock"
    # 파일은 **모두가 열 수 있어야** 겨룰 수 있다. 디렉터리가 0755 라 이 자리에
    # 링크를 심을 수 있는 것은 그것을 만든 쪽뿐이다.
    [ -e "$candidate" ] || (umask 0000 && : > "$candidate") 2> /dev/null || return 1
  else
    directory="${XDG_CACHE_HOME:-$HOME/.cache}/production-risk"
    mkdir -p "$directory" 2> /dev/null || return 1
    candidate="$directory/${key}.lock"
  fi
  # 이미 있는 파일은 **자르지 않는다.** 남이 잠금을 쥔 채로 있을 수 있고, 자를
  # 이유도 없다 — 이 파일의 내용은 아무도 읽지 않는다.
  [ -e "$candidate" ] || : > "$candidate" 2> /dev/null || return 1
  # 번호는 부르는 쪽이 글자로 적은 값이라 `eval` 이 밖에서 오는 값을 받지 않는다.
  eval "exec ${descriptor}>> \"\$candidate\"" 2> /dev/null || return 1
  status=0
  flock -w "$PRODUCTION_RISK_LOCK_TIMEOUT" -E "$PRODUCTION_RISK_LOCK_BUSY" \
    "$descriptor" 2> /dev/null || status=$?
  case "$status" in
    0) return 0 ;;
    "$PRODUCTION_RISK_LOCK_BUSY") return 2 ;;
    *) return 3 ;;
  esac
}

close_production_risk_lock() {
  eval "exec ${1}>&-" 2> /dev/null || true
}

# 잠금 상태를 값으로 받아 **「그대로 들어가도 되는가」**에 답한다. 0 이면 된다.
# 부르는 쪽은 `production_risk_lock_permits "$s" "무엇" || exit 1` 로 쓴다.
#
#   production_risk_lock_permits <상태> <지키려는 것>
#
# **셋을 같게 다루면 안 된다.** 예전에는 셋 다 「그대로 진행합니다」였는데, 그
# 셋은 서로 다른 사실이다.
#
#   1  잠글 자리가 없다   — `flock` 이 없거나 캐시 디렉터리를 못 쓴다.
#                          겹쳐 돈다는 **증거가 아니다.** 여기서 멈추면 그런
#                          환경에서는 준비를 영영 못 한다. 알리고 나아간다.
#   3  잠그지 못했다      — 다른 이유로 `flock` 이 실패했다. 위와 같다.
#   2  다른 실행이 쥐고 있다 — ${PRODUCTION_RISK_LOCK_TIMEOUT}초를 기다렸는데도
#                          놓지 않았다. 이것만은 **겹쳐 돈다는 증거 그 자체**다.
#                          그런데도 들어가면, 잠금이 막으려던 바로 그 상황에서만
#                          잠금이 없는 채로 들어가는 셈이 된다.
#
# 2에서 멈추는 것이 왜 옳은가. 이 잠금들이 지키는 것은 되돌릴 수 없는 것들이다 —
# `npm ci` 는 `node_modules` 를 **지우고** 다시 만들고(실측 2026-09-08: 겹쳐 돌린
# 세 번 중 두 번 양쪽이 다 실패하고 0개로 남았다), 프로파일 다시 쓰기는 남의
# `.bashrc` 를 갈아 끼운다(실측: 30만 줄 중 9,144줄이 사라졌다). 늦게 끝나는 것과
# 망가지는 것 중에는 늦게 끝나는 쪽이 낫다.
production_risk_lock_permits() {
  case "$1" in
    0) return 0 ;;
    2)
      echo "다른 실행이 ${2}을(를) 아직 쥐고 있습니다(${PRODUCTION_RISK_LOCK_TIMEOUT}초 기다림)." >&2
      echo "겹쳐 돌면 서로를 밟으므로 여기서 멈춥니다 — 그쪽이 끝난 뒤 다시 실행하십시오." >&2
      return 1
      ;;
    1) echo "잠금을 걸 자리가 없어 ${2}을(를) 그대로 진행합니다." >&2; return 0 ;;
    *) echo "잠금을 걸지 못해 ${2}을(를) 그대로 진행합니다." >&2; return 0 ;;
  esac
}
