"use client";

import React from "react";

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
          <p className="section-kicker">FINISHED GOODS</p>
          <h1>영업관리</h1>
          <p>
            제품별 완제품 로트 재고입니다. 출하 가능 재고는{" "}
            {format_quantity(releasable_total)}입니다.
          </p>
        </div>
        <span className="page-header__count">{finished_goods.length} PRODUCTS</span>
      </header>
      <FinishedGoodsTable finishedGoods={finished_goods} />
      <section className="page-panel">
        <div className="page-panel__header">
          <h2>이 화면을 읽는 법</h2>
          <span>다섯 수량은 서로 겹치지 않으며 합이 로트 합계와 같습니다</span>
        </div>
        <p className="page-panel__pending">
          완제품은 생산창고에서 OQC를 기다리고, 합격분만 완제품창고로 이관되어 출하 대상이
          됩니다. 불합격분은 생산창고에 남고 만료분은 목록에 남되 출하 가능 재고에서
          빠집니다 — 로트는 지우지 않는 영구 기록이기 때문입니다.
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
