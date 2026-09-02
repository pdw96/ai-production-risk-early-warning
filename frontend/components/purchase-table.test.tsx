import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { describe, expect, it } from "vitest";

import type { PurchaseReceipt } from "../lib/api";
import { PurchaseTable } from "./purchase-table";

function receipt(overrides: Partial<PurchaseReceipt> = {}): PurchaseReceipt {
  return {
    days_until_arrival: 5,
    expiry_date: "2026-12-01",
    material_code: "RM-01",
    material_name: "폴리머 베이스",
    receipt_id: 7,
    scheduled_date: "2026-09-07",
    scheduled_quantity: 375,
    within_horizon: true,
    ...overrides,
  };
}

describe("PurchaseTable", () => {
  it("renders the receipt number, material and schedule", () => {
    const markup = renderToStaticMarkup(<PurchaseTable receipts={[receipt()]} />);

    ["PO-007", "RM-01", "폴리머 베이스", "2026.09.07", "375개", "2026.12.01"].forEach(
      (value) => expect(markup).toContain(value),
    );
  });

  it("counts down to arrival and names today and overdue arrivals", () => {
    const markup = renderToStaticMarkup(
      <PurchaseTable
        receipts={[
          receipt({ days_until_arrival: 5, receipt_id: 1 }),
          receipt({ days_until_arrival: 0, receipt_id: 2 }),
          receipt({ days_until_arrival: -3, receipt_id: 3 }),
        ]}
      />,
    );

    expect(markup).toContain("D-5");
    expect(markup).toContain("오늘 도착");
    expect(markup).toContain("3일 경과");
  });

  it("says whether the receipt feeds the 14-day shortage forecast", () => {
    const markup = renderToStaticMarkup(
      <PurchaseTable
        receipts={[
          receipt({ receipt_id: 1, within_horizon: true }),
          receipt({ receipt_id: 2, within_horizon: false }),
        ]}
      />,
    );

    expect(markup).toContain("반영");
    expect(markup).toContain("기간 밖");
  });

  it("handles a receipt without an expiry date", () => {
    const markup = renderToStaticMarkup(
      <PurchaseTable receipts={[receipt({ expiry_date: null })]} />,
    );

    expect(markup).toContain("유효기간 없음");
  });
});
