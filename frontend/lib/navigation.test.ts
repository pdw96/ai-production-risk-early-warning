import { describe, expect, it } from "vitest";

import { flatten_navigation_links, navigation_groups } from "./navigation";

describe("navigation_groups", () => {
  it("keeps the cross-cutting alert screens out of the ERP modules", () => {
    const [alerts, erp] = navigation_groups;

    expect(alerts.label).toBe("경보");
    expect(alerts.items.map((item) => item.label)).toEqual(["운영 현황", "리스크 보드"]);
    expect(erp.label).toBe("ERP");
  });

  it("lists the six ERP modules in department order", () => {
    const erp = navigation_groups[1];

    expect(erp.items.map((item) => item.label)).toEqual([
      "기준정보관리",
      "구매관리",
      "재고관리",
      "생산관리",
      "품질관리",
      "영업관리",
    ]);
  });

  it("nests the three warehouses under 재고관리 · 창고별 재고", () => {
    const inventory = navigation_groups[1].items.find(
      (item) => item.label === "재고관리",
    );

    // 모듈 자체는 링크가 아니라 하위를 묶는 이름표다.
    expect(inventory?.href).toBeUndefined();
    expect(inventory?.children?.map((child) => child.label)).toEqual([
      "재고현황",
      "창고별 재고",
    ]);

    const warehouses = inventory?.children?.[1];
    expect(warehouses?.href).toBeUndefined();
    expect(warehouses?.children).toEqual([
      { href: "/materials/warehouses/raw", label: "원재료창고" },
      { href: "/materials/warehouses/production", label: "생산창고" },
      { href: "/materials/warehouses/products", label: "제품창고" },
    ]);
  });

  it("reuses the existing routes so old links keep working", () => {
    const routes = Object.fromEntries(
      flatten_navigation_links().map((item) => [item.label, item.href]),
    );

    expect(routes["재고현황"]).toBe("/materials");
    expect(routes["생산관리"]).toBe("/orders");
    expect(routes["리스크 보드"]).toBe("/risks");
    expect(routes["품질관리"]).toBe("/quality");
  });

  it("has no duplicate routes", () => {
    const hrefs = flatten_navigation_links().map((item) => item.href);

    expect(new Set(hrefs).size).toBe(hrefs.length);
  });
});
