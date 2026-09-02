import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { describe, expect, it } from "vitest";

import type { Material } from "../lib/api";
import { MaterialTable } from "./material-table";

const sample_material: Material = {
  current_stock: 1200,
  ending_stock: 300,
  expiring_quantity: 500,
  first_expiry_date: "2026-09-04",
  lots: [
    {
      expiry_date: "2026-09-04",
      lot_number: "LOT-MAT-001-01",
      quantity: 500,
      received_date: "2026-07-22",
      state: "기간 내 폐기",
      warehouse: "원재료창고",
    },
    {
      expiry_date: "2027-01-15",
      lot_number: "LOT-MAT-001-01",
      quantity: 400,
      received_date: "2026-07-22",
      state: "가용",
      warehouse: "생산창고",
    },
    {
      expiry_date: null,
      lot_number: "LOT-MAT-001-IN-01",
      quantity: 300,
      received_date: "2026-09-10",
      state: "예정 입고",
      warehouse: "원재료창고",
    },
  ],
  material_code: "MAT-001",
  material_id: 1,
  material_name: "가상 자재 A",
  minimum_stock: 150,
  production_warehouse_stock: 400,
  raw_warehouse_stock: 800,
  reason: "기간 종료 재고가 안전재고 미만입니다.",
  recommendation: "입고 일정을 앞당기세요.",
  safety_stock: 400,
  severity: "주의",
  shortage_expected: true,
  stockout_date: null,
};

describe("MaterialTable", () => {
  it("renders every material supply and stock field", () => {
    const markup = renderToStaticMarkup(<MaterialTable materials={[sample_material]} />);

    [
      "MAT-001",
      "ID 1",
      "가상 자재 A",
      "1,200개",
      "400개",
      "300개",
      "150개",
      "부족 예상",
      "소진 없음",
      "주의",
      sample_material.reason,
      sample_material.recommendation,
    ].forEach((value) => expect(markup).toContain(value));
  });

  it("shows stock split by warehouse and the expiry summary", () => {
    const markup = renderToStaticMarkup(<MaterialTable materials={[sample_material]} />);

    ["원재료창고 800개", "생산창고 400개", "500개", "2026.09.04"].forEach((value) =>
      expect(markup).toContain(value),
    );
  });

  it("lists every lot with its warehouse, dates and state", () => {
    const markup = renderToStaticMarkup(<MaterialTable materials={[sample_material]} />);

    expect(markup).toContain("로트 3건");
    ["LOT-MAT-001-01", "LOT-MAT-001-IN-01", "기간 내 폐기", "예정 입고"].forEach((value) =>
      expect(markup).toContain(value),
    );
    // 같은 로트번호가 두 창고에 나뉘어 있는 상태가 두 행으로 보인다.
    expect(markup.match(/LOT-MAT-001-01</g)).toHaveLength(2);
    // 로트의 유효기간 없음과 자재의 "14일 내 만료 없음"은 다른 말이다.
    // 로트 행에는 앞의 뜻만 나와야 한다.
    expect(markup).toContain("유효기간 없음");
    expect(markup).not.toContain("기간 내 없음");
  });

  it("distinguishes a material with no expiry inside the horizon", () => {
    const markup = renderToStaticMarkup(
      <MaterialTable materials={[{ ...sample_material, first_expiry_date: null }]} />,
    );

    expect(markup).toContain("기간 내 없음");
  });

  it("shows an expired lot with its own state instead of counting it as available", () => {
    // 기준일보다 앞서 만료된 로트는 가용 재고에 들어가지 않으므로 목록에서도
    // `가용`으로 보이면 안 된다.
    const markup = renderToStaticMarkup(
      <MaterialTable
        materials={[
          {
            ...sample_material,
            lots: [
              {
                expiry_date: "2026-08-30",
                lot_number: "LOT-MAT-001-OLD",
                quantity: 999,
                received_date: "2026-07-01",
                state: "만료",
                warehouse: "원재료창고",
              },
            ],
          },
        ]}
      />,
    );

    expect(markup).toContain("LOT-MAT-001-OLD");
    expect(markup).toContain("만료");
  });

  it("falls back to a placeholder when a material has no lots", () => {
    const markup = renderToStaticMarkup(
      <MaterialTable materials={[{ ...sample_material, lots: [] }]} />,
    );

    expect(markup).toContain("보유 로트 없음");
    expect(markup).not.toContain("로트 0건");
  });
});
