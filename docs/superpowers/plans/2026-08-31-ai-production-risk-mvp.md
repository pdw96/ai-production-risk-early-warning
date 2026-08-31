# AI 생산 리스크 조기경보·일일 운영 브리핑 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 합성 제조 데이터를 이용해 납기·자재 리스크와 일일 권장 조치를 제공하고 상태 변경을 영속화하는 로컬 웹 MVP를 구축한다.

**Architecture:** FastAPI 서비스 계층이 SQLAlchemy SQLite 데이터를 계산해 일관된 API를 제공하고, Next.js App Router가 해당 API만 호출해 통제실형 운영 화면을 렌더링한다. 리스크 상태는 결정적 리스크 키로 `risk_statuses`에 저장하며, 계산된 리스크와 조합해 표시한다.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, SQLite, Pandas, pytest, Next.js, TypeScript, Tailwind CSS, Recharts

**Spec:** `docs/superpowers/specs/2026-08-31-ai-production-risk-mvp-design.md`

## Global Constraints

- 실제 회사·제품·거래처·수치 대신 가상의 소재 제조공장 합성 데이터만 사용한다.
- 합성 데이터는 실행 당일 기준으로 생성하며 고정 시드로 같은 날짜에 재현 가능해야 한다.
- 프론트엔드는 FastAPI API만 호출하고 데이터 JSON을 직접 하드코딩하지 않는다.
- 납기·자재 계산 규칙은 상수와 순수 함수로 분리하고 pytest로 검증한다.
- 위험 상태는 색상뿐 아니라 텍스트 라벨과 아이콘을 제공한다.
- Python은 snake_case, 타입 힌트, async I/O 원칙을 따른다.
- Docker, LOT/FIFO, 품질·설비, 실제 LLM API는 구현하지 않는다.

---

## 파일 구조

```text
backend/
  app/
    api/routes.py               # 모든 MVP HTTP 엔드포인트
    core/config.py              # DB 경로·계산 상수
    db/base.py                  # SQLAlchemy 엔진·세션·Base
    db/models.py                # ORM 모델
    schemas/contracts.py        # Pydantic API 계약
    services/order_risk.py      # 납기 계산 순수 함수
    services/material_risk.py   # 14일 자재 수급 순수 함수
    services/briefing.py        # DB 조회·대시보드·리스크 조합
    main.py                     # FastAPI 앱·예외 처리·CORS
    seed.py                     # 데이터베이스 재생성·합성 데이터
  tests/
    test_order_risk.py
    test_material_risk.py
    test_api.py
  requirements.txt
frontend/
  app/layout.tsx                # 공통 쉘·네비게이션
  app/page.tsx                  # 대시보드
  app/orders/page.tsx           # 오더 화면
  app/orders/[orderId]/page.tsx # 오더 상세
  app/materials/page.tsx        # 자재 화면
  app/risks/page.tsx            # 리스크 보드
  components/*.tsx              # 표·카드·배지·상태 화면·차트
  lib/api.ts                    # 타입과 FastAPI 클라이언트
  package.json
README.md
```

### Task 1: 백엔드 프로젝트 골격 및 데이터 모델

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/db/base.py`
- Create: `backend/app/db/models.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Produces: `Base`, `SessionLocal`, `create_all()`, `Product`, `Order`, `DailyProduction`, `Material`, `BomRequirement`, `PurchaseReceipt`, `RiskStatus` ORM 모델.

- [ ] **Step 1: 실패하는 모델 관계 테스트 작성**

```python
def test_order_has_product_and_daily_productions(session: Session) -> None:
    product = Product(code="FG-01", name="가상 소재 A")
    order = Order(order_number="MO-001", product=product, due_date=date.today(), planned_quantity=100)
    order.daily_productions.append(DailyProduction(work_date=date.today(), planned_quantity=20, actual_quantity=18))
    session.add(order)
    session.commit()
    assert session.query(Order).one().product.code == "FG-01"
```

- [ ] **Step 2: 테스트가 모델 부재로 실패하는지 확인**

Run: `cd backend; pytest tests/test_models.py -v`

- [ ] **Step 3: 최소 SQLAlchemy 모델과 SQLite 세션 구현**

```python
class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(unique=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    due_date: Mapped[date]
    planned_quantity: Mapped[float]
```

- [ ] **Step 4: 모델 테스트 통과 확인**

Run: `cd backend; pytest tests/test_models.py -v`

### Task 2: 납기 위험 순수 계산 함수

**Files:**
- Create: `backend/app/services/order_risk.py`
- Create: `backend/tests/test_order_risk.py`
- Modify: `backend/app/core/config.py`

**Interfaces:**
- Produces: `calculate_order_risk(planned_quantity: float, actual_quantity: float, average_daily_output: float, due_date: date, reference_date: date) -> OrderRiskResult`.

- [ ] **Step 1: 위험·주의·정상·0 생산량의 실패 테스트 작성**

```python
def test_marks_order_danger_when_estimated_completion_is_after_due_date() -> None:
    result = calculate_order_risk(100, 40, 10, date(2026, 9, 2), date(2026, 8, 31))
    assert result.severity == "위험"
    assert result.estimated_completion_date == date(2026, 9, 6)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend; pytest tests/test_order_risk.py -v`

- [ ] **Step 3: 상수와 순수 계산 구현**

```python
WARNING_BUFFER_DAYS = 1

def calculate_order_risk(...) -> OrderRiskResult:
    remaining_quantity = max(planned_quantity - actual_quantity, 0)
    if average_daily_output <= 0 and remaining_quantity > 0:
        return OrderRiskResult(severity="위험", estimated_completion_date=None, ...)
    estimated_completion_date = reference_date + timedelta(days=ceil(remaining_quantity / average_daily_output))
    severity = "위험" if estimated_completion_date > due_date else "주의" if (due_date - reference_date).days <= WARNING_BUFFER_DAYS else "정상"
```

- [ ] **Step 4: 단위 테스트 통과 확인**

Run: `cd backend; pytest tests/test_order_risk.py -v`

### Task 3: 14일 자재 수급 순수 계산 함수

**Files:**
- Create: `backend/app/services/material_risk.py`
- Create: `backend/tests/test_material_risk.py`

**Interfaces:**
- Produces: `calculate_material_risk(current_stock: float, safety_stock: float, daily_demands: Mapping[date, float], scheduled_receipts: Mapping[date, float], reference_date: date, horizon_days: int = 14) -> MaterialRiskResult`.

- [ ] **Step 1: 입고 반영·안전재고 미만·소진의 실패 테스트 작성**

```python
def test_receipt_arriving_before_demand_prevents_stockout() -> None:
    result = calculate_material_risk(20, 10, {date(2026, 9, 1): 15, date(2026, 9, 2): 15}, {date(2026, 9, 2): 30}, date(2026, 9, 1))
    assert result.stockout_date is None
    assert result.shortage_expected is False
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend; pytest tests/test_material_risk.py -v`

- [ ] **Step 3: 일자별 입고 우선·수요 차감 시뮬레이션 구현**

```python
for offset in range(horizon_days):
    day = reference_date + timedelta(days=offset)
    stock += scheduled_receipts.get(day, 0)
    stock -= daily_demands.get(day, 0)
    if stock <= 0 and stockout_date is None:
        stockout_date = day
```

- [ ] **Step 4: 단위 테스트 통과 확인**

Run: `cd backend; pytest tests/test_material_risk.py -v`

### Task 4: 합성 데이터 초기화와 재현성 검증

**Files:**
- Create: `backend/app/seed.py`
- Create: `backend/tests/test_seed.py`

**Interfaces:**
- Consumes: Task 1 ORM 모델.
- Produces: `reset_database(reference_date: date | None = None) -> None`, CLI `python -m app.seed`.

- [ ] **Step 1: 최소 규모·상태 분포의 실패 테스트 작성**

```python
def test_seed_creates_required_minimum_records(session: Session) -> None:
    reset_database(date(2026, 8, 31))
    assert session.query(Product).count() == 5
    assert session.query(Order).count() == 30
    assert session.query(Material).count() == 15
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend; pytest tests/test_seed.py -v`

- [ ] **Step 3: 고정 시드·당일 기준 합성 데이터 생성 구현**

```python
seed_value = 20260831 + int(reference_date.strftime("%Y%m%d"))
rng = random.Random(seed_value)
```

- [ ] **Step 4: 초기화 테스트 통과 및 같은 기준일 결과 일치 확인**

Run: `cd backend; pytest tests/test_seed.py -v`

### Task 5: FastAPI 계약·조회·상태 변경 API

**Files:**
- Create: `backend/app/schemas/contracts.py`
- Create: `backend/app/services/briefing.py`
- Create: `backend/app/api/routes.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: Task 1~4 모델·계산·시드.
- Produces: 명세의 6개 `/api/*` 엔드포인트와 `{ "data": ... }` 응답.

- [ ] **Step 1: 대시보드·상세 404·상태 영속 PATCH의 실패 API 테스트 작성**

```python
def test_patch_risk_status_persists_after_followup_get(client: TestClient) -> None:
    risk = client.get("/api/risks").json()["data"][0]
    updated = client.patch(f"/api/risks/{risk['risk_id']}/status", json={"status": "확인 중"})
    assert updated.status_code == 200
    found = next(item for item in client.get("/api/risks").json()["data"] if item["risk_id"] == risk["risk_id"])
    assert found["status"] == "확인 중"
```

- [ ] **Step 2: API 테스트 실패 확인**

Run: `cd backend; pytest tests/test_api.py -v`

- [ ] **Step 3: 서비스·Pydantic 스키마·라우터 구현**

```python
@router.patch("/risks/{risk_id}/status")
def update_risk_status(risk_id: str, payload: RiskStatusUpdate, session: Session = Depends(get_session)) -> Envelope[RiskResponse]:
    return Envelope(data=briefing_service.update_risk_status(session, risk_id, payload.status))
```

- [ ] **Step 4: API 테스트 및 수동 HTTP 응답 통과 확인**

Run: `cd backend; pytest -v`

### Task 6: Next.js 기본 구성과 API 클라이언트

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/app/globals.css`
- Create: `frontend/app/layout.tsx`
- Create: `frontend/lib/api.ts`

**Interfaces:**
- Consumes: Task 5 API JSON.
- Produces: `getDashboard`, `getOrders`, `getOrder`, `getMaterials`, `getRisks`, `updateRiskStatus` 및 공통 레이아웃.

- [ ] **Step 1: API 클라이언트 실패 테스트 작성**

```typescript
it("throws the API detail for a failed response", async () => {
  mockFetch({ ok: false, status: 500, json: async () => ({ detail: "서버 오류" }) });
  await expect(requestData("/api/dashboard")).rejects.toThrow("서버 오류");
});
```

- [ ] **Step 2: 테스트가 클라이언트 부재로 실패하는지 확인**

Run: `cd frontend; npm test -- api.test.ts`

- [ ] **Step 3: 최소 API 클라이언트·타입·통제실 레이아웃 구현**

```typescript
export async function requestData<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { cache: "no-store" });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail ?? "API 요청에 실패했습니다.");
  return body.data as T;
}
```

- [ ] **Step 4: 테스트와 TypeScript 검사 통과 확인**

Run: `cd frontend; npm test -- api.test.ts; npm run lint`

### Task 7: 대시보드와 공통 표시 컴포넌트

**Files:**
- Create: `frontend/components/status-badge.tsx`
- Create: `frontend/components/kpi-card.tsx`
- Create: `frontend/components/production-trend-chart.tsx`
- Create: `frontend/components/data-state.tsx`
- Create: `frontend/app/page.tsx`

**Interfaces:**
- Consumes: Task 6 `getDashboard`와 API 타입.
- Produces: KPI 링크, 7일 차트, 위험 상위 5건, 권장 조치 UI.

- [ ] **Step 1: 위험 배지가 아이콘·텍스트를 모두 렌더링하는 실패 테스트 작성**

```typescript
it("renders icon and Korean severity label", () => {
  render(<StatusBadge severity="위험" />);
  expect(screen.getByText("위험")).toBeInTheDocument();
  expect(screen.getByLabelText("위험 상태")).toBeInTheDocument();
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd frontend; npm test -- status-badge.test.tsx`

- [ ] **Step 3: 대시보드 컴포넌트와 로딩·오류·빈 상태 구현**

```tsx
<Link href="/orders"><KpiCard label="납기 위험 오더" value={dashboard.kpis.due_risk_order_count} /></Link>
<ProductionTrendChart data={dashboard.production_trend} />
```

- [ ] **Step 4: 컴포넌트 테스트 및 프로덕션 빌드 통과 확인**

Run: `cd frontend; npm test; npm run build`

### Task 8: 오더·자재·리스크 화면과 상태 변경 연결

**Files:**
- Create: `frontend/app/orders/page.tsx`
- Create: `frontend/app/orders/[orderId]/page.tsx`
- Create: `frontend/app/materials/page.tsx`
- Create: `frontend/app/risks/page.tsx`
- Create: `frontend/components/order-table.tsx`
- Create: `frontend/components/material-table.tsx`
- Create: `frontend/components/risk-board.tsx`

**Interfaces:**
- Consumes: Task 6 API 클라이언트, Task 7 상태·데이터 상태 컴포넌트.
- Produces: 명세의 모든 화면과 DB 영속 상태 변경 UX.

- [ ] **Step 1: 리스크 상태 저장 후 갱신의 실패 UI 테스트 작성**

```typescript
it("updates a risk after the status API succeeds", async () => {
  render(<RiskBoard risks={[sampleRisk]} onUpdate={mockUpdate} />);
  await userEvent.selectOptions(screen.getByLabelText("RISK-ORDER-001 상태"), "조치 완료");
  expect(mockUpdate).toHaveBeenCalledWith("RISK-ORDER-001", "조치 완료");
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd frontend; npm test -- risk-board.test.tsx`

- [ ] **Step 3: 목록·상세·상태 변경 UI 구현**

```tsx
await updateRiskStatus(riskId, status);
setRisks(await getRisks());
```

- [ ] **Step 4: 전체 프론트 테스트·빌드 통과 확인**

Run: `cd frontend; npm test; npm run build`

### Task 9: 실행 문서화와 종단 간 검증

**Files:**
- Create: `README.md`
- Modify: `backend/app/seed.py`
- Modify: `frontend/.env.example`
- Create: `backend/tests/test_readme.py`

**Interfaces:**
- Consumes: 완성된 백엔드·프론트엔드.
- Produces: 다른 사용자가 DB 초기화, API·웹 실행, 테스트를 할 수 있는 한국어 README.

- [ ] **Step 1: README에 요구된 섹션을 검사하는 실패 문서 테스트 작성**

```python
def test_readme_documents_local_run_and_limitations() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    assert "샘플 데이터 초기화" in content
    assert "합성 데이터 기반 데모" in content
```

- [ ] **Step 2: 문서 테스트 실패 확인**

Run: `cd backend; pytest tests/test_readme.py -v`

- [ ] **Step 3: 설치·초기화·실행·테스트·한계·확장 계획 작성**

```markdown
cd backend
python -m venv .venv
.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
python -m app.seed
uvicorn app.main:app --reload --port 8000
```

- [ ] **Step 4: 문서 테스트와 실제 종단 간 검증 통과 확인**

Run: `cd backend; pytest -v`

Run: `cd frontend; npm run build`

Run: `Invoke-WebRequest http://127.0.0.1:8000/api/dashboard | Select-Object -Expand Content`

## 계획 자체 점검

- 명세의 데이터 규모, 6개 API, 4개 화면, 판정 규칙, 상태 영속, 오류/로딩/빈 상태, README 필수 항목은 각각 Task 1~9에 배정했다.
- 미결 표기나 모호한 후속 작업 표현은 포함하지 않았다.
- 모든 API와 화면이 앞선 작업의 명시된 인터페이스만 소비하도록 구성했다.
