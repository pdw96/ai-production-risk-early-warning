import React from "react";

import type { QualityInspection, QualityInspectionSummary } from "../lib/api";
import { format_date } from "../lib/format";

// 기록이 영구히 쌓이므로 한 화면에 다 그리면 읽을 수 없다. 잘라 보여주되,
// 전체에서 최신순으로 자르면 IQC 가 한 건도 안 남는다 — IQC 의 검사일은 자재
// 입고일이라 늘 PQC·OQC 보다 과거이기 때문이다. 그래서 유형별로 자른다.
export const INSPECTION_DISPLAY_LIMIT_PER_TYPE = 20;

/** 유형별 최신 기록만 남기고 다시 검사일 내림차순으로 되돌린다. */
export function take_recent_by_type(
  inspections: QualityInspection[],
  limit: number = INSPECTION_DISPLAY_LIMIT_PER_TYPE,
): QualityInspection[] {
  const counts = new Map<string, number>();
  const picked: QualityInspection[] = [];

  // 입력이 이미 검사일 내림차순이라 앞에서부터 세면 유형별 최신이 남는다.
  for (const inspection of inspections) {
    const seen = counts.get(inspection.inspection_type) ?? 0;
    if (seen >= limit) {
      continue;
    }
    counts.set(inspection.inspection_type, seen + 1);
    picked.push(inspection);
  }

  return picked.sort((left, right) =>
    left.inspected_date === right.inspected_date
      ? right.inspection_id - left.inspection_id
      : right.inspected_date < left.inspected_date
        ? -1
        : 1,
  );
}

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

export function QualityInspectionTable({
  inspections,
}: Readonly<{ inspections: QualityInspection[] }>) {
  const visible = take_recent_by_type(inspections);

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
          {visible.map((inspection) => (
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
