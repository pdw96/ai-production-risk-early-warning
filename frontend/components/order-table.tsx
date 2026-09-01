import Link from "next/link";
import React from "react";

import type { Order } from "../lib/api";
import { format_date, format_percentage, format_quantity } from "../lib/format";
import { StatusBadge } from "./status-badge";

export function OrderTable({ orders }: Readonly<{ orders: Order[] }>) {
  return (
    <div className="data-table-shell">
      <table className="operation-table operation-table--orders">
        <thead>
          <tr>
            <th scope="col">오더</th>
            <th scope="col">제품</th>
            <th scope="col">납기</th>
            <th scope="col">계획</th>
            <th scope="col">실적</th>
            <th scope="col">달성률</th>
            <th scope="col">일평균</th>
            <th scope="col">잔여</th>
            <th scope="col">완료 예상</th>
            <th scope="col">판정</th>
            <th scope="col">판정 근거</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((order) => (
            <tr key={order.order_id}>
              <td>
                <Link className="table-primary-link" href={`/orders/${order.order_id}`}>
                  {order.order_number}
                </Link>
                <span className="table-secondary">ID {order.order_id}</span>
              </td>
              <td>
                <strong>{order.product_name}</strong>
                <span className="table-secondary">{order.product_code}</span>
              </td>
              <td>{format_date(order.due_date)}</td>
              <td className="numeric-cell">{format_quantity(order.planned_quantity)}</td>
              <td className="numeric-cell">{format_quantity(order.actual_quantity)}</td>
              <td className="numeric-cell">{format_percentage(order.completion_rate)}</td>
              <td className="numeric-cell">{format_quantity(order.average_daily_output)}/일</td>
              <td className="numeric-cell">{format_quantity(order.remaining_quantity)}</td>
              <td>{format_date(order.estimated_completion_date)}</td>
              <td><StatusBadge severity={order.severity} /></td>
              <td className="operation-table__reason">{order.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
