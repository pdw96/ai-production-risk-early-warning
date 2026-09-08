// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as api from "../../lib/api";
import SalesPage from "./page";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function product(overrides: Partial<api.FinishedGoods> = {}): api.FinishedGoods {
  return {
    product_id: 1,
    product_code: "FG-01",
    product_name: "가상 제품 A",
    stock_uom: "EA",
    shelf_life_days: 180,
    releasable_stock: 500,
    inspection_pending_stock: 0,
    rejected_stock: 0,
    intake_pending_stock: 0,
    expired_stock: 0,
    total_lot_quantity: 500,
    ...overrides,
  };
}

describe("SalesPage", () => {
  it("does not list a unit that has nothing to ship", async () => {
    // 마스터에 m² 제품이 있지만 출하 가능 재고는 0 이다. 「500개 · 0 m2」로
    // 적으면 읽는 사람이 없는 재고를 세게 된다.
    vi.spyOn(api, "getFinishedGoods").mockResolvedValue([
      product(),
      product({
        product_id: 2,
        product_code: "FG-02",
        product_name: "가상 광학필름",
        stock_uom: "m2",
        releasable_stock: 0,
        total_lot_quantity: 0,
      }),
    ]);

    render(<SalesPage />);

    // 표는 제품별이라 FG-02 줄에 「0 m2」가 그대로 나오는 것이 맞다. 단위를
    // 넘어 더하는 **머리말의 합계**만 0 인 단위를 빼고 적는다.
    const summary = await screen.findByText(/출하 가능 재고는/);
    expect(summary.textContent).toContain("출하 가능 재고는 500개입니다.");
    expect(summary.textContent).not.toContain("m2");
  });

  it("says nothing is shippable instead of writing a unit onto zero", async () => {
    // 전부 0 일 때 「0개」라고 적으면, m² 제품만 있는 회사에서 그것은 이 화면이
    // 없애려던 바로 그 오류다 — 없는 것에는 단위가 없다.
    vi.spyOn(api, "getFinishedGoods").mockResolvedValue([
      product({ stock_uom: "m2", releasable_stock: 0, total_lot_quantity: 40, expired_stock: 40 }),
    ]);

    render(<SalesPage />);

    expect(await screen.findByText(/지금 내보낼 수 있는 재고가 없습니다/)).toBeDefined();
    expect(screen.queryByText(/0개/)).toBeNull();
  });
});
