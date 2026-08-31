import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { describe, expect, it } from "vitest";

import type { Material } from "../lib/api";
import { MaterialTable } from "./material-table";

const sample_material: Material = {
  current_stock: 1200,
  ending_stock: 300,
  material_code: "MAT-001",
  material_id: 1,
  material_name: "가상 자재 A",
  minimum_stock: 150,
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
});
