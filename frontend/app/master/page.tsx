"use client";

import React from "react";

import { DataState } from "../../components/data-state";
import { BomTable, MasterItemTable } from "../../components/master-item-table";
import { getMasterData } from "../../lib/api";
import { use_api_data } from "../../lib/use-api-data";

export default function MasterPage() {
  const { data: master_data, error_message, is_loading } = use_api_data(getMasterData);

  if (is_loading) {
    return <DataState state="loading" />;
  }
  if (error_message) {
    return <DataState errorMessage={error_message} state="error" />;
  }
  if (!master_data || master_data.items.length === 0) {
    return <DataState state="empty" />;
  }

  return (
    <div className="page-shell">
      <header className="page-header">
        <div>
          <p className="section-kicker">ITEM MASTER</p>
          <h1>기준정보관리</h1>
          <p>제품·자재 품목 코드와 제품별 자재 소요량(BOM)입니다.</p>
        </div>
        <span className="page-header__count">{master_data.items.length} ITEMS</span>
      </header>
      <MasterItemTable items={master_data.items} />
      <section className="page-panel">
        <div className="page-panel__header">
          <h2>BOM 소요량</h2>
          <span>제품 한 단위를 만드는 데 필요한 자재 수량</span>
        </div>
        <BomTable bomRequirements={master_data.bom_requirements} />
      </section>
    </div>
  );
}
