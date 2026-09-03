"use client";

import React from "react";
import Link from "next/link";

import { DataState } from "../../components/data-state";
import { FinishedGoodsTable } from "../../components/finished-goods-table";
import { getFinishedGoods } from "../../lib/api";
import { format_quantity } from "../../lib/format";
import { use_api_data } from "../../lib/use-api-data";

export default function SalesPage() {
  const { data: finished_goods, error_message, is_loading } = use_api_data(getFinishedGoods);

  if (is_loading) {
    return <DataState state="loading" />;
  }
  if (error_message) {
    return <DataState errorMessage={error_message} state="error" />;
  }
  if (!finished_goods || finished_goods.length === 0) {
    return <DataState state="empty" />;
  }

  const releasable_total = finished_goods.reduce(
    (total, product) => total + product.releasable_stock,
    0,
  );

  return (
    <div className="page-shell">
      <header className="page-header">
        <div>
          <p className="section-kicker">SHIPPABLE STOCK</p>
          <h1>영업관리</h1>
          <p>
            지금 내보낼 수 있는 완제품입니다. 출하 가능 재고는{" "}
            {format_quantity(releasable_total)}입니다.
          </p>
        </div>
        <span className="page-header__count">{finished_goods.length} PRODUCTS</span>
      </header>
      <FinishedGoodsTable finishedGoods={finished_goods} />
      <section className="page-panel">
        <div className="page-panel__header">
          <h2>이 화면을 읽는 법</h2>
          <span>네 수량은 서로 겹치지 않으며 합이 보유 합계와 같습니다</span>
        </div>
        <p className="page-panel__pending">
          <strong>출하 가능</strong>은 제품창고에 있고 만료되지 않은 재고입니다. 출하검사에
          합격해야 제품창고로 옮겨지므로, 검사 대기와 불합격은 생산창고에 남아 출하 가능
          재고에서 빠집니다. 만료분도 창고에는 남지만 내보낼 수 없습니다 — 로트는 지우지
          않는 영구 기록이기 때문입니다.
        </p>
        <p className="page-panel__pending">
          로트 하나하나와 창고 구분은{" "}
          <Link href="/materials/warehouses/products">재고관리 · 창고별 재고</Link>에서
          봅니다.
        </p>
        <p className="page-panel__pending">
          출하 일정과 수주 엔티티가 아직 없어 <strong>완제품 재고는 줄지 않고 쌓이기만
          합니다.</strong> 출하 일정 대비 부족을 경보하는 출하 리스크는 다음 확장 계획
          항목입니다.
        </p>
      </section>
    </div>
  );
}
