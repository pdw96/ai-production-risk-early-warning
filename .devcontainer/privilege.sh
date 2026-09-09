#!/usr/bin/env bash
# 권한을 올리는 규칙이 적히는 **단 한 곳**.
#
# root 면 그대로 돌리고, 아니면 **비대화형** sudo 를 쓴다. 둘 다 안 되면 1 이다.
#
# `su` 는 비root 에게 비밀번호를 묻는다 — 스크립트에는 그것을 줄 사람이 없어
# `Authentication failure` 로 끝난다. 그 실패를 그대로 두면 역할 조회가 「역할이
# 없다」로 읽히고, 이어지는 생성이 `set -e` 아래에서 준비를 통째로 죽인다.
#
# **왜 파일로 뺐는가.** 같은 규칙이 `database.sh` 와 `install-postgresql.sh` 에
# 따로 적혀 있었다. 앞의 것은 스스로 「권한을 올리는 **단 한 곳**」이라고 적어
# 두었는데 실제로는 한 곳이 아니었다. 이제 잠금(`lock.sh`)도 root 가 필요해져
# 셋이 될 참이었으므로, 세 번째를 쓰는 대신 한 곳으로 모은다.
#
# **모양이 둘인 이유.** 두 부르는 쪽이 서로 다른 것을 필요로 한다.
#
#   run_as_root <낱말...>       셸을 거치지 않는다. 낱말이 그대로 명령이 된다.
#   run_as <상대> <셸 문자열>   `sh -c` 로 돈다. 안에 인용·리다이렉션이 있을 때.
#
# 뒤의 것은 **문자열을 셸이 다시 읽는다.** 그러므로 거기에 값을 끼워 넣는 쪽은
# `printf '%q'` 로 감싸야 한다 — 그 책임은 부르는 쪽에 있다.

run_as_root() {
  if [ "$(id -u)" = "0" ]; then
    "$@"
  elif command -v sudo > /dev/null 2>&1 && sudo -n true 2> /dev/null; then
    sudo -n "$@"
  else
    return 1
  fi
}

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
