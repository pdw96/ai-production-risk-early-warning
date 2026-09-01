from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil
from typing import Literal

from app.core.config import WARNING_BUFFER_DAYS

OrderRiskSeverity = Literal["위험", "주의", "정상"]


@dataclass(frozen=True)
class OrderRiskResult:
    severity: OrderRiskSeverity
    estimated_completion_date: date | None
    remaining_quantity: float
    reason: str


def calculate_order_risk(
    planned_quantity: float,
    actual_quantity: float,
    average_daily_output: float,
    due_date: date,
    reference_date: date,
) -> OrderRiskResult:
    """기준일의 생산 실적과 평균 생산량으로 오더 납기 위험을 계산한다."""
    remaining_quantity = max(planned_quantity - actual_quantity, 0)

    if average_daily_output <= 0 and remaining_quantity > 0:
        return OrderRiskResult(
            severity="위험",
            estimated_completion_date=None,
            remaining_quantity=remaining_quantity,
            reason="평균 일 생산량이 0이어서 완료예정일을 산출할 수 없습니다.",
        )

    completion_days = ceil(remaining_quantity / average_daily_output) if remaining_quantity else 0
    estimated_completion_date = reference_date + timedelta(days=completion_days)

    if estimated_completion_date > due_date:
        severity: OrderRiskSeverity = "위험"
        reason = (
            f"완료예정일 {estimated_completion_date.isoformat()}이 "
            f"납기일 {due_date.isoformat()}보다 늦습니다."
        )
    elif (due_date - reference_date).days <= WARNING_BUFFER_DAYS:
        severity = "주의"
        reason = f"납기일까지 {(due_date - reference_date).days}일 남았습니다."
    else:
        severity = "정상"
        reason = "현재 생산 속도로 납기 내 완료가 예상됩니다."

    return OrderRiskResult(
        severity=severity,
        estimated_completion_date=estimated_completion_date,
        remaining_quantity=remaining_quantity,
        reason=reason,
    )
