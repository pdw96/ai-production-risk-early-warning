#!/usr/bin/env bash
# 빌드 캐시가 32GB 루프 디바이스를 다 먹는 것을 막는다.
#
# 이 Codespace에서 /, /workspaces, /var/lib/docker, /var/lib/containerd 는 모두
# 같은 32GB 루프 디바이스(/dev/loop4)를 공유한다. 이미지를 몇 번 빌드하면
# buildkit 캐시가 4GB 가까이 자라 "low disk space" 경고가 뜬다.
#
# dockerd 는 devcontainer 안에서(docker-in-docker) --config-file 없이 뜨므로
# /etc/docker/daemon.json 을 그대로 읽는다. 다만 /etc 는 컨테이너 쓰기 레이어라
# Codespace를 다시 만들면 사라진다. 그래서 postCreate/postStart 에서 매번 쓴다.
#
# builder.gc 는 SIGHUP 라이브 리로드로는 반영되지 않는다(리로드 로그에 GC 가
# 빈 값으로 남는다). dockerd 기동 시에만 읽히므로, 설정이 바뀐 경우에 한해
# docker-init.sh 로 데몬을 다시 띄운다.
set -euo pipefail

CONFIG=/etc/docker/daemon.json
DOCKER_INIT=/usr/local/share/docker-init.sh
MAX_USED_SPACE=${DOCKER_BUILD_CACHE_MAX:-2GB}

sudo mkdir -p "$(dirname "$CONFIG")"

before=$(sudo cat "$CONFIG" 2>/dev/null || true)

# 기존 설정이 있으면 builder.gc 만 덮어쓰고 나머지 키는 보존한다.
sudo python3 - "$CONFIG" "$MAX_USED_SPACE" <<'PY'
import json, os, sys

path, max_used = sys.argv[1], sys.argv[2]

config = {}
if os.path.exists(path):
    with open(path) as f:
        text = f.read().strip()
    if text:
        config = json.loads(text)

config.setdefault("builder", {})["gc"] = {
    "enabled": True,
    # 정책을 직접 주면 전역 reservedSpace/maxUsedSpace 는 무시된다.
    # all=true 라 모든 캐시 레코드가 상한을 넘으면 회수 대상이 된다.
    "policy": [{"all": True, "reservedSpace": "256MB", "maxUsedSpace": max_used}],
}

with open(path, "w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")
PY

sudo dockerd --validate --config-file "$CONFIG"

after=$(sudo cat "$CONFIG")

if [ "$before" = "$after" ]; then
  echo "빌드 캐시 상한이 이미 $MAX_USED_SPACE 로 설정되어 있다. 데몬을 건드리지 않는다."
  exit 0
fi

if ! pgrep -x dockerd > /dev/null; then
  echo "dockerd 가 실행 중이 아니다. 다음 기동 때 $CONFIG 가 적용된다."
  exit 0
fi

if [ ! -x "$DOCKER_INIT" ]; then
  echo "$DOCKER_INIT 이 없다. Codespace를 다시 시작하면 $CONFIG 가 적용된다."
  exit 0
fi

echo "빌드 캐시 상한을 $MAX_USED_SPACE 로 적용하기 위해 dockerd 를 다시 띄운다."
old_pid=$(pgrep -x dockerd)
sudo pkill -x dockerd || true

# pkill 은 시그널만 보내고 종료를 기다리지 않는다. 옛 데몬이 소켓을 쥔 채로
# 새 데몬을 띄우면 기동에 실패하고, 그 실패가 묻힌 채 docker info 가
# 죽어가는 옛 데몬에 붙어 거짓 성공을 보고할 수 있다. 완전히 죽을 때까지
# 기다린다. (kill -0 은 권한이 없으면 EPERM 이라 생사 판정에 못 쓴다.)
for _ in $(seq 30); do
  pgrep -x dockerd > /dev/null || break
  sleep 1
done

if pgrep -x dockerd > /dev/null; then
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

# 옛 데몬은 이미 죽은 것을 확인했으므로, 응답하는 데몬은 새 설정으로 뜬 것이다.
if [ -n "$new_pid" ] && docker info > /dev/null 2>&1; then
  echo "dockerd 재기동 완료(pid $old_pid -> $new_pid). 빌드 캐시 상한: $MAX_USED_SPACE"
  rm -f "$restart_log"
else
  echo "경고: dockerd 가 다시 뜨지 않았다. Codespace를 재시작할 것." >&2
  echo "        기동 로그: $restart_log, dockerd 로그: /tmp/dockerd.log" >&2
  exit 1
fi
