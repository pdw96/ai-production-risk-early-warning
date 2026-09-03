import React from "react";

import type { WarehouseLot } from "../lib/api";
import { format_date, format_quantity } from "../lib/format";

function format_expiry(value: string | null): string {
  return value ? format_date(value) : "무기한";
}

// 자재는 입고일, 완제품은 생산일이다. 창고에 언제 놓였는가라는 뜻은 같지만
// 같은 말로 쓰면 완제품이 어디선가 입고된 것처럼 읽힌다.
function format_stocked_label(lot: WarehouseLot): string {
  return lot.item_type === "자재" ? "입고" : "생산";
}

export function WarehouseStockTable({ lots }: Readonly<{ lots: WarehouseLot[] }>) {
  return (
    <div className="data-table-shell">
      <table className="operation-table operation-table--warehouse">
        <thead>
          <tr>
            <th scope="col">구분</th>
            <th scope="col">품목</th>
            <th scope="col">로트</th>
            <th scope="col">수량</th>
            <th scope="col">입고·생산일</th>
            <th scope="col">유효기간</th>
            <th scope="col">출하검사</th>
            <th scope="col">상태</th>
          </tr>
        </thead>
        <tbody>
          {lots.map((lot) => (
            <tr key={`${lot.item_type}-${lot.item_code}-${lot.lot_number}`}>
              <td>{lot.item_type}</td>
              <td>
                <strong>{lot.item_name}</strong>
                <span className="table-secondary">{lot.item_code}</span>
              </td>
              <td><span className="table-secondary">{lot.lot_number}</span></td>
              <td className="numeric-cell">{format_quantity(lot.quantity)}</td>
              <td>
                <span className="table-secondary">{format_stocked_label(lot)}</span>
                {format_date(lot.stocked_date)}
              </td>
              <td>{format_expiry(lot.expiry_date)}</td>
              {/* 자재의 수입검사는 입고 시점에 이미 끝나 있어 창고에서 볼 상태가 없다. */}
              <td>{lot.qc_status ?? "—"}</td>
              <td>{lot.expired ? "만료" : "가용"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
