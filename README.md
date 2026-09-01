# AI 생산 리스크 조기경보 MVP

가상의 소재 제조공장 데이터를 이용해 생산관리자가 납기, 자재, 오늘의 조치를 한 화면에서 확인하는 로컬 실행 데모입니다. 이 저장소에는 실제 회사·제품·거래처·운영 수치나 개인 경험을 사용하지 않았습니다.

## 문제 정의

생산 계획과 실적, 재고와 예정 입고가 흩어져 있으면 납기 지연과 자재 부족을 조기에 발견하기 어렵습니다. 이 MVP는 결정적인 계산 규칙으로 위험 근거를 표시하고, 담당자가 리스크 상태를 `신규` → `확인 중` → `조치 완료`로 기록할 수 있게 합니다.

## 설계 착안점

실제 생산관리 화면에서 유용한 밀도 높은 통제실형 정보 구조를 참고해 KPI, 납기 오더, 14일 자재 전망, 권장 조치를 연결했습니다. 특정 기업의 화면이나 실제 업무 프로세스를 복제한 것이 아니라, 운영 의사결정에 필요한 정보 흐름을 합성 데이터로 표현한 설계입니다.

## 아키텍처

Next.js App Router 프론트엔드는 기본적으로 같은 출처의 `/api`를 내부 FastAPI로 프록시하며, 필요하면 `NEXT_PUBLIC_API_BASE_URL`로 공개 API 주소를 지정할 수 있습니다. FastAPI 라우터는 조회·상태 변경을 제공하고, 서비스 계층의 순수 함수가 납기·자재 리스크를 계산하며, SQLAlchemy가 SQLite를 영속화합니다.

```text
Next.js 화면 → FastAPI API → briefing 서비스 → risk 계산 함수
                                  ↓
                           SQLAlchemy / SQLite
                                  ↑
                     app.seed 합성 샘플 초기화
```

## 데이터 모델

`products`(가상 제품 5개), `orders`(생산 오더 30개), `daily_productions`(과거 30일 이상 및 향후 14일 계획), `materials`(자재 15개), `bom_requirements`(제품-자재 단위 소요량), `purchase_receipts`(예정 입고), `risk_statuses`(결정적 리스크 키와 상태)를 사용합니다.

## 판정 규칙

### 납기 위험

기준일 이전(포함) 실적을 누적하고, 기준일 포함 최근 7일 평균 생산량으로 잔여 수량의 완료예정일을 올림 계산합니다. 완료예정일이 납기일보다 늦으면 `위험`, 납기까지 1일 이하면 `주의`, 그 외는 `정상`입니다. 평균 생산량이 0이고 잔여량이 있으면 완료예정일 없이 `위험`으로 표시합니다.

### 14일 안전재고

현재 재고에서 기준일 포함 14일의 일별 계획수량 × BOM 소요량을 차감합니다. 각 날짜의 예정 입고는 수요 차감보다 먼저 반영합니다. 14일 안에 안전재고 미만이 되거나 재고가 0 이하가 되면 부족 예상으로 보고 소진일과 권장 조치를 표시합니다.

## 샘플 데이터 초기화

시드는 실행 당일을 기준일로 사용하며, 같은 기준일에는 고정 시드로 동일한 합성 결과를 재현합니다. 날짜를 직접 지정하면 검증이나 시나리오 재현에도 사용할 수 있습니다.

```powershell
Set-Location .\backend
python -m app.seed
# 선택: Python에서 initialize_sample_database(date(...)) 또는 reset_database(date(...)) 호출
```

초기화는 SQLite 스키마를 재생성하므로 리스크 상태를 포함한 기존 로컬 샘플 DB를 덮어씁니다.

## 사전 요구사항

- Windows PowerShell
- Python 3.11 이상
- Node.js 20 이상 및 npm
- Docker로 실행할 경우: Docker Engine과 Compose v2 이상 (위 Python·Node 설치는 불필요)

## 백엔드 설치·실행

별도 PowerShell 창에서 실행합니다.

```powershell
Set-Location C:\path\to\ai-production-risk-mvp\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m app.seed
uvicorn app.main:app --reload --port 8000
```

## 프론트엔드 설치·실행

또 다른 PowerShell 창에서 실행합니다.

```powershell
Set-Location C:\path\to\ai-production-risk-mvp\frontend
Copy-Item .env.example .env.local
npm install
npm run dev
```

브라우저에서 `http://localhost:3000`을 엽니다. API 주소를 바꾸려면 `.env.local`의 `NEXT_PUBLIC_API_BASE_URL`을 수정합니다.

## Docker로 실행

`compose.yaml`(일반 Docker 호스트)과 `compose.codespaces.yaml`(GitHub Codespaces) 두 구성을 제공합니다. 두 파일은 **`API_INTERNAL_BASE_URL` 빌드 인자 값이 다르기 때문에** 분리되어 있습니다. 각 파일이 자기 환경에 맞는 값을 명시적으로 담고 있으므로, 사용하는 파일만 고르면 됩니다.

| 구성 | 파일 | 네트워크 | `API_INTERNAL_BASE_URL` |
| --- | --- | --- | --- |
| 로컬 PC·서버 | `compose.yaml` | bridge | `http://backend:8000` |
| GitHub Codespaces | `compose.codespaces.yaml` | host | `http://127.0.0.1:8000` |

### 로컬 PC·서버

```bash
docker compose up --build
```

### GitHub Codespaces

```bash
docker compose -f compose.codespaces.yaml up --build
```

두 경우 모두 `http://localhost:3000`에서 대시보드를, `http://localhost:8000`에서 FastAPI를 엽니다. 종료와 정리는 사용한 파일을 그대로 지정해 실행합니다.

```bash
docker compose down                                # 로컬
docker compose -f compose.codespaces.yaml down     # Codespaces
# 합성 데이터 볼륨까지 지우려면 -v 를 덧붙입니다.
```

### 데이터 영속화

백엔드 컨테이너는 `DATABASE_PATH=/data/production_risk.db`로 SQLite를 `backend-data` 볼륨에 둡니다. 진입점은 **DB 파일이 없을 때만** `python -m app.seed`를 실행합니다. `app.seed`의 `reset_database()`가 `drop_all` → `create_all`을 수행하므로, 기동할 때마다 시드하면 리스크 상태를 포함한 기존 데이터가 사라지기 때문입니다. 합성 데이터를 처음부터 다시 만들려면 `docker compose down -v`로 볼륨을 지우고 다시 올립니다.

### 기존 devcontainer 방식과의 차이 · 포트 충돌 주의

`.devcontainer/start.sh`(개발 서버, `npm run dev` + `uvicorn --reload`)와 Docker 구성은 **모두 호스트의 3000·8000 포트를 사용하므로 동시에 실행할 수 없습니다.** 하나를 먼저 종료한 뒤 다른 하나를 실행하세요. 특히 `compose.codespaces.yaml`은 `network_mode: host`라서 `ports:` 매핑 없이 호스트 포트를 직접 점유합니다.

| 방식 | 용도 | 코드 변경 반영 |
| --- | --- | --- |
| `.devcontainer/start.sh` | 개발 | 즉시(핫 리로드) |
| Docker compose | 재현 가능한 실행·배포 확인 | 재빌드 필요 |

### 알아두면 좋은 함정 두 가지

1. **`API_INTERNAL_BASE_URL`은 런타임 환경변수가 아니라 빌드 시점 값입니다.** `next.config.ts`의 `rewrites()`는 빌드할 때 `.next/routes-manifest.json`으로 구워지므로, 이미 빌드된 컨테이너에 환경변수를 주입해도 프록시 대상은 바뀌지 않습니다. 값을 바꾸려면 `--build`로 다시 빌드해야 합니다.
2. **Codespaces에서는 컨테이너 간 bridge 통신이 막힙니다.** 서비스 이름 DNS는 정상 해석되지만(`backend` → `172.18.0.2`) TCP 연결이 타임아웃됩니다(docker-in-docker의 iptables-legacy/nftables 혼재). 그래서 Codespaces용 구성만 `network_mode: host`를 사용합니다. 이 제약은 Codespaces 환경 문제이며 일반 Docker 호스트에는 해당하지 않습니다.

## GitHub Codespaces에서 실행

GitHub 저장소의 **Code → Codespaces → Create codespace**로 일시적인 개발 환경을 만들 수 있습니다. 컨테이너 생성 시 Python·Node 의존성과 합성 SQLite 데이터가 자동으로 준비됩니다. 준비가 끝나면 Codespace 터미널에서 다음 명령을 실행합니다.

```bash
bash .devcontainer/start.sh
```

이 방식은 핫 리로드가 동작하는 개발 서버입니다. 컨테이너로 재현 가능한 실행을 확인하려면 위의 [Docker로 실행](#docker로-실행)에서 `compose.codespaces.yaml`을 사용하세요. 두 방식은 포트가 겹치므로 동시에 실행할 수 없습니다.

포트 3000의 **AI 생산 리스크 대시보드**를 열면 브라우저에서 화면을 직접 검증할 수 있습니다. 프론트엔드는 같은 출처의 `/api` 요청을 Codespace 내부 FastAPI로 프록시하므로 별도의 공개 API URL이 필요하지 않습니다. 종료할 때는 터미널에서 `Ctrl+C`를 누르고 Codespace를 중지하거나 삭제합니다. SQLite 파일은 Git에 포함되지 않으며 Codespace마다 합성 데이터로 다시 생성됩니다.

GitHub Actions의 `Cloud validation` 워크플로는 테스트·타입 검사·빌드를 수행하고 FastAPI와 Next.js를 일시적으로 실행합니다. 완료된 실행의 **Artifacts → production-risk-screenshots**에서 대시보드, 오더, 자재, 리스크 화면 PNG를 내려받을 수 있습니다. `workflow_dispatch`가 설정되어 있으므로 Actions 화면에서 수동으로도 실행할 수 있습니다.

## 화면 안내

- `/`: KPI, 최근 7일 계획·실적 추이, 상위 위험, 오늘의 권장 조치
- `/orders`: 납기 위험 오더 목록 및 오더 상세
- `/materials`: 14일 자재 수급, 안전재고, 소진 예상일
- `/risks`: 납기·자재 통합 리스크 보드와 상태 변경

화면은 로딩·오류·빈 상태를 구분하며, 위험도는 색상뿐 아니라 아이콘과 텍스트로 표시합니다.

## 테스트와 종단 간 검증

```powershell
# 백엔드
Set-Location C:\path\to\ai-production-risk-mvp\backend
python -m pytest tests -v

# 프론트엔드
Set-Location ..\frontend
npm test
npm run lint
npm run build
```

백엔드가 실행 중일 때 실제 API 요청은 다음처럼 확인합니다.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/dashboard
```

## 합성 데이터 기반 데모의 한계

데이터와 위험 패턴은 재현 가능한 합성 샘플이며 실제 수요, 공급업체, 생산능력, 품질 또는 설비 상태를 의미하지 않습니다. 따라서 운영 의사결정이나 성능·정확도 검증에 직접 사용할 수 없습니다. 외부 LLM 연동도 포함하지 않습니다.

## 향후 확장 계획

- **LOT/FIFO**: 로트별 입고·유효기간과 FIFO 출고를 모델링해 자재 가용성을 정교화합니다.
- **품질·설비**: 검사 결과, 설비 가동률·고장·정비 일정을 연결해 생산능력 리스크를 추가합니다.
- **AI 브리핑**: 검증 가능한 계산 근거를 입력으로 삼아 담당자용 일일 브리핑을 생성하되, 실제 모델 연동과 권한·감사 로그를 별도로 설계합니다.
