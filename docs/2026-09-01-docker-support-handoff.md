# Docker 지원 추가 작업 핸드오프 (2026-09-01)

이 문서는 새 세션에 그대로 붙여넣어 작업을 이어가기 위한 프롬프트입니다.
본문의 사실들은 2026-09-01에 Codespaces에서 실제로 이미지를 빌드하고 컨테이너를
띄워 확인한 실측 결과입니다. "미검증 항목"으로 표시한 부분만 예외입니다.

---

저장소 pdw96/ai-production-risk-early-warning 에 Docker 실행 환경을 추가하는 PR을 만들어 줘.

## 배경

이전 세션에서 "이 프로젝트가 Docker에서, 그리고 Codespaces에서 돌아가는지"를
실제로 이미지 빌드 + 컨테이너 실행으로 검증했다. 결론은 "둘 다 가능"이고,
그 과정에서 함정 두 개를 재현하고 해결책까지 확인했다. 아래는 전부 실측 결과이니
다시 검증하느라 시간 쓰지 말고 그대로 신뢰해도 된다. (단, 명시적으로
"미검증"이라고 적은 항목은 예외다.)

## 검증 완료된 사실

### 환경

- Codespaces 안에서 Docker 사용 가능: Docker 29.7.2, Compose v5.5.0, 데몬 접근 정상
  (storage=overlayfs, root=/var/lib/docker).
- 저장소에는 Dockerfile / compose 파일이 아직 하나도 없다. `.devcontainer/`만 있다
  (devcontainer.json + setup.sh + start.sh).

### 프로젝트 구조상 유리한 점

- frontend의 모든 페이지가 `"use client"` + `useEffect` 방식이다
  (app/page.tsx, orders, materials, risks 전부). 따라서 `next build` 시점에
  백엔드가 떠 있을 필요가 없다. 빌드와 실행을 분리할 수 있다.
- 브라우저는 same-origin `/api/...`로 호출하고, Next.js rewrites가 FastAPI로 프록시한다
  (frontend/lib/api.ts의 `api_base_url`은 `NEXT_PUBLIC_API_BASE_URL ?? ""`).

### ⚠️ 함정 ① API_INTERNAL_BASE_URL은 런타임 env가 아니라 빌드 인자다

`frontend/next.config.ts`의 `rewrites()`는 **빌드 시점에
`.next/routes-manifest.json`으로 구워진다.** 런타임 env는 무시된다.
컨테이너에 env를 정확히 주입하고도 500이 났고, 실측 증거는 다음과 같다:

```text
컨테이너 런타임 env : API_INTERNAL_BASE_URL=http://backend:8000   ← 제대로 들어감
routes-manifest.json: "destination": "http://127.0.0.1:8000/api/:path*"  ← 빌드 때 값
frontend 로그       : Failed to proxy http://127.0.0.1:8000/api/dashboard ECONNREFUSED
```

`ARG`로 바꾼 뒤 manifest가 `http://backend:8000/api/:path*`로 바뀌는 것까지 확인했다.
`frontend/.env.example`에는 런타임 변수처럼 적혀 있으니 주석 보강이 필요하다.

### ⚠️ 함정 ② Codespaces에서는 컨테이너 간 bridge 통신이 막힌다

빌드 인자를 고친 뒤에도 실패했다. 원인은 프로젝트가 아니라 Codespaces의
docker-in-docker 환경이다:

```text
DNS 조회    : backend → 172.18.0.2        ✅ 정상
TCP connect : ETIMEDOUT 172.18.0.2:8000   ❌ SYN 드롭
iptables    : FORWARD 정책은 ACCEPT인데도 실패.
              "Warning: iptables-legacy tables present" (nftables와 혼재)
```

→ 해결책은 `network_mode: host`. 이걸로 전 경로가 정상 동작했다. 부수 효과도 좋다:
컨테이너가 호스트 3000/8000에 직접 바인딩하므로 devcontainer.json의
`forwardPorts: [3000, 8000]`이 지금과 똑같이 동작한다. 이때는
API_INTERNAL_BASE_URL이 기본값 `http://127.0.0.1:8000`이어야 한다.

### 실제로 통과한 구성과 결과

host 네트워크 구성으로 전수 확인한 결과:

```text
/                HTTP 200  6978B     /api/dashboard   HTTP 200   4116B
/orders          HTTP 200  7335B     /api/orders      HTTP 200  11444B
/materials       HTTP 200  7300B     /api/materials   HTTP 200   5515B
/risks           HTTP 200  7329B     /api/risks       HTTP 200   6855B
PATCH /api/risks/RISK-ORDER-001/status → 200 (쓰기 경로 정상)
```

이미지 크기: backend 311MB, frontend 1.38GB.

### 검증에 사용한 파일 (그대로 출발점으로 써라)

`backend/Dockerfile`:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# DB 파일이 없을 때만 시드 (seed는 drop_all을 하므로 매번 돌리면 데이터 초기화됨)
CMD ["sh","-c","[ -f production_risk.db ] || python -m app.seed; exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]
```

`backend/.dockerignore`:

```text
.venv
__pycache__
**/__pycache__
*.db
tests
```

`frontend/Dockerfile`:

```dockerfile
FROM node:22-slim
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# next.config.ts의 rewrites()는 빌드 시점에 routes-manifest.json으로 구워지므로
# 런타임 env가 아니라 빌드 인자로 넣어야 한다.
ARG API_INTERNAL_BASE_URL=http://backend:8000
ENV API_INTERNAL_BASE_URL=${API_INTERNAL_BASE_URL}
RUN npm run build
CMD ["npm","run","start","--","--hostname","0.0.0.0","--port","3000"]
```

`frontend/.dockerignore`:

```text
node_modules
.next
.env.local
```

`compose.host.yaml` (Codespaces용, 실제 통과한 구성):

```yaml
services:
  backend:
    build: ./backend
    network_mode: host
  frontend:
    build:
      context: ./frontend
      args:
        API_INTERNAL_BASE_URL: http://127.0.0.1:8000
    network_mode: host
    depends_on: [backend]
```

### 그 외 알아둘 점

- SQLite 경로가 하드코딩되어 있다: `backend/app/core/config.py`의 `DATABASE_PATH`
  (= `backend/production_risk.db`, env 미지원). 볼륨으로 데이터를 유지하려면
  `/app/production_risk.db`를 직접 마운트해야 한다.
- `backend/app/seed.py`의 `reset_database()`는 `drop_all` → `create_all`을 한다.
  컨테이너 시작마다 무조건 실행하면 재시작 때마다 데이터가 날아간다.
- 기존 `.devcontainer/start.sh`는 uvicorn + `npm run dev`를 0.0.0.0:8000 / 0.0.0.0:3000에
  띄운다. Docker 경로와 포트가 겹치므로 동시에 못 쓴다는 점을 README에 적어야 한다.
- `.github/workflows/cloud-validation.yml`은 Docker를 쓰지 않는다. 이번 작업과 무관하고
  영향받지 않는다. (main은 9edee0a 기준 green, 액션은 전부 v7/node24로 최신화 완료)

### ❗미검증 항목 (중요)

- **bridge 네트워크 + `http://backend:8000` 조합은 end-to-end로 검증되지 않았다.**
  Codespaces 네트워크 제약 때문에 막힌 것이지 설정이 틀려서가 아니며,
  routes-manifest에 `http://backend:8000`이 정확히 박히는 것까지만 확인했다.
  일반 Docker 호스트에서는 동작할 것으로 예상되지만 **추정이다.** 문서에 그렇게 쓰거나,
  검증할 방법이 있으면 검증해라. 검증 못 하면 "Codespaces에서는 compose.host.yaml을
  쓰라"고 명확히 안내해라.
- `output: "standalone"` 적용은 시도하지 않았다.

## 해야 할 일

1. 위 파일들을 저장소에 정식으로 추가해라. 로컬/일반 서버용(bridge)과 Codespaces용(host)
   두 구성을 어떻게 나눌지는 네가 판단해라 — compose 파일 2개, override, profile 중
   무엇이든 좋으니 고른 이유를 알려줘. 핵심은 API_INTERNAL_BASE_URL 빌드 인자 값이
   두 환경에서 다르다는 점(`http://backend:8000` vs `http://127.0.0.1:8000`)이
   사용자에게 헷갈리지 않게 드러나는 것이다.
2. frontend 이미지 1.38GB를 `output: "standalone"` + multi-stage 빌드로 줄여라.
   `frontend/next.config.ts` 수정이 필요하다. 단, standalone으로 바꾼 뒤에도
   rewrites 프록시와 4개 페이지 + 4개 API가 전부 정상 동작하는지 반드시 재확인할 것.
   여기서 깨지면 무리하지 말고 되돌리고 이유를 알려줘.
3. `backend/app/core/config.py`의 DATABASE_PATH를 환경변수로 재정의 가능하게 할지
   검토해라. 기존 동작(기본값)이 바뀌면 안 되고, backend 테스트가 깨져도 안 된다.
   불필요하다고 판단하면 안 해도 되니 판단 근거를 알려줘.
4. README에 실행법을 추가해라: 로컬 Docker, Codespaces, 기존 devcontainer 방식의
   차이와 포트 충돌 주의사항. 위의 함정 ①②도 짧게 남겨서 다음 사람이 같은 데서
   막히지 않게 해줘.
5. 실제로 빌드하고 띄워서 검증해라. 최소한 위 "실제로 통과한 구성과 결과"의
   8개 경로 + PATCH 쓰기 경로가 전부 통과해야 한다. 검증은 저장소를 더럽히지 않게
   진행하고, 끝나면 컨테이너를 정리해라.
6. push/PR 생성 전에 변경 사항을 요약해서 보여줘. 그 다음 main에서 새 브랜치를 따서
   커밋 → push → PR 생성하고, CI(Cloud validation)가 green인지 확인해서 알려줘.
   Docker를 추가해도 기존 CI는 영향받지 않아야 한다.

## 환경 주의사항

- gh는 환경변수 GITHUB_TOKEN(GitHub App 설치 토큰, ghu_)으로 인증된다.
  actions 권한과 저장소 administration 권한이 없다. `gh run rerun` / `gh workflow run` 및
  저장소 설정 변경(PATCH /repos/...)은 403으로 실패한다. 재실행이나 설정 변경이 필요하면
  나에게 웹 UI에서 해달라고 요청해라. 조회(gh run view/list), push, PR 생성/머지는 가능하다.
- 저장소는 merge commit 관례를 쓴다(PR #1, #2, #3 모두 merge commit).
- delete_branch_on_merge=true로 설정되어 있어 머지 후 브랜치는 자동 삭제된다.
- host 네트워크 모드에서는 `ports:`가 무시되고 호스트 포트를 그대로 점유한다.
  검증 중 3000/8000이 이미 사용 중이면 기존 프로세스를 먼저 정리해야 한다.
