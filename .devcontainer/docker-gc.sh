#!/usr/bin/env bash
# 빌드 캐시가 32GB 루프 디바이스를 다 먹는 것을 막는다.
#
# 이 Codespace에서 /, /workspaces, /var/lib/docker, /var/lib/containerd 는 모두
# 같은 32GB 루프 디바이스(/dev/loop4)를 공유한다. 이미지를 몇 번 빌드하면
# buildkit 캐시가 4GB 가까이 자라 "low disk space" 경고가 뜬다.
#
# dockerd 는 devcontainer 안에서(docker-in-docker) --config-file 없이 뜨므로
# /etc/docker/daemon.json 을 그대로 읽는다. 다만 /etc 는 컨테이너 쓰기 레이어라
# Codespace를 다시 만들면 사라진다. 그래서 postStart 에서 매번 쓴다.
#
# builder.gc 는 SIGHUP 라이브 리로드로는 반영되지 않는다(리로드 로그에 GC 가
# 빈 값으로 남는다). dockerd 기동 시에만 읽히므로, 설정이 바뀐 경우에 한해
# docker-init.sh 로 데몬을 다시 띄운다.
#
# 상한을 영구히 바꾸려면 devcontainer.json 의 containerEnv 에 있는
# DOCKER_BUILD_CACHE_MAX 를 고칠 것. 셸에서 환경변수만 주고 이 스크립트를
# 직접 돌리면 그 값은 이번 실행에만 적용되고 다음 기동 때 되돌아간다.
set -euo pipefail

CONFIG=/etc/docker/daemon.json
DOCKER_INIT=/usr/local/share/docker-init.sh
MAX_USED_SPACE=${DOCKER_BUILD_CACHE_MAX:-2GB}

# dockerd --validate 는 크기 문자열을 검사하지 않는다. maxUsedSpace 에
# "banana" 를 넣어도 "configuration OK" 를 반환하고, 정작 기동 때
# "error initializing buildkit: failed to parse maxUsedSpace" 로 데몬이
# 통째로 죽는다(실측). 그래서 값 형식을 여기서 직접 본다.
#
# 퍼센트는 쓸 수 없다. buildkitd.toml 의 [worker.oci] 에서는 "30%" 가 되지만
# daemon.json 의 builder.gc 에서는 "50%" 조차 "invalid suffix: '%'" 로 데몬이
# 죽는다(실측). 바이트 수 또는 K/M/G/T 접미사만 받는다. 2GB, 512MB, 512K,
# 2.5GB, 1gb, 1024000000 은 모두 정상 기동을 확인했다.
if ! [[ "$MAX_USED_SPACE" =~ ^[0-9]+(\.[0-9]+)?[KMGTPkmgtp]?[Bb]?$ ]]; then
  echo "DOCKER_BUILD_CACHE_MAX 값이 잘못됐다: '$MAX_USED_SPACE'" >&2
  echo "        바이트 수나 K/M/G/T 접미사를 쓸 것. 퍼센트는 지원되지 않는다." >&2
  echo "        예: 2GB, 512MB, 2.5GB, 1024000000" >&2
  exit 1
fi

wait_for_dockerd_exit() {
  # pkill 은 시그널만 보내고 종료를 기다리지 않는다. 옛 데몬이 소켓을 쥔 채로
  # 새 데몬을 띄우면 기동에 실패하고, docker info 가 죽어가는 옛 데몬에 붙어
  # 거짓 성공을 보고할 수 있다. (kill -0 은 권한이 없으면 EPERM 이라 생사
  # 판정에 못 쓴다. dockerd 는 root 소유다.)
  local i
  for i in $(seq 30); do
    pgrep -x dockerd > /dev/null || return 0
    sleep 1
  done
  return 1
}

sudo mkdir -p "$(dirname "$CONFIG")"

previous=$(sudo cat "$CONFIG" 2>/dev/null || true)

candidate=$(mktemp)
prev_file=$(mktemp)
trap 'rm -f "$candidate" "$prev_file"' EXIT
printf '%s' "$previous" > "$prev_file"

# 기존 설정이 있으면 builder.gc 만 덮어쓰고 나머지 키는 보존한다.
# 살아 있는 daemon.json 을 직접 열지 않는다. 검증에 실패하거나 중간에
# 죽으면 잘린 파일이 남아 다음 기동을 막기 때문이다.
# 기존 내용은 인자로 준 파일로 넘긴다. 힙독이 stdin 을 차지하므로
# 파이프로는 전달되지 않는다.
python3 - "$prev_file" "$MAX_USED_SPACE" > "$candidate" <<'PY'
import json, pathlib, sys

prev_path, max_used = sys.argv[1], sys.argv[2]

text = pathlib.Path(prev_path).read_text().strip()
try:
    config = json.loads(text) if text else {}
except json.JSONDecodeError as exc:
    sys.exit(
        f"기존 daemon.json 이 올바른 JSON 이 아니다: {exc}\n"
        "        손으로 고친 뒤 다시 실행할 것. 설정을 건드리지 않았다."
    )

# "builder": null 이면 setdefault 는 None 을 돌려주고 뒤이은 대입이
# TypeError 로 죽는다. dockerd 는 null 섹션을 기본값으로 받아들이므로
# 그런 설정으로도 데몬은 떠 있을 수 있다. 객체로 정규화한다.
builder = config.get("builder")
if not isinstance(builder, dict):
    builder = {}
config["builder"] = builder

builder["gc"] = {
    "enabled": True,
    # 정책을 직접 주면 전역 reservedSpace/maxUsedSpace 는 무시된다.
    # all=true 라 모든 캐시 레코드가 상한을 넘으면 회수 대상이 된다.
    "policy": [{"all": True, "reservedSpace": "256MB", "maxUsedSpace": max_used}],
}

json.dump(config, sys.stdout, indent=2)
sys.stdout.write("\n")
PY

# JSON 구조와 키 이름은 여기서 걸러진다(크기 문자열은 위에서 이미 봤다).
sudo dockerd --validate --config-file "$candidate"

if [ "$previous" = "$(cat "$candidate")" ]; then
  echo "빌드 캐시 상한이 이미 $MAX_USED_SPACE 로 설정되어 있다. 데몬을 건드리지 않는다."
  exit 0
fi

install_config() {
  # $1 의 내용으로 $CONFIG 를 원자적으로 바꾼다.
  # install/tee 는 대상 inode 를 잘라서 덮어쓰므로, 중간에 죽으면 잘린
  # daemon.json 이 남아 다음 기동을 막는다. 같은 디렉터리에 임시 파일을
  # 만들고 rename 으로 갈아끼운다.
  local src=$1 tmp
  tmp=$(sudo mktemp "$(dirname "$CONFIG")/.daemon.json.XXXXXX")
  sudo cp "$src" "$tmp"
  sudo chmod 0644 "$tmp"
  sudo mv -f "$tmp" "$CONFIG"
}

# 검증을 통과한 뒤에만 교체한다.
install_config "$candidate"

if ! pgrep -x dockerd > /dev/null; then
  echo "dockerd 가 실행 중이 아니다. 다음 기동 때 $CONFIG 가 적용된다."
  exit 0
fi

if [ ! -x "$DOCKER_INIT" ]; then
  echo "$DOCKER_INIT 이 없다. Codespace를 다시 시작하면 $CONFIG 가 적용된다."
  exit 0
fi

restore_previous() {
  echo "        이전 설정으로 되돌리고 다시 띄운다." >&2
  if [ -n "$previous" ]; then
    install_config "$prev_file"
  else
    sudo rm -f "$CONFIG"
  fi
  sudo pkill -x dockerd || true
  # 여기서도 종료를 확인하지 않으면 방금 고친 재기동 경합을 그대로 재현한다.
  if ! wait_for_dockerd_exit; then
    echo "        문제의 dockerd 가 30초 안에 종료되지 않아 복구를 중단한다." >&2
    echo "        $CONFIG 는 이전 설정으로 되돌렸다. Codespace를 재시작할 것." >&2
    return 1
  fi
  "$DOCKER_INIT" > /dev/null 2>&1 || true
  if docker info > /dev/null 2>&1; then
    echo "        복구했다. dockerd 는 이전 설정으로 돌아갔다." >&2
  else
    echo "        복구 실패. Codespace를 재시작할 것." >&2
  fi
}

echo "빌드 캐시 상한을 $MAX_USED_SPACE 로 적용하기 위해 dockerd 를 다시 띄운다."
old_pid=$(pgrep -x dockerd)
sudo pkill -x dockerd || true

if ! wait_for_dockerd_exit; then
  echo "경고: dockerd(pid $old_pid)가 30초 안에 종료되지 않았다." >&2
  echo "        상한은 $CONFIG 에 기록됐다. Codespace를 재시작하면 적용된다." >&2
  exit 1
fi

restart_log=$(mktemp)
if ! "$DOCKER_INIT" > "$restart_log" 2>&1; then
  echo "경고: $DOCKER_INIT 이 실패했다." >&2
  tail -20 "$restart_log" >&2
fi

new_pid=$(pgrep -x dockerd || true)

# 옛 데몬이 죽은 것을 확인한 뒤이므로, 응답하는 데몬은 새 설정으로 뜬 것이다.
if [ -n "$new_pid" ] && docker info > /dev/null 2>&1; then
  echo "dockerd 재기동 완료(pid $old_pid -> $new_pid). 빌드 캐시 상한: $MAX_USED_SPACE"
  rm -f "$restart_log"
else
  echo "경고: dockerd 가 새 설정으로 뜨지 않았다." >&2
  echo "        기동 로그: $restart_log, dockerd 로그: /tmp/dockerd.log" >&2
  # set -e 아래에서 restore_previous 가 1을 반환하면 그대로 빠져나가므로,
  # 복구 실패든 성공이든 아래 exit 1 로 모이게 한다.
  restore_previous || true
  exit 1
fi
