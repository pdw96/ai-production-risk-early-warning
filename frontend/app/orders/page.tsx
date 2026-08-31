"use client";

import React from "react";

import { DataState } from "../../components/data-state";
import { OrderTable } from "../../components/order-table";
import { getOrders } from "../../lib/api";
import { use_api_data } from "../../lib/use-api-data";

export default function OrdersPage() {
  const { data: orders, error_message, is_loading } = use_api_data(getOrders);

  if (is_loading) {
    return <DataState state="loading" />;
  }
  if (error_message) {
    return <DataState errorMessage={error_message} state="error" />;
  }
  if (!orders || orders.length === 0) {
    return <DataState state="empty" />;
  }

  return (
    <div className="page-shell">
      <header className="page-header">
        <div>
          <p className="section-kicker">ORDER REGISTER</p>
          <h1>오더 납기 현황</h1>
          <p>계획 대비 실적과 완료 예상일을 기준으로 납기 위험을 확인합니다.</p>
        </div>
        <span className="page-header__count">{orders.length} ORDERS</span>
      </header>
      <OrderTable orders={orders} />
    </div>
  );
}
