# 이 저장소에서 일하는 법

가상의 소재 제조공장 데이터로 도는 생산 리스크 조기경보 MVP. Next.js 화면 →
FastAPI → 서비스 계층 순수 함수 → SQLAlchemy(PostgreSQL, 로컬 기본값은 SQLite).
무엇을 만드는지는 `README.md` 에 있다. 이 파일은 **어떻게 일하는지**만 적는다.

## 명령

줄마다 괄호로 감싼 것은 셸의 현재 위치를 바꾸지 않기 위해서다. 위에서 아래로
붙여 넣어도 그대로 돈다.

```bash
# 백엔드 — 두 엔진에서 다 돌아야 한다. 한쪽만 통과한 것은 통과가 아니다.

# ① 운영 엔진(PostgreSQL). 주소를 주지 않으면 설정이 SQLite 로 **조용히**
#    떨어져 ②와 같은 엔진을 두 번 도는 것으로 끝난다 — `:?` 가 그것을 막는다.
(cd backend && DATABASE_URL="${DATABASE_URL:?postgresql+psycopg:// 주소를 주십시오}" \
   python -m pytest tests -v)

# ② SQLite. 비우면 설정이 backend/production_risk.db 로 떨어진다.
(cd backend && DATABASE_URL="" python -m pytest tests -v)

# 프런트엔드
(cd frontend && npm test)        # vitest run
(cd frontend && npm run lint)    # tsc --noEmit (린터가 아니라 타입 검사다)
(cd frontend && npm run build)
```

①에 줄 PostgreSQL 은 따로 띄워야 한다. `compose.yaml` 의 `database` 는 호스트로
포트를 열지 않으므로 그대로는 붙지 않는다 — CI 가 하는 것처럼 포트를 연
`postgres:16-alpine` 하나를 띄우고 그 주소를 준다(`.github/workflows/cloud-validation.yml`
의 `services` 블록이 사용자·데이터베이스 이름까지 그대로 보여 준다). 비밀번호는
그 자리에서 만들어 쓰고 저장소에 적지 않는다.

린터·포매터는 아직 없다. 스타일은 주변 코드를 보고 맞춘다.

## 파이썬은 3.12 다

CI 와 `backend/Dockerfile` 이 3.12 로 돈다. `backend/.venv` 가 3.11 이면
`test_golden_cases.py` 의 오더 완료예정일이 **하루 어긋나 빨갛게 뜬다** —
`sum()` 의 보정 덧셈이 판본마다 달라 `ceil` 의 끝자리를 밀기 때문이다. 코드가
깨진 게 아니다. 로컬이 빨간데 CI 가 초록이면 이것부터 의심한다.

## 절대 하지 않는 것

- **머지하지 않는다.** 리뷰가 깨끗해도 머지 버튼은 저자가 누른다.
- **비밀번호를 저장소에 적지 않는다.** 운영은 `.env` 의 `POSTGRES_PASSWORD`
  (compose 가 읽고, `.gitignore` 에 있다). CI 는 잡 안에서만 사는 서비스
  컨테이너의 환경변수를 쓴다 — 그 값은 밖에서 닿지 않으므로 비밀이 아니고,
  운영 비밀번호는 워크플로에 오지 않는다. 이 짝은 `test_ci_workflow.py` 가 본다.
- **머지되지 않은 가지에서 잰 값을 문서에 사실로 적지 않는다.** 그 가지가
  안 들어가면 문서만 남아 거짓이 된다. 재고 싶으면 재되, 어디서 쟀는지 같이 적는다.
- **PR 을 키우지 않는다.** 한 PR 은 한 가지를 한다.

## 조용히 깨지는 자리

이 저장소에는 **다른 파일을 읽는 검사**가 있다. 산문으로 적어 둔 규칙은 한쪽을
고칠 때 나머지가 조용히 거짓이 되므로, 짝을 기계가 본다. 무엇을 고치면 무엇이
깨지는지 알고 시작한다.

| 고치면 | 깨진다 | 무엇을 보나 |
| --- | --- | --- |
| `.github/workflows/cloud-validation.yml` | `test_ci_workflow.py` | 접속 주소와 서비스 컨테이너의 짝, CI 와 compose 의 엔진 판, 두 엔진 실행, 운영 비밀번호 유입 |
| `README.md` 의 절 제목 | `test_readme.py` | 있어야 하는 절이 있는지 |
| 시드(`app/seed.py`)·판정 규칙 | `test_golden_cases.py` | 시드를 통과한 실제 값 전개를 통째로 |
| 마이그레이션·제약 | `test_migrations.py`·`test_live_engine.py` | 앞은 방언별 SQL 문자열, 뒤는 **실제 엔진에서 무는지** |

`test_live_engine.py` 는 `DATABASE_URL` 의 엔진에 붙되 **일회용 데이터베이스를
따로 만들어** 표를 지웠다 다시 만든다. 설정이 가리키는 곳을 그대로 쓰면 로컬에서
한 번 돌리는 것만으로 데이터가 사라지기 때문이다.

`test_golden_cases.py` 는 `reset_database(reference_date)` 로 기준일을 고정해야
성립한다. 안 넘기면 오늘 날짜로 흔들려 박아 둔 숫자가 전부 무의미해진다.

## 이 저장소가 주석을 쓰는 방식

주석과 커밋 메시지는 한국어이고, **무엇을 하는지가 아니라 왜 그런지**를 적는다.
`app/core/config.py` 와 워크플로의 주석이 본보기다 — 왜 두 엔진을 함께 두는지,
왜 창고 목록이 둘로 갈리는지, 왜 BOM 제약을 아직 걸지 않는지를 적는다. 판단이
적혀 있지 않으면 다음 사람이 그 판단을 다시 한다.

같은 이유로, **지키지 않는 규칙을 상수로 적지 않는다**. 적어 두면 지켜지는 것처럼
보이기 때문이다(`BOM_LEVELS` 주석 참고).

## 절차 문서는 아티팩트에 있다

이 저장소를 만드는 **절차** 자체가 따로 관리된다. 코드에 손대기 전에 허브를 본다.

- 허브 — **파이프라인 조기경보** https://claude.ai/code/artifact/bbb2fc87-6daf-4075-a27e-3f2d5d0798a1
  실행 목록과 완료선이 여기 있다. 상태는 **허브에만** 산다.
- 세 레인과 아홉 문턱 https://claude.ai/code/artifact/fe9d6b9c-ea26-4e9c-87ab-2de67942e796
- 파이프라인 문턱 도면 https://claude.ai/code/artifact/5698bb1e-47b4-4c16-8e87-f79369b67822
- 라운드 계기판 https://claude.ai/code/artifact/7999cda4-de48-4714-b469-92b152be51a5
- 지금 도는 파이프라인 https://claude.ai/code/artifact/d1ac383f-df1f-4116-bf7e-8d256df2bd17
- 조기경보 ERP 설계도 https://claude.ai/code/artifact/7c4ef005-f388-459e-ae6c-87041b1b7745

자식은 다섯을 넘기지 않는다. 나누는 기준은 크기가 아니라 **수명** 이다 — 둘이 늘
같은 편집에서 바뀌면 한 문서다.

## 세션을 새로 열었다면

대화 맥락이 아니라 이 파일과 허브가 원본이다. 순서대로:

1. 이 파일.
2. 허브의 실행 목록과 완료선 — 지금 무엇을 할 차례인지는 거기 있다.
3. `git log --oneline -10 origin/main` 과 열린 PR.

여기까지 읽고 이어갈 수 없으면 허브가 불완전한 것이다. 코드를 고치기 전에
**허브를 먼저 고친다.**
