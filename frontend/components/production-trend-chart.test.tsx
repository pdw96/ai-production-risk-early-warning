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
    stock_uom: "EA",
  },
  {
    points: [
      { actual_quantity: 72, planned_quantity: 76.32, work_date: "2026-09-02" },
      { actual_quantity: 71, planned_quantity: 71, work_date: "2026-09-01" },
    ],
    product_code: "FG-05",
    product_name: "테라패널",
    // 세는 단위가 아닌 제품 하나를 섞어 둔다 — 계열마다 단위가 다를 수 있다는
    // 것이 이 칸의 존재 이유이고, 하나뿐이면 이 파일이 그것을 지키지 못한다.
    stock_uom: "m2",
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

  it("labels the picked product's quantities in that product's own unit", async () => {
    // 제품 하나를 고르면 단위가 정해진다. 전 제품 합계는 여러 제품을 더한 값이라
    // 정해지지 않으므로 세는 단위를 그대로 쓴다.
    const user = userEvent.setup();
    render(<ProductionTrendChart data={total} productTrends={product_trends} />);

    await user.click(screen.getByRole("button", { name: "테라패널" }));

    expect(within(accessible_table()).getByText("76.32 m2")).toBeDefined();
    expect(screen.getByText(/단위: m2/)).toBeDefined();

    await user.click(screen.getByRole("button", { name: "전체" }));

    expect(screen.getByText(/단위: 개/)).toBeDefined();
  });

  it("says the all-product total has no single unit when products disagree", () => {
    // 완제품 단위가 갈리면 백엔드가 `quantity_uom: null` 을 보낸다. 그 합에는
    // 붙일 단위가 없으므로 「개」라고 적지 않는다.
    render(
      <ProductionTrendChart data={total} productTrends={product_trends} totalUnit={null} />,
    );

    expect(screen.getByText(/단위: 혼재/)).toBeDefined();
    expect(within(accessible_table()).getByText("357.22 (단위 혼재)")).toBeDefined();
  });

  it("does not label an empty window as mixed units", () => {
    // 실적이 하나도 없는 창은 단위가 갈린 것이 아니라 더한 것이 없는 것이다.
    const empty = total.map((point) => ({
      ...point,
      planned_quantity: 0,
      actual_quantity: 0,
    }));
    render(<ProductionTrendChart data={empty} productTrends={[]} totalUnit={null} />);

    expect(screen.queryByText(/단위: 혼재/)).toBeNull();
    expect(within(accessible_table()).queryByText(/단위 혼재/)).toBeNull();
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
