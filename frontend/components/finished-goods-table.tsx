import React from "react";

import type { FinishedGoods } from "../lib/api";
import { format_quantity } from "../lib/format";

// 설정기간이 없다는 것은 유효기간을 두지 않는 제품이라는 뜻이다.
function format_shelf_life(value: number | null): string {
  return value === null ? "무기한" : `${value}일`;
}

/**
 * 영업관리는 출하 관점만 본다 — 제품별로 지금 내보낼 수 있는 양과, 그러지
 * 못하는 양이 어디에 묶여 있는지. 로트 하나하나와 창고 구분은 재고관리의
 * 창고별 재고가 맡는다.
 */
export function FinishedGoodsTable({
  finishedGoods,
}: Readonly<{ finishedGoods: FinishedGoods[] }>) {
  return (
    <div className="data-table-shell">
      <table className="operation-table operation-table--finished-goods">
        <thead>
          <tr>
            <th scope="col">제품</th>
            <th scope="col">유효기간 설정</th>
            <th scope="col">출하 가능</th>
            <th scope="col">검사 대기</th>
            <th scope="col">불합격</th>
            <th scope="col">만료</th>
            <th scope="col">보유 합계</th>
          </tr>
        </thead>
        <tbody>
          {finishedGoods.map((product) => (
            <tr key={product.product_id}>
              <td>
                <strong>{product.product_name}</strong>
                <span className="table-secondary">
                  {product.product_code} · ID {product.product_id}
                </span>
              </td>
              <td className="numeric-cell">{format_shelf_life(product.shelf_life_days)}</td>
              <td className="numeric-cell">{format_quantity(product.releasable_stock)}</td>
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
