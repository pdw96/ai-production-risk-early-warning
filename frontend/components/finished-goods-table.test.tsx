import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { describe, expect, it } from "vitest";

import type { FinishedGoods } from "../lib/api";
import { FinishedGoodsTable } from "./finished-goods-table";

const sample_product: FinishedGoods = {
  expired_stock: 40,
  inspection_pending_stock: 30,
  product_code: "FG-01",
  product_id: 1,
  product_name: "가상 제품 A",
  rejected_stock: 20,
  releasable_stock: 110,
  shelf_life_days: 180,
  total_lot_quantity: 200,
};

describe("FinishedGoodsTable", () => {
  it("renders every stock bucket and the shelf life setting", () => {
    const markup = renderToStaticMarkup(
      <FinishedGoodsTable finishedGoods={[sample_product]} />,
    );

    ["FG-01", "ID 1", "가상 제품 A", "180일", "110개", "30개", "20개", "40개", "200개"].forEach(
      (expected) => {
        expect(markup).toContain(expected);
      },
    );
  });

  it("says a product without a shelf life setting never expires", () => {
    const markup = renderToStaticMarkup(
      <FinishedGoodsTable
        finishedGoods={[{ ...sample_product, shelf_life_days: null }]}
      />,
    );

    expect(markup).toContain("무기한");
  });

  it("leaves lot detail to the warehouse screens", () => {
    // 영업관리는 출하 관점만 본다. 로트 하나하나는 창고별 재고가 맡는다.
    const markup = renderToStaticMarkup(
      <FinishedGoodsTable finishedGoods={[sample_product]} />,
    );

    expect(markup).not.toContain("로트");
    expect(markup).not.toContain("생산창고");
    expect(markup).not.toContain("제품창고");
  });
});
