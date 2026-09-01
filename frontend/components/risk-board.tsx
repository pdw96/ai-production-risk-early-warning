"use client";

import Link from "next/link";
import React, { useState } from "react";

import type { Risk, RiskWorkflowStatus } from "../lib/api";
import { StatusBadge } from "./status-badge";

interface RiskBoardProps {
  onUpdate: (risk_id: string, status: RiskWorkflowStatus) => Promise<void>;
  risks: Risk[];
}

const workflow_statuses: Array<{ icon: string; label: RiskWorkflowStatus }> = [
  { icon: "○", label: "신규" },
  { icon: "◐", label: "확인 중" },
  { icon: "✓", label: "조치 완료" },
];

const responsible_departments: Record<Risk["risk_type"], string> = {
  납기: "생산관리팀",
  자재: "자재관리팀",
};

function related_href(risk: Risk): string {
  return risk.risk_type === "납기" ? `/orders/${risk.entity_id}` : "/materials";
}

export function RiskBoard({ onUpdate, risks }: Readonly<RiskBoardProps>) {
  const [pending_risk_id, set_pending_risk_id] = useState<string | null>(null);
  const [update_errors, set_update_errors] = useState<Record<string, string>>({});

  async function handle_status_change(
    risk_id: string,
    status: RiskWorkflowStatus,
  ): Promise<void> {
    set_pending_risk_id(risk_id);
    set_update_errors((current) => ({ ...current, [risk_id]: "" }));

    try {
      await onUpdate(risk_id, status);
    } catch (error: unknown) {
      set_update_errors((current) => ({
        ...current,
        [risk_id]: error instanceof Error ? error.message : "상태를 저장하지 못했습니다.",
      }));
    } finally {
      set_pending_risk_id(null);
    }
  }

  return (
    <div className="risk-board">
      {risks.map((risk) => {
        const is_pending = pending_risk_id === risk.risk_id;
        const update_error = update_errors[risk.risk_id];

        return (
          <article className="risk-board__item" key={risk.risk_id}>
            <header className="risk-board__heading">
              <div>
                <span className="risk-board__type">{risk.risk_type}</span>
                <strong>{risk.risk_id}</strong>
              </div>
              <StatusBadge severity={risk.severity} />
            </header>

            <dl className="risk-board__details">
              <div>
                <dt>관련 대상</dt>
                <dd>
                  <Link href={related_href(risk)}>
                    {risk.entity_code} · {risk.entity_name}
                  </Link>
                </dd>
              </div>
              <div>
                <dt>판정 근거</dt>
                <dd>{risk.reason}</dd>
              </div>
              <div>
                <dt>권장 조치</dt>
                <dd>{risk.recommendation}</dd>
              </div>
              <div>
                <dt>담당 부서</dt>
                <dd>{responsible_departments[risk.risk_type]}</dd>
              </div>
            </dl>

            <div className="risk-board__workflow">
              <label htmlFor={`risk-status-${risk.risk_id}`}>
                <span className="sr-only">{risk.risk_id} </span>상태
              </label>
              <select
                aria-label={`${risk.risk_id} 상태`}
                disabled={is_pending}
                id={`risk-status-${risk.risk_id}`}
                onChange={(event) => {
                  void handle_status_change(
                    risk.risk_id,
                    event.target.value as RiskWorkflowStatus,
                  );
                }}
                value={risk.status}
              >
                {workflow_statuses.map((status) => (
                  <option key={status.label} value={status.label}>
                    {status.icon} {status.label}
                  </option>
                ))}
              </select>
              {is_pending ? <span role="status">상태 저장 중</span> : null}
              {update_error ? <span role="alert">{update_error} 다시 시도하세요.</span> : null}
            </div>
          </article>
        );
      })}
    </div>
  );
}
