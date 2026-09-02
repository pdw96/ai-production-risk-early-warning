import React from "react";

import type { ProductionResult } from "../lib/api";
import { format_date, format_percentage, format_quantity } from "../lib/format";

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
          {results.map((result) => (
            <tr key={result.work_date}>
              <td>{format_date(result.work_date)}</td>
              <td className="numeric-cell">{format_quantity(result.planned_quantity)}</td>
              <td className="numeric-cell">{format_quantity(result.actual_quantity)}</td>
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
