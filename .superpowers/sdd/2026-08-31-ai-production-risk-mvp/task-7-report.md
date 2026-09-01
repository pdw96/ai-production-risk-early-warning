# Task 7 작업 보고서: 대시보드와 공통 표시 컴포넌트

구현 커밋: `21d29b490c820c01418c8e03ccdb430463abd8b8`

## 구현 범위

- `frontend/app/page.tsx`에 실제 `getDashboard()` API 응답만 사용한 `/` 운영 대시보드를 구현했다. 대시보드는 로딩, API 오류, 빈 데이터 상태를 분기해 표시한다.
- 네 가지 KPI(납기 위험 오더, 자재 부족 위험, 오늘 생산 계획, 오늘 생산 실적)를 한국어 수량 단위로 표시하고 각 상세 화면으로 연결했다.
- 최근 7일 생산 계획·실적을 Recharts 선형 차트와 스크린 리더용 데이터 표로 제공했다.
- 상위 5개 납기 리스크와 자재 리스크, API의 권장 조치를 표시했다. 오더·자재 항목도 상세 화면으로 연결했다.
- `StatusBadge`는 정상·주의·위험의 아이콘, 한국어 텍스트, 접근 가능한 상태 레이블을 공통으로 제공한다.
- `DataState`, `KpiCard`, `ProductionTrendChart` 공통 컴포넌트를 추가하고 데스크톱 우선 정보 밀도의 통제실 스타일을 적용했다.

## TDD 증빙

1. `components/status-badge.test.tsx`와 `components/data-state.test.tsx`를 구현 전에 추가했다.
2. 컴포넌트가 없을 때 `npm test -- status-badge.test.tsx data-state.test.tsx`를 실행했고, 두 모듈을 찾지 못해 2개 테스트 스위트가 실패하는 것을 확인했다.
3. 최소 구현 후 상태 배지 2건 및 데이터 상태 3건, 총 5건이 통과했다.

## 검증 결과

- `npm test` — 3개 파일, 8개 테스트 통과
- `npm run lint` — TypeScript 오류 없음
- `npm run build` — Next.js 프로덕션 빌드 성공
- `git diff --check` — 공백 오류 없음

## 의존성 및 유의사항

- 7일 생산 추이 차트를 위해 `recharts` 3.10.1을 추가했다.
- `npm install`의 감사 결과에는 기존 의존성 트리 기준 4건(높음 2, 심각 2)의 취약점이 남아 있다. 이번 작업에서는 자동 수정이나 대규모 의존성 업그레이드를 수행하지 않았다.
- 리스크·오더·자재의 상세 경로는 후속 Task 8 화면에서 구현된다. 현재 대시보드 링크는 해당 예정 경로를 사용한다.
