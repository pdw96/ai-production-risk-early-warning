import { describe, expect, it } from "vitest";

import { navigation_groups } from "./navigation";

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

  it("reuses the existing routes so old links keep working", () => {
    const routes = Object.fromEntries(
      navigation_groups.flatMap((group) => group.items).map((item) => [item.label, item.href]),
    );

    expect(routes["재고관리"]).toBe("/materials");
    expect(routes["생산관리"]).toBe("/orders");
    expect(routes["리스크 보드"]).toBe("/risks");
    expect(routes["품질관리"]).toBe("/quality");
  });

  it("has no duplicate routes", () => {
    const hrefs = navigation_groups.flatMap((group) => group.items).map((item) => item.href);

    expect(new Set(hrefs).size).toBe(hrefs.length);
  });
});
