"use client";

import React from "react";

import { DataState } from "../../components/data-state";
import { PurchaseTable } from "../../components/purchase-table";
import { getPurchases } from "../../lib/api";
import { use_api_data } from "../../lib/use-api-data";

export default function PurchasesPage() {
  const { data: receipts, error_message, is_loading } = use_api_data(getPurchases);

  if (is_loading) {
    return <DataState state="loading" />;
  }
  if (error_message) {
    return <DataState errorMessage={error_message} state="error" />;
  }
  if (!receipts || receipts.length === 0) {
    return <DataState state="empty" />;
  }

  const within_horizon_count = receipts.filter((receipt) => receipt.within_horizon).length;

  return (
    <div className="page-shell">
      <header className="page-header">
        <div>
          <p className="section-kicker">INBOUND SCHEDULE</p>
          <h1>구매관리</h1>
          <p>
            자재 예정 입고 일정입니다. 14일 전망에 반영되는 입고 {within_horizon_count}건이
            재고 소진 판정에 쓰입니다.
          </p>
        </div>
        <span className="page-header__count">{receipts.length} RECEIPTS</span>
      </header>
      <PurchaseTable receipts={receipts} />
    </div>
  );
}
