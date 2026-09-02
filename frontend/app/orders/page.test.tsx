// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as api from "../../lib/api";
import OrdersPage from "./page";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const order: api.Order = {
  actual_quantity: 466,
  average_daily_output: 8,
  completion_rate: 86.6,
  due_date: "2026-09-07",
  estimated_completion_date: "2026-09-11",
  order_id: 1,
  order_number: "MO-20260902-001",
  planned_quantity: 538,
  product_code: "FG-01",
  product_name: "아크솔 시트",
  reason: "완료예정일이 납기일보다 늦습니다.",
  remaining_quantity: 72,
  severity: "위험",
};

describe("OrdersPage", () => {
  it("shows a failure message when the production results request fails", async () => {
    vi.spyOn(api, "getOrders").mockResolvedValue([order]);
    vi.spyOn(api, "getProductionResults").mockRejectedValue(
      new Error("생산실적 API가 응답하지 않습니다."),
    );

    render(<OrdersPage />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeDefined();
    });
    expect(screen.getByRole("alert").textContent).toContain(
      "생산실적 API가 응답하지 않습니다.",
    );
    // 실패했는데 계속 로딩 문구가 떠 있으면 안 된다.
    expect(screen.queryByText("생산실적을 불러오는 중입니다.")).toBeNull();
  });

  it("renders the production results once both requests succeed", async () => {
    vi.spyOn(api, "getOrders").mockResolvedValue([order]);
    vi.spyOn(api, "getProductionResults").mockResolvedValue([
      {
        achievement_rate: 94.3,
        active_order_count: 30,
        actual_quantity: 340,
        planned_quantity: 360.4,
        work_date: "2026-09-02",
      },
    ]);

    render(<OrdersPage />);

    await waitFor(() => {
      expect(screen.getByText("94.3%")).toBeDefined();
    });
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
