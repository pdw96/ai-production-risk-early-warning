// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as api from "../lib/api";
import HomePage from "./page";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function dashboard(overrides: Partial<api.Dashboard> = {}): api.Dashboard {
  return {
    kpis: {
      due_risk_order_count: 0,
      material_shortage_count: 0,
      today_plan_quantity: 0,
      today_actual_quantity: 0,
      today_quantity_uom: "EA",
    },
    quantity_uom: "EA",
    // 추이는 실적이 없어도 7일치 0을 채워 보낸다. 비어 있음의 표식이 될 수 없다.
    production_trend: Array.from({ length: 7 }, (_, index) => ({
      work_date: `2026-09-0${index + 1}`,
      planned_quantity: 0,
      actual_quantity: 0,
    })),
    product_trends: [],
    top_order_risks: [],
    top_material_risks: [],
    // 위험이 없으면 서버가 이 한 줄을 넣는다. 이것도 표식이 될 수 없다.
    recommended_actions: ["현재 주요 위험이 없습니다. 정상 모니터링을 유지하세요."],
    ...overrides,
  };
}

describe("HomePage", () => {
  it("does not present an empty database as a risk-free factory", async () => {
    // 표만 있고 행이 없는 상태(운영 기본값은 자동 시드를 켜지 않는다). 0으로 채운
    // 차트와 「위험 없음」이 아무 문제 없는 공장처럼 읽혀서는 안 된다.
    vi.spyOn(api, "getDashboard").mockResolvedValue(dashboard());

    render(<HomePage />);

    // **빈 상태를 직접 확인한다.** 「차트가 없다」만 보면 아직 로딩 중인 첫
    // 렌더에서 이미 참이라, 판단을 통째로 꺼도 테스트가 통과한다(그렇게 되는
    // 것을 확인했다). 응답을 받은 뒤에만 나올 수 있는 문구를 기다린다.
    expect(await screen.findByText("운영 데이터 없음")).toBeDefined();
    expect(screen.queryByText(/최근 7일 생산 계획 대비 실적/)).toBeNull();
  });

  it("shows the dashboard when master data exists even with no risks", async () => {
    // 정상적으로 도는 공장은 위험이 없어도 제품 계열이 차 있다.
    vi.spyOn(api, "getDashboard").mockResolvedValue(
      dashboard({
        product_trends: [
          {
            product_code: "FG-01",
            product_name: "아크솔 시트",
            stock_uom: "EA",
            points: [
              { work_date: "2026-09-01", planned_quantity: 0, actual_quantity: 0 },
            ],
          },
        ],
      }),
    );

    render(<HomePage />);

    expect(await screen.findByText(/최근 7일 생산 계획 대비 실적/)).toBeDefined();
    expect(screen.queryByText("운영 데이터 없음")).toBeNull();
  });
});
