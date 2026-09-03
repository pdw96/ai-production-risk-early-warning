import React from "react";

import type { QualityInspection, QualityInspectionSummary } from "../lib/api";
import { format_date } from "../lib/format";

const INSPECTION_LABELS: Record<string, string> = {
  IQC: "IQC 수입검사",
  OQC: "OQC 출하검사",
  PQC: "PQC 공정검사",
};

export function QualitySummaryCards({
  summaries,
}: Readonly<{ summaries: QualityInspectionSummary[] }>) {
  return (
    <div className="quality-summary">
      {summaries.map((summary) => (
        <article className="quality-summary__card" key={summary.inspection_type}>
          <p className="quality-summary__label">
            {INSPECTION_LABELS[summary.inspection_type] ?? summary.inspection_type}
          </p>
          <strong className="quality-summary__value">{summary.total_count}건</strong>
          <p className="quality-summary__detail">
            합격 {summary.passed_count} · 불합격 {summary.failed_count}
          </p>
        </article>
      ))}
    </div>
  );
}

/**
 * 목록은 API 가 이미 유형별 최신 기록만 잘라 검사일 내림차순으로 보내 준다.
 * 화면에서 다시 자르지 않는다 — 어디까지 보여줄지는 응답 크기를 결정하는
 * 문제라 서버가 진다.
 */
export function QualityInspectionTable({
  inspections,
}: Readonly<{ inspections: QualityInspection[] }>) {
  return (
    <div className="data-table-shell">
      <table className="operation-table operation-table--quality">
        <thead>
          <tr>
            <th scope="col">유형</th>
            <th scope="col">검사일</th>
            <th scope="col">품목</th>
            <th scope="col">대상</th>
            <th scope="col">판정</th>
            <th scope="col">불합격 사유</th>
          </tr>
        </thead>
        <tbody>
          {inspections.map((inspection) => (
            <tr key={inspection.inspection_id}>
              <td>{inspection.inspection_type}</td>
              <td>{format_date(inspection.inspected_date)}</td>
              <td>
                <strong>{inspection.item_name}</strong>
                <span className="table-secondary">{inspection.item_code}</span>
              </td>
              <td>
                <span className="table-secondary">{inspection.target_type}</span>
                {inspection.target_label}
              </td>
              <td>{inspection.result}</td>
              <td className="operation-table__reason">{inspection.reason ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
