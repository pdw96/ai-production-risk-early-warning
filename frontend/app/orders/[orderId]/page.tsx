"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import React, { useCallback } from "react";

import { DataState } from "../../../components/data-state";
import { OrderTable } from "../../../components/order-table";
import { getOrder } from "../../../lib/api";
import { format_date, format_quantity } from "../../../lib/format";
import { use_api_data } from "../../../lib/use-api-data";

export default function OrderDetailPage() {
  const params = useParams<{ orderId: string }>();
  const order_id = Number(params.orderId);
  const load_order = useCallback(async () => {
    if (!Number.isInteger(order_id) || order_id <= 0) {
      throw new Error("올바르지 않은 오더 ID입니다.");
    }
    return getOrder(order_id);
  }, [order_id]);
  const { data: order, error_message, is_loading } = use_api_data(load_order);

  if (is_loading) {
    return <DataState state="loading" />;
  }
  if (error_message) {
    return <DataState errorMessage={error_message} state="error" />;
  }
  if (!order) {
    return <DataState state="empty" />;
  }

  return (
    <div className="page-shell">
      <header className="page-header">
        <div>
          <Link className="page-back-link" href="/orders">← 전체 오더</Link>
          <p className="section-kicker">ORDER TRACE</p>
          <h1>{order.order_number}</h1>
          <p>{order.product_code} · {order.product_name}</p>
        </div>
        <span className="page-header__count">DUE {format_date(order.due_date)}</span>
      </header>

      <section aria-label="오더 계산 결과" className="page-panel">
        <div className="page-panel__header">
          <h2>납기 계산 결과</h2>
          <span>잔여 {format_quantity(order.remaining_quantity)}</span>
        </div>
        <OrderTable orders={[order]} />
      </section>

      <section aria-label="최근 생산 실적" className="page-panel">
        <div className="page-panel__header">
          <h2>최근 생산 기록</h2>
          <span>{order.recent_productions.length} DAYS</span>
        </div>
        {order.recent_productions.length === 0 ? (
          <DataState state="empty" />
        ) : (
          <div className="data-table-shell">
            <table className="operation-table operation-table--history">
              <thead>
                <tr>
                  <th scope="col">작업일</th>
                  <th scope="col">계획 수량</th>
                  <th scope="col">실적 수량</th>
                </tr>
              </thead>
              <tbody>
                {order.recent_productions.map((production) => (
                  <tr key={production.work_date}>
                    <td>{format_date(production.work_date)}</td>
                    <td className="numeric-cell">{format_quantity(production.planned_quantity)}</td>
                    <td className="numeric-cell">{format_quantity(production.actual_quantity)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
