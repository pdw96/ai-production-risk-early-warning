import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { describe, expect, it } from "vitest";

import type { FinishedGoods } from "../lib/api";
import { FinishedGoodsTable } from "./finished-goods-table";

const sample_product: FinishedGoods = {
  expired_stock: 40,
  inspection_pending_stock: 30,
  lots: [
    {
      expiry_date: "2026-08-20",
      lot_number: "LOT-FG-01-260801",
      produced_date: "2026-08-01",
      qc_status: "합격",
      quantity: 40,
      state: "만료",
      warehouse: "완제품창고",
    },
    {
      expiry_date: "2026-09-20",
      lot_number: "LOT-FG-01-260829",
      produced_date: "2026-08-29",
      qc_status: "합격",
      quantity: 100,
      state: "출하 가능",
      warehouse: "완제품창고",
    },
    {
      expiry_date: null,
      lot_number: "LOT-FG-01-260831",
      produced_date: "2026-08-31",
      qc_status: "검사 대기",
      quantity: 30,
      state: "검사 대기",
      warehouse: "생산창고",
    },
    {
      expiry_date: "2026-09-22",
      lot_number: "LOT-FG-01-260830",
      produced_date: "2026-08-30",
      qc_status: "불합격",
      quantity: 20,
      state: "불합격",
      warehouse: "생산창고",
    },
  ],
  product_code: "FG-01",
  product_id: 1,
  product_name: "가상 제품 A",
  rejected_stock: 20,
  releasable_stock: 100,
  shelf_life_days: 180,
  total_lot_quantity: 200,
  transfer_pending_stock: 10,
};

describe("FinishedGoodsTable", () => {
  it("renders every stock bucket and the shelf life setting", () => {
    const markup = renderToStaticMarkup(
      <FinishedGoodsTable finishedGoods={[sample_product]} />,
    );

    ["FG-01", "ID 1", "가상 제품 A", "180일", "100개", "10개", "30개", "20개", "40개", "200개"].forEach(
      (expected) => {
        expect(markup).toContain(expected);
      },
    );
  });

  it("keeps expired and rejected lots visible because lots are a permanent record", () => {
    const markup = renderToStaticMarkup(
      <FinishedGoodsTable finishedGoods={[sample_product]} />,
    );

    expect(markup).toContain("LOT-FG-01-260801");
    expect(markup).toContain("만료");
    expect(markup).toContain("LOT-FG-01-260830");
    expect(markup).toContain("불합격");
    expect(markup).toContain("로트 4건");
  });

  it("says a product without a shelf life setting never expires", () => {
    const markup = renderToStaticMarkup(
      <FinishedGoodsTable
        finishedGoods={[{ ...sample_product, shelf_life_days: null }]}
      />,
    );

    expect(markup).toContain("무기한");
    expect(markup).toContain("유효기간 없음");
  });

  it("tells the empty lot list apart from a zero quantity", () => {
    const markup = renderToStaticMarkup(
      <FinishedGoodsTable finishedGoods={[{ ...sample_product, lots: [] }]} />,
    );

    expect(markup).toContain("보유 로트 없음");
  });
});
