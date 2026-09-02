import React from "react";

import type { PurchaseReceipt } from "../lib/api";
import { format_date, format_quantity } from "../lib/format";

function format_arrival(days: number): string {
  if (days === 0) {
    return "오늘 도착";
  }
  return days > 0 ? `D-${days}` : `${Math.abs(days)}일 경과`;
}

function format_expiry_date(value: string | null): string {
  return value ? format_date(value) : "유효기간 없음";
}

export function PurchaseTable({
  receipts,
}: Readonly<{ receipts: PurchaseReceipt[] }>) {
  return (
    <div className="data-table-shell">
      <table className="operation-table operation-table--purchases">
        <thead>
          <tr>
            <th scope="col">입고 번호</th>
            <th scope="col">자재</th>
            <th scope="col">입고 예정일</th>
            <th scope="col">도착까지</th>
            <th scope="col">수량</th>
            <th scope="col">유효기간</th>
            <th scope="col">14일 전망 반영</th>
          </tr>
        </thead>
        <tbody>
          {receipts.map((receipt) => (
            <tr key={receipt.receipt_id}>
              <td>
                <span className="table-primary-link">
                  PO-{receipt.receipt_id.toString().padStart(3, "0")}
                </span>
              </td>
              <td>
                <strong>{receipt.material_name}</strong>
                <span className="table-secondary">{receipt.material_code}</span>
              </td>
              <td>{format_date(receipt.scheduled_date)}</td>
              <td>{format_arrival(receipt.days_until_arrival)}</td>
              <td className="numeric-cell">{format_quantity(receipt.scheduled_quantity)}</td>
              <td>{format_expiry_date(receipt.expiry_date)}</td>
              <td>{receipt.within_horizon ? "반영" : "기간 밖"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
