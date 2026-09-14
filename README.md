# AI 생산 리스크 조기경보 MVP

가상의 소재 제조공장 데이터를 이용해 생산관리자가 납기, 자재, 오늘의 조치를 한 화면에서 확인하는 로컬 실행 데모입니다. 이 저장소에는 실제 회사·제품·거래처·운영 수치나 개인 경험을 사용하지 않았습니다.

**이 파일은 돌리는 법과 보이는 것만 적습니다.** 무엇을 왜 어디까지 만드는지는 옆에
따로 삽니다 — 목적이 다른 글을 한 파일에 두면 고칠 때 어느 쪽을 고쳐야 하는지가
흐려지기 때문입니다.

| 묻는 것 | 사는 곳 |
| --- | --- |
| 무엇을 왜, 어디까지 만드는가 — 단계·범위·제약·한계 | [`PRD.md`](PRD.md) |
| 엔티티와 관계는 어떻게 생겼나 | [`docs/schema.md`](docs/schema.md) |
| 무엇을 보고 위험이라 하는가 — 납기·자재·출하검사·품질 | [`docs/decision-rules.md`](docs/decision-rules.md) |
| 어떻게 돌리고 무엇이 보이나 | **이 파일** |
| 이 저장소에서 어떻게 일하는가 | [`CLAUDE.md`](CLAUDE.md) |
| 머지 전에 무엇을 보는가 | [`CHECKLIST.md`](CHECKLIST.md) |

**어디까지 왔는지는 이 파일이 들지 않습니다** — 손으로 적은 진척은 반드시 낡습니다.
[열린 이슈](../../issues)와 [마일스톤](../../milestones)이 셉니다.

## 아키텍처

Next.js App Router 프론트엔드는 기본적으로 같은 출처의 `/api`를 내부 FastAPI로 프록시하며, 필요하면 `NEXT_PUBLIC_API_BASE_URL`로 공개 API 주소를 지정할 수 있습니다. FastAPI 라우터는 조회·상태 변경을 제공하고, 서비스 계층의 순수 함수가 납기·자재 리스크를 계산하며, SQLAlchemy가 PostgreSQL(로컬 기본값은 SQLite 파일)을 영속화하며, 스키마 변경은 Alembic 마이그레이션으로 옮깁니다.

```text
Next.js 화면 → FastAPI API → briefing 서비스 → risk 계산 함수
                                  ↓
                       SQLAlchemy / PostgreSQL · Alembic
                                  ↑
                     app.seed 합성 샘플 초기화
```

## 샘플 데이터 초기화

시드는 실행 당일을 기준일로 사용하며, 같은 기준일에는 고정 시드로 동일한 합성 결과를 재현합니다. 날짜를 직접 지정하면 검증이나 시나리오 재현에도 사용할 수 있습니다.

과거 실적일의 계획 수량과 최근 7일 실적 수량에는 각각 다른 고정 주기의 편차(±10% 내외)를 넣습니다. 둘을 같은 값으로 두면 달성률이 늘 100%가 되고 추이 그래프의 두 선이 겹쳐 아무것도 말해주지 않기 때문입니다. 난수가 아니라 고정 주기를 쓰므로 재현성은 그대로입니다.

실적 쪽 편차는 **7일 합계를 정확히 보존**합니다(주기의 합이 7.0이고 반올림 잔차는 마지막 날에 몰아 넣습니다). 납기 판정이 최근 7일 평균 생산량으로 완료예정일을 내므로, 합계가 흔들리면 경계선에 있는 오더의 정상·주의·위험 판정이 뒤집히기 때문입니다.

```powershell
Set-Location .\backend
python -m app.seed
# 선택: Python에서 initialize_sample_database(date(...)) 또는 reset_database(date(...)) 호출
```

초기화는 스키마를 재생성하므로 리스크 상태를 포함한 기존 로컬 샘플 DB를 덮어씁니다. **지우는 것은 이 앱이 만든 표뿐입니다** — 현재 모델의 표와 옛 이름들(`app.db.base.LEGACY_TABLE_NAMES`), 그리고 `alembic_version`입니다. 보이는 표를 전부 지우면 스키마를 나눠 쓰는 곳에서 옆에 있는 남의 표까지 사라지고, 개발용이라고 여기 적어 두는 것으로는 막지 못합니다 — 한 번 실행하면 되돌릴 수 없기 때문입니다. 표 이름을 바꿀 때는 옛 이름을 그 목록에 한 줄 더하십시오. 적지 않으면 옛 표가 살아남아 굳습니다.

### 기준정보는 SQL, 시나리오는 파이썬

경계는 한 줄입니다 — **「오늘」이 안 나오면 SQL, 나오면 파이썬**입니다.

공통코드 그룹은 **값이 늘 수 있는가**로 갈립니다. 값이 고정된 그룹(창고·재고구분·품목유형 등)은 값마다 프로그램이 다른 일을 하므로 화면에서 늘릴 수 없고, 그 허용값은 파이썬 상수에서 구운 CHECK 제약이 지킵니다. 값이 늘 수 있는 그룹(공정·단위·불합격사유 등)은 세기만 하므로 늘어도 아무것도 고장 나지 않아야 합니다 — 그래서 품목의 `process`·`stock_uom`은 상수 목록을 CHECK로 박지 않고 **`common_codes`를 복합 외래키로 가리킵니다.** 허용값을 상수에서 구우면 코드 한 줄을 더하는 데 파이썬 수정과 마이그레이션이 함께 필요해지고, 그동안 드롭다운에는 뜨는데 저장은 거부되는 값이 생깁니다. 짝의 왼쪽 절반인 `process_group`·`stock_uom_group`은 데이터가 아니라 구조이므로 값이 언제나 그 그룹이며 CHECK가 그것을 못박습니다.

품목·BOM·공통코드·거래처·근무형태·검사 기준은 `backend/app/seed_data/*.sql`에 있습니다. 사람이 읽고 고치는 표이고 난수일 이유가 없으며, 품목 하나 추가가 한 줄 추가입니다. 파일 이름의 번호가 곧 의존 관계이고(`01_common_codes` → `02_items` → `03_purchase`), 뒤 파일은 앞 파일의 행을 **id가 아니라 코드로** 찾아 잇습니다 — id는 삽입 순서에 딸린 값이라 품목 하나를 앞에 끼워 넣으면 모든 줄이 조용히 다른 자재를 가리키게 됩니다.

로트·예정 입고·생산 실적·검사 기록은 파이썬에 남습니다. 날짜가 기준일에 대한 상대값이라 고정 INSERT는 내일 낡고, 「RM-05가 유효기간 폐기로 부족해진다」 같은 고정 시나리오는 코드라야 표현되기 때문입니다.

### 시드 판단 세 조건

컨테이너 기동은 `reset_database()`로 오지 않습니다. 표를 지우는 것과 채우는 것은 다른 일이며, 운영에서 지우는 쪽이 도는 것은 사고이기 때문입니다. 대신 세 조건을 **모두** 통과할 때만 시드합니다.

| 순서 | 조건 | 왜 이것인가 |
|---|---|---|
| 1 | 마이그레이션을 끝까지 돌린다 | 판단이 아니라 **전제**다. 항상 돌린다 — 표가 없으면 「비어 있는지」를 물어볼 수조차 없다 |
| 2 | `SEED_SAMPLE_DATA=1` 스위치가 켜져 있다 | 개발과 시연에서만 켠다. 운영에서 자동 시드는 편의가 아니라 사고다 |
| 3 | 품목 표가 비어 있다 | 「표가 있는가」는 아무것도 말해 주지 않는다 — 마이그레이션이 항상 만들어 둔다. 물어야 할 것은 **내용의 유무**다 |

품목 표를 표식으로 쓰는 것은 **가장 먼저 채워지고 마지막까지 남는 표**이기 때문입니다. 생산실적이나 출하실적 같은 거래 표는 비어 있는 것이 정상 상태라 판단 기준이 될 수 없습니다.

시드 전체는 **트랜잭션 하나**입니다. 중간에 실패하면 아무것도 들어가지 않은 상태로 되돌아가고 다음 기동에서 다시 시도됩니다 — 「반쯤 채워짐」이라는 상태 자체가 없어집니다. SQLite라면 파일을 지우고 처음으로 돌아갈 수 있지만 PostgreSQL에는 지울 파일이 없고, 반쯤 채워진 데이터베이스는 「비어 있지 않다」로 판정되어 다시는 시드되지 않은 채 굳습니다. 컨테이너가 둘 이상 동시에 뜨면 둘 다 「비어 있다」를 보므로 시드 구간에 잠금을 하나 겁니다(PostgreSQL이라서 생기는 문제이고, 파일 하나였을 때는 없던 일입니다).

### 스키마 변경과 마이그레이션

스키마는 Alembic으로 옮깁니다.

```powershell
Set-Location .\backend
python -m alembic upgrade head          # 표를 최신으로
python -m alembic revision --autogenerate -m "설명"   # 모델을 고친 뒤
```

접속 주소는 `alembic.ini`에 적지 않습니다. `migrations/env.py`가 앱 설정에서 읽어 가므로 앱과 마이그레이션이 같은 곳을 봅니다 — 두 곳에 적으면 마이그레이션이 앱과 다른 데이터베이스를 고치는 사고가 나고, 그때 화면은 멀쩡하고 표만 조용히 어긋납니다.

이전 판의 데이터베이스는 그대로 올라가지 않습니다. Alembic 없이 `create_all`로 만들어진 데이터베이스에는 표가 있는데 `alembic_version`이 없고, Alembic은 그것을 **빈 데이터베이스**로 읽어 초기 리비전을 처음부터 돌리다 이미 있는 표에서 실패합니다. 진입점은 마이그레이션 앞에 `python -m app.db.preflight`를 두어 그 상태를 먼저 알아보고 멈춥니다 — 옛 데이터베이스를 말없이 지우는 쪽이 훨씬 나쁘기 때문입니다. 합성 데이터라면 `python -m app.seed`로 지우고 다시 만들고, 지울 수 없는 데이터라면 스키마가 현재 리비전과 같은지 직접 확인한 뒤에만 `python -m alembic stamp head`로 버전을 찍으십시오.

**자동 생성이 만든 CHECK 제약은 반드시 읽어 보십시오.** 자동 생성은 제약을 실행 시점 방언으로 구워 문자열로 박아 둡니다. 불합격 사유의 공백 검사처럼 함수 이름이 엔진마다 다른 제약(SQLite `trim` / PostgreSQL `btrim`)은 그 문자열이 남으면 다른 엔진에서 뜻을 잃습니다. 그런 제약은 **방언을 가르는 식을 리비전 파일 안에 두어** 실행 시점 방언이 정하게 합니다(`migrations/versions/65f0715f47d9_initial_schema.py`의 `_BlankTrimmed`). 모델에서 불러오면 안 됩니다 — 지나간 리비전은 **그때의 스키마를 적은 기록**이라 나중의 모델 변경에 흔들리면 안 되고, 식이 바뀌거나 이름이 사라지면 그 리비전이 다른 제약을 만들거나 아예 임포트에서 터집니다. 굳히지 않으면서 매이지도 않는 자리가 그것입니다. 회귀 테스트가 `migrations/versions/`에 한 엔진의 문법이 박히는 것을 막습니다.

## 사전 요구사항

- Windows PowerShell
- Python 3.12 — CI와 컨테이너 이미지가 쓰는 판입니다. 3.11에서는 골든 케이스의 완료예정일이 하루 어긋납니다.
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

`compose.yaml` 하나로 돕니다. 프런트엔드는 빌드 시점에 `API_INTERNAL_BASE_URL`(`http://backend:8000`)로 프록시 대상을 굽고, 서비스는 bridge 네트워크로 붙습니다.

**먼저 데이터베이스 비밀번호를 정합니다.** 저장소에 적어 두지 않으므로 값이 없으면 기동이 거기서 멈춥니다 — 기본값을 두면 그 기본값이 곧 저장소에 적힌 비밀번호이기 때문입니다.

```bash
echo "POSTGRES_PASSWORD=$(openssl rand -hex 16)" >> .env   # compose 가 자동으로 읽는다
```

이 값은 접속 주소에 그대로 끼워 넣으므로 **URL 에 안전한 문자만** 써야 합니다 — `/` `#` `?` `@` `%` 가 들어가면 주소가 깨져 마이그레이션이 접속하지 못합니다. 위 `openssl rand -hex` 는 16진수만 내므로 이 조건을 만족합니다. 그 밖의 문자를 꼭 써야 하면 `DATABASE_URL` 을 직접 정하면 되고, 그때는 그 값이 우선합니다.

```bash
docker compose up --build
```

`http://localhost:3000`에서 대시보드를, `http://localhost:8000`에서 FastAPI를 엽니다.

```bash
docker compose down
# 합성 데이터 볼륨까지 지우려면 -v 를 덧붙입니다.
```

### 데이터 영속화

데이터베이스는 별도 서비스로 돕니다(`postgres:16-alpine`, 볼륨 `database-data`). 백엔드는 `DATABASE_URL`로 접속하며, 진입점은 **기동할 때마다 마이그레이션을 돌린 뒤** 위의 세 조건으로 시드 여부를 판단합니다. 헬스체크를 둔 것은 백엔드가 마이그레이션부터 돌리기 때문입니다 — 데이터베이스가 받을 준비를 마치기 전에 뜨면 첫 기동이 그냥 실패합니다.

합성 데이터를 처음부터 다시 만들려면 `docker compose down -v`로 볼륨을 지우고 다시 올립니다. **기록해 둔 리스크 상태는 사라집니다.**

`DATABASE_URL`을 주지 않으면 SQLite 파일로 떨어지며 경로는 `DATABASE_PATH`로 바꿉니다. **두 엔진 모두 배포되므로 CI 는 둘 다 돌립니다** — 어느 한쪽만 돌리면 다른 쪽에서만 나는 결함이 그대로 나갑니다. 그 결함은 대칭이 아닙니다: 불리언 칸의 정수처럼 PostgreSQL 만 거부하는 것이 있고, `LIKE` 의 대소문자처럼 SQLite 만 통과시켜 **개발에서만 되는** 행을 만드는 것이 있습니다. 무엇을 어떻게 돌리는지는 산문이 아니라 `.github/workflows/cloud-validation.yml` 과 그것을 읽는 `backend/tests/test_ci_workflow.py` 에 있습니다.

### 알아두면 좋은 함정

**`API_INTERNAL_BASE_URL`은 런타임 환경변수가 아니라 빌드 시점 값입니다.** `next.config.ts`의 `rewrites()`는 빌드할 때 `.next/routes-manifest.json`으로 구워지므로, 이미 빌드된 컨테이너에 환경변수를 주입해도 프록시 대상은 바뀌지 않습니다. 값을 바꾸려면 `--build`로 다시 빌드해야 합니다.

## 화면 안내

메뉴는 두 단으로 나뉩니다. **경보**는 납기와 자재를 가로지르는 조기경보 화면이라 특정 업무 모듈에 속하지 않고, **ERP**는 부서별로 확인하기 쉽도록 업무 모듈로 나눴습니다.

| 단 | 메뉴 | 경로 | 내용 |
| --- | --- | --- | --- |
| 경보 | 운영 현황 | `/` | KPI, 최근 7일 계획·실적 추이(제품별로 나눠 보기), 상위 위험, 오늘의 권장 조치 |
| 경보 | 리스크 보드 | `/risks` | 납기·자재 통합 리스크와 상태 변경 |
| ERP | 기준정보관리 | `/master` | 제품·자재 품목 코드와 제품별 자재 소요량(BOM) |
| ERP | 구매관리 | `/purchases` | 자재 예정 입고 일정, 유효기간, 14일 전망 반영 여부 |
| ERP | 재고관리 · 재고현황 | `/materials` | 자재별 로트 재고, 14일 수급·안전재고·소진 예상일 |
| ERP | 재고관리 · 창고별 재고 | `/materials/warehouses/{raw\|production\|products}` | 창고 한 곳에 실제로 놓여 있는 자재·완제품 로트 |
| ERP | 생산관리 | `/orders` | 생산 오더 납기 현황, 최근 14일 생산실적, 오더 상세(`/orders/{id}`) |
| ERP | 품질관리 | `/quality` | IQC·PQC·OQC 검사 기록과 유형별 합격·불합격 건수 |
| ERP | 영업관리 | `/sales` | 제품별 출하 가능 재고와, 내보내지 못하는 재고가 어디에 묶여 있는지 |

**경로는 개편 전 그대로 둡니다.** 생산관리가 `/orders`, 재고관리가 `/materials`인 것은 메뉴 라벨만 업무 모듈 이름으로 바꾸고 URL은 유지해 기존 링크와 CI 스크린샷 경로가 깨지지 않게 했기 때문입니다. 품질관리와 창고별 재고만 신규 화면이라 `/quality`, `/materials/warehouses/…`를 새로 씁니다. **재고관리만 하위 메뉴를 갖습니다** — 재고를 품목 기준(재고현황)과 창고 기준(창고별 재고)으로 나눠 봐야 하고, 창고는 담는 것이 서로 달라 한 화면에 섞으면 읽을 수 없기 때문입니다. 메뉴에서 생산관리와 영업관리 사이에 둔 것은 자재 입고(IQC) → 생산(PQC) → 출하(OQC) 순서이고, OQC가 출하의 관문이기 때문입니다.

영업관리는 **출하 관점만** 다룹니다 — 지금 내보낼 수 있는 양과, 그러지 못하는 양이 어디에 묶여 있는지입니다. 로트 하나하나와 창고 구분은 재고관리의 창고별 재고가 맡습니다. 출하 일정과 수주 엔티티가 없어 **부족 판정은 아직 하지 않습니다** — 자세한 내용은 [`docs/decision-rules.md`](docs/decision-rules.md#완제품-로트와-출하검사)에 있습니다.

추이 그래프는 기본으로 전 제품 합계를 보여주고, 위의 제품 버튼으로 한 제품만 따로 볼 수 있습니다. 제품 5개를 한꺼번에 그리면 계획·실적까지 선이 10개가 되어 읽을 수 없기 때문에, 선은 항상 두 개로 유지하고 대상을 바꾸는 방식을 택했습니다. 선택은 스크린리더용 표와 차트 설명에도 함께 반영됩니다.

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

GitHub Actions의 `Cloud validation` 워크플로는 PostgreSQL 서비스 컨테이너를 띄워 운영과 같은 길(`preflight` → `alembic upgrade head` → `app.seed --if-empty`)을 밟은 뒤 백엔드 검사를 두 엔진에서 각각 돌리고, 타입 검사·빌드를 수행하고 FastAPI와 Next.js를 일시적으로 실행합니다. 완료된 실행의 **Artifacts → production-risk-screenshots**에서 운영 현황(`dashboard.png`), 생산관리(`orders.png`), 재고현황(`materials.png`), 창고별 재고(`warehouse-raw.png`·`warehouse-production.png`·`warehouse-products.png`), 리스크 보드(`risks.png`), 기준정보관리(`master.png`), 구매관리(`purchases.png`), 품질관리(`quality.png`), 영업관리(`sales.png`) 화면 PNG를 내려받을 수 있습니다. `workflow_dispatch`가 설정되어 있으므로 Actions 화면에서 수동으로도 실행할 수 있습니다.
