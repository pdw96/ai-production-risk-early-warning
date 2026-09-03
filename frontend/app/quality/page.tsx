"use client";

import React from "react";

import { DataState } from "../../components/data-state";
import {
  QualityInspectionTable,
  QualitySummaryCards,
} from "../../components/quality-inspection-table";
import { getQualityInspections } from "../../lib/api";
import { use_api_data } from "../../lib/use-api-data";

export default function QualityPage() {
  const { data: quality, error_message, is_loading } = use_api_data(getQualityInspections);

  if (is_loading) {
    return <DataState state="loading" />;
  }
  if (error_message) {
    return <DataState errorMessage={error_message} state="error" />;
  }
  if (!quality || quality.inspections.length === 0) {
    return <DataState state="empty" />;
  }

  // 요약은 잘라낸 기록까지 포함한 전체 집계라 목록 길이와 다르다.
  const failed_count = quality.summaries.reduce(
    (total, summary) => total + summary.failed_count,
    0,
  );
  const recorded_count = quality.summaries.reduce(
    (total, summary) => total + summary.total_count,
    0,
  );

  return (
    <div className="page-shell">
      <header className="page-header">
        <div>
          <p className="section-kicker">QUALITY CONTROL</p>
          <h1>품질관리</h1>
          <p>
            수입검사(IQC)·공정검사(PQC)·출하검사(OQC) 기록입니다. 불합격 {failed_count}건이
            조치 대상입니다.
          </p>
        </div>
        <span className="page-header__count">{recorded_count} RECORDS</span>
      </header>
      <QualitySummaryCards summaries={quality.summaries} />
      <section className="page-panel">
        <div className="page-panel__header">
          <h2>검사 기록</h2>
          <span>
            유형별 최신 {quality.inspections.length}건 / 전체 {recorded_count}건
          </span>
        </div>
        <QualityInspectionTable inspections={quality.inspections} />
        <p className="page-panel__pending">
          OQC 합격분만 완제품창고로 이관되어 출하 대상이 됩니다. IQC는 이미 입고된 자재의
          기록이라 전건 합격이며, PQC 불합격은 공정 이상 기록일 뿐 생산 수량을 바꾸지
          않습니다.
        </p>
      </section>
    </div>
  );
}
