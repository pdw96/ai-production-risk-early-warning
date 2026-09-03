import React from "react";

import type { FinishedGoods, FinishedGoodsLot } from "../lib/api";
import { format_date, format_quantity } from "../lib/format";

// 설정기간이 없다는 것은 유효기간을 두지 않는 제품이라는 뜻이다.
function format_shelf_life(value: number | null): string {
  return value === null ? "무기한" : `${value}일`;
}

function format_lot_expiry(value: string | null): string {
  return value ? `유효기간 ${format_date(value)}` : "유효기간 없음";
}

function LotDetails({ lots }: Readonly<{ lots: FinishedGoodsLot[] }>) {
  if (lots.length === 0) {
    return <span className="table-secondary">보유 로트 없음</span>;
  }

  return (
    <details className="lot-details">
      <summary>로트 {lots.length}건</summary>
      <ul className="lot-details__list">
        {lots.map((lot) => (
          <li key={`${lot.lot_number}-${lot.warehouse}`}>
            <span className="lot-details__number">{lot.lot_number}</span>
            <span className="lot-details__warehouse">{lot.warehouse}</span>
            <span className="lot-details__quantity">{format_quantity(lot.quantity)}</span>
            <span className="lot-details__dates">
              생산 {format_date(lot.produced_date)} · {format_lot_expiry(lot.expiry_date)} ·
              OQC {lot.qc_status}
            </span>
            <span className="lot-details__state">{lot.state}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}

export function FinishedGoodsTable({
  finishedGoods,
}: Readonly<{ finishedGoods: FinishedGoods[] }>) {
  return (
    <div className="data-table-shell">
      <table className="operation-table operation-table--finished-goods">
        <thead>
          <tr>
            <th scope="col">제품</th>
            <th scope="col">출하 가능</th>
            <th scope="col">이관 대기</th>
            <th scope="col">검사 대기</th>
            <th scope="col">불합격</th>
            <th scope="col">만료</th>
            <th scope="col">로트 합계</th>
          </tr>
        </thead>
        <tbody>
          {finishedGoods.map((product) => (
            <tr key={product.product_id}>
              <td>
                <strong>{product.product_name}</strong>
                <span className="table-secondary">
                  {product.product_code} · ID {product.product_id} · 유효기간{" "}
                  {format_shelf_life(product.shelf_life_days)}
                </span>
                <LotDetails lots={product.lots} />
              </td>
              <td className="numeric-cell">{format_quantity(product.releasable_stock)}</td>
              <td className="numeric-cell">
                {format_quantity(product.transfer_pending_stock)}
              </td>
              <td className="numeric-cell">
                {format_quantity(product.inspection_pending_stock)}
              </td>
              <td className="numeric-cell">{format_quantity(product.rejected_stock)}</td>
              <td className="numeric-cell">{format_quantity(product.expired_stock)}</td>
              <td className="numeric-cell">{format_quantity(product.total_lot_quantity)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
