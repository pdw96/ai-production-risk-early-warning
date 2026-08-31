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
          <h1>자재 수급 전망</h1>
          <p>예정 입고와 생산 소요를 반영한 재고 소진·안전재고 위험입니다.</p>
        </div>
        <span className="page-header__count">{materials.length} MATERIALS</span>
      </header>
      <MaterialTable materials={materials} />
    </div>
  );
}
