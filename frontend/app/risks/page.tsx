"use client";

import React, { useState } from "react";

import { DataState } from "../../components/data-state";
import { RiskBoard } from "../../components/risk-board";
import {
  getRisks,
  updateRiskStatus,
  type Risk,
  type RiskWorkflowStatus,
} from "../../lib/api";
import { use_api_data } from "../../lib/use-api-data";

export default function RisksPage() {
  const { data: initial_risks, error_message, is_loading } = use_api_data(getRisks);
  const [refreshed_risks, set_refreshed_risks] = useState<Risk[] | null>(null);

  async function handle_update(
    risk_id: string,
    status: RiskWorkflowStatus,
  ): Promise<void> {
    await updateRiskStatus(risk_id, status);
    set_refreshed_risks(await getRisks());
  }

  if (is_loading) {
    return <DataState state="loading" />;
  }
  if (error_message) {
    return <DataState errorMessage={error_message} state="error" />;
  }

  const risks = refreshed_risks ?? initial_risks;
  if (!risks || risks.length === 0) {
    return <DataState state="empty" />;
  }

  return (
    <div className="page-shell">
      <header className="page-header">
        <div>
          <p className="section-kicker">ACTION QUEUE</p>
          <h1>통합 리스크 보드</h1>
          <p>판정 근거와 권장 조치를 확인하고 처리 상태를 기록합니다.</p>
        </div>
        <span className="page-header__count">{risks.length} ACTIVE RISKS</span>
      </header>
      <RiskBoard onUpdate={handle_update} risks={risks} />
    </div>
  );
}
