from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from sqlalchemy import func, select

from app.core.config import FINISHED_ITEM, RAW_ITEM
from app.db import base as db_base
from app.db import preflight
from app.db.master_data import SupplierItem
from app.db.models import (
    BomComponent,
    DailyProduction,
    FinishedGoodsLot,
    Item,
    MaterialLot,
    Order,
    PurchaseReceipt,
    QualityInspection,
)
from app.services.lead_time import HOURS_PER_DAY, days_from_hours
from app import seed as seed_module
from app.seed import (
    RECENT_OUTPUT_VARIANCE_CYCLE,
    _recent_output_series,
    reset_database,
    seed_if_empty,
)
from app.services.briefing import get_master_data, list_materials
from app.services.order_risk import calculate_order_risk


@pytest.fixture
def seeded_session_factory(
    bound_session_factory: sessionmaker[Session],
) -> sessionmaker[Session]:
    """`DATABASE_URL` 의 엔진 위 일회용 데이터베이스에 붙는 세션 공장.

    예전에는 여기서 `sqlite:///:memory:` 엔진을 만들어 `db_base` 에 물렸다.
    그러면 `DATABASE_URL` 을 무엇으로 주든 SQLite 로 돌아, CI 가 두 엔진에서
    각각 돌려도 이 파일의 검사들은 **같은 엔진을 두 번** 볼 뿐이었다.

    바꾼 것은 붙는 곳이지 안전장치가 아니다. `db_base` 를 갈아 끼우는 것은
    그대로이며(`conftest.py` 의 `bound_engine`), 갈아 끼우는 대상만 설정된 엔진
    위의 **일회용 데이터베이스**가 되었다 — 이 파일의 검사들은 `reset_database()`
    로 표를 지웠다 다시 만들므로, 설정이 가리키는 곳에 그대로 붙으면 로컬에서
    한 번 돌리는 것만으로 개발자의 데이터가 사라진다.

    시드를 넣는 것은 이 픽스처가 아니라 **검사 쪽**이다. 기준일을 검사마다
    달리 주기 때문이며, 그래서 이름과 달리 여기서는 아직 비어 있다.

    무엇을 이 픽스처로 옮기고 무엇을 두는지의 기준은 `CLAUDE.md` 에 있다.
    """
    return bound_session_factory


def test_reset_database_creates_required_synthetic_operational_records(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    reference_date = date(2026, 8, 31)

    reset_database(reference_date)

    with seeded_session_factory() as session:
        assert session.query(Item).filter_by(item_type=FINISHED_ITEM).count() == 5
        assert session.query(Order).count() == 30
        assert session.query(Item).filter_by(item_type=RAW_ITEM).count() == 15
        assert session.query(BomComponent).count() == 15
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
            (order.order_number, order.item.code, order.due_date, order.planned_quantity)
            for order in session.query(Order).order_by(Order.order_number)
        ]

    reset_database(reference_date)
    with seeded_session_factory() as session:
        second_snapshot = [
            (order.order_number, order.item.code, order.due_date, order.planned_quantity)
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
                (lot.item_id, 1) for lot in session.query(MaterialLot).all()
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
            for material in session.query(Item).filter_by(item_type=RAW_ITEM).all()
        }

    assert receipts
    for receipt in receipts:
        shelf_life_days = shelf_life_by_material[receipt.item_id]
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
            distinct_lot_numbers.setdefault(lot.item_id, set()).add(lot.lot_number)
            lot_row_counts[lot.item_id] = lot_row_counts.get(lot.item_id, 0) + 1

        materials = {
            material.id: material.code
            for material in session.query(Item).filter_by(item_type=RAW_ITEM).all()
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
            for material in session.query(Item).filter_by(item_type=RAW_ITEM).all()
        }

    assert lots
    for lot in lots:
        shelf_life_days = shelf_life_by_material[lot.item_id]
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


def test_finished_goods_lots_derive_their_expiry_from_the_pass_date(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    """지적 ⑰ — 시계는 생산이 아니라 합격에서 시작한다.

    아직 판정을 받지 않았거나 불합격한 로트는 합격일이 없고, 그래서 유효기간도
    아직 없다. 불합격분은 팔 물건이 아니므로 유효기간을 셀 이유가 없다.
    """
    reset_database(date(2026, 8, 31))

    with seeded_session_factory() as session:
        lots = session.query(FinishedGoodsLot).all()
        shelf_life_by_product = {
            product.id: product.shelf_life_days
            for product in session.query(Item).filter_by(item_type=FINISHED_ITEM).all()
        }

    assert lots
    for lot in lots:
        shelf_life_days = shelf_life_by_product[lot.item_id]
        if lot.passed_date is None or shelf_life_days is None:
            assert lot.expiry_date is None
        else:
            assert lot.expiry_date == lot.passed_date + timedelta(days=shelf_life_days)

    # 세 경우가 모두 데이터에 있어야 이 판정이 무언가를 말한다.
    assert any(lot.passed_date is None for lot in lots)
    assert any(lot.passed_date is not None and lot.expiry_date is None for lot in lots)
    assert any(lot.expiry_date is not None for lot in lots)


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


def test_seeded_incoming_inspections_are_one_per_physical_lot(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    """수입검사는 물리적 로트 단위로 한 번이다.

    한 로트가 두 창고에 나뉘어 있어도 입고 시점에 한 번 검사한 것이다. 행마다
    기록을 남기면 같은 검사가 두 건으로 불어나 IQC 집계가 부풀고, 화면에는
    구분되지 않는 중복 행이 나온다. 기준정보가 보유 로트를 로트번호로 세는
    것과 같은 규칙이다.

    창고에 있는 자재는 검사를 통과했다는 뜻이므로 전건 합격이다.
    """
    reset_database(date(2026, 8, 31))

    with seeded_session_factory() as session:
        lots_by_id = {lot.id: lot for lot in session.query(MaterialLot).all()}
        physical_lots = {
            (lot.item_id, lot.lot_number) for lot in lots_by_id.values()
        }
        incoming = [
            inspection
            for inspection in session.query(QualityInspection).all()
            if inspection.inspection_type == "IQC"
        ]
        inspected = [
            (
                lots_by_id[inspection.material_lot_id].item_id,
                lots_by_id[inspection.material_lot_id].lot_number,
            )
            for inspection in incoming
        ]

    # 데모에는 두 창고에 나뉜 로트가 반드시 하나 있다(행 수 > 물리적 로트 수).
    assert len(lots_by_id) > len(physical_lots)
    assert sorted(inspected) == sorted(physical_lots)
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


def test_every_material_has_a_supplier_with_a_lead_time_in_hours(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    """지적 ⑬ — 구매 리드타임은 입력 시점에 일 × 24 로 바뀌어 저장된다.

    저장된 숫자 하나만 보고는 그것이 날인지 시간인지 알 수 없으므로 단위를 섞지
    않는다. 그리고 자재마다 공급사가 있어야 「지금 발주해야 늦지 않는다」를
    말할 수 있다 — 역산의 세 번째 겹이다.
    """
    reset_database(date(2026, 8, 31))

    with seeded_session_factory() as session:
        supplier_items = session.scalars(select(SupplierItem)).all()
        materials = session.scalars(
            select(Item).where(Item.item_type == RAW_ITEM)
        ).all()
        stock_uom_by_id = {item.id: item.stock_uom for item in materials}

    assert {row.item_id for row in supplier_items} == set(stock_uom_by_id)
    for row in supplier_items:
        # 날 × 24 로 저장했으므로 24의 배수여야 한다.
        assert row.lead_time_hours > 0
        assert row.lead_time_hours % HOURS_PER_DAY == 0
        # 환산 계수가 1이면 구매 단위와 재고 단위가 같아야 한다.
        if row.conversion_factor == 1.0:
            assert row.purchase_uom == stock_uom_by_id[row.item_id]


def test_the_purchase_lead_time_reads_back_as_whole_days_on_screen(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    """저장은 시간이고 날은 화면에서만 쓴다. 되돌려도 어긋나지 않아야 한다."""
    reset_database(date(2026, 8, 31))

    with seeded_session_factory() as session:
        hours = session.scalars(select(SupplierItem.lead_time_hours)).all()

    assert hours
    assert all(days_from_hours(value) == int(days_from_hours(value)) for value in hours)


def test_seeding_only_happens_when_the_item_table_is_empty(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    """시드 판단의 셋째 조건.

    「표가 있는가」는 아무것도 말해 주지 않는다 — 마이그레이션이 항상 만들어
    두기 때문이다. 물어야 할 것은 내용의 유무이고, 그 표식은 품목 표다:
    가장 먼저 채워지고 마지막까지 남는 표이기 때문이다.
    """
    db_base.drop_all()
    db_base.create_all()

    assert seed_if_empty(date(2026, 8, 31)) is True
    # 두 번째 기동은 아무것도 하지 않는다. 하면 사람이 넣은 데이터가 지워진다.
    assert seed_if_empty(date(2026, 8, 31)) is False

    with seeded_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Item)) == 20


def test_a_failed_seed_leaves_nothing_behind(
    monkeypatch: pytest.MonkeyPatch,
    seeded_session_factory: sessionmaker[Session],
) -> None:
    """전체가 트랜잭션 하나다 — 「반쯤 채워짐」이라는 상태가 아예 없어야 한다.

    SQLite 라면 파일을 지우고 처음으로 돌아갈 수 있지만 PostgreSQL 에는 지울
    파일이 없다. 반쯤 채워진 데이터베이스는 「비어 있지 않다」로 판정되어 다시는
    시드되지 않고 고장난 채로 굳는다.
    """
    db_base.drop_all()
    db_base.create_all()

    def explode(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("시드 도중 실패")

    intact = seed_module._seed_finished_goods_lots
    monkeypatch.setattr(seed_module, "_seed_finished_goods_lots", explode)
    with pytest.raises(RuntimeError):
        seed_if_empty(date(2026, 8, 31))

    with seeded_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Item)) == 0

    # 되돌아갔으므로 다음 기동이 다시 시도할 수 있다. 이 하나만 되돌린다 —
    # monkeypatch.undo() 는 픽스처가 갈아 끼운 엔진까지 되돌려, 시험이 임시
    # 데이터베이스가 아니라 진짜 파일을 보게 만든다.
    monkeypatch.setattr(seed_module, "_seed_finished_goods_lots", intact)
    assert seed_if_empty(date(2026, 8, 31)) is True


def test_the_master_data_comes_from_sql_and_the_scenario_from_python(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    """경계는 한 줄이다 — 「오늘」이 안 나오면 SQL, 나오면 파이썬.

    그래서 기준일을 바꿔도 기준정보는 한 글자도 달라지지 않고, 시나리오만
    통째로 움직인다. 난수가 안전재고를 흔들던 동안에는 어제 본 화면과 오늘 본
    화면의 숫자가 달라도 「왜 달라졌나」를 물을 수 없었다.
    """
    reset_database(date(2026, 8, 31))
    with seeded_session_factory() as session:
        first_master = sorted(
            (item.code, item.safety_stock, item.shelf_life_days, item.stock_uom)
            for item in session.scalars(select(Item)).all()
        )
        first_orders = session.scalar(select(func.count()).select_from(Order))

    reset_database(date(2026, 9, 20))
    with seeded_session_factory() as session:
        second_master = sorted(
            (item.code, item.safety_stock, item.shelf_life_days, item.stock_uom)
            for item in session.scalars(select(Item)).all()
        )
        second_order_numbers = session.scalars(select(Order.order_number)).all()

    assert first_master == second_master
    assert first_orders == len(second_order_numbers)
    # 오더 번호에는 기준일이 박혀 있다 — 시나리오는 움직였다.
    assert all(number.startswith("MO-20260920-") for number in second_order_numbers)


def test_a_mistyped_option_does_not_wipe_the_tables(monkeypatch) -> None:
    """모르는 인자를 조용히 무시하면 `--ifempty` 오타가 「비었을 때만」 이 아니라
    **표를 지우는 길**로 떨어진다 — 기동 스크립트가 그렇게 부르면 경고 한 줄
    없이 전부 사라진다.
    """
    def _must_not_run(*_args, **_kwargs):
        raise AssertionError("표를 지우는 길이 돌면 안 된다")

    monkeypatch.setattr(seed_module, "initialize_sample_database", _must_not_run)
    monkeypatch.setattr(seed_module, "seed_if_empty", _must_not_run)

    with pytest.raises(SystemExit) as raised:
        seed_module.main(["--ifempty"])

    assert "--ifempty" in str(raised.value)


def test_the_supported_option_still_works(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        seed_module, "seed_if_empty", lambda: calls.append("if-empty") or True
    )

    seed_module.main(["--if-empty"])

    assert calls == ["if-empty"]


def test_no_arguments_still_takes_the_reset_path(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        seed_module, "initialize_sample_database", lambda: calls.append("reset")
    )

    seed_module.main([])

    assert calls == ["reset"]


def test_the_reset_path_leaves_the_database_under_alembic_control(
    tmp_path, monkeypatch
) -> None:
    """`create_all` 은 표만 만들고 `alembic_version` 을 남기지 않는다.

    그대로 두면 README 가 함께 안내하는 `alembic upgrade head` 가 초기
    마이그레이션을 처음부터 돌리려다 **이미 있는 표에서 터진다.** 두 길이 같은
    데이터베이스를 가리키는 이상 한쪽이 다른 쪽을 못 쓰게 만들면 안 된다.
    """
    database_path = tmp_path / "reset.db"
    url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(url)
    monkeypatch.setattr(db_base, "engine", engine)
    monkeypatch.setattr(db_base, "SessionLocal", sessionmaker(bind=engine))

    seed_module.reset_database()

    with engine.connect() as connection:
        stamped = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()

    config = Config(str(seed_module.BACKEND_DIRECTORY / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    head = ScriptDirectory.from_config(config).get_current_head()
    assert stamped == head


def test_the_reset_path_stamps_the_engine_it_actually_used(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    """버전은 **표를 만든 그 데이터베이스**에 찍혀야 한다.

    이 픽스처는 `db_base` 를 **일회용 데이터베이스**로 갈아 끼운다. 찍는 쪽이
    설정의 접속 주소로 따로 접속하면, 표는 그 일회용에 서고 `alembic_version` 은
    설정이 가리키는 진짜 데이터베이스에 남는다 — 표가 하나도 없는데 head 로
    보이는 데이터베이스가 생기고, 옛 스키마가 들어 있었다면 「최신」으로 굳어
    마이그레이션이 건너뛰어진다. 그래서 여기서 묻는 것은 「찍혔는가」가 아니라
    **어디에 찍혔는가**다.

    갈아 끼우는 대상이 설정된 엔진 위의 일회용이 되면서 이 검사는 두 엔진 모두에서
    같은 것을 묻게 되었다 — 엇나간 접속이 PostgreSQL 에서도 잡힌다.
    """
    reset_database()

    with seeded_session_factory() as session:
        stamped = session.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()

    config = Config(str(seed_module.BACKEND_DIRECTORY / "alembic.ini"))
    assert stamped == ScriptDirectory.from_config(config).get_current_head()


def test_the_reset_path_removes_tables_the_models_no_longer_know(
    empty_bound_engine: Engine,
) -> None:
    """이름이 바뀐 옛 표는 메타데이터가 모르므로 살아남는다.

    품목 통합 전의 `products` 를 가진 데이터베이스에서 시드를 돌리면 새 표가
    그 옆에 생기고, 시드가 현재 리비전을 찍어 두므로 **Alembic 도 영영 치우지
    못한다** — 옛 데이터를 든 표가 그대로 굳는다.

    표 목록을 `sqlite_master` 대신 인스펙터로 읽는다. 묻는 것은 「reset 이 무엇을
    지우는가」이지 그 목록을 어느 방언의 어느 표에서 읽는가가 아니므로, 수단만
    바꾸면 묻는 내용을 그대로 둔 채 두 엔진에서 돌게 된다 — 그리고 지우는 쪽은
    **엔진마다 다른 반사**를 쓴다.
    """
    with empty_bound_engine.begin() as connection:
        connection.execute(text("CREATE TABLE products (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE bom_requirements (id INTEGER PRIMARY KEY)"))

    seed_module.reset_database()

    remaining = set(inspect(empty_bound_engine).get_table_names())

    assert "products" not in remaining
    assert "bom_requirements" not in remaining
    assert "items" in remaining


def test_preflight_stops_a_database_that_predates_alembic(
    empty_bound_engine: Engine, monkeypatch
) -> None:
    """표는 있는데 버전 표가 없으면 마이그레이션 앞에서 멈춰야 한다.

    이전 판은 Alembic 없이 `create_all` 로 표를 만들었다. Alembic 은 그런
    데이터베이스를 **빈 것**으로 읽고 초기 리비전을 처음부터 돌리다가 이미 있는
    표에서 죽는다. 진입점이 마이그레이션을 먼저 돌리므로 기동은 그 자리에서
    멈추고, 그 메시지로는 무엇을 해야 하는지 알 수 없다.
    """
    with empty_bound_engine.begin() as connection:
        connection.execute(text("CREATE TABLE products (id INTEGER PRIMARY KEY)"))

    monkeypatch.setattr(preflight, "engine", empty_bound_engine)

    problem = preflight.check()

    assert problem is not None
    assert "products" in problem
    # 고를 수 있는 두 길이 문장 안에 있어야 한다 — 없으면 멈추기만 한 것이다.
    assert "python -m app.seed" in problem
    assert "alembic stamp head" in problem


def test_preflight_lets_an_empty_or_managed_database_through(
    empty_bound_engine: Engine, monkeypatch
) -> None:
    """빈 데이터베이스와 Alembic 이 아는 데이터베이스는 그냥 지나가야 한다."""
    monkeypatch.setattr(preflight, "engine", empty_bound_engine)

    assert preflight.check() is None

    with empty_bound_engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num TEXT)"))
        connection.execute(text("CREATE TABLE items (id INTEGER PRIMARY KEY)"))

    assert preflight.check() is None


def test_the_reset_path_leaves_tables_this_app_does_not_own(
    empty_bound_engine: Engine,
) -> None:
    """옆에 있는 남의 표는 살아남아야 한다.

    옛 표를 치우려고 데이터베이스를 읽어서 지우면, 스키마를 나눠 쓰는 곳에서는
    **보이는 표를 전부** 지운다. 개발용이라고 문서에 적는 것으로는 막지 못한다 —
    한 번 실행하면 되돌릴 수 없기 때문이다. 지울 것은 이름으로 정한다.

    빈 데이터베이스에서 시작해야 뜻이 선다. 앞 검사가 남긴 `payroll_entries` 를
    보고 「남았다」로 읽으면, 이 검사는 지우는 쪽이 남의 표까지 쓸어 가도 초록이다.
    """
    with empty_bound_engine.begin() as connection:
        # 옛 이름 하나와, 이 앱과 무관한 표 하나를 나란히 둔다.
        connection.execute(text("CREATE TABLE products (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE payroll_entries (id INTEGER PRIMARY KEY)"))

    seed_module.reset_database()

    remaining = set(inspect(empty_bound_engine).get_table_names())

    assert "products" not in remaining
    assert "payroll_entries" in remaining
    assert "items" in remaining


def test_the_reset_path_works_from_any_working_directory(tmp_path, monkeypatch) -> None:
    """`alembic.ini` 의 리비전 폴더는 **현재 작업 디렉터리**를 기준으로 풀린다.

    그래서 `backend/` 밖에서 부르면 표를 지우고 다시 만든 **뒤에** 버전을 찍다가
    죽는다. 남는 것은 빈 표 스무 개에 버전도 데이터도 없는 데이터베이스이고,
    그 상태를 `preflight` 는 「옛 데이터베이스」로 잘못 읽어 기동을 막는다 —
    지우는 데까지는 성공했으므로 되돌릴 것도 없다.
    """
    database_path = tmp_path / "elsewhere.db"
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    monkeypatch.setattr(db_base, "engine", engine)
    monkeypatch.setattr(db_base, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.chdir(tmp_path)

    seed_module.reset_database()

    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        assert connection.execute(text("SELECT count(*) FROM items")).scalar_one() == 20


def test_preflight_ignores_tables_this_app_does_not_own(
    empty_bound_engine: Engine, monkeypatch
) -> None:
    """남의 표 하나가 첫 기동을 영영 막아서는 안 된다.

    스키마를 나눠 쓰는 곳에서 「아무 표나 있으면 멈춘다」로 두면, 이 앱이 아직
    한 줄도 만들지 않았는데도 마이그레이션이 시작되지 못한다. 그리고 그때
    알려 주는 두 길(리셋 · 스탬프)은 둘 다 그 상태에 대한 답이 아니다.
    """
    with empty_bound_engine.begin() as connection:
        connection.execute(text("CREATE TABLE payroll_entries (id INTEGER PRIMARY KEY)"))

    monkeypatch.setattr(preflight, "engine", empty_bound_engine)

    assert preflight.check() is None


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]


def test_the_container_startup_path_seeds_a_migrated_database(
    empty_bound_engine: Engine,
) -> None:
    """컨테이너 기동이 오는 길을 **프로세스째** 밟는다.

    `docker-entrypoint.sh` 는 `alembic upgrade head` 로 표를 맞춘 뒤
    `python -m app.seed --if-empty` 로 내용만 넣는다. 그 길은 표를 만들지 않으므로
    `drop_all`/`create_all` 안에서 일어나던 모델 등록이 **아무 데서도 일어나지
    않는다** — 기준정보 모듈의 `common_codes` 가 메타데이터에 없어 품목의 복합
    외래키가 가리킬 표를 찾지 못하고, 첫 flush 가 `NoReferencedTableError` 로
    죽는다. 지금까지 CI 는 인자 없는 `python -m app.seed`(표를 지우고 다시 만드는
    길)만 돌려 이 자리를 한 번도 밟지 않았다.

    같은 프로세스 안에서는 재현되지 않는다. 다른 검사가 이미 두 모듈을 불러
    등록해 두기 때문이다 — 메타데이터는 프로세스 하나에 하나다. 그래서 프로세스를
    따로 띄운다.

    **프로세스 경계와 설정된 엔진은 함께 설 수 있다.** 자식에게 일회용
    데이터베이스의 주소를 `DATABASE_URL` 로 넘기면 된다 — 부모가 아무것도
    불러 두지 않은 새 프로세스라는 성질은 그대로이고, 밟는 길이 운영 엔진에서도
    밟히게 된다. 이 길에는 방언이 다른 것이 실제로 있다: 마이그레이션이 세우는
    표와 시드의 첫 flush 다.

    비어 있는 데이터베이스여야 뜻이 선다. 앞 검사가 세워 둔 표 위에서는
    `upgrade head` 가 할 일을 찾지 못하고 `--if-empty` 가 곧바로 건너뛰므로,
    아무것도 하지 않고 초록이 된다.
    """
    url = empty_bound_engine.url.render_as_string(hide_password=False)
    environment = {**os.environ, "DATABASE_URL": url}
    # 주소가 있으면 설정은 이 값을 쓰지만, 남겨 두면 다음에 읽는 사람이 둘 중
    # 어느 것이 이겼는지를 다시 확인해야 한다.
    environment.pop("DATABASE_PATH", None)

    def run(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, *arguments],
            cwd=BACKEND_DIRECTORY,
            env=environment,
            capture_output=True,
            text=True,
        )

    migrated = run("-m", "alembic", "upgrade", "head")
    assert migrated.returncode == 0, migrated.stderr

    seeded = run("-m", "app.seed", "--if-empty")
    assert seeded.returncode == 0, seeded.stderr

    # 두 번째 기동은 아무것도 하지 않아야 한다. 하면 사람이 넣은 데이터가 지워진다.
    again = run("-m", "app.seed", "--if-empty")
    assert again.returncode == 0, again.stderr
    assert "건너뜁니다" in again.stdout

    with Session(empty_bound_engine) as session:
        assert session.scalar(select(func.count()).select_from(Item)) == 20
