"use client";

import React from "react";
import { notFound, useParams } from "next/navigation";

import { DataState } from "../../../../components/data-state";
import { WarehouseStockTable } from "../../../../components/warehouse-stock-table";
import { getWarehouseStock } from "../../../../lib/api";
import type { WarehouseLot } from "../../../../lib/api";
import { format_quantity } from "../../../../lib/format";
import { use_api_data } from "../../../../lib/use-api-data";

// 주소에 한글 창고명을 넣지 않기 위한 코드다. 서버의 WAREHOUSE_SLUGS 와 같은 집합.
const WAREHOUSE_SLUGS = ["raw", "production", "products"];

/**
 * 창고 합계를 단위별로 낸다.
 *
 * 응답의 `material_quantity` 는 단위를 넘어 더한 값이라, 원재료창고처럼 kg 와
 * L 이 함께 있는 곳에서는 무엇도 세지 않는다. 그래서 그 칸을 쓰지 않고 로트에서
 * 직접 낸다 — 킬로그램과 리터를 더한 숫자를 크게 띄우는 것보다, 두 줄로 나누어
 * 적는 편이 사실이다.
 */
function total_by_unit(lots: WarehouseLot[], keep: (lot: WarehouseLot) => boolean): string {
  const totals = new Map<string, number>();
  for (const lot of lots) {
    if (!keep(lot)) {
      continue;
    }
    totals.set(lot.stock_uom, (totals.get(lot.stock_uom) ?? 0) + lot.quantity);
  }
  if (totals.size === 0) {
    return format_quantity(0);
  }
  return [...totals.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([unit, quantity]) => format_quantity(quantity, unit))
    .join(" · ");
}

export default function WarehouseStockPage() {
  const params = useParams<{ warehouseSlug: string }>();
  const warehouse_slug = params.warehouseSlug;
  const load = React.useCallback(
    () => getWarehouseStock(warehouse_slug),
    [warehouse_slug],
  );
  const { data: stock, error_message, is_loading } = use_api_data(load);

  if (!WAREHOUSE_SLUGS.includes(warehouse_slug)) {
    notFound();
  }
  if (is_loading) {
    return <DataState state="loading" />;
  }
  if (error_message) {
    return <DataState errorMessage={error_message} state="error" />;
  }
  if (!stock) {
    return <DataState state="empty" />;
  }

  return (
    <div className="page-shell">
      <header className="page-header">
        <div>
          <p className="section-kicker">WAREHOUSE STOCK</p>
          <h1>{stock.warehouse}</h1>
          <p>{stock.description}</p>
        </div>
        <span className="page-header__count">{stock.lots.length} LOTS</span>
      </header>
      <div className="warehouse-summary">
        <article className="warehouse-summary__card">
          <p className="warehouse-summary__label">자재</p>
          <strong className="warehouse-summary__value">
            {total_by_unit(stock.lots, (lot) => lot.item_type === "자재")}
          </strong>
          <p className="warehouse-summary__detail">{stock.material_lot_count}개 로트</p>
        </article>
        <article className="warehouse-summary__card">
          <p className="warehouse-summary__label">제품</p>
          <strong className="warehouse-summary__value">
            {total_by_unit(stock.lots, (lot) => lot.item_type === "제품")}
          </strong>
          <p className="warehouse-summary__detail">{stock.product_lot_count}개 로트</p>
        </article>
        <article className="warehouse-summary__card">
          <p className="warehouse-summary__label">만료</p>
          <strong className="warehouse-summary__value">
            {total_by_unit(stock.lots, (lot) => lot.expired)}
          </strong>
          <p className="warehouse-summary__detail">창고에 남아 있으나 쓸 수 없음</p>
        </article>
      </div>
      {stock.lots.length === 0 ? (
        <DataState state="empty" />
      ) : (
        <WarehouseStockTable lots={stock.lots} />
      )}
    </div>
  );
}
