import React from "react";

interface KpiCardProps {
  detail: string;
  label: string;
  value: string;
}

export function KpiCard({ detail, label, value }: Readonly<KpiCardProps>) {
  return (
    <article className="kpi-card">
      <p className="kpi-card__label">{label}</p>
      <strong className="kpi-card__value">{value}</strong>
      <p className="kpi-card__detail">{detail}</p>
      <span aria-hidden="true" className="kpi-card__link-cue">
        상세 보기 →
      </span>
    </article>
  );
}
