from datetime import date

from app.services.material_risk import calculate_material_risk


def test_receipt_arriving_before_demand_prevents_stockout() -> None:
    result = calculate_material_risk(
        20,
        10,
        {date(2026, 9, 1): 15, date(2026, 9, 2): 15},
        {date(2026, 9, 2): 30},
        date(2026, 9, 1),
    )

    assert result.stockout_date is None
    assert result.shortage_expected is True
    assert result.ending_stock == 20


def test_marks_safety_stock_shortage_without_stockout() -> None:
    result = calculate_material_risk(
        20,
        10,
        {date(2026, 9, 1): 6, date(2026, 9, 2): 6},
        {},
        date(2026, 9, 1),
    )

    assert result.stockout_date is None
    assert result.shortage_expected is True
    assert result.minimum_stock == 8


def test_marks_first_day_stock_reaches_zero_as_stockout() -> None:
    result = calculate_material_risk(
        10,
        3,
        {date(2026, 9, 1): 4, date(2026, 9, 2): 6},
        {},
        date(2026, 9, 1),
    )

    assert result.stockout_date == date(2026, 9, 2)
    assert result.shortage_expected is True
    assert result.minimum_stock == 0
