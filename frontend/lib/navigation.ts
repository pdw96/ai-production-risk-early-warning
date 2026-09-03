export interface NavigationNode {
  /** 링크가 없는 노드는 하위 항목을 묶는 이름표다. */
  href?: string;
  label: string;
  children?: NavigationNode[];
}

export interface NavigationGroup {
  items: NavigationNode[];
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
 *
 * 재고관리만 하위 메뉴를 갖는다. 재고를 품목 기준(재고현황)과 창고 기준
 * (창고별 재고)으로 나눠 봐야 하기 때문이다. 창고는 담는 것이 서로 달라
 * 한 화면에 섞으면 읽을 수 없다.
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
      {
        children: [
          { href: "/materials", label: "재고현황" },
          {
            children: [
              { href: "/materials/warehouses/raw", label: "원재료창고" },
              { href: "/materials/warehouses/production", label: "생산창고" },
              { href: "/materials/warehouses/products", label: "제품창고" },
            ],
            label: "창고별 재고",
          },
        ],
        label: "재고관리",
      },
      { href: "/orders", label: "생산관리" },
      { href: "/quality", label: "품질관리" },
      { href: "/sales", label: "영업관리" },
    ],
    label: "ERP",
  },
];

/** 트리를 평평하게 펴서 링크만 모은다. 중복 경로 검사와 테스트에 쓴다. */
export function flatten_navigation_links(
  nodes: NavigationNode[] = navigation_groups.flatMap((group) => group.items),
): { href: string; label: string }[] {
  return nodes.flatMap((node) => [
    ...(node.href ? [{ href: node.href, label: node.label }] : []),
    ...(node.children ? flatten_navigation_links(node.children) : []),
  ]);
}
