import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { describe, expect, it } from "vitest";

import type { Order } from "../lib/api";
import { OrderTable } from "./order-table";

const sample_order: Order = {
  actual_quantity: 800,
  average_daily_output: 100,
  completion_rate: 80,
  due_date: "2026-09-03",
  estimated_completion_date: "2026-09-02",
  order_id: 1,
  order_number: "ORD-001",
  planned_quantity: 1000,
  product_code: "PRD-001",
  product_name: "가상 제품 A",
  reason: "완료 예상일이 납기 안에 있습니다.",
  remaining_quantity: 200,
  severity: "정상",
};

describe("OrderTable", () => {
  it("renders every order response field", () => {
    const markup = renderToStaticMarkup(<OrderTable orders={[sample_order]} />);

    [
      "ORD-001",
      "ID 1",
      "PRD-001",
      "가상 제품 A",
      "2026.09.03",
      "1,000개",
      "800개",
      "80.0%",
      "100개/일",
      "200개",
      "2026.09.02",
      "정상",
      sample_order.reason,
    ].forEach((value) => expect(markup).toContain(value));
  });
});
