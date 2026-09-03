import React from "react";

import type { BomRequirement, MasterItem } from "../lib/api";
import { format_quantity } from "../lib/format";

function format_optional_quantity(value: number | null): string {
  return value === null ? "해당 없음" : format_quantity(value);
}

// 설정기간이 없다는 것은 유효기간을 두지 않는 품목이라는 뜻이다. "해당 없음"
// 으로 쓰면 값을 아직 안 정한 것처럼 읽힌다.
function format_shelf_life(value: number | null): string {
  return value === null ? "무기한" : `${value}일`;
}

function format_linked_label(item: MasterItem): string {
  return item.item_type === "제품"
    ? `소요 자재 ${item.linked_item_count}종`
    : `사용 제품 ${item.linked_item_count}종`;
}

export function MasterItemTable({ items }: Readonly<{ items: MasterItem[] }>) {
  return (
    <div className="data-table-shell">
      <table className="operation-table operation-table--master">
        <thead>
          <tr>
            <th scope="col">구분</th>
            <th scope="col">품목 코드</th>
            <th scope="col">품목명</th>
            <th scope="col">안전 재고</th>
            <th scope="col">유효기간 설정</th>
            <th scope="col">보유 로트</th>
            <th scope="col">연결 품목</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={`${item.item_type}-${item.item_code}`}>
              <td>{item.item_type}</td>
              <td><span className="table-primary-link">{item.item_code}</span></td>
              <td><strong>{item.item_name}</strong></td>
              <td className="numeric-cell">{format_optional_quantity(item.safety_stock)}</td>
              <td className="numeric-cell">{format_shelf_life(item.shelf_life_days)}</td>
              <td className="numeric-cell">
                {item.lot_count === null ? "해당 없음" : `${item.lot_count}건`}
              </td>
              <td>{format_linked_label(item)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function BomTable({
  bomRequirements,
}: Readonly<{ bomRequirements: BomRequirement[] }>) {
  return (
    <div className="data-table-shell">
      <table className="operation-table operation-table--bom">
        <thead>
          <tr>
            <th scope="col">제품</th>
            <th scope="col">자재</th>
            <th scope="col">단위 소요량</th>
          </tr>
        </thead>
        <tbody>
          {bomRequirements.map((requirement) => (
            <tr key={`${requirement.product_code}-${requirement.material_code}`}>
              <td>
                <strong>{requirement.product_name}</strong>
                <span className="table-secondary">{requirement.product_code}</span>
              </td>
              <td>
                <strong>{requirement.material_name}</strong>
                <span className="table-secondary">{requirement.material_code}</span>
              </td>
              <td className="numeric-cell">{format_quantity(requirement.unit_quantity)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
