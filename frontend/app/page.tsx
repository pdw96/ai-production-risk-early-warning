"use client";

import Link from "next/link";
import React, { useEffect, useState } from "react";

import { DataState } from "../components/data-state";
import { KpiCard } from "../components/kpi-card";
import { ProductionTrendChart } from "../components/production-trend-chart";
import { StatusBadge } from "../components/status-badge";
import { getDashboard, type Dashboard } from "../lib/api";
// 수량 표기는 한 곳에서만 정한다. 여기 사본을 두었더니 자재에 단위가 생겼을 때
// 이 화면만 「개」로 남았다 — 같은 규칙을 두 곳에 적으면 반드시 갈린다.
// 날짜와 백분율은 이 화면만의 표기라(「2026년 9월 7일」) 아직 사본이 맞다.
import { format_count, format_mixed_quantity, format_quantity } from "../lib/format";

function format_percentage(value: number): string {
  return `${new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 1 }).format(value)}%`;
}

function format_date(value: string | null): string {
  if (!value) {
    return "예측 불가";
  }

  const [year, month, day] = value.split("-").map(Number);
  return `${year}년 ${month}월 ${day}일`;
}

/**
 * 데이터베이스에 아직 아무것도 없는가.
 *
 * 이 판단이 **한 번도 참이 될 수 없었다.** 추이는 실적이 없어도 7일치 0을 채워
 * 보내므로 `production_trend` 는 언제나 7이고, 권고도 위험이 없으면 「현재 주요
 * 위험이 없습니다」 한 줄이 들어가 0이 되지 않는다. 그래서 표가 비어 있는
 * 데이터베이스(운영 기본값은 자동 시드를 켜지 않는다)에서 화면은 **아무 문제
 * 없는 공장**처럼 보였다 — 0으로 채운 차트와 「위험 없음」이 그렇게 읽힌다.
 *
 * 대신 **제품이 하나라도 있는가**를 본다. 제품별 계열은 실적과 무관하게 완제품
 * 마스터에서 나오므로, 그것이 비어 있다는 것은 기준정보가 아직 없다는 뜻이다.
 * 정상적으로 도는 공장에서는 위험이 없어도 이 목록이 차 있다.
 */
function is_empty_dashboard(dashboard: Dashboard): boolean {
  return (
    dashboard.product_trends.length === 0 &&
    dashboard.top_order_risks.length === 0 &&
    dashboard.top_material_risks.length === 0
  );
}

export default function HomePage() {
  const [dashboard, set_dashboard] = useState<Dashboard | null>(null);
  const [error_message, set_error_message] = useState<string | null>(null);

  useEffect(() => {
    let is_current = true;

    async function load_dashboard(): Promise<void> {
      try {
        const response = await getDashboard();
        if (is_current) {
          set_dashboard(response);
        }
      } catch (error: unknown) {
        if (is_current) {
          set_error_message(error instanceof Error ? error.message : "알 수 없는 오류가 발생했습니다.");
        }
      }
    }

    void load_dashboard();
    return () => {
      is_current = false;
    };
  }, []);

  if (error_message) {
    return <DataState errorMessage={error_message} state="error" />;
  }

  if (!dashboard) {
    return <DataState state="loading" />;
  }

  if (is_empty_dashboard(dashboard)) {
    return <DataState state="empty" />;
  }

  return (
    <div className="dashboard-page">
      <header className="dashboard-header">
        <div>
          <p className="section-kicker">LIVE OPERATIONS</p>
          <h1>생산 리스크 운영 현황</h1>
          <p>오늘의 생산 차질과 자재 부족 신호를 우선순위로 확인하세요.</p>
        </div>
        <span className="dashboard-header__status">API 실시간 조회</span>
      </header>

      <section aria-label="핵심 운영 지표" className="kpi-grid">
        <Link aria-label={`납기 위험 오더 ${dashboard.kpis.due_risk_order_count}건 상세 보기`} href="/orders">
          <KpiCard detail="납기 일정 재확인 필요" label="납기 위험 오더" value={format_count(dashboard.kpis.due_risk_order_count)} />
        </Link>
        <Link aria-label={`자재 부족 위험 ${dashboard.kpis.material_shortage_count}건 상세 보기`} href="/materials">
          <KpiCard detail="14일 수급 점검 필요" label="자재 부족 위험" value={format_count(dashboard.kpis.material_shortage_count)} />
        </Link>
        {/* 아래 둘은 제품을 넘어 더한 값이다. 응답의 `quantity_uom` 이 그 합의
            단위를 말하고, 완제품 단위가 갈리면 null 이 되어 「단위 혼재」로 적힌다. */}
        <Link aria-label={`오늘 생산 계획 ${format_mixed_quantity(dashboard.kpis.today_plan_quantity, dashboard.quantity_uom)} 상세 보기`} href="/orders">
          <KpiCard detail="당일 계획 물량" label="오늘 생산 계획" value={format_mixed_quantity(dashboard.kpis.today_plan_quantity, dashboard.quantity_uom)} />
        </Link>
        <Link aria-label={`오늘 생산 실적 ${format_mixed_quantity(dashboard.kpis.today_actual_quantity, dashboard.quantity_uom)} 상세 보기`} href="/orders">
          <KpiCard detail="당일 누적 실적" label="오늘 생산 실적" value={format_mixed_quantity(dashboard.kpis.today_actual_quantity, dashboard.quantity_uom)} />
        </Link>
      </section>

      <ProductionTrendChart
        data={dashboard.production_trend}
        productTrends={dashboard.product_trends}
        totalUnit={dashboard.quantity_uom}
      />

      <section className="dashboard-lower-grid">
        <article className="dashboard-panel risk-list-panel">
          <div className="dashboard-panel__header">
            <div>
              <p className="section-kicker">DELIVERY WATCH</p>
              <h2>우선 납기 리스크</h2>
            </div>
            <Link className="panel-link" href="/orders">전체 오더</Link>
          </div>
          <ol className="risk-list">
            {dashboard.top_order_risks.slice(0, 5).map((order) => (
              <li key={order.order_id}>
                <Link href={`/orders/${order.order_id}`}>
                  <div>
                    <strong>{order.order_number}</strong>
                    <span>{order.product_name} · 납기 {format_date(order.due_date)}</span>
                  </div>
                  <div className="risk-list__metrics">
                    <StatusBadge severity={order.severity} />
                    <span>달성 {format_percentage(order.completion_rate)}</span>
                  </div>
                </Link>
              </li>
            ))}
          </ol>
        </article>

        <article className="dashboard-panel risk-list-panel">
          <div className="dashboard-panel__header">
            <div>
              <p className="section-kicker">MATERIAL WATCH</p>
              <h2>우선 자재 리스크</h2>
            </div>
            <Link className="panel-link" href="/materials">전체 자재</Link>
          </div>
          <ol className="risk-list">
            {dashboard.top_material_risks.slice(0, 5).map((material) => (
              <li key={material.material_id}>
                <Link href="/materials">
                  <div>
                    <strong>{material.material_name}</strong>
                    <span>{material.material_code} · 재고 {format_quantity(material.current_stock, material.stock_uom)}</span>
                  </div>
                  <div className="risk-list__metrics">
                    <StatusBadge severity={material.severity} />
                    <span>안전재고 {format_quantity(material.safety_stock, material.stock_uom)}</span>
                  </div>
                </Link>
              </li>
            ))}
          </ol>
        </article>

        <article className="dashboard-panel action-panel">
          <div className="dashboard-panel__header">
            <div>
              <p className="section-kicker">NEXT ACTIONS</p>
              <h2>권장 조치</h2>
            </div>
            <Link className="panel-link" href="/risks">리스크 보드</Link>
          </div>
          <ol className="action-list">
            {dashboard.recommended_actions.map((action, index) => (
              <li key={`${index}-${action}`}>
                <span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
                <p>{action}</p>
              </li>
            ))}
          </ol>
        </article>
      </section>
    </div>
  );
}
