from datetime import date

from app.services.material_risk import Lot, calculate_material_risk


def _lot(
    quantity: float,
    received_day: int = 1,
    expiry_day: int | None = None,
    warehouse: str = "원재료창고",
    lot_number: str = "LOT-A",
) -> Lot:
    return Lot(
        lot_number=lot_number,
        warehouse=warehouse,
        quantity=quantity,
        received_date=date(2026, 9, received_day),
        expiry_date=date(2026, 9, expiry_day) if expiry_day else None,
    )


def test_receipt_arriving_before_demand_prevents_stockout() -> None:
    result = calculate_material_risk(
        [_lot(20), _lot(30, received_day=2, lot_number="LOT-B")],
        10,
        {date(2026, 9, 1): 15, date(2026, 9, 2): 15},
        date(2026, 9, 1),
    )

    assert result.stockout_date is None
    assert result.shortage_expected is True
    assert result.ending_stock == 20


def test_marks_safety_stock_shortage_without_stockout() -> None:
    result = calculate_material_risk(
        [_lot(20)],
        10,
        {date(2026, 9, 1): 6, date(2026, 9, 2): 6},
        date(2026, 9, 1),
    )

    assert result.stockout_date is None
    assert result.shortage_expected is True
    assert result.minimum_stock == 8


def test_marks_first_day_stock_reaches_zero_as_stockout() -> None:
    result = calculate_material_risk(
        [_lot(10)],
        3,
        {date(2026, 9, 1): 4, date(2026, 9, 2): 6},
        date(2026, 9, 1),
    )

    assert result.stockout_date == date(2026, 9, 2)
    assert result.shortage_expected is True
    assert result.minimum_stock == 0


def test_unmet_demand_carries_over_and_is_paid_by_a_later_receipt() -> None:
    result = calculate_material_risk(
        [_lot(20), _lot(150, received_day=2, lot_number="LOT-B")],
        10,
        {date(2026, 9, 1): 100},
        date(2026, 9, 1),
    )

    assert result.stockout_date == date(2026, 9, 1)
    assert result.minimum_stock == -80
    assert result.ending_stock == 70


def test_lot_is_unavailable_on_its_expiry_date_and_counted_as_discarded() -> None:
    result = calculate_material_risk(
        [_lot(100, expiry_day=3)],
        10,
        {},
        date(2026, 9, 1),
    )

    assert result.available_stock == 100
    assert result.expiring_quantity == 100
    assert result.ending_stock == 0
    assert result.stockout_date == date(2026, 9, 3)
    assert result.first_expiry_date == date(2026, 9, 3)


def test_expiry_driven_shortage_is_reported_even_with_enough_total_stock() -> None:
    result = calculate_material_risk(
        [_lot(500, expiry_day=5), _lot(40, lot_number="LOT-B", expiry_day=30)],
        100,
        {},
        date(2026, 9, 1),
    )

    assert result.available_stock == 540
    assert result.expiring_quantity == 500
    assert result.shortage_expected is True
    assert result.minimum_stock == 40


def test_demand_is_issued_from_the_earliest_expiring_lot_first() -> None:
    result = calculate_material_risk(
        [
            _lot(50, received_day=1, expiry_day=20, lot_number="LOT-LATE"),
            _lot(50, received_day=1, expiry_day=6, lot_number="LOT-SOON"),
        ],
        10,
        {date(2026, 9, 1): 50},
        date(2026, 9, 1),
    )

    # 유효기간이 빠른 LOT-SOON 이 먼저 나가므로 만료 폐기가 발생하지 않는다.
    assert result.expiring_quantity == 0
    assert result.ending_stock == 50


def test_production_warehouse_is_issued_first_when_lots_are_otherwise_equal() -> None:
    result = calculate_material_risk(
        [
            _lot(60, warehouse="원재료창고", lot_number="LOT-SPLIT"),
            _lot(40, warehouse="생산창고", lot_number="LOT-SPLIT"),
        ],
        10,
        {date(2026, 9, 1): 40},
        date(2026, 9, 1),
    )

    assert result.available_stock == 100
    assert result.stock_by_warehouse == {"원재료창고": 60.0, "생산창고": 40.0}
    assert result.ending_stock == 60


def test_both_warehouses_count_towards_available_stock() -> None:
    result = calculate_material_risk(
        [
            _lot(100, warehouse="원재료창고", lot_number="LOT-A"),
            _lot(150, warehouse="생산창고", lot_number="LOT-B"),
        ],
        200,
        {},
        date(2026, 9, 1),
    )

    assert result.available_stock == 250
    assert result.shortage_expected is False


def test_a_lot_expiring_on_the_reference_date_counts_as_discarded_today() -> None:
    """기준일 당일 만료는 '오늘 버리는 것'이라 폐기 수량에 들어가야 한다."""
    result = calculate_material_risk(
        [_lot(100, received_day=1, expiry_day=1)],
        10,
        {},
        date(2026, 9, 1),
    )

    assert result.available_stock == 0
    assert result.expiring_quantity == 100
    assert result.first_discard_date == date(2026, 9, 1)
    assert result.discarded_by_lot == {("LOT-A", "원재료창고"): 100}


def test_a_lot_expired_before_the_reference_date_is_not_reported_as_disposal() -> None:
    """기준일보다 앞선 유효기간은 이미 지난 재고이지 이번 기간의 폐기가 아니다."""
    result = calculate_material_risk(
        [Lot("LOT-OLD", "원재료창고", 100, date(2026, 8, 1), date(2026, 8, 20))],
        10,
        {},
        date(2026, 9, 1),
    )

    assert result.available_stock == 0
    assert result.expiring_quantity == 0
    assert result.first_discard_date is None
    assert result.discarded_by_lot == {}


def test_a_lot_eaten_by_demand_before_its_expiry_is_not_counted_as_discarded() -> None:
    result = calculate_material_risk(
        [
            _lot(50, expiry_day=5, lot_number="LOT-SOON"),
            _lot(500, expiry_day=30, lot_number="LOT-LATE"),
        ],
        10,
        {date(2026, 9, 1): 50},
        date(2026, 9, 1),
    )

    assert result.expiring_quantity == 0
    assert result.discarded_by_lot == {}
    assert result.first_discard_date is None


def test_partial_consumption_only_discards_what_is_left_at_expiry() -> None:
    result = calculate_material_risk(
        [
            _lot(50, expiry_day=5, lot_number="LOT-SOON"),
            _lot(500, expiry_day=30, lot_number="LOT-LATE"),
        ],
        10,
        {date(2026, 9, 1): 20},
        date(2026, 9, 1),
    )

    assert result.discarded_by_lot == {("LOT-SOON", "원재료창고"): 30}
    assert result.expiring_quantity == 30
    assert result.first_discard_date == date(2026, 9, 5)


def test_first_discard_date_is_reported_after_an_earlier_demand_stockout() -> None:
    """수요로 먼저 소진된 뒤 나중에 폐기가 나면 두 날짜가 갈려야 한다."""
    result = calculate_material_risk(
        [
            _lot(10, lot_number="LOT-NOW"),
            Lot("LOT-LATER", "원재료창고", 40, date(2026, 9, 4), date(2026, 9, 8)),
        ],
        5,
        {date(2026, 9, 1): 10},
        date(2026, 9, 1),
    )

    assert result.stockout_date == date(2026, 9, 1)
    assert result.first_discard_date == date(2026, 9, 8)
    assert result.first_discard_date > result.stockout_date
