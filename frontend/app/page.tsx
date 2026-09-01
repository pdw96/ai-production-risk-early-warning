"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { DataState } from "../components/data-state";
import { KpiCard } from "../components/kpi-card";
import { ProductionTrendChart } from "../components/production-trend-chart";
import { StatusBadge } from "../components/status-badge";
import { getDashboard, type Dashboard } from "../lib/api";

function format_quantity(value: number): string {
  return `${new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 2 }).format(value)}개`;
}

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

function is_empty_dashboard(dashboard: Dashboard): boolean {
  return (
    dashboard.production_trend.length === 0 &&
    dashboard.top_order_risks.length === 0 &&
    dashboard.top_material_risks.length === 0 &&
    dashboard.recommended_actions.length === 0
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
          <KpiCard detail="납기 일정 재확인 필요" label="납기 위험 오더" value={`${format_quantity(dashboard.kpis.due_risk_order_count).replace("개", "건")}`} />
        </Link>
        <Link aria-label={`자재 부족 위험 ${dashboard.kpis.material_shortage_count}건 상세 보기`} href="/materials">
          <KpiCard detail="14일 수급 점검 필요" label="자재 부족 위험" value={`${format_quantity(dashboard.kpis.material_shortage_count).replace("개", "건")}`} />
        </Link>
        <Link aria-label={`오늘 생산 계획 ${format_quantity(dashboard.kpis.today_plan_quantity)} 상세 보기`} href="/orders">
          <KpiCard detail="당일 계획 물량" label="오늘 생산 계획" value={format_quantity(dashboard.kpis.today_plan_quantity)} />
        </Link>
        <Link aria-label={`오늘 생산 실적 ${format_quantity(dashboard.kpis.today_actual_quantity)} 상세 보기`} href="/orders">
          <KpiCard detail="당일 누적 실적" label="오늘 생산 실적" value={format_quantity(dashboard.kpis.today_actual_quantity)} />
        </Link>
      </section>

      <ProductionTrendChart data={dashboard.production_trend} />

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
                    <span>{material.material_code} · 재고 {format_quantity(material.current_stock)}</span>
                  </div>
                  <div className="risk-list__metrics">
                    <StatusBadge severity={material.severity} />
                    <span>안전재고 {format_quantity(material.safety_stock)}</span>
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
