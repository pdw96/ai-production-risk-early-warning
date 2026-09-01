from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    DailyProduction,
    Material,
    Order,
    RiskStatus,
)
from app.schemas.contracts import (
    DashboardKpis,
    DashboardResponse,
    MaterialResponse,
    OrderDetailResponse,
    OrderResponse,
    ProductionPoint,
    RiskResponse,
    RiskWorkflowStatus,
)
from app.services.material_risk import calculate_material_risk
from app.services.order_risk import calculate_order_risk


HORIZON_DAYS = 14
RISK_STATUS_NEW: RiskWorkflowStatus = "신규"


def get_reference_date(session: Session) -> date:
    """실적이 존재하는 가장 최근 날짜를 운영 기준일로 사용한다."""
    reference_date = session.scalar(
        select(func.max(DailyProduction.work_date)).where(
            DailyProduction.actual_quantity > 0
        )
    )
    return reference_date or date.today()


def list_orders(session: Session) -> list[OrderResponse]:
    reference_date = get_reference_date(session)
    orders = session.scalars(
        select(Order)
        .options(selectinload(Order.product), selectinload(Order.daily_productions))
        .order_by(Order.due_date, Order.id)
    ).all()
    return [_build_order_response(order, reference_date) for order in orders]


def get_order(session: Session, order_id: int) -> OrderDetailResponse | None:
    reference_date = get_reference_date(session)
    order = session.scalar(
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.product), selectinload(Order.daily_productions))
    )
    if order is None:
        return None

    response = _build_order_response(order, reference_date)
    recent_start = reference_date - timedelta(days=6)
    recent_productions = sorted(
        (
            ProductionPoint(
                work_date=production.work_date,
                planned_quantity=production.planned_quantity,
                actual_quantity=production.actual_quantity,
            )
            for production in order.daily_productions
            if recent_start <= production.work_date <= reference_date
        ),
        key=lambda item: item.work_date,
    )
    return OrderDetailResponse(
        **response.model_dump(),
        recent_productions=recent_productions,
    )


def list_materials(session: Session) -> list[MaterialResponse]:
    reference_date = get_reference_date(session)
    materials = session.scalars(
        select(Material)
        .options(
            selectinload(Material.bom_requirements),
            selectinload(Material.purchase_receipts),
        )
        .order_by(Material.code)
    ).all()
    planned_by_product_day = _planned_quantities_by_product_day(
        session,
        reference_date,
    )

    return [
        _build_material_response(
            material,
            reference_date,
            planned_by_product_day,
        )
        for material in materials
    ]


def list_risks(session: Session) -> list[RiskResponse]:
    statuses = {
        item.risk_key: item.status
        for item in session.scalars(select(RiskStatus)).all()
    }
    risks: list[RiskResponse] = []

    for order in list_orders(session):
        if order.severity == "정상":
            continue
        risk_id = f"RISK-ORDER-{order.order_id:03d}"
        risks.append(
            RiskResponse(
                risk_id=risk_id,
                risk_type="납기",
                entity_id=order.order_id,
                entity_code=order.order_number,
                entity_name=order.product_name,
                severity=order.severity,
                reason=order.reason,
                recommendation=(
                    "생산 우선순위를 즉시 조정하세요."
                    if order.severity == "위험"
                    else "일일 생산 진도를 집중 확인하세요."
                ),
                status=statuses.get(risk_id, RISK_STATUS_NEW),
            )
        )

    for material in list_materials(session):
        if not material.shortage_expected:
            continue
        risk_id = f"RISK-MATERIAL-{material.material_id:03d}"
        risks.append(
            RiskResponse(
                risk_id=risk_id,
                risk_type="자재",
                entity_id=material.material_id,
                entity_code=material.material_code,
                entity_name=material.material_name,
                severity=material.severity,
                reason=material.reason,
                recommendation=material.recommendation,
                status=statuses.get(risk_id, RISK_STATUS_NEW),
            )
        )

    severity_order = {"위험": 0, "주의": 1}
    return sorted(
        risks,
        key=lambda risk: (severity_order[risk.severity], risk.risk_id),
    )


def update_risk_status(
    session: Session,
    risk_id: str,
    status: RiskWorkflowStatus,
) -> RiskResponse | None:
    risk = next((item for item in list_risks(session) if item.risk_id == risk_id), None)
    if risk is None:
        return None

    stored_status = session.scalar(
        select(RiskStatus).where(RiskStatus.risk_key == risk_id)
    )
    if stored_status is None:
        stored_status = RiskStatus(risk_key=risk_id, status=status)
        session.add(stored_status)
    else:
        stored_status.status = status
    session.commit()
    return risk.model_copy(update={"status": status})


def get_dashboard(session: Session) -> DashboardResponse:
    reference_date = get_reference_date(session)
    orders = list_orders(session)
    materials = list_materials(session)
    order_risks = sorted(
        (order for order in orders if order.severity != "정상"),
        key=lambda order: (
            0 if order.severity == "위험" else 1,
            order.due_date,
            order.order_id,
        ),
    )
    material_risks = [material for material in materials if material.shortage_expected]
    daily_totals = session.execute(
        select(
            DailyProduction.work_date,
            func.sum(DailyProduction.planned_quantity),
            func.sum(DailyProduction.actual_quantity),
        )
        .where(
            DailyProduction.work_date.between(
                reference_date - timedelta(days=6),
                reference_date,
            )
        )
        .group_by(DailyProduction.work_date)
    ).all()
    totals_by_day = {
        work_date: (float(planned or 0), float(actual or 0))
        for work_date, planned, actual in daily_totals
    }
    production_trend = []
    for offset in range(6, -1, -1):
        day = reference_date - timedelta(days=offset)
        planned, actual = totals_by_day.get(day, (0.0, 0.0))
        production_trend.append(
            ProductionPoint(
                work_date=day,
                planned_quantity=round(planned, 2),
                actual_quantity=round(actual, 2),
            )
        )

    today_plan, today_actual = totals_by_day.get(reference_date, (0.0, 0.0))
    actions = [
        risk.recommendation
        for risk in list_risks(session)
        if risk.status != "조치 완료"
    ][:5]
    if not actions:
        actions = ["현재 주요 위험이 없습니다. 정상 모니터링을 유지하세요."]

    return DashboardResponse(
        kpis=DashboardKpis(
            due_risk_order_count=sum(
                order.severity == "위험" for order in orders
            ),
            material_shortage_count=len(material_risks),
            today_plan_quantity=round(today_plan, 2),
            today_actual_quantity=round(today_actual, 2),
        ),
        production_trend=production_trend,
        top_order_risks=order_risks[:5],
        top_material_risks=material_risks[:5],
        recommended_actions=actions,
    )


def _build_order_response(order: Order, reference_date: date) -> OrderResponse:
    actual_quantity = sum(
        production.actual_quantity
        for production in order.daily_productions
        if production.work_date <= reference_date
    )
    recent_start = reference_date - timedelta(days=6)
    average_daily_output = sum(
        production.actual_quantity
        for production in order.daily_productions
        if recent_start <= production.work_date <= reference_date
    ) / 7
    result = calculate_order_risk(
        planned_quantity=order.planned_quantity,
        actual_quantity=actual_quantity,
        average_daily_output=average_daily_output,
        due_date=order.due_date,
        reference_date=reference_date,
    )
    completion_rate = (
        min(actual_quantity / order.planned_quantity * 100, 100.0)
        if order.planned_quantity > 0
        else 0.0
    )
    return OrderResponse(
        order_id=order.id,
        order_number=order.order_number,
        product_code=order.product.code,
        product_name=order.product.name,
        due_date=order.due_date,
        planned_quantity=round(order.planned_quantity, 2),
        actual_quantity=round(actual_quantity, 2),
        completion_rate=round(completion_rate, 1),
        average_daily_output=round(average_daily_output, 2),
        remaining_quantity=round(result.remaining_quantity, 2),
        estimated_completion_date=result.estimated_completion_date,
        severity=result.severity,
        reason=result.reason,
    )


def _planned_quantities_by_product_day(
    session: Session,
    reference_date: date,
) -> dict[tuple[int, date], float]:
    horizon_end = reference_date + timedelta(days=HORIZON_DAYS - 1)
    rows = session.execute(
        select(
            Order.product_id,
            DailyProduction.work_date,
            func.sum(DailyProduction.planned_quantity),
        )
        .join(Order, DailyProduction.order_id == Order.id)
        .where(DailyProduction.work_date.between(reference_date, horizon_end))
        .group_by(Order.product_id, DailyProduction.work_date)
    ).all()
    return {
        (product_id, work_date): float(quantity or 0)
        for product_id, work_date, quantity in rows
    }


def _build_material_response(
    material: Material,
    reference_date: date,
    planned_by_product_day: dict[tuple[int, date], float],
) -> MaterialResponse:
    daily_demands: defaultdict[date, float] = defaultdict(float)
    for requirement in material.bom_requirements:
        for offset in range(HORIZON_DAYS):
            day = reference_date + timedelta(days=offset)
            daily_demands[day] += (
                planned_by_product_day.get((requirement.product_id, day), 0)
                * requirement.unit_quantity
            )

    scheduled_receipts: defaultdict[date, float] = defaultdict(float)
    for receipt in material.purchase_receipts:
        if reference_date <= receipt.scheduled_date < reference_date + timedelta(
            days=HORIZON_DAYS
        ):
            scheduled_receipts[receipt.scheduled_date] += receipt.scheduled_quantity

    result = calculate_material_risk(
        current_stock=material.current_stock,
        safety_stock=material.safety_stock,
        daily_demands=daily_demands,
        scheduled_receipts=scheduled_receipts,
        reference_date=reference_date,
        horizon_days=HORIZON_DAYS,
    )
    if result.stockout_date is not None:
        severity = "위험"
        reason = f"재고가 {result.stockout_date.isoformat()}에 소진될 전망입니다."
        recommendation = (
            "구매 예정 입고일을 즉시 재확인하세요."
            if scheduled_receipts
            else "영향 오더의 생산 우선순위를 조정하세요."
        )
    elif result.shortage_expected:
        severity = "주의"
        reason = "14일 내 안전재고 미만으로 하락할 전망입니다."
        recommendation = "안전재고 상향과 추가 발주를 검토하세요."
    else:
        severity = "정상"
        reason = "14일 내 안전재고 이상을 유지할 전망입니다."
        recommendation = "정상 모니터링을 유지하세요."

    return MaterialResponse(
        material_id=material.id,
        material_code=material.code,
        material_name=material.name,
        current_stock=round(material.current_stock, 2),
        safety_stock=round(material.safety_stock, 2),
        ending_stock=round(result.ending_stock, 2),
        minimum_stock=round(result.minimum_stock, 2),
        shortage_expected=result.shortage_expected,
        stockout_date=result.stockout_date,
        severity=severity,
        reason=reason,
        recommendation=recommendation,
    )
