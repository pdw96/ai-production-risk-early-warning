"""시드를 통과한 실제 값을 고정하는 골든 케이스.

기존 검사(`test_material_risk.py` · `test_briefing.py` · `test_order_risk.py`)는
손으로 만든 객체로 경계 조건을 하나씩 본다. `test_briefing.py` 는 첫 주석에
「DB를 띄우지 않고 경계 조건을 직접 만든다」고 적어 두었다. 그래서 **시드
데이터를 통과한 실제 값이 맞는지는 아무도 보지 않는다** — 이 파일이 그 자리다.

값 하나(예: 소진일)만 비교하면 중간 판단이 그대로 통과하므로 **전개를 통째로**
비교한다. 자재는 `horizon_days=1..14` 의 날짜별 전개를, 오더는 시드의 30건
전부를, 완제품 로트는 상태별 집계를 고정한다.

**기준일 고정이 이 파일의 성립 조건이다.** `reset_database(reference_date)` 는
기준일을 인자로 받아 시드를 그 날짜 기준으로 만든다. 넘기지 않으면 오늘 날짜로
흔들려 아래 숫자가 전부 무의미해진다.

숫자는 소수 둘째 자리로 맞춰 비교한다. 수량의 뜻이 거기까지이고 API 도 그
자리로 내보내므로, 그 아래 부동소수 꼬리를 골든 값에 박아 둘 이유가 없다.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, selectinload, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import (
    PRODUCT_WAREHOUSE,
    QC_PASSED,
    RAW_MATERIAL_WAREHOUSE,
    WARNING_BUFFER_DAYS,
)
from app.db import base as db_base
from app.db.models import FinishedGoodsLot, Item, Order
from app.seed import reset_database
from app.services.briefing import (
    HORIZON_DAYS,
    _build_material_response,
    _finished_goods_lot_state,
    _planned_quantities_by_product_day,
)
from app.services.material_risk import Lot, MaterialRiskResult, calculate_material_risk
from app.services.order_risk import calculate_order_risk


# 시드가 쓰는 기준일. 이 값을 바꾸면 아래 골든 값이 전부 달라진다.
REFERENCE_DATE = date(2026, 9, 1)

# 폐기와 소진이 둘 다 일어나는 자재. 시드가 `EXPIRY_SHORTAGE_MATERIAL_INDEX` 로
# 고정하는 시나리오이며, 그래서 이 코드가 골든 케이스의 대상이다.
GOLDEN_MATERIAL_CODE = "RM-05"


@pytest.fixture
def seeded_session_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> sessionmaker[Session]:
    """고정 기준일로 시드한 인메모리 DB. 파일도 서버도 남기지 않는다.

    `DATABASE_URL` 이 무엇이든 SQLite 인메모리로 돈다 — `test_api.py` ·
    `test_seed.py` 와 같은 방식이다. 이 파일이 묻는 것은 엔진 이식성이 아니라
    같은 입력에서 나오는 값이다.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(db_base, "engine", engine)
    monkeypatch.setattr(db_base, "SessionLocal", session_factory)
    reset_database(REFERENCE_DATE)
    return session_factory


def _load_material(session: Session, code: str) -> Item:
    material = session.scalar(
        select(Item)
        .where(Item.code == code)
        .options(
            selectinload(Item.used_in),
            selectinload(Item.purchase_receipts),
            selectinload(Item.material_lots),
        )
    )
    assert material is not None, f"시드에 {code} 가 없습니다."
    return material


def _material_risk_inputs(
    session: Session,
    material: Item,
) -> tuple[list[Lot], float, dict[date, float]]:
    """`_build_material_response` 와 같은 방식으로 계산 입력을 만든다.

    화면 조립을 통째로 부르지 않는 이유는 `discarded_by_date` 가 응답에 실리지
    않기 때문이다 — 폐기를 어느 날로 귀속하는가가 이 골든 케이스의 핵심이라
    엔진 결과를 직접 봐야 한다. 조립 경로와 어긋나지 않는지는
    `test_the_material_response_agrees_with_the_golden_expansion` 이 본다.
    """
    planned_by_product_day = _planned_quantities_by_product_day(
        session, REFERENCE_DATE
    )
    daily_demands: defaultdict[date, float] = defaultdict(float)
    for requirement in material.used_in:
        for offset in range(HORIZON_DAYS):
            day = REFERENCE_DATE + timedelta(days=offset)
            daily_demands[day] += (
                planned_by_product_day.get((requirement.parent_item_id, day), 0)
                * requirement.unit_quantity
            )

    horizon_end = REFERENCE_DATE + timedelta(days=HORIZON_DAYS - 1)
    lots = [
        Lot(
            lot_number=lot.lot_number,
            warehouse=lot.warehouse,
            quantity=lot.quantity,
            received_date=lot.received_date,
            expiry_date=lot.expiry_date,
        )
        for lot in material.material_lots
    ]
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
        if REFERENCE_DATE <= receipt.scheduled_date <= horizon_end
    ]
    return [*lots, *scheduled_lots], material.safety_stock, dict(daily_demands)


def _expansion_row(result: MaterialRiskResult) -> dict[str, object]:
    return {
        "stockout_date": result.stockout_date,
        "first_shortage_date": result.first_shortage_date,
        "minimum_stock": round(result.minimum_stock, 2),
        "ending_stock": round(result.ending_stock, 2),
        "expiring_quantity": round(result.expiring_quantity, 2),
        "first_expiry_date": result.first_expiry_date,
        "discarded_by_date": {
            day: round(quantity, 2)
            for day, quantity in sorted(result.discarded_by_date.items())
        },
        "shortage_expected": result.shortage_expected,
    }


# RM-05(접착 수지) 의 날짜별 전개. 시드가 만든 실제 로트는 셋이다.
#   LOT-RM-05-01  원재료창고 598.0  입고 2026-07-23  유효기간 2026-09-05
#   LOT-RM-05-02  생산창고   104.0  입고 2026-08-22  유효기간 2026-10-05
#   LOT-RM-05-IN-01(예정) 원재료창고 275.0  입고 2026-09-14  유효기간 2026-10-28
# 안전재고 260.0, 수요는 9/1 이 143.1 이고 9/2~9/14 는 매일 37.6714 다.
#
# 읽는 법 — 9/5 아침에 첫 로트가 통째로 폐기되고(341.89), 그날 처음 안전재고
# 아래로 떨어진다. 9/7 에 소진되고, 못 채운 수요는 적자로 이월된다. 9/14 에
# 예정 입고 275 가 도착해 그 적자를 갚고 2.29 가 남는다.
MATERIAL_GOLDEN_EXPANSION: dict[int, dict[str, object]] = {
    1: dict(
        stockout_date=None,
        first_shortage_date=None,
        minimum_stock=558.9,
        ending_stock=558.9,
        expiring_quantity=0.0,
        first_expiry_date=None,
        discarded_by_date={},
        shortage_expected=False,
    ),
    2: dict(
        stockout_date=None,
        first_shortage_date=None,
        minimum_stock=521.23,
        ending_stock=521.23,
        expiring_quantity=0.0,
        first_expiry_date=None,
        discarded_by_date={},
        shortage_expected=False,
    ),
    3: dict(
        stockout_date=None,
        first_shortage_date=None,
        minimum_stock=483.56,
        ending_stock=483.56,
        expiring_quantity=0.0,
        first_expiry_date=None,
        discarded_by_date={},
        shortage_expected=False,
    ),
    4: dict(
        stockout_date=None,
        first_shortage_date=None,
        minimum_stock=445.89,
        ending_stock=445.89,
        expiring_quantity=0.0,
        first_expiry_date=None,
        discarded_by_date={},
        shortage_expected=False,
    ),
    # 여기서부터 유효기간이 창에 들어온다. 폐기가 9/5 로 귀속되고, 같은 날
    # 처음 안전재고 미만이 된다.
    5: dict(
        stockout_date=None,
        first_shortage_date=date(2026, 9, 5),
        minimum_stock=66.33,
        ending_stock=66.33,
        expiring_quantity=341.89,
        first_expiry_date=date(2026, 9, 5),
        discarded_by_date={date(2026, 9, 5): 341.89},
        shortage_expected=True,
    ),
    6: dict(
        stockout_date=None,
        first_shortage_date=date(2026, 9, 5),
        minimum_stock=28.66,
        ending_stock=28.66,
        expiring_quantity=341.89,
        first_expiry_date=date(2026, 9, 5),
        discarded_by_date={date(2026, 9, 5): 341.89},
        shortage_expected=True,
    ),
    # 소진은 폐기보다 이틀 뒤다. 폐기를 소진일로 몰아 세면 여기가 어긋난다.
    7: dict(
        stockout_date=date(2026, 9, 7),
        first_shortage_date=date(2026, 9, 5),
        minimum_stock=-9.01,
        ending_stock=-9.01,
        expiring_quantity=341.89,
        first_expiry_date=date(2026, 9, 5),
        discarded_by_date={date(2026, 9, 5): 341.89},
        shortage_expected=True,
    ),
    8: dict(
        stockout_date=date(2026, 9, 7),
        first_shortage_date=date(2026, 9, 5),
        minimum_stock=-46.69,
        ending_stock=-46.69,
        expiring_quantity=341.89,
        first_expiry_date=date(2026, 9, 5),
        discarded_by_date={date(2026, 9, 5): 341.89},
        shortage_expected=True,
    ),
    9: dict(
        stockout_date=date(2026, 9, 7),
        first_shortage_date=date(2026, 9, 5),
        minimum_stock=-84.36,
        ending_stock=-84.36,
        expiring_quantity=341.89,
        first_expiry_date=date(2026, 9, 5),
        discarded_by_date={date(2026, 9, 5): 341.89},
        shortage_expected=True,
    ),
    10: dict(
        stockout_date=date(2026, 9, 7),
        first_shortage_date=date(2026, 9, 5),
        minimum_stock=-122.03,
        ending_stock=-122.03,
        expiring_quantity=341.89,
        first_expiry_date=date(2026, 9, 5),
        discarded_by_date={date(2026, 9, 5): 341.89},
        shortage_expected=True,
    ),
    11: dict(
        stockout_date=date(2026, 9, 7),
        first_shortage_date=date(2026, 9, 5),
        minimum_stock=-159.7,
        ending_stock=-159.7,
        expiring_quantity=341.89,
        first_expiry_date=date(2026, 9, 5),
        discarded_by_date={date(2026, 9, 5): 341.89},
        shortage_expected=True,
    ),
    12: dict(
        stockout_date=date(2026, 9, 7),
        first_shortage_date=date(2026, 9, 5),
        minimum_stock=-197.37,
        ending_stock=-197.37,
        expiring_quantity=341.89,
        first_expiry_date=date(2026, 9, 5),
        discarded_by_date={date(2026, 9, 5): 341.89},
        shortage_expected=True,
    ),
    13: dict(
        stockout_date=date(2026, 9, 7),
        first_shortage_date=date(2026, 9, 5),
        minimum_stock=-235.04,
        ending_stock=-235.04,
        expiring_quantity=341.89,
        first_expiry_date=date(2026, 9, 5),
        discarded_by_date={date(2026, 9, 5): 341.89},
        shortage_expected=True,
    ),
    # 마지막 날 예정 입고 275 가 도착해 이월 적자를 갚는다. 최소재고는 그대로
    # 남고 기말재고만 양수로 돌아선다 — 둘이 갈리는 유일한 칸이다.
    14: dict(
        stockout_date=date(2026, 9, 7),
        first_shortage_date=date(2026, 9, 5),
        minimum_stock=-235.04,
        ending_stock=2.29,
        expiring_quantity=341.89,
        first_expiry_date=date(2026, 9, 5),
        discarded_by_date={date(2026, 9, 5): 341.89},
        shortage_expected=True,
    ),
}


def test_the_material_risk_expansion_of_a_seeded_material_is_fixed(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    # 시드가 만든 실제 자재 하나를 1일부터 14일까지 전 구간으로 돌려, 어느
    # 날 무엇이 일어나는지를 통째로 고정한다. 값 하나만 보면 중간 판단이
    # 그대로 통과하기 때문이다.
    with seeded_session_factory() as session:
        material = _load_material(session, GOLDEN_MATERIAL_CODE)
        lots, safety_stock, daily_demands = _material_risk_inputs(session, material)

        expansion = {
            horizon_days: _expansion_row(
                calculate_material_risk(
                    lots=lots,
                    safety_stock=safety_stock,
                    daily_demands=daily_demands,
                    reference_date=REFERENCE_DATE,
                    horizon_days=horizon_days,
                )
            )
            for horizon_days in range(1, HORIZON_DAYS + 1)
        }

    assert expansion == MATERIAL_GOLDEN_EXPANSION


def test_the_material_response_agrees_with_the_golden_expansion(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    # 위 검사는 엔진에 직접 입력을 넣는다. 그 입력을 만드는 조립 경로가
    # 어긋나면 엔진이 맞아도 화면이 틀리므로, 실제 응답이 같은 값을 내는지
    # 한 번 더 본다.
    with seeded_session_factory() as session:
        material = _load_material(session, GOLDEN_MATERIAL_CODE)
        response = _build_material_response(
            material,
            REFERENCE_DATE,
            _planned_quantities_by_product_day(session, REFERENCE_DATE),
        )

    golden = MATERIAL_GOLDEN_EXPANSION[HORIZON_DAYS]
    assert response.stockout_date == golden["stockout_date"]
    assert response.minimum_stock == golden["minimum_stock"]
    assert response.ending_stock == golden["ending_stock"]
    assert response.expiring_quantity == golden["expiring_quantity"]
    assert response.first_expiry_date == golden["first_expiry_date"]
    assert response.shortage_expected == golden["shortage_expected"]


# 시드의 생산오더 30건 전부. `(심각도, 완료예정일, 잔여수량)` 이다.
#
# 납기가 기준일 +1 인 오더(002·005·008 …)가 `WARNING_BUFFER_DAYS` 경계를 실제로
# 밟는다 — 완료예정일이 납기와 같아 「위험」은 아니지만 완충 기간 안이라
# 「주의」다. 경계를 하루라도 밀면 이 열 건이 「정상」으로 떨어진다.
ORDER_GOLDEN: dict[str, tuple[str, date | None, float]] = {
    "MO-20260901-001": ("위험", date(2026, 9, 10), 64.0),
    "MO-20260901-002": ("주의", date(2026, 9, 2), 12.0),
    "MO-20260901-003": ("정상", date(2026, 9, 3), 20.0),
    "MO-20260901-004": ("위험", date(2026, 9, 11), 72.0),
    "MO-20260901-005": ("주의", date(2026, 9, 2), 9.0),
    "MO-20260901-006": ("정상", date(2026, 9, 3), 24.0),
    "MO-20260901-007": ("위험", date(2026, 9, 10), 108.0),
    "MO-20260901-008": ("주의", date(2026, 9, 2), 9.0),
    "MO-20260901-009": ("정상", date(2026, 9, 3), 30.0),
    "MO-20260901-010": ("위험", date(2026, 9, 10), 81.0),
    "MO-20260901-011": ("주의", date(2026, 9, 2), 14.0),
    "MO-20260901-012": ("정상", date(2026, 9, 3), 28.0),
    "MO-20260901-013": ("위험", date(2026, 9, 10), 117.0),
    "MO-20260901-014": ("주의", date(2026, 9, 2), 8.0),
    "MO-20260901-015": ("정상", date(2026, 9, 3), 24.0),
    "MO-20260901-016": ("위험", date(2026, 9, 11), 120.0),
    "MO-20260901-017": ("주의", date(2026, 9, 2), 13.0),
    "MO-20260901-018": ("정상", date(2026, 9, 3), 16.0),
    "MO-20260901-019": ("위험", date(2026, 9, 9), 80.0),
    "MO-20260901-020": ("주의", date(2026, 9, 2), 10.0),
    "MO-20260901-021": ("정상", date(2026, 9, 3), 30.0),
    "MO-20260901-022": ("위험", date(2026, 9, 10), 108.0),
    "MO-20260901-023": ("주의", date(2026, 9, 2), 8.0),
    "MO-20260901-024": ("정상", date(2026, 9, 3), 20.0),
    "MO-20260901-025": ("위험", date(2026, 9, 11), 99.0),
    "MO-20260901-026": ("주의", date(2026, 9, 2), 8.0),
    "MO-20260901-027": ("정상", date(2026, 9, 3), 24.0),
    "MO-20260901-028": ("위험", date(2026, 9, 11), 150.0),
    "MO-20260901-029": ("주의", date(2026, 9, 2), 11.0),
    "MO-20260901-030": ("정상", date(2026, 9, 3), 26.0),
}


def test_the_order_risk_of_every_seeded_order_is_fixed(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    with seeded_session_factory() as session:
        orders = session.scalars(
            select(Order)
            .options(selectinload(Order.daily_productions))
            .order_by(Order.order_number)
        ).all()

        actual: dict[str, tuple[str, date | None, float]] = {}
        boundary_orders: set[str] = set()
        for order in orders:
            completed = sum(
                production.actual_quantity
                for production in order.daily_productions
                if production.work_date <= REFERENCE_DATE
            )
            recent_start = REFERENCE_DATE - timedelta(days=6)
            average_daily_output = (
                sum(
                    production.actual_quantity
                    for production in order.daily_productions
                    if recent_start <= production.work_date <= REFERENCE_DATE
                )
                / 7
            )
            result = calculate_order_risk(
                planned_quantity=order.planned_quantity,
                actual_quantity=completed,
                average_daily_output=average_daily_output,
                due_date=order.due_date,
                reference_date=REFERENCE_DATE,
            )
            actual[order.order_number] = (
                result.severity,
                result.estimated_completion_date,
                round(result.remaining_quantity, 2),
            )
            if (order.due_date - REFERENCE_DATE).days == WARNING_BUFFER_DAYS:
                boundary_orders.add(order.order_number)

    assert actual == ORDER_GOLDEN
    # 완충 기간 경계를 실제로 밟는 오더가 시드에 남아 있어야 위 표가 그 경계를
    # 지킨다. 시드가 바뀌어 경계 오더가 사라지면 여기서 먼저 드러난다.
    assert boundary_orders, "납기가 기준일 +WARNING_BUFFER_DAYS 인 오더가 없습니다."
    assert all(actual[number][0] == "주의" for number in boundary_orders)


# 시드의 완제품 로트 150건을 상태별로 센 값. `(로트 수, 수량 합)` 이다.
#
# 「만료」7건이 이 표의 핵심이다. 그 일곱은 **합격 판정을 받고 제품창고에
# 들어와 있는** 로트라, 만료를 먼저 보지 않으면 그대로 「출하 가능」으로
# 넘어가 화면이 출하할 수 없는 791.0 을 출하 가능이라고 말한다.
#
# 「입고 대기」가 0 인 것도 사실로 고정한다 — 합격했으나 아직 제품창고로
# 옮겨지지 않은 로트는 재고이동이 서는 단계부터 생긴다(`briefing` 주석). 여기에
# 수량이 생기면 판정 순서가 흔들렸다는 뜻이다.
FINISHED_GOODS_STATE_GOLDEN: dict[str, tuple[int, float]] = {
    "만료": (7, 791.0),
    "검사 대기": (10, 666.0),
    "불합격": (8, 837.15),
    "출하 가능": (125, 12534.85),
    "입고 대기": (0, 0.0),
}


def test_the_finished_goods_lot_states_of_the_seed_are_fixed(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    with seeded_session_factory() as session:
        lots = session.scalars(select(FinishedGoodsLot)).all()

        aggregated: dict[str, tuple[int, float]] = {
            state: (0, 0.0) for state in FINISHED_GOODS_STATE_GOLDEN
        }
        expired_but_releasable_on_paper = 0
        for lot in lots:
            state = _finished_goods_lot_state(lot, REFERENCE_DATE)
            count, quantity = aggregated.get(state, (0, 0.0))
            aggregated[state] = (count + 1, quantity + lot.quantity)
            # 만료 판정을 빼면 「출하 가능」으로 흘러갈 로트.
            if (
                state == "만료"
                and lot.qc_status == QC_PASSED
                and lot.warehouse == PRODUCT_WAREHOUSE
            ):
                expired_but_releasable_on_paper += 1

        rounded = {
            state: (count, round(quantity, 2))
            for state, (count, quantity) in aggregated.items()
        }

    assert rounded == FINISHED_GOODS_STATE_GOLDEN
    assert len(lots) == sum(count for count, _ in FINISHED_GOODS_STATE_GOLDEN.values())
    # 판정 순서가 이 시드에서 실제로 일을 하는지 — 만료 판정을 지우면 「출하
    # 가능」이 늘어날 로트가 있어야 위 표가 순서를 지킨다.
    assert expired_but_releasable_on_paper > 0
