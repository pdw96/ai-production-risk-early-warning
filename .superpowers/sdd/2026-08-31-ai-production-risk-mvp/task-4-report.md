# Task 4 보고서: 합성 데이터 초기화와 재현성 검증

## 구현 파일

- `backend/app/seed.py`
  - `reset_database(reference_date: date | None = None)`가 SQLite 스키마를 초기화하고 합성 운영 데이터를 생성한다.
  - `python -m app.seed`로 실행 당일 기준 데이터를 생성한다.
  - 기준일 `YYYYMMDD`와 고정 시드를 조합한 난수를 사용하며, 모든 오더번호·납기·생산·입고 날짜는 기준일 상대값이다.
  - 가상 제품 5개, 가상 자재 15개, 오더 30개, 제품당 BOM 3건, 자재별 예정 입고 1건, 오더별 기준일 포함 과거 30일 실적과 향후 14일 계획을 생성한다.
  - 생성 직후 기존 `calculate_order_risk`로 재계산하여 `정상`, `주의`, `위험`이 모두 존재하지 않으면 예외를 발생시킨다.
- `backend/tests/test_seed.py`
  - 실제 인메모리 SQLite DB에서 필수 최소 레코드 수와 과거/미래 생산 일자 범위를 검증한다.
  - 동일 기준일로 두 번 초기화한 오더 스냅샷이 같은지 검증한다.
  - 저장된 실적을 기존 납기 위험 함수에 입력해 정상·주의·위험 분포를 검증한다.

## TDD 실행 기록

### RED

명령:

```text
cd backend
python -m pytest tests/test_seed.py -v
```

결과: `ModuleNotFoundError: No module named 'app.seed'`로 수집 실패. 시드 모듈 부재에 따른 기대된 RED 상태를 확인했다.

### GREEN

명령:

```text
cd backend
python -m pytest tests/test_seed.py -v
```

결과: `3 passed`.

### 회귀 검증

명령:

```text
cd backend
python -m pytest tests -v
```

결과: `13 passed`.

`git diff --check`도 통과했다.

## 자체 검토

- 실존 회사·제품·거래처 데이터는 포함하지 않았으며, 제품과 자재 명칭은 모두 가상 소재 공장용 명칭이다.
- 난수 시드에는 고정값과 전달/당일 기준일이 함께 포함되어, 동일 기준일은 재현되고 기준일 변경 시 날짜 축과 난수 값이 함께 이동한다.
- 미래 14일 계획은 모든 오더에 생성되어 BOM 기반 자재 수요 계산에 사용할 수 있다.
- 시드 모듈은 API/UI를 추가하지 않는다.

## 우려 사항

- `backend` 루트에서 인자 없이 `pytest -v`를 실행하면 기존의 접근 불가 `pytest-cache-files-*` 디렉터리 6개를 pytest가 수집하려 해 `PermissionError`가 발생한다. 해당 디렉터리는 Task 4가 생성하거나 변경하지 않았으며, `pytest tests -v`로 명시한 실제 테스트 전체는 통과했다.

## 커밋

커밋 후 SHA를 이 항목에 기록한다.
