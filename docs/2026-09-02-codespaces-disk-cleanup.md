# Codespaces 디스크 부족(low disk space <10%) 조치 핸드오프 (2026-09-02)

이 문서는 새 세션에 그대로 붙여넣어 작업을 이어가기 위한 프롬프트입니다.
"현황" 절의 수치는 2026-09-02에 이 Codespace 안에서 `df`, `du`, `docker system df`를
실제로 실행해 얻은 실측값입니다. 추정한 부분은 "추정"이라고 명시했습니다.

---

이 Codespace에서 "low disk space (<10%)" 경고가 계속 뜬다. 아래 분석은 이미
실측으로 끝났으니 다시 조사하지 말고, **정리 실행부터 시작해 줘.**

## 현황 (2026-09-02 실측)

```
Filesystem      Size  Used Avail Use% Mounted on
overlay          32G   27G  3.3G  89% /
/dev/loop4       32G   27G  3.3G  89% /workspaces
/dev/root        29G   16G   14G  55% /vscode
/dev/sda1       118G  3.3G  109G   3% /tmp
```

### 핵심 구조 (이걸 모르면 엉뚱한 걸 지운다)

`/`(overlay), `/workspaces`, `/var/lib/docker`, `/var/lib/containerd`가 **전부
같은 32GB 루프 디바이스(`/dev/loop4` = `/mnt/cloudenvdata/dockerlib`)를 공유**한다.
즉 32GB 하나에 컨테이너 이미지 레이어 + 홈 디렉터리 + 안쪽 Docker 데이터가 다 들어간다.

27GB 사용량의 내역:

| 위치 | 크기 | 성격 |
|---|---|---|
| `/usr` (그중 `/usr/local` 4.2G) | 7.3G | **베이스 이미지 lower 레이어** |
| `/var/lib/containerd` | 3.9G | 안쪽 Docker의 이미지 + 빌드 캐시 |
| `/home/codespace` | 2.6G | 쓰기 레이어 |
| `/opt` (대부분 conda 1.2G) | 1.3G | **베이스 이미지 lower 레이어** |
| `/workspaces/...` (저장소) | 1.4M | 무시해도 됨 |

### ⚠️ 함정 ① `/usr/local`, `/opt`는 지워도 공간이 안 늘고 오히려 준다

`/usr/local/sdkman`(912M), `/usr/local/python`(827M), `/usr/local/rubies`(313M),
`/usr/local/go`(282M), `/usr/local/php`(173M), `/opt/conda`(1.2G) — 안 쓰는 런타임이
잔뜩 있어서 지우고 싶어지지만, 이건 전부 overlay의 **lower(이미지) 레이어**다.
컨테이너 안에서 `rm` 하면 upper 레이어에 whiteout 파일만 생기고 lower 레이어는
그대로 남는다. **사용량이 줄지 않고 미세하게 늘어난다.** 절대 건드리지 말 것.

줄일 수 있는 건 **런타임에 생성된 것들**뿐이다: `/var/lib/containerd`,
`/home/codespace` 아래 캐시류.

### ⚠️ 함정 ② `/var/lib/docker`를 재봐야 소용없다

`docker info`는 Docker Root Dir을 `/var/lib/docker`라고 보고하지만 실제 측정하면
5.7MB뿐이다. Docker 29.x는 containerd 스냅샷터를 쓰기 때문에 실체는
`/var/lib/containerd`(3.9G)에 있다. 용량 확인은 `docker system df`로 할 것.

### 왜 지금 터졌나

지난 세션(커밋 `b928eaf`, `855994e`)에서 Docker 지원을 추가하면서 4개 이미지를
빌드했다. `docker system df` 기준:

```
Images        5   790.2MB
Build Cache  41   3.895GB   (Reclaimable 3.895GB, Private 3.107GB)
```

**빌드 캐시 3.9GB가 단일 최대 원인**이고, 이건 100% 회수 가능하다.

## 해야 할 일

### 1단계 — 즉시 회수 (약 4.5~5GB, 되돌릴 수 있는 것만)

아래를 순서대로 실행하고 각 단계 후 `df -h /` 로 변화를 기록해 줘.

```bash
# (a) Docker 빌드 캐시 — 최대 회수분 ~3.9GB
docker builder prune -af

# (b) 멈춰 있는 컨테이너 2개 + 미사용 이미지
#     ai-production-risk-{frontend,backend}-1 은 Exited(255) 상태이고
#     ai-production-risk-codespaces-* 이미지는 중복이다
docker container prune -f
docker image prune -af

# (c) 재생성 가능한 사용자 캐시 (~800MB)
rm -rf ~/.cache/copilot/pkg      # 356M
rm -rf ~/.codex/.tmp             # 98M
npm cache clean --force          # ~147M

# (d) 구버전 Claude Code 바이너리 — 현재 버전은 2.1.258이므로 2.1.252만 제거
rm -rf ~/.local/share/claude/versions/2.1.252   # 205M
```

`(d)` 실행 전에 `~/.local/share/claude/versions/` 목록을 다시 확인해서 **현재
실행 중인 버전은 절대 지우지 말 것.** (2026-09-02 시점엔 2.1.258과 2.1.252 두 개였다.)

### 2단계 — VS Code 확장 정리 (~215MB, 선택)

`~/.vscode-remote/extensions/`에 `anthropic.claude-code`가 2.1.258과 2.1.252
두 버전 공존한다(각 ~215M). 구버전은 VS Code 재시작 시 정리되는 게 정상이나
남아 있다면 수동 삭제 가능. `openai.chatgpt`(578M)도 안 쓴다면 확장 UI에서
제거하는 게 안전하다 — 디렉터리 직접 삭제보다 확장 관리자를 쓸 것.

### 3단계 — 재발 방지 (이게 진짜 목적)

빌드 캐시는 이미지를 다시 빌드하는 순간 또 3~4GB로 자란다. 다음 중 하나를 적용해 줘:

- **(권장) buildkit GC 상한 설정**: `/etc/docker/daemon.json`에 빌드 캐시 상한을
  2GB 정도로 걸고 데몬 재시작. 이 환경에서 daemon.json이 Codespaces 재생성 시
  살아남는지는 **미검증** — `.devcontainer/setup.sh`에서 매번 쓰도록 해야 할 수도 있다.
- **차선**: `.devcontainer/`의 post-start 훅이나 프로젝트 문서에
  `docker builder prune -af --filter until=24h`를 넣어 주기적으로 돌린다.

추가로 `.dockerignore` 유무를 확인해 줘. 없으면 빌드 컨텍스트에 `.git`,
`node_modules`, `.next`가 통째로 들어가 캐시가 불필요하게 커진다.
(저장소 자체는 1.4MB로 작아서 영향이 크진 않을 것으로 **추정**한다.)

### 4단계 — 여유 공간 활용 (구조적 개선)

**`/tmp`는 별도 디스크(`/dev/sda1`, 118GB 중 109GB 여유)에 있다.** 32GB 루프
디바이스와 무관하다. 큰 빌드 산출물, 데이터셋, 임시 파일은 `/tmp` 아래로 보내면
경고 자체가 안 뜬다. 단 `/tmp`는 Codespace 재시작 시 사라질 수 있다는 점을
전제로만 쓸 것 (영속성 **미검증**).

## 목표

`/` 사용률을 89% → 70% 이하로 내리고, Docker 이미지를 다시 빌드해도 80%를 넘지
않도록 3단계 재발 방지책을 적용하는 것. 정리 전후 `df -h /` 출력을 함께 보고해 줘.

## 하지 말아야 할 것

- `/usr`, `/usr/local`, `/opt` 아래 파일 삭제 (함정 ① 참고 — 역효과)
- `docker system prune -a --volumes` 무지성 실행 — 볼륨 1개가 active 상태다
- `/workspaces` 정리 — 저장소 전체가 1.4MB라 얻을 게 없다

---

# 실행 결과 (2026-09-02)

위 계획을 실행한 기록이다. 모든 수치는 실측이다.

## 요약

| 시점 | 사용량 | 사용률 |
|---|---|---|
| 정리 전 | 27G / 32G | **89%** |
| 1단계 후 (캐시·이미지·컨테이너·사용자 캐시) | 22G | 74% |
| 2단계 후 (구버전 확장 제거) | 22G | **73%** |
| 이미지 4개 전체 재빌드 후 | 24G | **79%** |

빌드 캐시는 재빌드 후에도 **1.549GB**에 머물렀다. 같은 4개 이미지를 빌드했을 때
이전에는 3.895GB였다. 2GB 상한이 실제로 걸린다.

## 1단계 회수 내역

| 조치 | 회수 | 누적 사용률 |
|---|---|---|
| `docker builder prune -af` | 3.895GB | 89% → 79% |
| `docker container prune -f` | 12.29kB | 79% |
| `docker image prune -af` | 790.2MB | 79% → 77% |
| `~/.cache/copilot/pkg`(356M) + `~/.codex/.tmp`(98M) + `npm cache clean` | ~600MB | 77% → 75% |
| `~/.local/share/claude/versions/2.1.252` | 205MB | 75% → 74% |
| `~/.vscode-remote/extensions/anthropic.claude-code-2.1.252-*` | 215MB | 74% → 73% |

`docker image prune -af`는 실행 중인 컨테이너가 없었으므로 **5개 이미지 전부**를
지웠다(중복 `codespaces-*` 2개 + 주 이미지 2개 + `python:3.12-slim`). 빌드 캐시를
이미 비운 뒤라 어차피 전체 재빌드였고, 위 재빌드로 4개를 복구했다.

삭제 전 확인한 것:

- 실행 중인 Claude Code는 `2.1.258`이었다(`~/.local/share/claude/versions/`에
  2.1.252와 2.1.258 두 개). 2.1.252만 지웠다.
- `~/.vscode-remote/extensions/extensions.json`에 등록된 claude-code는 2.1.258
  하나뿐이었다. 2.1.252 디렉터리는 고아라 안전하게 지웠다.

## 목표 70%는 이 컨테이너 안에서 도달할 수 없다

정리를 끝낸 73% 상태에서 컨테이너 안에서 보이는 사용량을 전부 더하면:

```
/usr 7.3G  /home 1.7G  /opt 1.3G  /var 25M  /root 17M  /etc 3.2M  /workspaces 2.5M
= 10.2GB   (+ /var/lib/containerd 의 이미지·캐시 약 2.3GB)
```

그런데 `df`는 22~24GB를 쓴다고 보고한다. **차이 약 11~12GB는 이 devcontainer
자신의 이미지 레이어**로, 루프 디바이스(`/dev/loop4`) 위에 있지만 컨테이너의
마운트 네임스페이스 밖이라 안에서는 보이지도, 지울 수도 없다.

즉 **바닥이 73%**다. 안에서 더 줄이려면 함정 ①의 lower 레이어를 건드려야 하는데
그건 역효과다. 70%를 원하면 Codespace 머신 타입을 키워 디스크를 늘리는 수밖에 없다.

남은 선택지 하나: `~/.vscode-remote/extensions/openai.chatgpt-*`가 **578MB**를
쓴다. `extensions.json`에 정식 등록되어 있으므로 디렉터리를 직접 지우지 말고
확장 관리자에서 제거할 것. 제거하면 약 71%가 된다.

## 3단계 재발 방지 — 적용한 것

`.devcontainer/docker-gc.sh`를 추가하고 `devcontainer.json`의
`postStartCommand`로 걸었다. 이 스크립트가 `/etc/docker/daemon.json`에 buildkit
GC 상한 2GB를 쓴다.

```json
{
  "builder": {
    "gc": {
      "enabled": true,
      "policy": [
        { "all": true, "reservedSpace": "256MB", "maxUsedSpace": "2GB" }
      ]
    }
  }
}
```

### 확인한 사실 (계획서의 "미검증" 해소)

- **dockerd는 이 devcontainer 안에서 돈다**(docker-in-docker). PID 1의
  `/usr/local/share/docker-init.sh`가 띄우며 `--config-file`을 주지 않는다.
  따라서 `/etc/docker/daemon.json`이 그대로 읽힌다.
- **daemon.json은 Codespace 재생성 시 사라진다.** `/etc`는 컨테이너 쓰기
  레이어다. 그래서 `postStartCommand`로 매번 다시 쓴다. (중지→시작에서는 살아남는다.)
- **`builder.gc`는 SIGHUP 라이브 리로드로 반영되지 않는다.** SIGHUP을 보내면
  `/tmp/dockerd.log`의 "Reloaded configuration"에 `"builder":{"GC":{}}`로 남는다.
  dockerd 기동 시에만 읽히므로, 스크립트는 **설정이 실제로 바뀐 경우에만**
  `docker-init.sh`로 데몬을 다시 띄운다(멱등).
- 재기동할 때는 `pkill` 뒤에 **옛 데몬이 실제로 사라질 때까지 기다린다**(최대 30초).
  `pkill`은 시그널만 보내고 종료를 기다리지 않으므로, 그냥 이어서 새 데몬을 띄우면
  옛 데몬이 소켓을 쥔 채라 기동에 실패하고 `docker info`가 죽어가는 옛 데몬에 붙어
  거짓 성공을 보고할 수 있다. PID 교체까지 확인해야 새 설정이 실제로 붙은 것이다.
- 새 형식(`reservedSpace`/`maxUsedSpace`)을 썼다. Docker 28+에서
  `defaultKeepStorage`/`keepStorage`는 비권장이다. `dockerd --validate`로 검증했다.

상한을 바꾸려면 `devcontainer.json` 의 `containerEnv.DOCKER_BUILD_CACHE_MAX` 를
고칠 것. 저장소에 커밋되므로 Codespace를 다시 만들어도 유지된다. 셸에서
`DOCKER_BUILD_CACHE_MAX=1GB bash .devcontainer/docker-gc.sh` 로 주는 값은
**이번 실행에만** 적용되고 다음 기동 때 `containerEnv` 값으로 되돌아간다.
수동 회수는 여전히 `docker builder prune -af`.

### ⚠️ 함정 ③ `dockerd --validate` 는 크기 문자열을 검사하지 않는다

`maxUsedSpace` 에 `"banana"` 를 넣어도 `dockerd --validate` 는 `configuration OK`
(rc=0)를 반환한다. 그런데 실제로 기동하면

```
error initializing buildkit: error creating buildkit instance:
  failed to parse maxUsedSpace: invalid size: 'banana'
```

로 **데몬이 통째로 뜨지 못한다**(실측). 잘못된 값이 `daemon.json` 에 남으면
Codespace를 재시작할 때마다 Docker가 죽어 있게 된다. 그래서 `docker-gc.sh` 는

1. 값 형식을 정규식으로 **먼저** 검사하고,
2. 새 설정을 임시 파일에 써서 `dockerd --validate` 로 검증한 뒤에만
   `daemon.json` 을 교체하고(살아 있는 설정을 먼저 덮어쓰지 않는다),
3. 재기동 후 데몬이 뜨지 않으면 **이전 설정으로 되돌리고 다시 띄운다.**

기존 `daemon.json` 이 손상된 JSON이면 아무것도 건드리지 않고 중단한다.
교체는 같은 디렉터리에 임시 파일을 쓰고 `rename` 하는 방식이다. `install` 이나
`tee` 는 대상 inode 를 잘라서 덮어쓰기 때문에 중간에 죽으면 잘린 파일이 남는다.

### ⚠️ 함정 ④ `builder.gc` 에서는 퍼센트를 쓸 수 없다

Docker 문서의 `buildkitd.toml` 예시(`[worker.oci]`)에는 `reservedSpace = "30%"`
같은 퍼센트 표기가 나오지만, **`daemon.json` 의 `builder.gc.policy` 에서는 안 된다.**
`"50%"` 조차 기동 시 이렇게 죽는다(실측).

```
failed to parse maxUsedSpace: invalid suffix: '%'
```

바이트 수나 K/M/G/T 접미사만 받는다. `2GB`, `512MB`, `512K`, `2.5GB`, `1gb`,
`1024000000` 은 모두 정상 기동을 확인했다.

### `.dockerignore`는 손댈 필요가 없었다

`frontend/.dockerignore`(`node_modules`, `.next`), `backend/.dockerignore`
(`.venv`, `__pycache__`, `tests`)가 이미 있다. 빌드 컨텍스트가 `./frontend`와
`./backend`라 루트의 `.git`은 애초에 컨텍스트에 들어가지 않는다.

## 4단계 — `/tmp`

`/tmp`는 `/dev/sda1`의 `containerTmp`를 바인드 마운트한 것으로 32GB 루프
디바이스와 무관하다(118G 중 107G 여유). 큰 산출물은 여기로 보내면 된다.
**Codespace 재시작 후 유지되는지는 여전히 미검증**이므로 날아가도 되는 것만 둘 것.
