import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { describe, expect, it } from "vitest";

import type { ProductionResult } from "../lib/api";
import { ProductionResultTable } from "./production-result-table";

function result(overrides: Partial<ProductionResult> = {}): ProductionResult {
  return {
    achievement_rate: 94.3,
    active_order_count: 30,
    actual_quantity: 337,
    planned_quantity: 357.22,
    work_date: "2026-08-31",
    ...overrides,
  };
}

describe("ProductionResultTable", () => {
  it("renders the daily plan, actual output and achievement rate", () => {
    const markup = renderToStaticMarkup(<ProductionResultTable results={[result()]} />);

    ["2026.08.31", "357.22개", "337개", "94.3%", "30건"].forEach((value) =>
      expect(markup).toContain(value),
    );
  });

  it("separates days that met the plan from days that fell short", () => {
    const markup = renderToStaticMarkup(
      <ProductionResultTable
        results={[
          result({ achievement_rate: 103.1, work_date: "2026-08-29" }),
          result({ achievement_rate: 94.3, work_date: "2026-08-31" }),
          result({ achievement_rate: 100, work_date: "2026-08-30" }),
        ]}
      />,
    );

    expect(markup.match(/계획 달성/g)).toHaveLength(2);
    expect(markup.match(/계획 미달/g)).toHaveLength(1);
  });

  it("does not claim a shortfall on a day without any plan", () => {
    const markup = renderToStaticMarkup(
      <ProductionResultTable
        results={[result({ achievement_rate: 0, planned_quantity: 0 })]}
      />,
    );

    expect(markup).toContain("계획 없음");
    expect(markup).not.toContain("계획 미달");
  });
});
