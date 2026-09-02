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
    lot_count: null,
    safety_stock: null,
  },
  {
    item_code: "RM-01",
    item_name: "폴리머 베이스",
    item_type: "자재",
    linked_item_count: 1,
    lot_count: 2,
    safety_stock: 224,
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

  it("marks safety stock and lots as not applicable for products", () => {
    const markup = renderToStaticMarkup(<MasterItemTable items={[items[0]]} />);

    expect(markup.match(/해당 없음/g)).toHaveLength(2);
    expect(markup).not.toContain("224개");
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
