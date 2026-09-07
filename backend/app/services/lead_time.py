"""리드타임 — 저장은 시간, 화면은 날짜(지적 ⑬).

생산 리드타임은 시간으로 나오고(준비시간 + 개당 시간 × 수량) 공급사의 납기는
날로 온다. 역산은 이 둘을 한 축에서 이어 붙여야 하는데, 단위를 섞어 저장하면
어디선가 반올림이 생기고 **어느 값이 어느 단위인지 나중에 아무도 모른다.**

그래서 저장하는 값은 전부 시간이고, 날은 화면에서만 쓴다. 두 단위를 모두 다루는
것보다 경계에서 한 번 바꾸는 편이 싸다.

24시간 가동이 이 환산을 나눗셈으로 만든다 — 하루가 정확히 24시간이므로 달력이
필요 없다. 8시간 근무였다면 같은 환산에 캘린더가 필요했을 것이다. 공정 조건이
여기서도 문제를 지운다.
"""

from __future__ import annotations

from datetime import datetime, timedelta


# 24시간 풀타임 2교대이므로 하루가 정확히 24시간이다. 이 상수가 성립하지 않게
# 되는 날(휴일이 생기는 날) 역산은 산술에서 달력 계산으로 되돌아간다.
HOURS_PER_DAY = 24


def hours_from_days(days: float) -> float:
    """구매 리드타임을 **입력 시점에** 시간으로 바꾼다.

    공급사가 「3일」이라고 말한 것을 그대로 저장하지 않는 이유는, 저장된 숫자
    하나만 보고는 그것이 날인지 시간인지 알 수 없기 때문이다.
    """
    return days * HOURS_PER_DAY


def days_from_hours(hours: float) -> float:
    """화면에 날로 보여 주기 위한 경계. 저장 값을 바꾸지 않는다."""
    return hours / HOURS_PER_DAY


def production_lead_time_hours(
    setup_hours: float,
    hours_per_unit: float,
    quantity: float,
) -> float:
    """오더 하나의 소요 시간.

    리드타임이 품목의 상수가 아니라 **오더마다 다른 계산 결과**인 것이 요점이다.
    상수였다면 100개와 1000개가 같은 시각에 착수한다 — 계획은 그럴듯하고 현장은
    틀린다. 두 계수로 나누면 수량이 처음으로 일정에 반영된다.
    """
    if quantity < 0:
        raise ValueError("수량은 음수일 수 없습니다.")
    return setup_hours + hours_per_unit * quantity


def start_at(finish_at: datetime, lead_time_hours: float) -> datetime:
    """완료 시각에서 소요 시간을 그대로 빼 착수 시각을 낸다.

    쉬는 날이 없으므로 달력을 셀 필요가 없다. 반제품의 완료 시각이 곧 제품의
    착수 시각이고, 그렇게 2단이 한 축 위에서 이어 붙는다.
    """
    return finish_at - timedelta(hours=lead_time_hours)
