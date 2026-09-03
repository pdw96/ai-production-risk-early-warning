import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { describe, expect, it } from "vitest";

import type { QualityInspection, QualityInspectionSummary } from "../lib/api";
import { QualityInspectionTable, QualitySummaryCards } from "./quality-inspection-table";

const summaries: QualityInspectionSummary[] = [
  { failed_count: 0, inspection_type: "IQC", passed_count: 46, total_count: 46 },
  { failed_count: 8, inspection_type: "PQC", passed_count: 122, total_count: 130 },
  { failed_count: 8, inspection_type: "OQC", passed_count: 132, total_count: 140 },
];

const inspections: QualityInspection[] = [
  {
    inspected_date: "2026-08-31",
    inspection_id: 1,
    inspection_type: "OQC",
    item_code: "FG-01",
    item_name: "가상 제품 A",
    reason: "표면 광택 편차",
    result: "불합격",
    target_label: "LOT-FG-01-260830",
    target_type: "완제품 로트",
  },
  {
    inspected_date: "2026-08-30",
    inspection_id: 2,
    inspection_type: "IQC",
    item_code: "RM-01",
    item_name: "가상 자재 A",
    reason: null,
    result: "합격",
    target_label: "LOT-RM-01-01",
    target_type: "자재 로트",
  },
];

describe("QualitySummaryCards", () => {
  it("counts each inspection type separately", () => {
    const markup = renderToStaticMarkup(<QualitySummaryCards summaries={summaries} />);

    ["IQC 수입검사", "PQC 공정검사", "OQC 출하검사", "46건", "130건", "140건"].forEach(
      (expected) => {
        expect(markup).toContain(expected);
      },
    );
    expect(markup).toContain("합격 122 · 불합격 8");
  });
});

describe("QualityInspectionTable", () => {
  it("shows the target and the failure reason for each record", () => {
    const markup = renderToStaticMarkup(
      <QualityInspectionTable inspections={inspections} />,
    );

    ["OQC", "완제품 로트", "LOT-FG-01-260830", "불합격", "표면 광택 편차"].forEach(
      (expected) => {
        expect(markup).toContain(expected);
      },
    );
    // 합격에는 사유가 없으므로 빈 칸 대신 자리표시자를 쓴다.
    expect(markup).toContain("—");
  });

  it("renders exactly what the API sent without dropping rows", () => {
    // 어디까지 보여줄지는 응답 크기를 결정하는 문제라 서버가 진다. 화면이 또
    // 자르면 요약 건수와 목록이 왜 다른지 설명할 자리가 두 곳이 된다.
    const many = Array.from({ length: 60 }, (_, index) => ({
      ...inspections[1],
      inspection_id: index + 100,
      target_label: `LOT-RM-99-${index}`,
    }));

    const markup = renderToStaticMarkup(<QualityInspectionTable inspections={many} />);

    expect(markup).toContain("LOT-RM-99-0");
    expect(markup).toContain("LOT-RM-99-59");
    expect(markup.match(/<tr>/g)).toHaveLength(many.length + 1);
  });
});
