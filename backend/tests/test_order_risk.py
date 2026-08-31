from datetime import date

from app.services.order_risk import calculate_order_risk


def test_marks_order_danger_when_estimated_completion_is_after_due_date() -> None:
    result = calculate_order_risk(
        100, 40, 10, date(2026, 9, 2), date(2026, 8, 31)
    )

    assert result.severity == "위험"
    assert result.estimated_completion_date == date(2026, 9, 6)
    assert result.remaining_quantity == 60


def test_marks_order_warning_when_due_date_is_within_one_day() -> None:
    result = calculate_order_risk(
        100, 80, 20, date(2026, 9, 1), date(2026, 8, 31)
    )

    assert result.severity == "주의"
    assert result.estimated_completion_date == date(2026, 9, 1)


def test_marks_order_normal_when_completion_is_on_time_with_buffer() -> None:
    result = calculate_order_risk(
        100, 80, 20, date(2026, 9, 5), date(2026, 8, 31)
    )

    assert result.severity == "정상"
    assert result.estimated_completion_date == date(2026, 9, 1)


def test_marks_zero_production_as_danger_without_estimate() -> None:
    result = calculate_order_risk(
        100, 0, 0, date(2026, 9, 5), date(2026, 8, 31)
    )

    assert result.severity == "위험"
    assert result.estimated_completion_date is None
    assert "생산량" in result.reason
