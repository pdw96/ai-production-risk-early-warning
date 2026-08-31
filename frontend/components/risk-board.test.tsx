// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Risk } from "../lib/api";
import { RiskBoard } from "./risk-board";

const sample_risk: Risk = {
  entity_code: "ORD-001",
  entity_id: 1,
  entity_name: "가상 제품 A",
  reason: "예상 완료일이 납기일을 초과합니다.",
  recommendation: "생산 계획과 납기를 재조정하세요.",
  risk_id: "RISK-ORDER-001",
  risk_type: "납기",
  severity: "위험",
  status: "신규",
};

afterEach(() => {
  cleanup();
});

describe("RiskBoard", () => {
  it("shows every operational risk field with icon-and-label status cues", () => {
    render(<RiskBoard onUpdate={vi.fn()} risks={[sample_risk]} />);

    expect(screen.getAllByText("RISK-ORDER-001")).toHaveLength(2);
    expect(screen.getByText("납기")).toBeTruthy();
    expect(screen.getByLabelText("위험 상태")).toBeTruthy();
    expect(screen.getByText("ORD-001 · 가상 제품 A")).toBeTruthy();
    expect(screen.getByText(sample_risk.reason)).toBeTruthy();
    expect(screen.getByText(sample_risk.recommendation)).toBeTruthy();
    expect(screen.getByText("생산관리팀")).toBeTruthy();
    expect(screen.getByRole("option", { name: "○ 신규" })).toBeTruthy();
  });

  it("sends the selected status with the matching risk ID", async () => {
    const on_update = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<RiskBoard onUpdate={on_update} risks={[sample_risk]} />);

    await user.selectOptions(
      screen.getByLabelText("RISK-ORDER-001 상태"),
      "조치 완료",
    );

    expect(on_update).toHaveBeenCalledWith("RISK-ORDER-001", "조치 완료");
  });

  it("disables the status control while the update is in progress", async () => {
    let finish_update: (() => void) | undefined;
    const on_update = vi.fn(
      () => new Promise<void>((resolve) => {
        finish_update = resolve;
      }),
    );
    const user = userEvent.setup();
    render(<RiskBoard onUpdate={on_update} risks={[sample_risk]} />);

    await user.selectOptions(
      screen.getByLabelText("RISK-ORDER-001 상태"),
      "확인 중",
    );

    expect((screen.getByLabelText("RISK-ORDER-001 상태") as HTMLSelectElement).disabled).toBe(true);
    expect(screen.getByText("상태 저장 중")).toBeTruthy();

    finish_update?.();
    await waitFor(() => {
      expect((screen.getByLabelText("RISK-ORDER-001 상태") as HTMLSelectElement).disabled).toBe(false);
    });
  });

  it("shows an actionable error when the status update fails", async () => {
    const user = userEvent.setup();
    render(
      <RiskBoard
        onUpdate={vi.fn().mockRejectedValue(new Error("상태 저장 실패"))}
        risks={[sample_risk]}
      />,
    );

    await user.selectOptions(
      screen.getByLabelText("RISK-ORDER-001 상태"),
      "조치 완료",
    );

    expect((await screen.findByRole("alert")).textContent).toContain("상태 저장 실패");
  });
});
