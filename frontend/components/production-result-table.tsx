import React from "react";

import type { ProductionResult } from "../lib/api";
import { format_date, format_mixed_quantity, format_percentage } from "../lib/format";

function achievement_label(result: ProductionResult): string {
  // 실적이 0이어도 달성률은 0이 된다. 계획 수량을 함께 봐야 "계획이 없던 날"과
  // "계획을 통째로 놓친 날"이 갈린다.
  if (result.planned_quantity === 0) {
    return "계획 없음";
  }
  return result.achievement_rate >= 100 ? "계획 달성" : "계획 미달";
}

export function ProductionResultTable({
  results,
}: Readonly<{ results: ProductionResult[] }>) {
  return (
    <div className="data-table-shell">
      <table className="operation-table operation-table--results">
        <thead>
          <tr>
            <th scope="col">일자</th>
            <th scope="col">계획</th>
            <th scope="col">실적</th>
            <th scope="col">달성률</th>
            <th scope="col">판정</th>
            <th scope="col">실적 오더</th>
          </tr>
        </thead>
        <tbody>
          {/* 계획·실적은 그날 실적이 잡힌 여러 제품을 더한 값이다. 그 제품들의
              단위가 갈리면 null 이 되고 「단위 혼재」로 적힌다. 계획과 실적이
              단위를 나눠 갖는 것은 둘이 서로 다른 제품 집합에서 나오기 때문이다. */}
          {results.map((result) => (
            <tr key={result.work_date}>
              <td>{format_date(result.work_date)}</td>
              <td className="numeric-cell">{format_mixed_quantity(result.planned_quantity, result.planned_quantity_uom)}</td>
              <td className="numeric-cell">{format_mixed_quantity(result.actual_quantity, result.actual_quantity_uom)}</td>
              <td className="numeric-cell">{format_percentage(result.achievement_rate)}</td>
              <td>{achievement_label(result)}</td>
              <td className="numeric-cell">{result.active_order_count}건</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
