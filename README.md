# AI 생산 리스크 조기경보 MVP

가상의 소재 제조공장 데이터를 이용해 생산관리자가 납기, 자재, 오늘의 조치를 한 화면에서 확인하는 로컬 실행 데모입니다. 이 저장소에는 실제 회사·제품·거래처·운영 수치나 개인 경험을 사용하지 않았습니다.

## 문제 정의

생산 계획과 실적, 재고와 예정 입고가 흩어져 있으면 납기 지연과 자재 부족을 조기에 발견하기 어렵습니다. 이 MVP는 결정적인 계산 규칙으로 위험 근거를 표시하고, 담당자가 리스크 상태를 `신규` → `확인 중` → `조치 완료`로 기록할 수 있게 합니다.

## 설계 착안점

실제 생산관리 화면에서 유용한 밀도 높은 통제실형 정보 구조를 참고해 KPI, 납기 오더, 14일 자재 전망, 권장 조치를 연결했습니다. 특정 기업의 화면이나 실제 업무 프로세스를 복제한 것이 아니라, 운영 의사결정에 필요한 정보 흐름을 합성 데이터로 표현한 설계입니다.

## 아키텍처

Next.js App Router 프론트엔드는 `NEXT_PUBLIC_API_BASE_URL`의 FastAPI만 호출합니다. FastAPI 라우터는 조회·상태 변경을 제공하고, 서비스 계층의 순수 함수가 납기·자재 리스크를 계산하며, SQLAlchemy가 SQLite를 영속화합니다.

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
- **Docker**: 백엔드·프론트엔드·영속 볼륨을 컨테이너로 묶어 팀 단위 재현 환경을 제공합니다.
