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

# open_production_risk_lock <열쇠> <파일서술자>
#   0 잠갔다 · 1 잠글 자리가 없다 · 2 기다리다 지쳤다 · 3 잠금 자체가 실패했다
#
# 파일서술자는 부르는 쪽이 정한다 — 한 프로세스가 잠금을 둘 들 수 있어야 하고,
# 그러려면 서로 다른 번호를 써야 한다.
open_production_risk_lock() {
  local key="$1" descriptor="$2" directory candidate status
  directory="${XDG_CACHE_HOME:-$HOME/.cache}/production-risk"
  command -v flock > /dev/null 2>&1 || return 1
  mkdir -p "$directory" 2> /dev/null || return 1
  candidate="$directory/${key}.lock"
  : > "$candidate" 2> /dev/null || return 1
  # 번호는 부르는 쪽이 글자로 적은 값이라 `eval` 이 밖에서 오는 값을 받지 않는다.
  eval "exec ${descriptor}> \"\$candidate\"" 2> /dev/null || return 1
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

# 잠금을 못 얻었을 때 무엇을 할지는 부르는 쪽이 같은 말로 적게 한다.
production_risk_lock_note() {
  case "$1" in
    1) echo "잠금을 걸 자리가 없어 그대로 진행합니다." >&2 ;;
    2) echo "다른 실행이 ${PRODUCTION_RISK_LOCK_TIMEOUT}초 넘게 끝나지 않아 기다리지 않고 진행합니다." >&2 ;;
    3) echo "잠금을 걸지 못해 그대로 진행합니다." >&2 ;;
  esac
}
