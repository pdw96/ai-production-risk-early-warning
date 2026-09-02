import React from "react";

import Link from "next/link";

export default function SalesPage() {
  return (
    <div className="page-shell">
      <header className="page-header">
        <div>
          <p className="section-kicker">SALES &amp; SHIPPING</p>
          <h1>영업관리</h1>
          <p>출하 일정과 완제품 재고를 다루는 모듈입니다.</p>
        </div>
        <span className="page-header__count">준비 중</span>
      </header>
      <section className="page-panel module-placeholder">
        <div className="page-panel__header">
          <h2>아직 데이터가 없습니다</h2>
          <span>수주·거래처·출하 엔티티가 이 데모에 아직 없습니다</span>
        </div>
        <p>
          영업관리가 동작하려면 완제품에 로트를 부여하고 완제품 창고 재고를 관리한 뒤,
          출하 일정과 비교해 부족을 판정해야 합니다. 이는 납기·자재에 이은 세 번째
          리스크 타입이며, 기존 납기 리스크와 같은 사건을 두 번 경보할 수 있어 통합
          설계가 선행돼야 합니다.
        </p>
        <p>
          그 전까지 납기 관점의 위험은{" "}
          <Link href="/orders">생산관리</Link>와{" "}
          <Link href="/risks">리스크 보드</Link>에서 확인할 수 있습니다.
        </p>
      </section>
    </div>
  );
}
