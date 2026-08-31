import React from "react";

import type { RiskSeverity } from "../lib/api";

const severity_icons: Record<RiskSeverity, string> = {
  정상: "●",
  주의: "▲",
  위험: "!",
};

export function StatusBadge({ severity }: Readonly<{ severity: RiskSeverity }>) {
  return (
    <span
      aria-label={`${severity} 상태`}
      className={`status-badge status-badge--${severity}`}
    >
      <span aria-hidden="true" className="status-badge__icon">
        {severity_icons[severity]}
      </span>
      <span>{severity}</span>
    </span>
  );
}
