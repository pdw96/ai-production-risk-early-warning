export interface NavigationItem {
  href: string;
  label: string;
}

export interface NavigationGroup {
  items: NavigationItem[];
  label: string;
}

/**
 * 메뉴는 두 단으로 나뉜다.
 *
 * 위쪽 `경보`는 납기와 자재를 가로지르는 조기경보 화면이라 특정 ERP 모듈에
 * 속하지 않는다. 아래쪽 `ERP`는 부서별로 확인하기 쉽도록 업무 모듈로 나눈다.
 * 경로는 기존 것을 그대로 쓴다(예: 생산관리 → /orders). 라벨만 모듈 이름으로
 * 바꾸고 URL은 유지해 기존 링크와 CI 스크린샷 경로가 깨지지 않게 했다.
 * 품질관리는 신규 화면이라 `/quality` 를 새로 쓴다. 자재 입고(IQC) → 생산(PQC)
 * → 출하(OQC) 순서라 생산관리와 영업관리 사이에 둔다.
 */
export const navigation_groups: NavigationGroup[] = [
  {
    items: [
      { href: "/", label: "운영 현황" },
      { href: "/risks", label: "리스크 보드" },
    ],
    label: "경보",
  },
  {
    items: [
      { href: "/master", label: "기준정보관리" },
      { href: "/purchases", label: "구매관리" },
      { href: "/materials", label: "재고관리" },
      { href: "/orders", label: "생산관리" },
      { href: "/quality", label: "품질관리" },
      { href: "/sales", label: "영업관리" },
    ],
    label: "ERP",
  },
];
