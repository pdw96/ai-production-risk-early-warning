// @vitest-environment jsdom

import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { afterEach, describe, expect, it } from "vitest";

import type { ProductionPoint, ProductTrend } from "../lib/api";
import { ProductionTrendChart } from "./production-trend-chart";

afterEach(() => {
  cleanup();
});

const total: ProductionPoint[] = [
  { actual_quantity: 337, planned_quantity: 357.22, work_date: "2026-09-02" },
  { actual_quantity: 340, planned_quantity: 340, work_date: "2026-09-01" },
];

const product_trends: ProductTrend[] = [
  {
    points: [
      { actual_quantity: 66, planned_quantity: 69.96, work_date: "2026-09-02" },
      { actual_quantity: 70, planned_quantity: 70, work_date: "2026-09-01" },
    ],
    product_code: "FG-01",
    product_name: "아크솔 시트",
  },
  {
    points: [
      { actual_quantity: 72, planned_quantity: 76.32, work_date: "2026-09-02" },
      { actual_quantity: 71, planned_quantity: 71, work_date: "2026-09-01" },
    ],
    product_code: "FG-05",
    product_name: "테라패널",
  },
];

function accessible_table(): HTMLElement {
  return screen.getByRole("table");
}

function pressed_state(label: string): string | null {
  return screen.getByRole("button", { name: label }).getAttribute("aria-pressed");
}

describe("ProductionTrendChart", () => {
  it("starts on the all-product total", () => {
    render(<ProductionTrendChart data={total} productTrends={product_trends} />);

    expect(pressed_state("전체")).toBe("true");
    expect(within(accessible_table()).getByText("357.22개")).toBeDefined();
  });

  it("switches the chart and its accessible table to the picked product", async () => {
    const user = userEvent.setup();
    render(<ProductionTrendChart data={total} productTrends={product_trends} />);

    await user.click(screen.getByRole("button", { name: "아크솔 시트" }));

    const table = accessible_table();
    expect(within(table).getByText("69.96개")).toBeDefined();
    expect(within(table).queryByText("357.22개")).toBeNull();
    expect(table.querySelector("caption")?.textContent).toContain("아크솔 시트");
  });

  it("marks only the selected product as pressed", async () => {
    const user = userEvent.setup();
    render(<ProductionTrendChart data={total} productTrends={product_trends} />);

    await user.click(screen.getByRole("button", { name: "테라패널" }));

    expect(pressed_state("테라패널")).toBe("true");
    expect(pressed_state("전체")).toBe("false");
    expect(pressed_state("아크솔 시트")).toBe("false");
  });

  it("goes back to the total when 전체 is picked again", async () => {
    const user = userEvent.setup();
    render(<ProductionTrendChart data={total} productTrends={product_trends} />);

    await user.click(screen.getByRole("button", { name: "아크솔 시트" }));
    await user.click(screen.getByRole("button", { name: "전체" }));

    expect(within(accessible_table()).getByText("357.22개")).toBeDefined();
  });

  it("hides the picker when no product series were supplied", () => {
    render(<ProductionTrendChart data={total} />);

    expect(screen.queryByRole("group", { name: "추이를 볼 제품 선택" })).toBeNull();
    expect(within(accessible_table()).getByText("357.22개")).toBeDefined();
  });
});
