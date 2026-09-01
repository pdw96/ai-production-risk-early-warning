# Task 6 보고서 — Next.js 기본 구성과 API 클라이언트

## 범위

- `frontend`에 Next.js App Router, TypeScript, Tailwind CSS, Vitest 실행 환경을 구성했다.
- 데스크톱 생산 운영 통제실 셸과 좌측 내비게이션만 구현했다. 각 화면의 콘텐츠는 후속 Task 7·8 범위로 남겼다.
- FastAPI의 여섯 엔드포인트를 `NEXT_PUBLIC_API_BASE_URL`(기본값 `http://localhost:8000`)로 호출하는 타입 API 클라이언트를 구현했다. 프로덕션 코드에 목 데이터는 없다.

## TDD 증적

### RED

테스트를 먼저 추가한 뒤 아래 명령을 실행했다.

```text
cd frontend; npm test -- api.test.ts
```

`lib/api.test.ts`가 `./api`를 가져오지 못해 실패했다. 실패 원인은 의도대로 API 클라이언트 파일 부재였다.

### GREEN

`lib/api.ts`에 응답 envelope 해제, 오류 `detail` 전파, GET/PATCH 요청과 API 계약 타입을 최소 구현했다.

```text
cd frontend; npm test -- api.test.ts
```

결과: 테스트 3건 통과.

## 최종 검증

```text
cd frontend; npm test                 # 3 passed
cd frontend; npm run lint             # tsc --noEmit, exit 0
cd frontend; npm run build            # Next.js production build, exit 0
git diff --check                      # 출력 없음
```

## 유의 사항

- 의존성 설치 시 npm audit가 개발·런타임 의존성 기준 4건(높음 2, 심각 2)의 취약점을 보고했다. 범위를 벗어난 강제 업그레이드는 적용하지 않았다.
