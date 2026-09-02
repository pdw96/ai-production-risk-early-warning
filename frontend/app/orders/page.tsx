"use client";

import React from "react";

import { DataState } from "../../components/data-state";
import { OrderTable } from "../../components/order-table";
import { ProductionResultTable } from "../../components/production-result-table";
import { getOrders, getProductionResults } from "../../lib/api";
import { use_api_data } from "../../lib/use-api-data";

export default function OrdersPage() {
  const { data: orders, error_message, is_loading } = use_api_data(getOrders);
  const { data: production_results } = use_api_data(getProductionResults);

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
          <h1>생산관리</h1>
          <p>생산 오더의 계획 대비 실적과 완료 예상일을 기준으로 납기 위험을 확인합니다.</p>
        </div>
        <span className="page-header__count">{orders.length} ORDERS</span>
      </header>
      <OrderTable orders={orders} />
      <section className="page-panel">
        <div className="page-panel__header">
          <h2>생산실적</h2>
          <span>기준일 포함 최근 14일의 계획 대비 실적</span>
        </div>
        {production_results ? (
          <ProductionResultTable results={production_results} />
        ) : (
          <p className="page-panel__pending">생산실적을 불러오는 중입니다.</p>
        )}
      </section>
    </div>
  );
}
