# Task 8 보고서: 오더·자재·리스크 화면과 상태 변경 연결

## 상태

- 완료
- 구현 커밋: `09158fd` (`feat: add production risk detail screens`)

## 변경 파일

- `frontend/app/orders/page.tsx`: 실제 `GET /api/orders` 데이터 기반 오더 목록, 로딩·빈·오류 상태
- `frontend/app/orders/[orderId]/page.tsx`: 실제 오더 상세와 최근 생산 기록, 로딩·빈·오류 상태
- `frontend/app/materials/page.tsx`: 실제 `GET /api/materials` 데이터 기반 14일 자재 수급 화면
- `frontend/app/risks/page.tsx`: 실제 리스크 조회, PATCH 후 즉시 재조회 연결
- `frontend/components/order-table.tsx`: 오더 API 응답의 모든 필드와 아이콘·텍스트 판정 표시
- `frontend/components/material-table.tsx`: 자재 식별자, 수급·재고·소진·판정·근거·조치 표시
- `frontend/components/risk-board.tsx`: 리스크 ID·유형·심각도·관련 대상·근거·조치·담당 부서·상태 표시, 저장 중/오류 피드백
- `frontend/lib/format.ts`: `ko-KR` 수량, 한 자리 퍼센트, `YYYY.MM.DD` 날짜 포맷
- `frontend/lib/use-api-data.ts`: 취소 안전한 로딩·성공·오류 상태 훅
- `frontend/app/globals.css`: 기존 어두운 통제실 디자인을 표·상세 패널·리스크 보드에 확장
- `frontend/components/*.test.tsx`, `frontend/lib/*.test.*`: 필드·상태 선택·진행·오류·포맷·API 상태 테스트
- `frontend/package.json`, `frontend/package-lock.json`: DOM 상호작용 테스트용 Testing Library와 jsdom 개발 의존성

## TDD 증거

### RED 1: 리스크 상태 UI

명령:

`npm test -- risk-board.test.tsx --reporter=verbose`

결과: `RiskBoard` 모듈을 찾지 못해 1개 테스트 스위트가 예상대로 실패했다. 구현 후에는 정확한 `risk_id/status` 전달, 필수 필드, 저장 중 비활성화, 실패 알림 4건이 통과했다.

### RED 2: 오더·자재 표와 포맷

명령:

`npm test -- format.test.ts order-table.test.tsx material-table.test.tsx --reporter=verbose`

결과: 세 구현 모듈이 없는 상태에서 3개 테스트 스위트가 예상대로 실패했다. 최소 구현 후 3개 스위트 5건이 통과했다.

### RED 3: 라우트 API 상태 관리

명령:

`npm test -- use-api-data.test.tsx --reporter=verbose`

결과: 훅 모듈 부재로 예상 실패한 뒤, 로딩→성공과 API 오류 2건이 통과했다.

### RED 4: 내부 식별자 표시

명령:

`npm test -- order-table.test.tsx material-table.test.tsx --reporter=verbose`

결과: `ID 1`이 표시되지 않아 2건이 예상 실패했다. 식별자를 추가한 뒤 2건 모두 통과했다.

## 최종 검증

- `npm test`: 8개 파일, 19개 테스트 통과
- `npm run lint`: `tsc --noEmit` 통과
- `npm run build`: Next.js 15.5.2 프로덕션 빌드 통과
- 생성 경로: `/`, `/materials`, `/orders`, `/orders/[orderId]`, `/risks`
- `git diff --check`: 공백 오류 없음. Windows LF→CRLF 안내만 출력

## 자체 검토

- 생산 화면은 `frontend/lib/api.ts`의 FastAPI 클라이언트만 사용하며 프로덕션 mock JSON을 추가하지 않았다.
- 오더·자재 목록은 각 API 계약 필드를 빠짐없이 표시하며, 상세 화면은 최근 생산 기록까지 표시한다.
- 리스크 보드는 상태 선택 시 PATCH를 호출하고 성공 후 `getRisks()`를 재호출한다.
- 상태 저장 중 선택을 비활성화하고 `role=status`, 실패 시 `role=alert`와 재시도 안내를 제공한다.
- 심각도와 워크플로 상태는 색상만 사용하지 않고 아이콘과 한국어 라벨을 함께 제공한다.
- 네 경로 모두 로딩·빈·API 오류 UI를 분기한다.
- 자재 리스크 담당 부서는 API에 별도 필드가 없어 리스크 유형에 따라 `생산관리팀` 또는 `자재관리팀`으로 표시한다.

## 우려 사항

- `npm audit`는 기존 직접 의존성 `next@15.5.2`, `vitest@3.2.4` 계열에서 총 4건(critical 2, high 2)을 보고한다. 이번 Task 8에서 추가한 Testing Library/jsdom 항목은 취약점 목록에 없으며, 의존성 업그레이드는 Task 8 범위 밖이라 적용하지 않았다.
- 브라우저 E2E 자동화는 Task 9의 종단 간 검증 범위이며, 이번 작업은 컴포넌트 상호작용 테스트와 프로덕션 빌드까지 검증했다.
