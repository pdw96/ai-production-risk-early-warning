from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import base as db_base
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
)
from app.seed import (
    RECENT_OUTPUT_VARIANCE_CYCLE,
    _recent_output_series,
    reset_database,
)
from app.services.briefing import get_master_data, list_materials
from app.services.order_risk import calculate_order_risk


@pytest.fixture
def seeded_session_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> sessionmaker[Session]:
    engine = create_engine("sqlite:///:memory:")
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(db_base, "engine", engine)
    monkeypatch.setattr(db_base, "SessionLocal", session_factory)
    return session_factory


def test_reset_database_creates_required_synthetic_operational_records(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    reference_date = date(2026, 8, 31)

    reset_database(reference_date)

    with seeded_session_factory() as session:
        assert session.query(Product).count() == 5
        assert session.query(Order).count() == 30
        assert session.query(Material).count() == 15
        assert session.query(BomRequirement).count() == 15
        assert session.query(PurchaseReceipt).count() == 15
        assert session.query(DailyProduction).filter(
            DailyProduction.work_date == reference_date - timedelta(days=29)
        ).count() == 30
        assert session.query(DailyProduction).filter(
            DailyProduction.work_date == reference_date + timedelta(days=14)
        ).count() == 30


def test_reset_database_is_deterministic_for_the_same_reference_date(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    reference_date = date(2026, 8, 31)

    reset_database(reference_date)
    with seeded_session_factory() as session:
        first_snapshot = [
            (order.order_number, order.product.code, order.due_date, order.planned_quantity)
            for order in session.query(Order).order_by(Order.order_number)
        ]

    reset_database(reference_date)
    with seeded_session_factory() as session:
        second_snapshot = [
            (order.order_number, order.product.code, order.due_date, order.planned_quantity)
            for order in session.query(Order).order_by(Order.order_number)
        ]

    assert second_snapshot == first_snapshot


def test_seeded_orders_include_normal_caution_and_danger_by_existing_risk_rule(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    reference_date = date(2026, 8, 31)

    reset_database(reference_date)

    with seeded_session_factory() as session:
        severities = {
            calculate_order_risk(
                planned_quantity=order.planned_quantity,
                actual_quantity=sum(
                    daily.actual_quantity
                    for daily in order.daily_productions
                    if daily.work_date <= reference_date
                ),
                average_daily_output=sum(
                    daily.actual_quantity
                    for daily in order.daily_productions
                    if reference_date - timedelta(days=6)
                    <= daily.work_date
                    <= reference_date
                )
                / 7,
                due_date=order.due_date,
                reference_date=reference_date,
            ).severity
            for order in session.query(Order).all()
        }

    assert severities == {"정상", "주의", "위험"}


def test_seeded_materials_include_a_fourteen_day_shortage_risk(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    reset_database(date(2026, 8, 31))

    with seeded_session_factory() as session:
        materials = list_materials(session)

    assert any(material.shortage_expected for material in materials)


def test_available_stock_equals_the_sum_of_received_and_unexpired_lots(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    """가용 재고는 도착했고 아직 만료되지 않은 로트의 합과 정확히 같아야 한다.

    응답의 로트 목록에는 보유 로트와 기간 내 예정 입고가 함께 들어 있으므로,
    기준일 기준으로 이미 도착했고 유효기간이 남은 것만 골라 비교한다.
    """
    reference_date = date(2026, 8, 31)

    reset_database(reference_date)

    with seeded_session_factory() as session:
        materials = list_materials(session)
        lot_row_counts = {
            material_id: count
            for material_id, count in (
                (lot.material_id, 1) for lot in session.query(MaterialLot).all()
            )
        }

    assert materials
    for material in materials:
        on_hand = sum(
            lot.quantity
            for lot in material.lots
            if lot.received_date <= reference_date
            and (lot.expiry_date is None or lot.expiry_date > reference_date)
        )
        assert round(on_hand, 2) == material.current_stock
        assert (
            material.raw_warehouse_stock + material.production_warehouse_stock
            == material.current_stock
        )
    # 모든 자재가 보유 로트를 한 건 이상 가진다.
    assert set(lot_row_counts) == {material.material_id for material in materials}


def test_seeded_data_includes_a_lot_split_across_both_warehouses(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    """원재료창고 재고 일부를 생산창고로 옮긴 상태가 데모에 항상 있어야 한다."""
    reset_database(date(2026, 8, 31))

    with seeded_session_factory() as session:
        warehouses_by_lot_number: dict[str, set[str]] = {}
        for lot in session.query(MaterialLot).all():
            warehouses_by_lot_number.setdefault(lot.lot_number, set()).add(lot.warehouse)

    assert any(
        warehouses == {"원재료창고", "생산창고"}
        for warehouses in warehouses_by_lot_number.values()
    )


def test_seeded_materials_include_a_shortage_caused_by_expiring_lots(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    reset_database(date(2026, 8, 31))

    with seeded_session_factory() as session:
        materials = list_materials(session)

    expiry_driven = [
        material
        for material in materials
        if material.expiring_quantity > 0 and material.shortage_expected
    ]
    assert expiry_driven
    assert all("유효기간" in material.reason for material in expiry_driven)


def test_seeded_purchase_receipts_derive_their_expiry_from_the_item_master(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    """예정 입고의 유효기간은 도착일 + 자재의 설정기간이다.

    설정기간이 없는(무기한) 자재는 유효기간도 없다. 유효기간을 로트마다 따로
    박아 넣던 이전 방식에서는 이 대응이 성립하지 않았다.
    """
    reset_database(date(2026, 8, 31))

    with seeded_session_factory() as session:
        receipts = session.query(PurchaseReceipt).all()
        shelf_life_by_material = {
            material.id: material.shelf_life_days
            for material in session.query(Material).all()
        }

    assert receipts
    for receipt in receipts:
        shelf_life_days = shelf_life_by_material[receipt.material_id]
        if shelf_life_days is None:
            assert receipt.expiry_date is None
        else:
            assert receipt.expiry_date == receipt.scheduled_date + timedelta(
                days=shelf_life_days
            )
    # 무기한 자재와 유효기간이 있는 자재가 둘 다 있어야 두 경로가 다 검증된다.
    assert any(receipt.expiry_date is None for receipt in receipts)
    assert any(receipt.expiry_date is not None for receipt in receipts)


def test_recent_output_series_keeps_the_seven_day_total_exact() -> None:
    """납기 판정이 최근 7일 평균을 쓰므로 합계가 흔들리면 안 된다."""
    assert sum(RECENT_OUTPUT_VARIANCE_CYCLE) == 7.0

    for daily_output in (8.0, 9.0, 11.0, 13.0, 15.0):
        series = _recent_output_series(daily_output)

        assert len(series) == 7
        assert sum(series) == pytest.approx(daily_output * 7, abs=1e-9)
        # 날짜별로 실제로 갈려 있어야 실적선이 평평하지 않다.
        assert len(set(series)) > 1


def test_seeded_recent_actual_output_varies_by_day(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    reference_date = date(2026, 8, 31)

    reset_database(reference_date)

    with seeded_session_factory() as session:
        daily_totals: dict[date, float] = {}
        for production in session.query(DailyProduction).filter(
            DailyProduction.work_date.between(
                reference_date - timedelta(days=6), reference_date
            )
        ):
            daily_totals[production.work_date] = (
                daily_totals.get(production.work_date, 0.0)
                + production.actual_quantity
            )

    assert len(daily_totals) == 7
    assert len(set(daily_totals.values())) > 1


def test_seeded_orders_keep_their_seven_day_average_after_the_variance(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    """편차를 넣어도 오더별 7일 평균은 정수 기반 원래 값 그대로여야 한다."""
    reference_date = date(2026, 8, 31)

    reset_database(reference_date)

    with seeded_session_factory() as session:
        for order in session.query(Order).all():
            recent_total = sum(
                production.actual_quantity
                for production in order.daily_productions
                if reference_date - timedelta(days=6)
                <= production.work_date
                <= reference_date
            )
            average = recent_total / 7
            # 시드는 8~15의 정수 일평균에서 출발한다.
            assert average == pytest.approx(round(average), abs=1e-9)
            assert 8 <= round(average) <= 15


def test_master_data_counts_a_split_lot_as_one_held_lot(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    """한 로트를 두 창고에 나눠 뒀다고 보유 로트가 두 건이 되지는 않는다."""
    reset_database(date(2026, 8, 31))

    with seeded_session_factory() as session:
        distinct_lot_numbers: dict[int, set[str]] = {}
        lot_row_counts: dict[int, int] = {}
        for lot in session.query(MaterialLot).all():
            distinct_lot_numbers.setdefault(lot.material_id, set()).add(lot.lot_number)
            lot_row_counts[lot.material_id] = lot_row_counts.get(lot.material_id, 0) + 1

        materials = {
            material.id: material.code
            for material in session.query(Material).all()
        }
        counts_by_code = {
            item.item_code: item.lot_count
            for item in get_master_data(session).items
            if item.item_type == "자재"
        }

    # 창고에 나뉜 로트가 있는 자재가 최소 한 건은 있어야 이 검증이 의미가 있다.
    assert any(
        len(distinct_lot_numbers[material_id]) < lot_row_counts[material_id]
        for material_id in lot_row_counts
    )
    for material_id, code in materials.items():
        assert counts_by_code[code] == len(distinct_lot_numbers[material_id])


def test_seeded_material_lots_derive_their_expiry_from_the_item_master(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    reset_database(date(2026, 8, 31))

    with seeded_session_factory() as session:
        lots = session.query(MaterialLot).all()
        shelf_life_by_material = {
            material.id: material.shelf_life_days
            for material in session.query(Material).all()
        }

    assert lots
    for lot in lots:
        shelf_life_days = shelf_life_by_material[lot.material_id]
        if shelf_life_days is None:
            assert lot.expiry_date is None
        else:
            assert lot.expiry_date == lot.received_date + timedelta(
                days=shelf_life_days
            )
    assert any(lot.expiry_date is None for lot in lots)


def test_finished_goods_lot_quantity_equals_the_recorded_production(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    """완제품 로트는 생산 실적에서 파생되며 실적이 진실이다.

    PQC 불합격 기록이 있어도 이 등식은 흔들리지 않는다 — 이번 범위에서
    검사 결과가 수량을 바꾸는 것은 OQC 의 창고 이동뿐이다.
    """
    reference_date = date(2026, 8, 31)

    reset_database(reference_date)

    with seeded_session_factory() as session:
        lot_total = sum(lot.quantity for lot in session.query(FinishedGoodsLot).all())
        actual_total = sum(
            production.actual_quantity
            for production in session.query(DailyProduction).all()
            if production.work_date <= reference_date
        )
        failed_pqc = [
            inspection
            for inspection in session.query(QualityInspection).all()
            if inspection.inspection_type == "PQC" and inspection.result == "불합격"
        ]

    assert round(lot_total, 2) == round(actual_total, 2)
    assert failed_pqc


def test_finished_goods_lots_derive_their_expiry_from_the_product_master(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    reset_database(date(2026, 8, 31))

    with seeded_session_factory() as session:
        lots = session.query(FinishedGoodsLot).all()
        shelf_life_by_product = {
            product.id: product.shelf_life_days
            for product in session.query(Product).all()
        }

    assert lots
    for lot in lots:
        shelf_life_days = shelf_life_by_product[lot.product_id]
        if shelf_life_days is None:
            assert lot.expiry_date is None
        else:
            assert lot.expiry_date == lot.produced_date + timedelta(
                days=shelf_life_days
            )


def test_finished_goods_qc_status_agrees_with_the_oqc_record(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    """로트의 qc_status 는 OQC 기록의 캐시다. 기록이 없으면 검사 대기다."""
    reset_database(date(2026, 8, 31))

    with seeded_session_factory() as session:
        results_by_lot = {
            inspection.finished_goods_lot_id: inspection.result
            for inspection in session.query(QualityInspection).all()
            if inspection.inspection_type == "OQC"
        }
        statuses = set()
        for lot in session.query(FinishedGoodsLot).all():
            assert lot.qc_status == results_by_lot.get(lot.id, "검사 대기")
            statuses.add(lot.qc_status)

    assert statuses == {"검사 대기", "합격", "불합격"}


def test_seeded_incoming_inspections_cover_every_held_material_lot(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    """창고에 있는 자재는 수입검사를 통과했다는 뜻이므로 전건 합격이다."""
    reset_database(date(2026, 8, 31))

    with seeded_session_factory() as session:
        lot_ids = {lot.id for lot in session.query(MaterialLot).all()}
        incoming = [
            inspection
            for inspection in session.query(QualityInspection).all()
            if inspection.inspection_type == "IQC"
        ]

    assert {inspection.material_lot_id for inspection in incoming} == lot_ids
    assert all(inspection.result == "합격" for inspection in incoming)


def test_reset_database_is_deterministic_for_finished_goods_and_inspections(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    reference_date = date(2026, 8, 31)

    def snapshot() -> tuple[list, list]:
        with seeded_session_factory() as session:
            lots = [
                (lot.lot_number, lot.warehouse, lot.qc_status, lot.quantity)
                for lot in session.query(FinishedGoodsLot).order_by(
                    FinishedGoodsLot.lot_number
                )
            ]
            inspections = [
                (
                    inspection.inspection_type,
                    inspection.inspected_date,
                    inspection.result,
                    inspection.reason,
                )
                for inspection in session.query(QualityInspection).order_by(
                    QualityInspection.id
                )
            ]
        return lots, inspections

    reset_database(reference_date)
    first = snapshot()
    reset_database(reference_date)

    assert snapshot() == first
