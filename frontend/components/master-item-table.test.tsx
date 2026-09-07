import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { describe, expect, it } from "vitest";

import type { BomRequirement, MasterItem } from "../lib/api";
import { BomTable, MasterItemTable } from "./master-item-table";

const items: MasterItem[] = [
  {
    item_code: "FG-01",
    item_name: "아크솔 시트",
    item_type: "제품",
    linked_item_count: 3,
    lot_count: 30,
    safety_stock: null,
    shelf_life_days: 180,
  },
  {
    item_code: "RM-01",
    item_name: "폴리머 베이스",
    item_type: "자재",
    linked_item_count: 1,
    lot_count: 2,
    safety_stock: 224,
    shelf_life_days: null,
  },
];

const bom_requirements: BomRequirement[] = [
  {
    material_code: "RM-01",
    material_name: "폴리머 베이스",
    product_code: "FG-01",
    product_name: "아크솔 시트",
    unit_quantity: 1.42,
  },
];

describe("MasterItemTable", () => {
  it("shows product and material codes with their item type", () => {
    const markup = renderToStaticMarkup(<MasterItemTable items={items} />);

    ["제품", "자재", "FG-01", "RM-01", "아크솔 시트", "폴리머 베이스"].forEach((value) =>
      expect(markup).toContain(value),
    );
  });

  it("labels the linked item count differently for products and materials", () => {
    const markup = renderToStaticMarkup(<MasterItemTable items={items} />);

    expect(markup).toContain("소요 자재 3종");
    expect(markup).toContain("사용 제품 1종");
  });

  it("marks only safety stock as not applicable for products", () => {
    // 제품도 완제품 로트를 가지므로 로트 수는 값이 있다. 안전재고만 자재 개념이다.
    const markup = renderToStaticMarkup(<MasterItemTable items={[items[0]]} />);

    expect(markup.match(/해당 없음/g)).toHaveLength(1);
    expect(markup).toContain("30건");
    expect(markup).not.toContain("224개");
  });

  it("shows the shelf life setting and names the open-ended case", () => {
    // 설정기간이 없는 것은 값을 아직 안 정한 것이 아니라 유효기간을 두지 않는
    // 품목이라는 뜻이다.
    const markup = renderToStaticMarkup(<MasterItemTable items={items} />);

    expect(markup).toContain("180일");
    expect(markup).toContain("무기한");
  });

  it("shows safety stock and lot count for materials", () => {
    const markup = renderToStaticMarkup(<MasterItemTable items={[items[1]]} />);

    expect(markup).toContain("224개");
    expect(markup).toContain("2건");
  });
});

describe("BomTable", () => {
  it("renders the per-unit material requirement of a product", () => {
    const markup = renderToStaticMarkup(<BomTable bomRequirements={bom_requirements} />);

    ["아크솔 시트", "FG-01", "폴리머 베이스", "RM-01", "1.42개"].forEach((value) =>
      expect(markup).toContain(value),
    );
  });
});
