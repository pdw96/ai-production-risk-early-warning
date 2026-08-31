from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Mapping


@dataclass(frozen=True)
class MaterialRiskResult:
    """14일 자재 재고 시뮬레이션 결과."""

    ending_stock: float
    minimum_stock: float
    shortage_expected: bool
    stockout_date: date | None


def calculate_material_risk(
    current_stock: float,
    safety_stock: float,
    daily_demands: Mapping[date, float],
    scheduled_receipts: Mapping[date, float],
    reference_date: date,
    horizon_days: int = 14,
) -> MaterialRiskResult:
    """기준일 포함 기간의 입고·수요를 순서대로 반영해 자재 위험을 계산한다."""
    if horizon_days < 1:
        raise ValueError("horizon_days must be at least 1")

    stock = current_stock
    minimum_stock = current_stock
    stockout_date: date | None = None

    for offset in range(horizon_days):
        day = reference_date + timedelta(days=offset)
        stock += scheduled_receipts.get(day, 0)
        stock -= daily_demands.get(day, 0)
        minimum_stock = min(minimum_stock, stock)
        if stock <= 0 and stockout_date is None:
            stockout_date = day

    shortage_expected = stockout_date is not None or stock < safety_stock
    return MaterialRiskResult(
        ending_stock=stock,
        minimum_stock=minimum_stock,
        shortage_expected=shortage_expected,
        stockout_date=stockout_date,
    )
