"use client";

import React from "react";

import { DataState } from "../../components/data-state";
import { MaterialTable } from "../../components/material-table";
import { getMaterials } from "../../lib/api";
import { use_api_data } from "../../lib/use-api-data";

export default function MaterialsPage() {
  const { data: materials, error_message, is_loading } = use_api_data(getMaterials);

  if (is_loading) {
    return <DataState state="loading" />;
  }
  if (error_message) {
    return <DataState errorMessage={error_message} state="error" />;
  }
  if (!materials || materials.length === 0) {
    return <DataState state="empty" />;
  }

  return (
    <div className="page-shell">
      <header className="page-header">
        <div>
          <p className="section-kicker">14-DAY SUPPLY WINDOW</p>
          <h1>재고관리</h1>
          <p>로트별 재고와 창고, 예정 입고와 생산 소요를 반영한 14일 수급 전망입니다.</p>
        </div>
        <span className="page-header__count">{materials.length} MATERIALS</span>
      </header>
      <MaterialTable materials={materials} />
    </div>
  );
}
