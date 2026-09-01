# Task 3 보고서: 14일 자재 수급 순수 계산 함수

## 구현 파일

- `backend/app/services/material_risk.py`
  - `MaterialRiskResult` 불변 데이터 클래스
  - `calculate_material_risk(...)` 순수 계산 함수
  - 기준일 포함 `horizon_days` 일자를 순회하며 예정 입고를 수요보다 먼저 반영
  - 첫 재고 0 이하 날짜, 기간 중 최소 재고, 기간 종료 재고, 부족 예상 여부 반환
- `backend/tests/test_material_risk.py`
  - 입고가 다음 수요를 충당해 소진을 방지하는 경우
  - 소진 없이 안전재고 미만이 되는 경우
  - 첫 소진 날짜를 기록하는 경우

## TDD 실행 기록

### RED

명령:

```text
cd backend
python -m pytest tests/test_material_risk.py -v
```

결과: `ModuleNotFoundError: No module named 'app.services.material_risk'`로 수집 실패. 구현 부재에 따른 기대된 RED 상태를 확인했다.

### GREEN

명령:

```text
cd backend
python -m pytest tests/test_material_risk.py -v
```

결과: 3 passed.

회귀 명령:

```text
cd backend
python -m pytest tests/test_order_risk.py tests/test_models.py tests/test_material_risk.py -q
```

결과: 10 passed.

참고로 `python -m pytest -q` 전체 수집은 기존 worktree에 남아 있는 접근 불가 `pytest-cache-files-*` 디렉터리 때문에 PermissionError가 발생했다. 해당 디렉터리는 변경하지 않았고, 명시적 테스트 파일 회귀 실행은 통과했다.

## 자체 검토

- 함수는 외부 상태나 DB를 사용하지 않는 순수 계산 함수다.
- 타입 힌트와 snake_case를 적용했다.
- 시뮬레이션 날짜는 기준일과 기준일 + 13일을 포함한다.
- 동일 날짜의 입고를 수요 차감 전에 적용한다.
- `horizon_days < 1`은 `ValueError`로 거부한다.

## 우려 사항

- 브리프의 입고 회피 예시는 기간 중 일시적으로 안전재고 아래로 내려가지만 `shortage_expected is False`를 기대한다. 따라서 현재 구현은 일시적 하회가 예정 입고로 회복되면 부족으로 확정하지 않고, 소진 또는 기간 종료 재고가 안전재고 미만인 경우를 부족 예상으로 판정한다. API 계층에서 일중 최저 재고를 위험 근거로 표시할 때는 이 정책을 재확인해야 한다.
- 기존 접근 불가 pytest 캐시 디렉터리로 인해 경로 전체 자동 수집은 여전히 차단될 수 있다.

## 커밋

`c2f1ef26e9f051c48028c8d90e2a3f02dbd41327`

## 검토 수정 라운드 1

검토에서 확인된 명세 결함을 수정했다. 안전재고 하회는 후속 입고로 회복되더라도 기준일 포함 14일 중 어느 하루라도 발생하면 `shortage_expected=True`여야 한다.

### 수정 내용

- `backend/tests/test_material_risk.py`: 입고 회피 사례의 안전재고 하회 결과를 `True`로 변경
- `backend/app/services/material_risk.py`: 초기 재고 및 각 일자 차감 후 `stock < safety_stock` 여부를 누적 추적
- 입고는 계속 수요보다 먼저 반영하며, 첫 `stock <= 0` 날짜 기록은 유지

### 수정 TDD 실행

RED 명령:

```text
cd backend
python -m pytest tests/test_material_risk.py -v
```

결과: `1 failed, 2 passed`; 일시적 안전재고 하회를 누적하지 않던 기존 구현의 실패를 확인했다.

GREEN 명령:

```text
cd backend
python -m pytest tests/test_material_risk.py -v
```

결과: `3 passed`.

회귀 명령:

```text
cd backend
python -m pytest tests/test_order_risk.py tests/test_models.py tests/test_material_risk.py -q
```

결과: `10 passed`.

### 수정 라운드 자체 검토 및 우려

- 안전재고 하회 판정은 이제 기간 중 어느 하루라도 누적된다.
- 기준일 초기 재고가 이미 안전재고 미만인 경우도 부족 예상으로 판정한다.
- 기존 전체 자동 수집의 접근 거부 pytest 캐시 문제는 worktree 외부 산출물을 변경하지 않아 그대로 남아 있다.

### 수정 커밋

`75e22bb56a9f5d034acd0559b4306416f6ec5b69`
