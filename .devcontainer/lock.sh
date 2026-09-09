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

# 권한을 올리는 규칙은 `privilege.sh` 한 곳에 있다 — 호스트 공용 잠금 자리를
# **root 로** 만들어야 하기 때문이다(아래). 자리를 찾는 데 바깥 명령을 쓰지
# 않는다: 좁은 PATH 에서 `dirname` 이 없으면 소스가 실패한다.
# shellcheck source=.devcontainer/privilege.sh
. "${BASH_SOURCE[0]%/*}/privilege.sh" 2> /dev/null || true

PRODUCTION_RISK_LOCK_TIMEOUT=300

# 호스트 범위는 **더 오래 기다린다.** 그것이 지키는 구간은 의존성 설치가 아니라
# 꾸러미 놓기다 — `install-postgresql.sh` 스스로 「처음 한 번, 몇 분 걸립니다」라고
# 적는다. 5분을 그 구간에 걸어 두면, 앞사람의 놓기가 **정상으로 잘 되고 있는
# 중에** 뒷사람이 시간 초과로 끝나고, 시간 초과는 `exit 1` 이라 세션 준비가
# 통째로 실패한다. 아무것도 고장나지 않았는데 나는 실패다.
#
# 그래서 지키는 것의 크기에 맞춘다. 여전히 무한정은 아니다 — 20분을 넘겼다면
# 기다려서 될 일이 아니라는 판단은 그대로다.
PRODUCTION_RISK_HOST_LOCK_TIMEOUT=1200

# 대기 초과를 나타내는 값. `flock` 의 다른 실패와 **구분되어야** 한다 —
# 둘을 뭉뚱그리면 「앞 사람이 오래 걸린다」와 「이 환경에 잠금이 안 선다」가
# 같은 문장으로 나오고, 사람이 무엇을 고쳐야 하는지 알 수 없다.
PRODUCTION_RISK_LOCK_BUSY=77

# 호스트 공용 잠금을 둘 자리인지 묻는다. 믿을 만하면 0.
#
#   - 링크가 아니어야 한다(매달린 링크도 링크다).
#   - 소유자가 root 이거나 우리여야 한다 — 남의 것이면 그 안은 남이 정한다.
#   - 누구나 쓸 수 있으면 안 된다 — 그러면 지금도 링크를 심을 수 있다.
#
# 없으면 0755 로 만들어 본다. 못 만들면 그 자리는 못 쓰는 것이다.
production_risk_directory_is_trusted() {
  local directory="$1" owner mode
  [ -L "$directory" ] && return 1
  if [ ! -d "$directory" ]; then
    # **root 로 만든다.** 우리 손으로 만들면 그 디렉터리는 우리 것이 되고, 다음
    # 사람은 아래 소유자 검사에서 「남의 것」이라 물러나 **다른 자리**를 잡는다.
    # 그러면 둘 다 잠갔다고 믿으면서 서로 다른 파일을 잠근다 — 호스트 범위가
    # 이름만 호스트 범위다.
    run_as_root install -d -m 0755 -o root -g root "$directory" 2> /dev/null \
      || return 1
  fi
  command -v stat > /dev/null 2>&1 || return 1
  owner="$(stat -c %u "$directory" 2> /dev/null)" || return 1
  [ "$owner" = "0" ] || [ "$owner" = "$(id -u)" ] || return 1
  mode="$(stat -c %a "$directory" 2> /dev/null)" || return 1
  case "$mode" in
    *[2367]) return 1 ;;
  esac
  return 0
}

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
# 있는 것은 그것을 만든 쪽뿐이라 링크를 심을 자리가 없고, 파일은 이미 있으므로
# 다른 사용자도 열어서 겨룰 수 있다.
#
# **그런데 「디렉터리를 만든 쪽」이 우리라는 보장이 없다.** 공격자가 먼저 만들어
# 두면 그 안은 그 사람의 것이다. 실측(2026-09-09): 다른 사용자가
# `/run/lock/production-risk` 를 자기 것으로 만들고 그 안에 **매달린 링크**
# `provision.lock -> /tmp/attack-target` 을 심으니, `[ -e ]` 는 거짓이고(링크가
# 가리키는 것이 없으므로) 이어지는 `: >` 가 `umask 0000` 아래에서 그것을 따라가
# **`-rw-rw-rw- root root /tmp/attack-target`** 을 만들었다. 잠금을 고치려다 root
# 가 남이 고른 경로에 세계쓰기 파일을 만드는 길을 낸 셈이다.
#
# 그래서 셋을 함께 건다.
#
#   1. 디렉터리의 **소유자**가 root 이거나 우리여야 한다. 남의 것이면 믿지 않는다.
#   2. 디렉터리가 **누구나 쓸 수 있으면** 안 된다 — 그러면 지금도 링크를 심는다.
#   3. 파일은 `set -C`(noclobber)로 만든다. 그것은 `O_CREAT|O_EXCL` 이라
#      **경로가 링크이면 매달렸든 아니든 그 자리에서 실패한다.** 그리고 열기
#      직전에 링크인지 한 번 더 본다.
#
# **그리고 디렉터리는 root 가 만들어야 한다.** 위의 1번은 「남의 것이면 물러난다」
# 인데, 물러나서 **다른 자리를 잡으면** 잠금이 갈라진다. 앞사람이 root 가 아닌
# 보통 사용자면 `/run/lock/production-risk` 는 그 사람 것이 되고, 뒷사람은 1번에
# 걸려 다음 후보로 내려간다. 실측(2026-09-09, 실제 OS 계정 `devA`·`devB` 로):
#
#   devA  status=0   /run/lock/production-risk  (devA 소유)
#   devB  status=0   /tmp/production-risk       (devB 소유)
#
# **둘 다 0 이다** — 둘 다 잠갔다고 믿는데 서로 다른 파일을 잠갔다. 경고도 없다.
# 사람마다 갈라지는 것을 고치려고 만든 범위가 이름만 호스트 범위였다.
#
# 그래서 자리를 만드는 것은 `run_as_root` 다. 그러면 소유자가 늘 root 라 모두가
# 1번을 통과하고 **같은 파일**을 본다. 파일은 root 가 0666 으로 만들어 두므로
# 권한 없는 사용자도 열어서 겨룰 수 있다.
#
# 후보에서 **`/tmp` 를 뺐다.** 거기는 `/run/lock` 이 없는 환경을 위한 마지막
# 자리였는데, 위의 갈라짐이 실제로 나온 자리가 바로 거기다. 앞의 둘이 모두
# 막히면 잠그지 않는 편이 낫다 — 그때는 1 이 나가고 부르는 쪽이 그것을 소리 내어
# 말한다.
#
# 다 막히면 1 이 나가고 부르는 쪽은 「잠글 자리가 없다」로 다룬다 — 잠그지
# 못하는 것이지 남의 파일을 여는 것이 아니다.
open_production_risk_lock() {
  # `directory` 를 **비워서 시작한다.** 아래 반복은 `[ -d "$base" ]` 가 모두
  # 거짓이면 한 번도 대입하지 않는다(둘 다 없는 최소 컨테이너). 그때
  # `[ -n "$directory" ]` 는 `set -u` 아래에서 **셸을 죽인다** — 명령 실패가
  # 아니라 셸 오류라 `|| status=$?` 가 잡지 못한다. 실측(2026-09-09):
  # `directory: unbound variable` 뒤의 줄은 아예 돌지 않았고 종료코드는 1 이었다.
  # 이 파일이 약속한 것은 「잠글 자리가 없으면 1 을 돌려준다」이지 죽는 것이 아니다.
  local key="$1" descriptor="$2" scope="${3:-user}" base directory="" candidate status
  command -v flock > /dev/null 2>&1 || return 1
  candidate=""
  if [ "$scope" = "host" ]; then
    for base in /run/lock /var/lock; do
      [ -d "$base" ] || continue
      directory="$base/production-risk"
      production_risk_directory_is_trusted "$directory" || { directory=""; continue; }
      break
    done
    if [ -n "$directory" ]; then
      candidate="$directory/${key}.lock"
      # 파일은 **모두가 열 수 있어야** 겨룰 수 있다. `set -C` 는 `O_CREAT|O_EXCL`
      # 이라 이 이름이 링크이면 매달렸든 아니든 그 자리에서 실패한다.
      if [ ! -e "$candidate" ] && [ ! -L "$candidate" ]; then
        # 디렉터리가 root 것이고 우리가 root 가 아니면 여기에 못 만든다. 그때는
        # root 에게 만들게 한다 — 파일은 0666 이어야 누구든 열어서 겨룰 수 있다.
        # SC2016 은 여기서 맞다 — `$1` 은 **안쪽 `sh`** 가 펴야 한다. 우리가 펴서
        # 넣으면 경로가 그 셸의 문법을 다시 지나간다.
        # shellcheck disable=SC2016
        (set -C; umask 0000; : > "$candidate") 2> /dev/null \
          || run_as_root sh -c 'set -C; umask 0000; : > "$1"' sh "$candidate" \
               2> /dev/null || true
      fi
      # 열기 직전에 다시 본다 — 만들지 않고 지나온 길도 있다.
      if [ -L "$candidate" ] || [ ! -f "$candidate" ]; then
        candidate=""
      fi
    fi
    # **공용 자리를 못 세웠으면 우리 자리로 물러난다.** 여기서 그냥 1 을 내면
    # sudo 가 없는 1인 컨테이너는 잠금을 통째로 잃는다 — 사람끼리 갈라지는 것을
    # 고치려다 **한 사람의 준비와 훅이 겹치는 것**까지 못 막게 된다. 그것이 이
    # 파일이 애초에 세워진 이유다.
    #
    # 물러나는 자리는 남이 만든 자리가 아니라 **우리 캐시**다. 공용처럼 보이는
    # 자리에 우리 것을 만들어 두 사람이 서로 다른 파일을 잠그는 것 — 그것이 이
    # 회차에 고치는 결함이므로, 그 모양으로는 물러나지 않는다.
    [ -n "$candidate" ] || scope="user"
  fi
  if [ -z "$candidate" ]; then
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
  # `[ ... ] && var=...` 로 적지 않는다. 지금은 뒤에 명령이 더 있어 `set -e` 가
  # 물지 않지만(실측), 그것은 **문장 순서에 기댄 안전**이다.
  local wait_seconds="$PRODUCTION_RISK_LOCK_TIMEOUT"
  if [ "$scope" = "host" ]; then
    wait_seconds="$PRODUCTION_RISK_HOST_LOCK_TIMEOUT"
  fi
  flock -w "$wait_seconds" -E "$PRODUCTION_RISK_LOCK_BUSY" \
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
