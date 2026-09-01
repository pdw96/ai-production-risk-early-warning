import { afterEach, describe, expect, it, vi } from "vitest";

import { getDashboard, requestData, updateRiskStatus } from "./api";

const original_fetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = original_fetch;
  vi.restoreAllMocks();
});

describe("API client", () => {
  it("unwraps a dashboard envelope through the same-origin API proxy", async () => {
    const fetch_mock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: { kpis: { due_risk_order_count: 3 } } }),
    });
    globalThis.fetch = fetch_mock;

    const dashboard = await getDashboard();

    expect(dashboard.kpis.due_risk_order_count).toBe(3);
    expect(fetch_mock).toHaveBeenCalledWith("/api/dashboard", {
      cache: "no-store",
    });
  });

  it("throws the Korean API detail for a failed response", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ detail: "서버 오류" }),
    });

    await expect(requestData("/api/dashboard")).rejects.toThrow("서버 오류");
  });

  it("sends a risk status update as a PATCH request", async () => {
    const fetch_mock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: { risk_id: "RISK-ORDER-001", status: "조치 완료" } }),
    });
    globalThis.fetch = fetch_mock;

    const risk = await updateRiskStatus("RISK-ORDER-001", "조치 완료");

    expect(risk.status).toBe("조치 완료");
    expect(fetch_mock).toHaveBeenCalledWith(
      "/api/risks/RISK-ORDER-001/status",
      {
        body: '{"status":"조치 완료"}',
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        method: "PATCH",
      },
    );
  });
});
