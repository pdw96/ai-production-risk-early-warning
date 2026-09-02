"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import React, { useState } from "react";

import type { ProductionPoint, ProductTrend } from "../lib/api";

interface ProductionTrendChartProps {
  data: ProductionPoint[];
  productTrends?: ProductTrend[];
}

const ALL_PRODUCTS = "전체";

function format_number(value: number): string {
  return new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 2 }).format(value);
}

function format_short_date(value: string): string {
  const [, month, day] = value.split("-").map(Number);
  return `${month}/${day}`;
}

function format_full_date(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  return `${year}년 ${month}월 ${day}일`;
}

export function ProductionTrendChart({
  data,
  productTrends = [],
}: Readonly<ProductionTrendChartProps>) {
  const [selected_code, set_selected_code] = useState<string | null>(null);
  const selected_trend =
    productTrends.find((trend) => trend.product_code === selected_code) ?? null;

  // 제품을 고르면 그 제품의 계획·실적 두 선만 그린다. 제품 5개를 한꺼번에
  // 그리면 계획·실적까지 10선이 되어 읽을 수 없다.
  const points = selected_trend ? selected_trend.points : data;
  const scope_label = selected_trend
    ? `${selected_trend.product_name} · ${selected_trend.product_code}`
    : "전 제품 합계";

  return (
    <section aria-labelledby="production-trend-title" className="dashboard-panel trend-panel">
      <div className="dashboard-panel__header">
        <div>
          <p className="section-kicker">OUTPUT TREND</p>
          <h2 id="production-trend-title">최근 7일 생산 계획 대비 실적</h2>
        </div>
        <span className="dashboard-panel__meta">{scope_label} · 단위: 개</span>
      </div>
      {productTrends.length > 0 && (
        <div aria-label="추이를 볼 제품 선택" className="trend-panel__filter" role="group">
          <button
            aria-pressed={selected_code === null}
            onClick={() => set_selected_code(null)}
            type="button"
          >
            {ALL_PRODUCTS}
          </button>
          {productTrends.map((trend) => (
            <button
              aria-pressed={selected_code === trend.product_code}
              key={trend.product_code}
              onClick={() => set_selected_code(trend.product_code)}
              type="button"
            >
              {trend.product_name}
            </button>
          ))}
        </div>
      )}
      <div
        className="trend-panel__chart"
        role="img"
        aria-label={`${scope_label}의 최근 7일 생산 계획과 실적 추이 차트`}
      >
        <ResponsiveContainer height="100%" width="100%">
          <LineChart data={points} margin={{ bottom: 4, left: 0, right: 18, top: 18 }}>
            <CartesianGrid stroke="#2a3945" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="work_date"
              minTickGap={24}
              stroke="#91a3af"
              tickFormatter={format_short_date}
              tickLine={false}
            />
            <YAxis
              stroke="#91a3af"
              tickFormatter={(value: number) => format_number(value)}
              tickLine={false}
              width={48}
            />
            <Tooltip
              contentStyle={{ background: "#111820", border: "1px solid #2a3945" }}
              formatter={(value) => `${format_number(Number(value ?? 0))}개`}
              labelFormatter={(label) => format_full_date(String(label ?? ""))}
            />
            <Legend />
            <Line dataKey="planned_quantity" dot={false} name="계획" stroke="#74d5c4" strokeWidth={2.5} type="monotone" />
            <Line dataKey="actual_quantity" dot={false} name="실적" stroke="#f7b955" strokeWidth={2.5} type="monotone" />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <table className="sr-only">
        <caption>{scope_label}의 최근 7일 생산 계획과 실적</caption>
        <thead>
          <tr>
            <th>날짜</th>
            <th>계획 수량</th>
            <th>실적 수량</th>
          </tr>
        </thead>
        <tbody>
          {points.map((point) => (
            <tr key={point.work_date}>
              <th>{format_full_date(point.work_date)}</th>
              <td>{format_number(point.planned_quantity)}개</td>
              <td>{format_number(point.actual_quantity)}개</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
