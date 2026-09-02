# LOT/FIFO 자재 가용성 구현 프롬프트 (2026-09-02)

이 문서는 새 세션에 그대로 붙여넣어 작업을 시작하기 위한 실행 프롬프트입니다.
"현황" 절의 코드 사실은 2026-09-02에 저장소 파일을 직접 읽어 확인한 **실측**이며,
사용자와 합의된 항목은 **결정**, 아직 확인되지 않은 것은 **미검증**/**추정**으로
표기했습니다. 맨 끝에 정렬 게이트 채점표를 그대로 붙여 두었습니다.

**개정 이력**
- 2026-09-02 최초 작성 (게이트 16/18 통과)
- 2026-09-02 개정: 창고 구분(원재료/생산)과 로트 부분 이동을 범위에 편입.
  재고이동 트랜잭션·완제품 로트·출하 리스크는
  [`2026-09-02-warehouse-erp-followup.md`](./2026-09-02-warehouse-erp-followup.md)
  로 분리.

---

README `향후 확장 계획`의 첫 항목인 **LOT/FIFO**를 구현한다. 조사는 아래에 이미
끝나 있으니 다시 훑지 말고 **1단계부터 바로 시작**하면 된다.

> README 원문: "**LOT/FIFO**: 로트별 입고·유효기간과 FIFO 출고를 모델링해 자재
> 가용성을 정교화합니다."

## 현황 (2026-09-02 실측)

### 지금 자재 가용성이 계산되는 경로

```
Material.current_stock (스칼라)  ┐
PurchaseReceipt(예정 입고)       ├→ briefing._build_material_response
DailyProduction × BomRequirement ┘        ↓
                          material_risk.calculate_material_risk
                                          ↓
                    MaterialResponse → /api/materials → MaterialTable
```

`backend/app/services/material_risk.py:24`

```python
def calculate_material_risk(
    current_stock: float,
    safety_stock: float,
    daily_demands: Mapping[date, float],
    scheduled_receipts: Mapping[date, float],
    reference_date: date,
    horizon_days: int = 14,
) -> MaterialRiskResult:
```

입력이 **날짜 → 수량 Mapping**이라 로트 단위 상태도, 보관 위치도 표현할 방법이
없다. 즉 이 시그니처는 유지할 수 없고 **바꿔야 한다**(아래 2단계).

### 지금 모델에 없는 것 (실측)

`backend/app/db/models.py` 기준: 로트 테이블 없음, 유효기간 컬럼 없음, **창고/보관
위치 개념 없음**. 재고는 `Material.current_stock` 단일 스칼라, 입고는
`PurchaseReceipt(material_id, scheduled_date, scheduled_quantity)` 뿐이다.

### ⚠️ 함정 ① 마이그레이션이 없다 — 스키마 변경 = 전면 재시드

`backend/app/seed.py:29` `reset_database()` 는 `drop_all → create_all` 이다.
Alembic 같은 마이그레이션 도구는 저장소에 없다(실측).

그리고 `backend/docker-entrypoint.sh` 는 **DB 파일이 없을 때만** 시드한다.

```sh
if [ ! -f "$database_path" ]; then
  python -m app.seed
else
  echo "기존 SQLite 데이터를 사용합니다: $database_path"
fi
```

따라서 `backend-data` 볼륨이 이미 있는 사용자는 새 컬럼이 없는 구 스키마를 그대로
들고 기동해 **런타임에 깨진다.** 이건 자동 감지로 해결하지 않기로 **결정**했다
(결정 3). README에 재시드 절차를 안내하는 것으로 끝낸다.

> 부수 효과: 스키마 retrofit 비용이 사실상 0이다. 그래서 "나중에 바꾸면 비싸니
> 지금 넣자"는 논거는 이 저장소에서 성립하지 않는다. 창고를 지금 넣는 이유는
> 비용이 아니라 **가용 재고의 정의가 비어 있기 때문**이다(결정 5).

### ⚠️ 함정 ② `test_readme.py` 가 README 문구에 묶여 있다

`backend/tests/test_readme.py` 는 README에 아래 문자열이 존재하는지 단언한다.

```python
required_sections = (..., "LOT/FIFO", "품질·설비", "AI 브리핑", "Docker")
```

LOT/FIFO를 `향후 확장 계획`에서 빼면 **이 테스트가 깨진다.** 구현 완료 후에도
`LOT/FIFO` 라는 문자열은 README 어딘가(판정 규칙의 섹션 제목)에 남겨야 한다.

### ⚠️ 함정 ③ 시드에는 깨지면 안 되는 불변식이 있다

`seed.py` 끝에서 납기 심각도가 `{"정상", "주의", "위험"}` 3종을 모두 만들지
못하면 `RuntimeError` 를 던진다. `test_seed.py` 도 같은 것을 단언한다.
로트를 넣으면서 자재 수요/재고 구성을 건드리면 이 불변식이 깨질 수 있다.
**미검증** — 로트 도입 후 3종이 유지되는지는 실제로 돌려봐야 안다.

### ⚠️ 함정 ④ 합성 데이터 원칙

README 첫 문단의 "실제 회사·제품·거래처·운영 수치나 개인 경험을 사용하지
않았습니다"는 비협상 조건이다. 로트번호·유효기간·창고명도 합성 규칙으로만 만든다.

## 결정 사항 (사용자 확인됨)

1. **완료 조건 = 화면까지.** 자재 화면에서 로트별 재고·유효기간·FIFO 소진 근거를
   눈으로 확인할 수 있어야 한다. 백엔드 테스트 + 프론트엔드 테스트 + README 갱신
   포함. **CI 스크린샷 검증은 범위 밖.**
2. **로트가 재고의 유일한 출처.** 사용자가 확인한 수식:

   ```
   available(day) = Σ lot.qty  where lot.received ≤ day < lot.expiry
   출고: expiry 빠른 순(FIFO) 차감
   유효기간 경과분은 폐기 처리 → 부족 판정에 반영
   ```

   `expiry` 당일은 **가용하지 않다**(`day < lot.expiry`). 기존 판정 결과가
   바뀌는 것을 감수한다.
3. **재시드 전제, 안내만.** Alembic 도입하지 않는다. 기존 DB는
   `python -m app.seed` / `docker compose down -v` 로 다시 만들며, 리스크 상태가
   사라진다는 점을 README에 명시한다.
4. **범위 밖(명시적 제외):** 품질·설비, AI 브리핑, Alembic, CI 스크린샷 검증.
5. **창고 구분을 범위에 포함한다** (2026-09-02 개정). 사용자 발화: "창고
   구분(원재료 창고, 생산창고, 완제품 창고), 창고 내 이동 시 (…) 50EA 재고이동
   처리". 이 중 **이번 범위는 위치 차원과 로트 부분 보유까지**이고, 이동 처리
   워크플로·완제품·출하는 후속 문서로 분리했다(아래 "후속으로 분리한 것").

### 출고 순서에 대한 주석

사용자가 확인한 규칙은 "expiry 빠른 순"이므로 엄밀히는 **FEFO**
(First-Expired-First-Out)다. 유효기간이 같거나 없으면 입고일 빠른 순(FIFO)으로
낙차를 준다. 기능 이름은 README와 일관되게 LOT/FIFO로 두되, **정렬 키가
유효기간 우선이라는 사실을 README 판정 규칙에 명시**한다. 이렇게 정한 이유는
폐기를 최소화하는 순서라야 "유효기간 경과분 폐기가 부족 판정에 반영된다"는
결정 2번과 모순이 없기 때문이다.

## 창고 차원 (2026-09-02 개정)

### 이번 범위에 넣는 이유

기존 프롬프트의 `available(day)` 에는 **위치 개념이 없어서** "어느 창고에 있는
재고가 가용인가"가 정의되지 않은 채 남아 있었다. 이건 LOT/FIFO 판정 자체의
정확성 문제라 이번 범위다.

### 가용 규칙 (**추정** — 사용자 확인 없이 정한 가정)

**원재료창고 + 생산창고의 로트를 모두 가용으로 본다.**

수요는 생산계획(`DailyProduction.planned_quantity` × BOM)에서 나온다. 이미
생산창고로 옮겨 둔 자재를 가용에서 빼면 **정상 상황이 부족으로 오판된다**(자재를
라인 옆에 대 놨다는 이유로 부족 경보가 뜬다). 그래서 두 창고를 합산한다.
창고별 내역은 화면에서 구분해 보여주되 **판정 수치에는 영향을 주지 않는다.**

> 이 가정이 틀렸다면(예: 생산창고 이동분은 이미 특정 오더에 확정 배정된 것으로
> 보고 가용에서 제외해야 한다면) 2단계 계산 함수의 입력 필터만 바꾸면 된다.

### 완제품창고를 넣지 않는 이유

완제품은 `Material` 이 아니라 `Product` 다. 완제품 로트는 새 엔티티
(`FinishedGoodsLot`)와 생산 실적↔로트 연결이 필요하고, 그게 있어야 출하 리스크가
성립한다. `MaterialLot.warehouse` 의 값 집합은 **`원재료창고`, `생산창고` 둘뿐**으로
둔다. 이 선이 이번 범위와 후속을 가르는 자연스러운 경계다.

### 로트 부분 이동을 표현하는 방법

"원재료창고의 100EA 로트에서 50EA를 생산창고로 이동" 은 **같은 로트번호가 두
창고에 나뉘어 존재**하는 상태다. 따라서:

- 로트 유일키는 `lot_number` 가 아니라 **`(lot_number, warehouse)` 복합 unique**
- 수요 차감은 이미 부분 차감이므로 계산 로직 자체는 그대로다
- **이동 트랜잭션(이력·API·화면)은 이번 범위가 아니다.** 시드가 이미 나뉘어 있는
  상태를 만들고, 그 결과를 화면에서 보는 데까지만 한다

## 후속으로 분리한 것

`docs/2026-09-02-warehouse-erp-followup.md` 참조. 요약:

| 주제 | 왜 후속인가 |
|---|---|
| 재고이동 트랜잭션 (이동 이력·처리 화면) | 현재 앱에 쓰기 경로가 `PATCH /api/risks/{id}/status` 하나뿐이다. 쓰기 워크플로 도입은 별개 주제 |
| 완제품 로트 부여 + 완제품창고 | `Product` 쪽 새 엔티티, 생산 실적↔로트 연결 필요 |
| 출하 일정 대비 완제품 부족 + 대책 | 납기·자재에 이은 **세 번째 리스크 타입**. 기존 납기 리스크와 개념이 겹쳐 통합 설계가 선행돼야 함 |

## 작업 순서

### 1단계 — 모델

`backend/app/db/models.py`

- `MaterialLot` 추가
  - `id`, `material_id`(FK), `lot_number`, `warehouse`, `quantity`,
    `received_date`, `expiry_date`(nullable — 유효기간 없는 자재 허용)
  - `warehouse` 는 `"원재료창고" | "생산창고"` 문자열. `UniqueConstraint`
    `(lot_number, warehouse)`
- `Material.current_stock` 은 **컬럼에서 제거**하고 로트 합계에서 파생시킨다
  (결정 2: 로트가 유일한 출처). `safety_stock` 은 그대로 둔다.
- `PurchaseReceipt` 에 `expiry_date`(nullable) 추가 — 예정 입고분도 도착하면
  로트가 되므로 유효기간을 가져야 한다. 예정 입고는 **원재료창고로 도착**한다.

### 2단계 — 계산 함수 (핵심)

`backend/app/services/material_risk.py` 를 로트 기반으로 다시 쓴다.

```python
Warehouse = Literal["원재료창고", "생산창고"]

@dataclass(frozen=True)
class Lot:
    lot_number: str
    warehouse: Warehouse
    quantity: float
    received_date: date
    expiry_date: date | None

@dataclass(frozen=True)
class MaterialRiskResult:
    available_stock: float              # 기준일 가용 재고(만료분 제외, 두 창고 합)
    stock_by_warehouse: dict[Warehouse, float]
    ending_stock: float
    minimum_stock: float
    shortage_expected: bool
    stockout_date: date | None
    expiring_quantity: float            # 14일 내 폐기 예정 총량
    first_expiry_date: date | None
```

일별 루프 순서(기존 "입고를 수요 차감보다 먼저" 규칙 유지):

1. **입고** — `received_date == day` 인 로트를 풀에 추가
2. **폐기** — `expiry_date == day` 인 잔량을 풀에서 제거하고 `expiring_quantity`
   에 누적 (`day < expiry` 가 가용 조건이므로 당일 아침에 빠진다)
3. **출고** — 그날 수요를 아래 순서로 차감(부분 차감 허용):
   `expiry_date asc` → `received_date asc` → `생산창고 우선`.
   `expiry_date is None` 은 가장 뒤로.
   *생산창고를 먼저 쓰는 이유: 이미 라인 옆에 대 놓은 재고를 두고 원재료창고를
   먼저 헐면 현실에서 다시 이동이 생긴다.*
4. **집계** — `minimum_stock`, `safety_stock` 미만 여부, 잔량 ≤ 0이면 최초 소진일

`stock_by_warehouse` 는 **기준일 시점 스냅샷**이다(표시용). 판정 수치는 두 창고
합계로만 낸다(창고 가용 규칙 참조).

기존 테스트 3개(`test_material_risk.py`)의 **의미는 보존**한다: 입고가 수요보다
먼저 반영되어 소진을 막는 케이스, 소진 없이 안전재고만 하회하는 케이스,
당일 0 도달을 소진으로 보는 케이스. 입력만 로트 형태로 바꿔 다시 쓴다.

### 3단계 — 서비스·계약

- `briefing._build_material_response`: 로트를 읽어 계산 함수에 넘기고,
  `current_stock` 은 `result.available_stock` 으로 채운다(응답 필드명은 유지해
  프론트 호환을 지킨다).
- `MaterialResponse` 에 추가: `expiring_quantity`, `first_expiry_date`,
  `raw_warehouse_stock`, `production_warehouse_stock`,
  `lots: list[MaterialLotResponse]`.
- `MaterialLotResponse`: `lot_number`, `warehouse`, `quantity`, `received_date`,
  `expiry_date`, `state`(`"가용"` / `"예정 입고"` / `"기간 내 폐기"` / `"만료"`).
- 판정 문구에 폐기 원인을 추가한다. 예: 소진일이 있고 `expiring_quantity > 0`
  이면 `"유효기간 경과 폐기 N으로 YYYY-MM-DD에 소진될 전망입니다."`,
  권장 조치는 `"폐기 임박 로트를 우선 소진하도록 생산 순서를 조정하세요."`

### 4단계 — 시드

`backend/app/seed.py`

- 자재마다 로트 2~4건을 합성한다. 로트번호는 `LOT-{자재코드}-{연번}` 형태.
- **최소 1개 자재는 같은 로트번호가 원재료창고/생산창고에 나뉘어** 있게 만든다
  (예: `LOT-RM-03-01` 이 원재료창고 60 / 생산창고 40). 부분 이동 결과가 화면에
  보이는 것이 목적이다.
- 유효기간은 기준일 기준 상대 오프셋으로 흩뿌리되, **최소 1개 자재는 14일 안에
  폐기가 발생해 부족 판정이 되도록** 고정한다(현재 `materials[0]` 을
  `safety_stock + 1.0` 으로 고정해 둔 것과 같은 방식).
- 예정 입고에도 유효기간을 부여한다(도착지는 원재료창고).
- 기존 납기 심각도 3종 불변식(`RuntimeError` 가드)은 **그대로 유지**하고,
  자재 쪽에도 같은 성격의 가드를 추가한다: (a) 폐기로 인한 부족이 최소 1건,
  (b) 두 창고에 걸친 로트가 최소 1건.

### 5단계 — 화면

`frontend/lib/api.ts` 타입 확장 후 `frontend/components/material-table.tsx`:

- 컬럼 추가: `창고별 재고`(원재료/생산 두 값), `폐기 예정`, `최초 유효기간`
- 자재 셀 안에 `<details><summary>로트 N건</summary>` 로 로트 목록(번호·**창고**·
  수량·입고일·유효기간·상태)을 펼치게 한다. **JS 상태 없이** 동작하므로 기존
  컴포넌트 스타일(순수 렌더링)과 테스트 방식을 유지할 수 있다.

### 6단계 — 테스트

- `test_material_risk.py`: FIFO/FEFO 차감 순서, **동일 유효기간일 때 생산창고
  우선 차감**, 유효기간 당일 제외(`day < expiry`), 폐기가 원인이 된 소진,
  기존 3케이스 재작성
- `test_models.py`: `MaterialLot` 관계, `(lot_number, warehouse)` 복합 unique
- `test_seed.py`: 로트 건수, 로트 합계 = 가용 재고, 폐기 유발 부족 1건 이상,
  두 창고에 걸친 로트 1건 이상, **기존 납기 3종 불변식이 여전히 통과하는지**(함정 ③)
- `test_api.py`: `/api/materials` 응답에 `lots` 와 창고별 재고 포함
- `frontend/components/material-table.test.tsx`: 로트 행·창고·폐기 예정 렌더링
- 실행: `python -m pytest tests -v`, `npm test`, `npm run lint`, `npm run build`

### 7단계 — README

- `데이터 모델`: `material_lots` 추가(창고 포함), `materials` 에서
  `current_stock` 제거 설명
- `판정 규칙`: `### 14일 안전재고` 를 **LOT/FIFO 기반**으로 개정하고,
  출고 순서가 유효기간 우선이라는 점, `day < expiry` 경계, **원재료창고와
  생산창고 재고를 모두 가용으로 본다**는 규칙을 명시
- `향후 확장 계획`: LOT/FIFO 항목을 완료로 옮기되 **`LOT/FIFO` 문자열은 반드시
  README에 남긴다**(함정 ②). 대신 후속 항목 3개(재고이동 처리, 완제품 로트·
  완제품창고, 출하 리스크)를 확장 계획에 추가한다
- 재시드 안내: 스키마가 바뀌었으므로 기존 로컬 DB는 `python -m app.seed`,
  도커는 `docker compose down -v` 로 다시 만들어야 하며 **리스크 상태가
  사라진다**는 점을 명시(결정 3)

## 완료 판정 체크리스트

- [ ] 자재 화면에서 로트별 수량·**창고**·유효기간·상태가 보인다
- [ ] 같은 로트가 두 창고에 나뉘어 있는 사례가 화면에서 확인된다
- [ ] 유효기간 폐기로 부족해지는 자재가 화면에 판정 근거와 함께 뜬다
- [ ] `python -m pytest tests -v` 전부 통과 (README 테스트 포함)
- [ ] `npm test`, `npm run lint`, `npm run build` 전부 통과
- [ ] README 판정 규칙이 실제 코드 동작과 일치한다

---

## 채점표 (2026-09-02 개정판, 총점 16/18 통과)

| # | 항목 | 내용 | 점수 | 근거 |
|---|---|---|---|---|
| 1 | 문제 정의와 동기 | 자재 가용성이 단일 재고 풀 계산이라 만료·미도착 로트를 쓸 수 있는 것처럼 계산하고, 재고가 **어디 있는지**도 표현하지 못한다. README 확장 계획 1순위. | 3 | 사용자가 "로트가 재고의 유일한 출처" 선택으로 확인 + 창고 발화로 보강 |
| 2 | 완료 조건 | 화면까지. 로트별 재고·창고·유효기간·FIFO 소진 근거를 화면에서 확인 + 백/프론트 테스트 + README. | 3 | 사용자 선택: "화면까지" |
| 3 | 범위 경계 | 포함: 모델·계산·API·화면·테스트·README + **창고 차원과 로트 부분 보유**. 제외: 재고이동 트랜잭션, 완제품 로트·완제품창고, 출하 리스크, 품질·설비, AI 브리핑, Alembic, CI 스크린샷. | 3 | 사용자 선택 3건 + "관련 없다면 후속으로, 관련 있으면 프롬프트 개선" 지시. **경계선을 어디에 긋는지는 내 판단**(가정 목록 참조) |
| 4 | 제약과 함정 | 재시드 전제(사용자 명시). 그 외 함정 ②③④는 내 실측. | 2 | 일부만 사용자 발화 |
| 5 | 접근 방식 | 로트 단일 출처 + `day < expiry` + expiry 우선 차감 + 두 창고 합산 가용. 기각: 로트 병행 유지, 유효기간 없는 FIFO만, 완제품창고를 `MaterialLot` 에 넣기. | 3 | 사용자가 수식 프리뷰까지 확인. 창고 합산 규칙은 내 가정 |
| 6 | 사실 근거 상태 | 코드 사실은 전부 실측. 아래 가정 목록으로 라벨링. | 2 | 실측 + 라벨링, 사용자 확인은 없음 |

**게이트: 총점 16 ≥ 14, 2번 3점, 3번 3점, 0점 없음 → 통과**

### 가정 위에 서 있는 것 (나중에 틀린 것으로 드러날 수 있음)

- **생산창고 재고를 가용에 포함한다** — **추정**. 사용자 확인 없음.
  틀렸다면 2단계 입력 필터만 바꾸면 된다
- **동일 유효기간일 때 생산창고를 먼저 차감한다** — **사용자 확인됨**
  (2026-09-02: "동일 유효기간일 때 생산창고 우선 차감이 맞지")
- **창고는 이번 범위, 이동 처리·완제품·출하는 후속** 이라는 경계선 — **내 판단**.
  사용자는 "관련 있는 것만 반영" 이라는 규칙만 줬고 선 긋기는 위임했다
- 로트를 도입해도 시드의 납기 심각도 3종 불변식이 유지된다 — **미검증**
- `MaterialResponse.current_stock` 필드명을 유지하면 프론트 호환이 깨지지
  않는다 — **추정** (타입만 보고 판단, 실행 확인 안 함)
- 기존 `test_material_risk.py` 3케이스의 의미를 로트 입력으로 그대로 옮길 수
  있다 — **추정**

---

## 구현 완료 기록 (2026-09-02)

7단계 전부 구현했고 아래는 **실측**이다.

| 검증 | 결과 |
|---|---|
| `python -m pytest tests -q` | **44 passed** |
| `npm test` | **22 passed** (8 파일) |
| `npm run lint` (`tsc --noEmit`) | 통과 |
| `npm run build` | 통과 |
| 화면 확인 | `/materials`, `/`, `/risks` 를 headless chromium 으로 렌더해 육안 확인 |

### 완료 판정 체크리스트 결과

- [x] 자재 화면에서 로트별 수량·창고·유효기간·상태가 보인다
- [x] 같은 로트가 두 창고에 나뉘어 있는 사례가 화면에서 확인된다 —
  `LOT-RM-03-01` 이 원재료창고 193.05 / 생산창고 128.7 로 두 행에 나온다
- [x] 유효기간 폐기로 부족해지는 자재가 화면에 판정 근거와 함께 뜬다 —
  RM-05: "유효기간 경과 폐기 972.79으로 2026-09-08에 소진될 전망입니다.",
  권장 조치 "폐기 임박 로트를 우선 소진하도록 생산 순서를 조정하세요."
- [x] 백엔드/프론트엔드 테스트, lint, build 전부 통과
- [x] README 판정 규칙이 실제 코드 동작과 일치한다

### 프롬프트와 달라진 점

1. **`MaterialRiskResult` 에 이월 적자 개념을 넣었다.** 프롬프트에는 없던
   항목이다. 스칼라 재고 시절에는 `stock -= demand` 가 누적되어 미충족 수요가
   음수로 남았는데, 로트 풀로 바꾸면서 그날 못 채운 수요가 다음 날 사라지는
   버그가 생겼다. `deficit` 를 이월하고 뒤늦은 입고가 먼저 갚도록 해서 기존
   의미를 복원했다. 회귀 테스트:
   `test_unmet_demand_carries_over_and_is_paid_by_a_later_receipt`.
2. **`first_expiry_date` 는 14일 밖이면 `None` 이다.** 자재 화면의 판단
   근거라서 지평 밖 유효기간을 보여줄 이유가 없다. 화면에는 "기간 내 없음"으로
   나온다.
3. **시드에서 RM-05 의 예정 입고를 13일 뒤로 고정했다.** 처음에는 폐기 직후
   예정 입고가 도착해 재고를 안전재고 위로 되돌리는 바람에 "폐기로 인한 부족"
   가드가 걸려 시드가 실패했다(실측). RM-01 과 같은 방식으로 입고일을 밀었다.
4. **`available_stock` 은 기준일에 도착하는 예정 입고를 포함한다.** 입고를
   수요 차감보다 먼저 반영하는 기존 규칙의 귀결이다. 그래서
   `material_lots` 행 합계와 화면의 "가용 재고" 가 다를 수 있고, 응답의 로트
   목록에는 그 당일 입고분이 함께 들어 있어 목록 합계와는 일치한다. 처음 쓴
   테스트가 이 차이를 몰라 실패했고, 정확한 불변식
   (`도착했고 만료 안 된 로트의 합 == 가용 재고`)으로 다시 썼다.
5. **CSS 를 두 번 손봤다.** 로트 목록을 세로 그리드로 두니 자재 한 행이 5줄씩
   차지해 화면이 못 볼 수준이 됐다(실측). 한 줄 flex 로 바꾸고, 컬럼이 13개로
   늘면서 `정상`·`부족 예상` 같은 짧은 셀이 줄바꿈되기에 `white-space: nowrap`
   과 `min-width: 1900px` 을 넣었다.

### 이번에 검증된 가정

- 로트 도입 후에도 시드의 납기 심각도 3종 불변식이 유지된다 — **확인됨**
  (`test_seeded_orders_include_normal_caution_and_danger_by_existing_risk_rule` 통과)
- `MaterialResponse.current_stock` 필드명 유지로 프론트 호환이 깨지지 않는다 —
  **확인됨** (기존 테스트와 화면 모두 통과)
- 기존 `test_material_risk.py` 3케이스의 의미를 로트 입력으로 옮길 수 있다 —
  **확인됨** (같은 기대값으로 통과)

### 아직 가정인 것

- **생산창고 재고를 가용에 포함한다** — 사용자가 "생산창고 재고 포함 맞아"로
  확인. 다만 현업 검증은 아니다
- 없음. 생산창고 우선 차감도 2026-09-02 사용자 확인으로 가정에서 빠졌다.
