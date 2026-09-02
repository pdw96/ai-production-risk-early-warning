from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Iterable, Literal, Mapping

from app.core.config import PRODUCTION_WAREHOUSE, RAW_MATERIAL_WAREHOUSE


Warehouse = Literal["원재료창고", "생산창고"]

# 출고 시 창고 우선순위(낮을수록 먼저 차감). 이미 라인 옆에 대 놓은 생산창고
# 재고를 두고 원재료창고를 먼저 헐면 현실에서 다시 이동이 생기므로 생산창고를
# 먼저 쓴다. 총 가용량 판정에는 영향이 없고 어느 로트가 남는지만 달라진다.
_WAREHOUSE_ISSUE_PRIORITY: dict[str, int] = {
    PRODUCTION_WAREHOUSE: 0,
    RAW_MATERIAL_WAREHOUSE: 1,
}

# 유효기간이 없는 로트는 폐기되지 않으므로 가장 마지막에 쓴다.
_NO_EXPIRY_SORT_KEY = date.max

# 수량은 소수점 둘째 자리까지만 의미가 있다. 차감을 부동소수로 그냥 두면
# 0.1 + 0.2 에서 0.3 을 뺀 잔차(2.8e-17)가 `quantity > 0` 을 통과해, 정확히
# 소진된 재고가 남아 있는 것처럼 보인다(소진일이 안 잡힌다).
_QUANTITY_PRECISION = 6


def _normalize(quantity: float) -> float:
    return round(quantity, _QUANTITY_PRECISION)


@dataclass(frozen=True)
class Lot:
    """로트 한 건의 보유(또는 예정 입고) 상태."""

    lot_number: str
    warehouse: Warehouse
    quantity: float
    received_date: date
    expiry_date: date | None = None
    # 예정 입고에서 만들어진 가상 로트인가. 로트번호는 보유 로트와 겹칠 수
    # 있으므로(예정 입고는 DB 유일 제약 밖이다) 이 값까지 넣어야 두 로트의
    # 폐기 기록이 한 칸으로 합쳐지지 않는다.
    scheduled: bool = False

    @property
    def key(self) -> tuple[str, str, bool]:
        """로트를 유일하게 가리키는 키. 폐기 기록의 dict 키로 쓴다."""
        return (self.lot_number, self.warehouse, self.scheduled)


@dataclass(frozen=True)
class MaterialRiskResult:
    """14일 로트/FIFO 재고 시뮬레이션 결과."""

    available_stock: float
    stock_by_warehouse: dict[str, float]
    ending_stock: float
    minimum_stock: float
    shortage_expected: bool
    stockout_date: date | None
    expiring_quantity: float
    first_expiry_date: date | None
    # 안전재고 미만이 처음 드러난 날. 소진 전에 이미 부족했는지 구분한다.
    first_shortage_date: date | None
    # `Lot.key` -> 기간 내 실제 폐기 수량. 수요가 먼저 먹어치운 로트는
    # 유효기간이 기간 안이어도 여기에 들어오지 않는다.
    discarded_by_lot: dict[tuple[str, str, bool], float]
    # 날짜 -> 그날 폐기된 수량. 부족이 드러난 날까지의 폐기만 그 부족의
    # 원인으로 말하기 위해 필요하다(전체 폐기량을 원인으로 적으면 부족 이후에
    # 도착한 입고가 나중에 버려진 것까지 원인으로 둔갑한다).
    discarded_by_date: dict[date, float]

    @property
    def first_discard_date(self) -> date | None:
        """폐기가 처음 일어난 날."""
        return min(self.discarded_by_date, default=None)


def _issue_order_key(lot: Lot) -> tuple[date, date, int, str]:
    """출고 순서: 유효기간 → 입고일 → 창고(생산창고 우선) → 로트번호."""
    return (
        lot.expiry_date or _NO_EXPIRY_SORT_KEY,
        lot.received_date,
        _WAREHOUSE_ISSUE_PRIORITY.get(lot.warehouse, len(_WAREHOUSE_ISSUE_PRIORITY)),
        lot.lot_number,
    )


def calculate_material_risk(
    lots: Iterable[Lot],
    safety_stock: float,
    daily_demands: Mapping[date, float],
    reference_date: date,
    horizon_days: int = 14,
) -> MaterialRiskResult:
    """로트별 유효기간과 FIFO 출고를 반영해 자재 위험을 계산한다.

    가용 조건은 ``received_date <= day < expiry_date`` 다. 유효기간 당일은
    가용하지 않으며 그날 아침 폐기 처리된다. 원재료창고와 생산창고 재고는
    모두 가용으로 본다(수요가 생산계획에서 나오므로 생산창고 이동분을 빼면
    정상 상황이 부족으로 오판된다).
    """
    if horizon_days < 1:
        raise ValueError("horizon_days must be at least 1")

    pending = sorted(lots, key=lambda lot: (lot.received_date, _issue_order_key(lot)))
    horizon_end = reference_date + timedelta(days=horizon_days - 1)
    first_expiry_date = min(
        (
            lot.expiry_date
            for lot in pending
            if lot.expiry_date is not None and lot.expiry_date >= reference_date
        ),
        default=None,
    )

    pool: list[Lot] = []
    expiring_quantity = 0.0
    discarded_by_lot: dict[tuple[str, str, bool], float] = {}
    discarded_by_date: dict[date, float] = {}
    stockout_date: date | None = None
    first_shortage_date: date | None = None
    minimum_stock: float | None = None
    shortage_expected = False
    available_stock = 0.0
    stock_by_warehouse: dict[str, float] = {
        RAW_MATERIAL_WAREHOUSE: 0.0,
        PRODUCTION_WAREHOUSE: 0.0,
    }
    # 충족하지 못한 수요는 다음 날로 이월된다. 뒤늦게 들어온 입고가 이 적자를
    # 먼저 갚는다(스칼라 재고 시절 stock 이 음수로 남던 동작과 같은 의미다).
    deficit = 0.0
    stock = 0.0

    for offset in range(horizon_days):
        day = reference_date + timedelta(days=offset)

        # 1) 입고 — 기존 규칙대로 수요 차감보다 먼저 반영한다.
        while pending and pending[0].received_date <= day:
            pool.append(pending.pop(0))

        # 2) 폐기 — day < expiry 가 가용 조건이므로 유효기간 당일 아침에 빠진다.
        #    기준일 당일 만료도 오늘 버리는 것이므로 폐기 수량에 넣는다.
        #    기준일보다 앞선 유효기간만 이미 지난 재고로 보고 조용히 뺀다.
        remaining_pool: list[Lot] = []
        for lot in pool:
            if lot.expiry_date is not None and lot.expiry_date <= day:
                if lot.expiry_date >= reference_date and lot.quantity > 0:
                    expiring_quantity = _normalize(expiring_quantity + lot.quantity)
                    discarded_by_lot[lot.key] = _normalize(
                        discarded_by_lot.get(lot.key, 0.0) + lot.quantity
                    )
                    discarded_by_date[day] = _normalize(
                        discarded_by_date.get(day, 0.0) + lot.quantity
                    )
            else:
                remaining_pool.append(lot)
        pool = remaining_pool

        if offset == 0:
            available_stock = _normalize(sum(lot.quantity for lot in pool))
            for lot in pool:
                stock_by_warehouse[lot.warehouse] = _normalize(
                    stock_by_warehouse.get(lot.warehouse, 0.0) + lot.quantity
                )
            # 기준일 시점 재고가 이미 안전재고 미만이면 그 자체로 부족이다.
            shortage_expected = available_stock < safety_stock
            if shortage_expected:
                first_shortage_date = day
            minimum_stock = available_stock

        # 3) 출고 — 이월 적자를 포함해 유효기간 빠른 순으로 부분 차감한다.
        outstanding = daily_demands.get(day, 0) + deficit
        if outstanding > 0:
            pool.sort(key=_issue_order_key)
            for index, lot in enumerate(pool):
                if outstanding <= 0:
                    break
                issued = min(lot.quantity, outstanding)
                pool[index] = replace(lot, quantity=_normalize(lot.quantity - issued))
                outstanding = _normalize(outstanding - issued)
            pool = [lot for lot in pool if lot.quantity > 0]
        deficit = max(outstanding, 0.0)

        # 4) 집계 — 못 채운 수요만큼 재고를 음수로 표현해 소진을 드러낸다.
        stock = _normalize(sum(lot.quantity for lot in pool) - deficit)
        minimum_stock = stock if minimum_stock is None else min(minimum_stock, stock)
        shortage_expected = shortage_expected or stock < safety_stock
        if stock < safety_stock and first_shortage_date is None:
            first_shortage_date = day
        if stock <= 0 and stockout_date is None:
            stockout_date = day

    if first_expiry_date is not None and first_expiry_date > horizon_end:
        # 14일 밖의 유효기간은 이 화면의 판단 근거가 아니다.
        first_expiry_date = None
    return MaterialRiskResult(
        available_stock=available_stock,
        stock_by_warehouse=stock_by_warehouse,
        ending_stock=stock,
        minimum_stock=minimum_stock if minimum_stock is not None else available_stock,
        shortage_expected=shortage_expected or stockout_date is not None,
        stockout_date=stockout_date,
        expiring_quantity=expiring_quantity,
        first_expiry_date=first_expiry_date,
        first_shortage_date=first_shortage_date,
        discarded_by_lot=discarded_by_lot,
        discarded_by_date=discarded_by_date,
    )
