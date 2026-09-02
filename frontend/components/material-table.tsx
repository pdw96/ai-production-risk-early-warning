import React from "react";

import type { Material, MaterialLot } from "../lib/api";
import { format_date, format_quantity } from "../lib/format";
import { StatusBadge } from "./status-badge";

function format_stockout_date(value: string | null): string {
  return value ? format_date(value) : "소진 없음";
}

function format_expiry_date(value: string | null): string {
  return value ? format_date(value) : "기간 내 없음";
}

function LotDetails({ lots }: Readonly<{ lots: MaterialLot[] }>) {
  if (lots.length === 0) {
    return <span className="table-secondary">보유 로트 없음</span>;
  }

  return (
    <details className="lot-details">
      <summary>로트 {lots.length}건</summary>
      <ul className="lot-details__list">
        {/* 예정 입고의 가상 로트번호는 보유 로트와 겹칠 수 있으므로 순번까지 키에 넣는다. */}
        {lots.map((lot, index) => (
          <li key={`${lot.lot_number}-${lot.warehouse}-${index}`}>
            <span className="lot-details__number">{lot.lot_number}</span>
            <span className="lot-details__warehouse">{lot.warehouse}</span>
            <span className="lot-details__quantity">{format_quantity(lot.quantity)}</span>
            <span className="lot-details__dates">
              입고 {format_date(lot.received_date)} · 유효기간{" "}
              {format_expiry_date(lot.expiry_date)}
            </span>
            <span className="lot-details__state">{lot.state}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}

export function MaterialTable({ materials }: Readonly<{ materials: Material[] }>) {
  return (
    <div className="data-table-shell">
      <table className="operation-table operation-table--materials">
        <thead>
          <tr>
            <th scope="col">자재</th>
            <th scope="col">가용 재고</th>
            <th scope="col">창고별 재고</th>
            <th scope="col">안전 재고</th>
            <th scope="col">14일 말 재고</th>
            <th scope="col">기간 최저</th>
            <th scope="col">폐기 예정</th>
            <th scope="col">최초 유효기간</th>
            <th scope="col">부족 예상</th>
            <th scope="col">소진일</th>
            <th scope="col">판정</th>
            <th scope="col">판정 근거</th>
            <th scope="col">권장 조치</th>
          </tr>
        </thead>
        <tbody>
          {materials.map((material) => (
            <tr key={material.material_id}>
              <td>
                <strong>{material.material_name}</strong>
                <span className="table-secondary">
                  {material.material_code} · ID {material.material_id}
                </span>
                <LotDetails lots={material.lots} />
              </td>
              <td className="numeric-cell">{format_quantity(material.current_stock)}</td>
              <td className="numeric-cell">
                <span className="table-secondary">
                  원재료창고 {format_quantity(material.raw_warehouse_stock)}
                </span>
                <span className="table-secondary">
                  생산창고 {format_quantity(material.production_warehouse_stock)}
                </span>
              </td>
              <td className="numeric-cell">{format_quantity(material.safety_stock)}</td>
              <td className="numeric-cell">{format_quantity(material.ending_stock)}</td>
              <td className="numeric-cell">{format_quantity(material.minimum_stock)}</td>
              <td className="numeric-cell">{format_quantity(material.expiring_quantity)}</td>
              <td>{format_expiry_date(material.first_expiry_date)}</td>
              <td>{material.shortage_expected ? "부족 예상" : "수급 가능"}</td>
              <td>{format_stockout_date(material.stockout_date)}</td>
              <td><StatusBadge severity={material.severity} /></td>
              <td className="operation-table__reason">{material.reason}</td>
              <td className="operation-table__reason">{material.recommendation}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
