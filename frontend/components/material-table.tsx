import React from "react";

import type { Material } from "../lib/api";
import { format_date, format_quantity } from "../lib/format";
import { StatusBadge } from "./status-badge";

function format_stockout_date(value: string | null): string {
  return value ? format_date(value) : "소진 없음";
}

export function MaterialTable({ materials }: Readonly<{ materials: Material[] }>) {
  return (
    <div className="data-table-shell">
      <table className="operation-table operation-table--materials">
        <thead>
          <tr>
            <th scope="col">자재</th>
            <th scope="col">현재 재고</th>
            <th scope="col">안전 재고</th>
            <th scope="col">14일 말 재고</th>
            <th scope="col">기간 최저</th>
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
              </td>
              <td className="numeric-cell">{format_quantity(material.current_stock)}</td>
              <td className="numeric-cell">{format_quantity(material.safety_stock)}</td>
              <td className="numeric-cell">{format_quantity(material.ending_stock)}</td>
              <td className="numeric-cell">{format_quantity(material.minimum_stock)}</td>
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
