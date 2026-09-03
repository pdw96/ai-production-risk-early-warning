from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import (
    FINISHED_GOODS_WAREHOUSE,
    INCOMING_INSPECTION,
    OUTGOING_INSPECTION,
    PROCESS_INSPECTION,
    PRODUCTION_WAREHOUSE,
    QC_FAILED,
    QC_PASSED,
    QC_PENDING,
    RAW_MATERIAL_WAREHOUSE,
)
from app.db.models import (
    BomRequirement,
    DailyProduction,
    FinishedGoodsLot,
    Material,
    MaterialLot,
    Order,
    Product,
    PurchaseReceipt,
    QualityInspection,
    RiskStatus,
)
from app.schemas.contracts import (
    BomRequirementResponse,
    DashboardKpis,
    DashboardResponse,
    FinishedGoodsLotResponse,
    FinishedGoodsResponse,
    MasterDataResponse,
    MasterItemResponse,
    MaterialLotResponse,
    MaterialResponse,
    OrderDetailResponse,
    OrderResponse,
    ProductionPoint,
    ProductionResultResponse,
    ProductTrend,
    PurchaseReceiptResponse,
    QualityDataResponse,
    QualityInspectionResponse,
    QualityInspectionSummary,
    RiskResponse,
    RiskWorkflowStatus,
)
from app.services.material_risk import Lot, calculate_material_risk
from app.services.order_risk import calculate_order_risk


HORIZON_DAYS = 14
RISK_STATUS_NEW: RiskWorkflowStatus = "신규"

# 검사 기록은 영구히 쌓이므로 조회에 상한을 둔다. 전체에서 최신순으로 자르면
# IQC 가 한 건도 안 남는다 — IQC 의 검사일은 자재 입고일이라 늘 PQC·OQC 보다
# 과거이기 때문이다. 그래서 유형별로 자른다. 요약 건수는 잘라낸 것까지 포함한
# 전체를 세므로, 화면의 합격·불합격 집계는 목록 길이와 무관하게 정확하다.
RECENT_INSPECTIONS_PER_TYPE = 20
INSPECTION_TYPE_ORDER = (
    INCOMING_INSPECTION,
    PROCESS_INSPECTION,
    OUTGOING_INSPECTION,
)


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
            selectinload(Material.lots),
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


def list_production_results(session: Session) -> list[ProductionResultResponse]:
    """생산관리 화면용 일자별 생산실적(생산일보)을 최근 날짜부터 만든다."""
    reference_date = get_reference_date(session)
    start_date = reference_date - timedelta(days=HORIZON_DAYS - 1)
    rows = session.execute(
        select(
            DailyProduction.work_date,
            DailyProduction.planned_quantity,
            DailyProduction.actual_quantity,
            DailyProduction.order_id,
        ).where(DailyProduction.work_date.between(start_date, reference_date))
    ).all()

    planned_by_day: defaultdict[date, float] = defaultdict(float)
    actual_by_day: defaultdict[date, float] = defaultdict(float)
    orders_by_day: defaultdict[date, set[int]] = defaultdict(set)
    for work_date, planned, actual, order_id in rows:
        planned_by_day[work_date] += float(planned or 0)
        actual_by_day[work_date] += float(actual or 0)
        if actual:
            orders_by_day[work_date].add(order_id)

    results = []
    for offset in range(HORIZON_DAYS):
        day = reference_date - timedelta(days=offset)
        planned = planned_by_day.get(day, 0.0)
        actual = actual_by_day.get(day, 0.0)
        results.append(
            ProductionResultResponse(
                work_date=day,
                planned_quantity=round(planned, 2),
                actual_quantity=round(actual, 2),
                achievement_rate=round(actual / planned * 100, 1) if planned else 0.0,
                active_order_count=len(orders_by_day.get(day, ())),
            )
        )
    return results


def _distinct_lot_counts(session: Session, owner_column, lot_number_column) -> dict[int, int]:
    """품목별 물리적 로트 수. 한 로트가 두 창고에 나뉘어 있어도 한 건으로 센다."""
    return {
        owner_id: int(count)
        for owner_id, count in session.execute(
            select(owner_column, func.count(distinct(lot_number_column))).group_by(
                owner_column
            )
        ).all()
    }


def get_master_data(session: Session) -> MasterDataResponse:
    """기준정보관리 화면용 품목 마스터와 BOM을 만든다."""
    products = session.scalars(
        select(Product)
        .options(selectinload(Product.bom_requirements))
        .order_by(Product.code)
    ).all()
    materials = session.scalars(
        select(Material)
        .options(selectinload(Material.bom_requirements))
        .order_by(Material.code)
    ).all()
    # 로트는 영구 기록이라 계속 쌓인다. 화면이 쓰는 것은 품목당 정수 하나뿐이므로
    # 행을 다 적재하지 않고 집계 질의로 센다.
    finished_lot_counts = _distinct_lot_counts(
        session, FinishedGoodsLot.product_id, FinishedGoodsLot.lot_number
    )
    material_lot_counts = _distinct_lot_counts(
        session, MaterialLot.material_id, MaterialLot.lot_number
    )

    items = [
        MasterItemResponse(
            item_type="제품",
            item_code=product.code,
            item_name=product.name,
            # 안전재고는 자재만 관리한다.
            safety_stock=None,
            # 완제품 로트도 한 로트가 두 창고에 나뉠 수 있으므로 번호로 센다.
            lot_count=finished_lot_counts.get(product.id, 0),
            shelf_life_days=product.shelf_life_days,
            linked_item_count=len(product.bom_requirements),
        )
        for product in products
    ] + [
        MasterItemResponse(
            item_type="자재",
            item_code=material.code,
            item_name=material.name,
            safety_stock=round(material.safety_stock, 2),
            # 한 로트가 두 창고에 나뉘어 있어도 물리적으로는 한 로트다.
            lot_count=material_lot_counts.get(material.id, 0),
            shelf_life_days=material.shelf_life_days,
            linked_item_count=len(material.bom_requirements),
        )
        for material in materials
    ]

    bom_rows = session.scalars(
        select(BomRequirement).options(
            selectinload(BomRequirement.product),
            selectinload(BomRequirement.material),
        )
    ).all()
    bom_requirements = sorted(
        (
            BomRequirementResponse(
                product_code=row.product.code,
                product_name=row.product.name,
                material_code=row.material.code,
                material_name=row.material.name,
                unit_quantity=round(row.unit_quantity, 2),
            )
            for row in bom_rows
        ),
        key=lambda item: (item.product_code, item.material_code),
    )
    return MasterDataResponse(items=items, bom_requirements=bom_requirements)


def list_purchase_receipts(session: Session) -> list[PurchaseReceiptResponse]:
    """구매관리 화면용 예정 입고 목록을 만든다."""
    reference_date = get_reference_date(session)
    horizon_end = reference_date + timedelta(days=HORIZON_DAYS - 1)
    receipts = session.scalars(
        select(PurchaseReceipt)
        .options(selectinload(PurchaseReceipt.material))
        .order_by(PurchaseReceipt.scheduled_date, PurchaseReceipt.id)
    ).all()

    return [
        PurchaseReceiptResponse(
            receipt_id=receipt.id,
            material_code=receipt.material.code,
            material_name=receipt.material.name,
            scheduled_date=receipt.scheduled_date,
            scheduled_quantity=round(receipt.scheduled_quantity, 2),
            expiry_date=receipt.expiry_date,
            days_until_arrival=(receipt.scheduled_date - reference_date).days,
            within_horizon=reference_date <= receipt.scheduled_date <= horizon_end,
        )
        for receipt in receipts
    ]


def list_finished_goods(session: Session) -> list[FinishedGoodsResponse]:
    reference_date = get_reference_date(session)
    products = session.scalars(
        select(Product)
        .options(selectinload(Product.finished_goods_lots))
        .order_by(Product.code)
    ).all()
    return [
        _build_finished_goods_response(product, reference_date)
        for product in products
    ]


def list_quality_inspections(session: Session) -> QualityDataResponse:
    """유형별 합격·불합격 전체 집계와, 유형별 최신 기록을 모아 돌려준다.

    전체를 실어 보내지 않는 이유는 기록이 영구히 쌓이기 때문이다. 화면이 다
    그리지도 못할 양을 직렬화하면 응답과 파싱 비용만 무한정 커진다. 대신 건수는
    집계 질의로 세어 잘라낸 기록까지 반영한다.
    """
    summaries = _build_inspection_summaries(session)
    rows = [
        _build_inspection_response(inspection)
        for inspection_type in INSPECTION_TYPE_ORDER
        for inspection in _recent_inspections_of_type(session, inspection_type)
    ]
    # 유형별로 뽑았으므로 다시 검사일 내림차순으로 되돌린다.
    rows.sort(key=lambda row: (row.inspected_date, row.inspection_id), reverse=True)
    return QualityDataResponse(summaries=summaries, inspections=rows)


def _build_inspection_summaries(session: Session) -> list[QualityInspectionSummary]:
    """유형×판정 건수를 집계 질의로 센다(잘라낸 기록까지 포함한 전체)."""
    counts: defaultdict[tuple[str, str], int] = defaultdict(int)
    for inspection_type, result, count in session.execute(
        select(
            QualityInspection.inspection_type,
            QualityInspection.result,
            func.count(),
        ).group_by(QualityInspection.inspection_type, QualityInspection.result)
    ).all():
        counts[(inspection_type, result)] = int(count)

    return [
        QualityInspectionSummary(
            inspection_type=inspection_type,
            total_count=(
                counts[(inspection_type, QC_PASSED)]
                + counts[(inspection_type, QC_FAILED)]
            ),
            passed_count=counts[(inspection_type, QC_PASSED)],
            failed_count=counts[(inspection_type, QC_FAILED)],
        )
        for inspection_type in INSPECTION_TYPE_ORDER
    ]


def _recent_inspections_of_type(
    session: Session,
    inspection_type: str,
) -> list[QualityInspection]:
    return list(
        session.scalars(
            select(QualityInspection)
            .options(
                selectinload(QualityInspection.material_lot).selectinload(
                    MaterialLot.material
                ),
                selectinload(QualityInspection.daily_production)
                .selectinload(DailyProduction.order)
                .selectinload(Order.product),
                selectinload(QualityInspection.finished_goods_lot).selectinload(
                    FinishedGoodsLot.product
                ),
            )
            .where(QualityInspection.inspection_type == inspection_type)
            .order_by(
                QualityInspection.inspected_date.desc(),
                QualityInspection.id.desc(),
            )
            .limit(RECENT_INSPECTIONS_PER_TYPE)
        ).all()
    )


def _build_inspection_response(
    inspection: QualityInspection,
) -> QualityInspectionResponse:
    """검사 대상이 유형마다 다르므로 화면이 쓸 품목·대상 표기로 풀어 준다."""
    if inspection.material_lot is not None:
        target_type = "자재 로트"
        item_code = inspection.material_lot.material.code
        item_name = inspection.material_lot.material.name
        target_label = inspection.material_lot.lot_number
    elif inspection.daily_production is not None:
        order = inspection.daily_production.order
        target_type = "생산 실적"
        item_code = order.product.code
        item_name = order.product.name
        target_label = order.order_number
    else:
        target_type = "완제품 로트"
        item_code = inspection.finished_goods_lot.product.code
        item_name = inspection.finished_goods_lot.product.name
        target_label = inspection.finished_goods_lot.lot_number

    return QualityInspectionResponse(
        inspection_id=inspection.id,
        inspection_type=inspection.inspection_type,
        inspected_date=inspection.inspected_date,
        result=inspection.result,
        reason=inspection.reason,
        target_type=target_type,
        item_code=item_code,
        item_name=item_name,
        target_label=target_label,
    )


def _finished_goods_lot_state(lot: FinishedGoodsLot, reference_date: date) -> str:
    """완제품 로트의 화면 상태. 요약의 다섯 수량과 1:1로 대응한다.

    만료 판정에 `<=` 를 쓰는 것은 자재의 가용 조건(`입고일 <= 날짜 < 유효기간`)과
    같은 규칙이다 — 유효기간 당일은 이미 쓸 수 없다.

    판정 순서가 곧 우선순위다. 만료를 먼저 보는 이유는, 만료된 로트가 완제품창고에
    남아 있어도 출하할 수 없기 때문이다.
    """
    if lot.expiry_date is not None and lot.expiry_date <= reference_date:
        return "만료"
    if lot.warehouse == FINISHED_GOODS_WAREHOUSE:
        return "출하 가능"
    if lot.qc_status == QC_PASSED:
        return "이관 대기"
    if lot.qc_status == QC_PENDING:
        return "검사 대기"
    return "불합격"


def _build_finished_goods_response(
    product: Product,
    reference_date: date,
) -> FinishedGoodsResponse:
    # 출하가 소진하게 될 순서(유효기간 → 생산일)로 정렬한다. 자재 로트 목록과
    # 같은 규칙이라 두 화면을 같은 눈으로 읽을 수 있다.
    lots = sorted(
        product.finished_goods_lots,
        key=lambda lot: (
            lot.expiry_date or date.max,
            lot.produced_date,
            lot.lot_number,
        ),
    )
    quantity_by_state: defaultdict[str, float] = defaultdict(float)
    lot_responses: list[FinishedGoodsLotResponse] = []
    for lot in lots:
        state = _finished_goods_lot_state(lot, reference_date)
        quantity_by_state[state] += lot.quantity
        lot_responses.append(
            FinishedGoodsLotResponse(
                lot_number=lot.lot_number,
                warehouse=lot.warehouse,
                qc_status=lot.qc_status,
                quantity=round(lot.quantity, 2),
                produced_date=lot.produced_date,
                expiry_date=lot.expiry_date,
                state=state,
            )
        )

    return FinishedGoodsResponse(
        product_id=product.id,
        product_code=product.code,
        product_name=product.name,
        shelf_life_days=product.shelf_life_days,
        releasable_stock=round(quantity_by_state["출하 가능"], 2),
        transfer_pending_stock=round(quantity_by_state["이관 대기"], 2),
        inspection_pending_stock=round(quantity_by_state["검사 대기"], 2),
        rejected_stock=round(quantity_by_state["불합격"], 2),
        expired_stock=round(quantity_by_state["만료"], 2),
        total_lot_quantity=round(sum(lot.quantity for lot in lots), 2),
        lots=lot_responses,
    )


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

    product_trends = _build_product_trends(session, reference_date)

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
        product_trends=product_trends,
        top_order_risks=order_risks[:5],
        top_material_risks=material_risks[:5],
        recommended_actions=actions,
    )


def _build_product_trends(
    session: Session,
    reference_date: date,
) -> list[ProductTrend]:
    """합계 추이와 같은 7일 축을 제품별로 나눈다.

    실적이 없는 날도 0으로 채워 넣는다. 날짜 축이 합계 차트와 어긋나면 제품을
    바꿀 때마다 그래프가 튄다.
    """
    # 제품 목록은 실적과 무관하게 전부 가져온다. 조인으로만 뽑으면 최근 7일에
    # 실적이 한 줄도 없는 제품이 선택지에서 통째로 사라진다.
    names: dict[int, tuple[str, str]] = {
        product.id: (product.code, product.name)
        for product in session.scalars(select(Product).order_by(Product.code)).all()
    }
    rows = session.execute(
        select(
            Order.product_id,
            DailyProduction.work_date,
            func.sum(DailyProduction.planned_quantity),
            func.sum(DailyProduction.actual_quantity),
        )
        .join(Order, DailyProduction.order_id == Order.id)
        .where(
            DailyProduction.work_date.between(
                reference_date - timedelta(days=6),
                reference_date,
            )
        )
        .group_by(Order.product_id, DailyProduction.work_date)
    ).all()

    totals: dict[int, dict[date, tuple[float, float]]] = defaultdict(dict)
    for product_id, work_date, planned, actual in rows:
        totals[product_id][work_date] = (float(planned or 0), float(actual or 0))

    trends = []
    for product_id, (code, name) in sorted(names.items(), key=lambda item: item[1][0]):
        points = []
        for offset in range(6, -1, -1):
            day = reference_date - timedelta(days=offset)
            planned, actual = totals[product_id].get(day, (0.0, 0.0))
            points.append(
                ProductionPoint(
                    work_date=day,
                    planned_quantity=round(planned, 2),
                    actual_quantity=round(actual, 2),
                )
            )
        trends.append(
            ProductTrend(product_code=code, product_name=name, points=points)
        )
    return trends


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

    horizon_end = reference_date + timedelta(days=HORIZON_DAYS - 1)
    lots = [
        Lot(
            lot_number=lot.lot_number,
            warehouse=lot.warehouse,
            quantity=lot.quantity,
            received_date=lot.received_date,
            expiry_date=lot.expiry_date,
        )
        for lot in material.lots
    ]
    # 예정 입고는 도착하면 원재료창고의 로트가 된다.
    scheduled_lots = [
        Lot(
            lot_number=f"LOT-{material.code}-IN-{index + 1:02d}",
            warehouse=RAW_MATERIAL_WAREHOUSE,
            quantity=receipt.scheduled_quantity,
            received_date=receipt.scheduled_date,
            expiry_date=receipt.expiry_date,
            scheduled=True,
        )
        for index, receipt in enumerate(
            sorted(material.purchase_receipts, key=lambda item: item.scheduled_date)
        )
        if reference_date <= receipt.scheduled_date <= horizon_end
    ]

    result = calculate_material_risk(
        lots=[*lots, *scheduled_lots],
        safety_stock=material.safety_stock,
        daily_demands=daily_demands,
        reference_date=reference_date,
        horizon_days=HORIZON_DAYS,
    )

    # 폐기가 원인이려면 부족이 드러난 날보다 늦지 않아야 한다. 소진보다 늦게
    # 일어난 폐기, 그리고 기준일부터 이미 안전재고 미만이던 자재를 뒤늦은 폐기
    # 탓으로 돌리면 담당자가 엉뚱한 로트를 붙잡게 된다.
    shortage_onset = result.stockout_date or result.first_shortage_date
    # 부족이 드러난 날까지 실제로 버려진 양만 그 부족의 원인이다. 전체
    # 폐기량을 적으면, 부족 이후에 도착해 나중에 버려진 입고분까지 원인으로
    # 둔갑해 담당자가 실제보다 큰 폐기를 부족의 이유로 읽게 된다.
    discarded_until_shortage = (
        round(
            sum(
                quantity
                for day, quantity in result.discarded_by_date.items()
                if day <= shortage_onset
            ),
            2,
        )
        if shortage_onset is not None
        else 0.0
    )
    discard_caused_shortage = discarded_until_shortage > 0

    if result.stockout_date is not None:
        severity = "위험"
        if discard_caused_shortage:
            reason = (
                f"유효기간 경과 폐기 {discarded_until_shortage}으로 "
                f"{result.stockout_date.isoformat()}에 소진될 전망입니다."
            )
            recommendation = "폐기 임박 로트를 우선 소진하도록 생산 순서를 조정하세요."
        else:
            reason = f"재고가 {result.stockout_date.isoformat()}에 소진될 전망입니다."
            recommendation = (
                "구매 예정 입고일을 즉시 재확인하세요."
                if scheduled_lots
                else "영향 오더의 생산 우선순위를 조정하세요."
            )
    elif result.shortage_expected:
        severity = "주의"
        if discard_caused_shortage:
            reason = (
                f"{discarded_until_shortage}이 유효기간 경과로 폐기되어 "
                f"{shortage_onset.isoformat()}에 안전재고 미만으로 하락할 "
                "전망입니다."
            )
            recommendation = "폐기 임박 로트를 우선 소진하고 추가 발주를 검토하세요."
        else:
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
        current_stock=round(result.available_stock, 2),
        raw_warehouse_stock=round(
            result.stock_by_warehouse.get(RAW_MATERIAL_WAREHOUSE, 0.0), 2
        ),
        production_warehouse_stock=round(
            result.stock_by_warehouse.get(PRODUCTION_WAREHOUSE, 0.0), 2
        ),
        safety_stock=round(material.safety_stock, 2),
        ending_stock=round(result.ending_stock, 2),
        minimum_stock=round(result.minimum_stock, 2),
        shortage_expected=result.shortage_expected,
        stockout_date=result.stockout_date,
        expiring_quantity=round(result.expiring_quantity, 2),
        first_expiry_date=result.first_expiry_date,
        lots=_build_lot_responses(
            [*lots, *scheduled_lots],
            reference_date,
            result.discarded_by_lot,
        ),
        severity=severity,
        reason=reason,
        recommendation=recommendation,
    )


def _build_lot_responses(
    lots: list[Lot],
    reference_date: date,
    discarded_by_lot: dict[tuple[str, str, bool], float],
) -> list[MaterialLotResponse]:
    """로트를 출고 순서(유효기간 → 입고일)대로 정렬해 화면용으로 변환한다.

    `기간 내 폐기`는 유효기간이 아니라 **시뮬레이션에서 실제로 버려졌는지**로
    정한다. 유효기간이 기간 안이어도 그전에 수요가 다 먹어치웠으면 폐기가
    아니다. 날짜만 보고 표시하면 담당자에게 없는 폐기를 알리게 된다.

    판정 순서가 곧 우선순위다.

    1. `만료` — 기준일보다 앞서 유효기간이 지난 로트. 시뮬레이션이 가용 재고와
       폐기 수량 어디에도 넣지 않으므로, 상태를 붙이지 않으면 `가용`으로 흘러가
       쓸 수 없는 수량을 가용으로 읽히게 된다.
    2. `기간 내 폐기` — 예정 입고로 들어와 기간 안에 버려지는 로트도 여기 든다.
       입고 여부를 먼저 보면 요약의 폐기 수량에 대응하는 로트가 목록에서 사라진다.
    3. `예정 입고` — 기준일 이후에 도착하며 기간 내 폐기되지 않는 로트.
    """
    responses = []
    for lot in sorted(
        lots,
        key=lambda item: (
            item.expiry_date or date.max,
            item.received_date,
            item.lot_number,
        ),
    ):
        if lot.expiry_date is not None and lot.expiry_date < reference_date:
            state = "만료"
        elif discarded_by_lot.get(lot.key, 0.0) > 0:
            state = "기간 내 폐기"
        elif lot.received_date > reference_date:
            state = "예정 입고"
        else:
            state = "가용"
        responses.append(
            MaterialLotResponse(
                lot_number=lot.lot_number,
                warehouse=lot.warehouse,
                quantity=round(lot.quantity, 2),
                received_date=lot.received_date,
                expiry_date=lot.expiry_date,
                state=state,
            )
        )
    return responses
