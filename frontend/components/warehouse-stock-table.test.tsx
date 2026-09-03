import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { describe, expect, it } from "vitest";

import type { WarehouseLot } from "../lib/api";
import { WarehouseStockTable } from "./warehouse-stock-table";

const lots: WarehouseLot[] = [
  {
    expired: false,
    expiry_date: "2026-11-20",
    item_code: "RM-01",
    item_name: "가상 자재 A",
    item_type: "자재",
    lot_number: "LOT-RM-01-01",
    qc_status: null,
    quantity: 320,
    stocked_date: "2026-08-01",
  },
  {
    expired: true,
    expiry_date: "2026-08-20",
    item_code: "FG-02",
    item_name: "가상 제품 B",
    item_type: "제품",
    lot_number: "LOT-FG-02-260801",
    qc_status: "합격",
    quantity: 80,
    stocked_date: "2026-08-01",
  },
  {
    expired: false,
    expiry_date: null,
    item_code: "FG-03",
    item_name: "가상 제품 C",
    item_type: "제품",
    lot_number: "LOT-FG-03-260901",
    qc_status: "불합격",
    quantity: 15,
    stocked_date: "2026-09-01",
  },
];

describe("WarehouseStockTable", () => {
  it("puts materials and products side by side with their lot numbers", () => {
    const markup = renderToStaticMarkup(<WarehouseStockTable lots={lots} />);

    ["자재", "제품", "LOT-RM-01-01", "LOT-FG-02-260801", "320개", "80개"].forEach(
      (expected) => expect(markup).toContain(expected),
    );
  });

  it("labels the stocked date differently for materials and products", () => {
    // 완제품은 어디선가 입고된 것이 아니라 여기서 생산된 것이다.
    const markup = renderToStaticMarkup(<WarehouseStockTable lots={lots} />);

    expect(markup).toContain("입고");
    expect(markup).toContain("생산");
  });

  it("shows an inspection result only for products", () => {
    const markup = renderToStaticMarkup(<WarehouseStockTable lots={lots} />);

    expect(markup).toContain("합격");
    expect(markup).toContain("불합격");
    // 자재의 수입검사는 입고 시점에 끝나 있어 창고에서 볼 상태가 없다.
    expect(markup).toContain("—");
  });

  it("marks an expired lot that is still sitting in the warehouse", () => {
    const markup = renderToStaticMarkup(<WarehouseStockTable lots={lots} />);

    expect(markup).toContain("만료");
    expect(markup).toContain("가용");
    expect(markup).toContain("무기한");
  });
});
