"""리드타임 — 저장은 시간, 화면은 날짜(지적 ⑬)."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.services.lead_time import (
    HOURS_PER_DAY,
    days_from_hours,
    hours_from_days,
    production_lead_time_hours,
    start_at,
)


def test_a_day_is_exactly_twenty_four_hours() -> None:
    """24시간 가동이 환산을 나눗셈으로 만든다.

    8시간 근무였다면 같은 환산에 캘린더가 필요했다 — 공정 조건이 문제를 지운다.
    """
    assert HOURS_PER_DAY == 24
    assert hours_from_days(3) == 72
    assert days_from_hours(72) == 3


def test_the_conversion_round_trips_without_drift() -> None:
    """단위를 섞어 저장하면 어디선가 반올림이 생긴다. 경계에서 한 번만 바꾼다."""
    for days in (0, 1, 5, 14, 21):
        assert days_from_hours(hours_from_days(days)) == days


def test_lead_time_grows_with_quantity() -> None:
    """리드타임이 품목의 상수가 아니라 오더마다 다른 계산 결과다.

    상수였다면 100개와 1000개가 같은 시각에 착수한다 — 계획은 그럴듯하고 현장은
    틀린다. 두 계수로 나누면 수량이 처음으로 일정에 반영된다.
    """
    hundred = production_lead_time_hours(setup_hours=4, hours_per_unit=0.2, quantity=100)
    thousand = production_lead_time_hours(setup_hours=4, hours_per_unit=0.2, quantity=1000)

    # 설계도의 예시 그대로다 — 준비 4h + 0.2h × 100개 = 24h.
    assert hundred == 24
    assert thousand == 204


def test_a_zero_quantity_order_still_costs_its_setup() -> None:
    """준비시간은 수량과 무관하게 든다. 그것이 계수를 둘로 나눈 이유다."""
    assert production_lead_time_hours(setup_hours=3, hours_per_unit=0.15, quantity=0) == 3


def test_a_negative_quantity_is_refused() -> None:
    with pytest.raises(ValueError):
        production_lead_time_hours(setup_hours=3, hours_per_unit=0.15, quantity=-1)


def test_negative_coefficients_are_refused() -> None:
    """음수 계수는 소요 시간을 음수로 만들고, 그러면 착수가 완료보다 뒤에 잡힌다.

    `(4, -1, 100)` 은 `-96` 이 되어 `start_at` 이 일정을 거꾸로 세운다. 손으로
    고치는 품목 마스터에서 부호 하나가 그 일을 하므로, 표의 제약과 이 함수
    양쪽에서 막는다.
    """
    with pytest.raises(ValueError):
        production_lead_time_hours(setup_hours=4, hours_per_unit=-1, quantity=100)
    with pytest.raises(ValueError):
        production_lead_time_hours(setup_hours=-4, hours_per_unit=0.2, quantity=100)


def test_backward_scheduling_just_subtracts_hours() -> None:
    """쉬는 날이 없으므로 달력을 셀 필요가 없다.

    설계도의 시간 축 그대로다 — 제품오더 24h 를 되짚으면 착수가 −24h 이고,
    반제품 18h 를 거기서 더 되짚으면 −42h 다. 두 막대가 한 축 위에서 이어 붙는다.
    """
    finish = datetime(2026, 9, 10, 0, 0)

    product_start = start_at(finish, 24)
    semi_finished_start = start_at(product_start, 18)

    assert product_start == datetime(2026, 9, 9, 0, 0)
    assert semi_finished_start == datetime(2026, 9, 8, 6, 0)


def test_backward_scheduling_crosses_midnight_without_a_calendar() -> None:
    """교대가 자정을 넘어도 산술은 그대로다 — 띠에 빈칸이 없기 때문이다."""
    assert start_at(datetime(2026, 9, 10, 3, 0), 6) == datetime(2026, 9, 9, 21, 0)
