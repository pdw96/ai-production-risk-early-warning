from __future__ import annotations

import random
from collections import defaultdict
from datetime import date, timedelta

from app.core.config import PRODUCTION_WAREHOUSE, RAW_MATERIAL_WAREHOUSE
from app.db import base as db_base
from app.db.models import (
    BomRequirement,
    DailyProduction,
    Material,
    MaterialLot,
    Order,
    Product,
    PurchaseReceipt,
)
from app.services.briefing import list_materials
from app.services.order_risk import calculate_order_risk


FIXED_SEED = 20_260_831

# 유효기간 폐기로 14일 내 부족해지는 자재(RM-05)와, 한 로트가 두 창고에 나뉘어
# 있는 자재(RM-03)를 고정한다. 데모가 이 두 시나리오를 항상 보여줘야 한다.
EXPIRY_SHORTAGE_MATERIAL_INDEX = 4
SPLIT_WAREHOUSE_MATERIAL_INDEX = 2

# 과거 실적일의 계획 대비 편차. 계획과 실적을 같은 값으로 두면 달성률이 늘
# 100%가 되어 생산실적 화면과 추이 그래프가 아무것도 말해주지 않는다.
# rng 를 쓰지 않고 고정 주기로 만들어 기존 난수 시퀀스를 흔들지 않는다.
PLAN_VARIANCE_CYCLE = (1.06, 0.93, 1.11, 0.9, 1.04, 0.97, 1.0)

# 최근 7일 실적의 날짜별 편차. 계획과 다른 모양이어야 두 선이 겹쳐 보이지 않는다.
# 합이 정확히 7.0이라 7일 평균이 바뀌지 않는다. 납기 판정이 그 평균으로
# 완료예정일을 내므로, 합이 흔들리면 정상·주의·위험 시나리오가 무너진다.
RECENT_OUTPUT_VARIANCE_CYCLE = (1.08, 0.94, 1.05, 0.9, 1.03, 1.0, 1.0)


def initialize_sample_database(reference_date: date | None = None) -> None:
    """실행일(또는 지정 기준일)에 맞춘 합성 샘플 DB를 초기화한다."""
    reset_database(reference_date)


def reset_database(reference_date: date | None = None) -> None:
    """기준일에 상대적인 가상 소재 공장 데이터를 SQLite에 다시 생성한다."""
    effective_reference_date = reference_date or date.today()
    seed_value = FIXED_SEED + int(effective_reference_date.strftime("%Y%m%d"))
    rng = random.Random(seed_value)

    db_base.Base.metadata.drop_all(bind=db_base.engine)
    db_base.create_all()

    products = [
        Product(code=f"FG-{index:02d}", name=name)
        for index, name in enumerate(
            ("아크솔 시트", "노바필름", "루멘코트", "벨로스랩", "테라패널"),
            start=1,
        )
    ]
    materials = [
        Material(
            code=f"RM-{index:02d}",
            name=name,
            safety_stock=float(rng.randrange(180, 361)),
        )
        for index, name in enumerate(
            (
                "폴리머 베이스",
                "세라믹 분말",
                "광학 안료",
                "보강 섬유",
                "접착 수지",
                "방열 첨가제",
                "차단 필름",
                "표면 코팅제",
                "미세 충전재",
                "유연 가소제",
                "보호 라이너",
                "안정화 첨가제",
                "전도성 페이스트",
                "기능성 염료",
                "포장 라미네이트",
            ),
            start=1,
        )
    ]
    # 로트 합계가 곧 가용 재고다(Material 에는 재고 컬럼이 없다).
    target_stocks = [float(rng.randrange(700, 1_401)) for _ in materials]
    # RM-01 은 안전재고를 겨우 넘긴 상태로 고정해 부족 시나리오를 보장한다.
    target_stocks[0] = materials[0].safety_stock + 1.0

    with db_base.SessionLocal() as session:
        session.add_all(products + materials)
        session.flush()

        for product_index, product in enumerate(products):
            for material in materials[product_index * 3 : product_index * 3 + 3]:
                session.add(
                    BomRequirement(
                        product=product,
                        material=material,
                        unit_quantity=round(rng.uniform(0.8, 2.4), 2),
                    )
                )

        for material_index, material in enumerate(materials):
            scheduled_offset = rng.randrange(14)
            if material_index in (0, EXPIRY_SHORTAGE_MATERIAL_INDEX):
                # 예정 입고가 일찍 도착하면 부족 시나리오가 지워지므로 뒤로 민다.
                scheduled_offset = 13
            scheduled_date = effective_reference_date + timedelta(days=scheduled_offset)
            session.add(
                PurchaseReceipt(
                    material=material,
                    scheduled_date=scheduled_date,
                    scheduled_quantity=float(rng.randrange(180, 521)),
                    # 도착분도 로트가 되므로 유효기간을 갖는다.
                    expiry_date=scheduled_date + timedelta(days=rng.randrange(60, 121)),
                )
            )

        _seed_material_lots(session, materials, target_stocks, effective_reference_date, rng)

        for order_index in range(30):
            risk_pattern = order_index % 3
            historical_output = [float(rng.randrange(14, 23)) for _ in range(23)]
            recent_daily_output = float(rng.randrange(8, 16))
            historical_output.extend(_recent_output_series(recent_daily_output))
            completed_quantity = sum(historical_output)

            if risk_pattern == 0:
                remaining_quantity = recent_daily_output * float(rng.randrange(8, 11))
                due_date = effective_reference_date + timedelta(days=5)
            elif risk_pattern == 1:
                remaining_quantity = recent_daily_output
                due_date = effective_reference_date + timedelta(days=1)
            else:
                remaining_quantity = recent_daily_output * 2
                due_date = effective_reference_date + timedelta(days=rng.randrange(5, 10))

            order = Order(
                order_number=f"MO-{effective_reference_date:%Y%m%d}-{order_index + 1:03d}",
                product=products[order_index % len(products)],
                due_date=due_date,
                planned_quantity=completed_quantity + remaining_quantity,
            )
            session.add(order)

            for day_offset, actual_quantity in enumerate(historical_output, start=-29):
                variance = PLAN_VARIANCE_CYCLE[day_offset % len(PLAN_VARIANCE_CYCLE)]
                session.add(
                    DailyProduction(
                        order=order,
                        work_date=effective_reference_date + timedelta(days=day_offset),
                        planned_quantity=round(actual_quantity * variance, 2),
                        actual_quantity=actual_quantity,
                    )
                )
            for day_offset in range(1, 15):
                session.add(
                    DailyProduction(
                        order=order,
                        work_date=effective_reference_date + timedelta(days=day_offset),
                        planned_quantity=remaining_quantity / 14,
                        actual_quantity=0.0,
                    )
                )

        session.commit()

        severities = set()
        for order in session.query(Order).all():
            completed_quantity = sum(
                production.actual_quantity
                for production in order.daily_productions
                if production.work_date <= effective_reference_date
            )
            recent_output = sum(
                production.actual_quantity
                for production in order.daily_productions
                if effective_reference_date - timedelta(days=6)
                <= production.work_date
                <= effective_reference_date
            ) / 7
            severities.add(
                calculate_order_risk(
                    planned_quantity=order.planned_quantity,
                    actual_quantity=completed_quantity,
                    average_daily_output=recent_output,
                    due_date=order.due_date,
                    reference_date=effective_reference_date,
                ).severity
            )

        if severities != {"정상", "주의", "위험"}:
            raise RuntimeError("합성 데이터가 정상·주의·위험 납기 상태를 모두 만들지 못했습니다.")

        if not any(
            material.expiring_quantity > 0 and material.shortage_expected
            for material in list_materials(session)
        ):
            raise RuntimeError("합성 데이터가 유효기간 폐기로 부족해지는 자재를 만들지 못했습니다.")

        warehouses_by_lot_number: defaultdict[str, set[str]] = defaultdict(set)
        for lot in session.query(MaterialLot).all():
            warehouses_by_lot_number[lot.lot_number].add(lot.warehouse)
        if not any(
            len(warehouses) > 1 for warehouses in warehouses_by_lot_number.values()
        ):
            raise RuntimeError("합성 데이터가 두 창고에 나뉜 로트를 만들지 못했습니다.")


def _recent_output_series(daily_output: float) -> list[float]:
    """최근 7일 실적을 날짜별로 흩뜨리되 합계는 그대로 둔다.

    반올림 잔차는 마지막 날에 몰아 합을 정확히 맞춘다. 잔차를 그냥 두면
    7일 평균이 미세하게 달라져 경계선에 있는 오더의 납기 판정이 뒤집힐 수 있다.
    """
    total = daily_output * len(RECENT_OUTPUT_VARIANCE_CYCLE)
    series = [
        round(daily_output * factor, 2)
        for factor in RECENT_OUTPUT_VARIANCE_CYCLE[:-1]
    ]
    series.append(round(total - sum(series), 2))
    return series


def _seed_material_lots(
    session,
    materials: list[Material],
    target_stocks: list[float],
    reference_date: date,
    rng: random.Random,
) -> None:
    """자재별 보유 로트를 합성한다. 로트 합계가 곧 그 자재의 가용 재고가 된다."""
    for index, (material, target_stock) in enumerate(zip(materials, target_stocks)):
        if index == EXPIRY_SHORTAGE_MATERIAL_INDEX:
            entries = _expiring_lot_plan(material, target_stock, reference_date)
        else:
            entries = _regular_lot_plan(target_stock, reference_date, rng)
        if index == SPLIT_WAREHOUSE_MATERIAL_INDEX:
            entries = _split_first_lot_across_warehouses(entries)

        for entry in entries:
            session.add(
                MaterialLot(
                    material=material,
                    lot_number=f"LOT-{material.code}-{entry['lot_sequence']:02d}",
                    warehouse=entry["warehouse"],
                    quantity=entry["quantity"],
                    received_date=entry["received_date"],
                    expiry_date=entry["expiry_date"],
                )
            )


def _regular_lot_plan(
    target_stock: float,
    reference_date: date,
    rng: random.Random,
) -> list[dict]:
    """목표 보유량을 2~4개 로트로 쪼갠다. 합계는 목표량과 정확히 일치한다."""
    weights = [rng.uniform(0.6, 1.4) for _ in range(rng.randrange(2, 5))]
    total_weight = sum(weights)
    entries: list[dict] = []
    allocated = 0.0
    for sequence, weight in enumerate(weights, start=1):
        is_last = sequence == len(weights)
        quantity = (
            round(target_stock - allocated, 2)
            if is_last
            else round(target_stock * weight / total_weight, 2)
        )
        allocated += quantity
        entries.append(
            {
                "lot_sequence": sequence,
                "warehouse": (
                    PRODUCTION_WAREHOUSE
                    if rng.random() < 0.35
                    else RAW_MATERIAL_WAREHOUSE
                ),
                "quantity": quantity,
                "received_date": reference_date - timedelta(days=rng.randrange(5, 60)),
                "expiry_date": reference_date + timedelta(days=rng.randrange(30, 181)),
            }
        )
    return entries


def _expiring_lot_plan(
    material: Material,
    target_stock: float,
    reference_date: date,
) -> list[dict]:
    """대부분이 곧 만료되고 남는 잔량은 안전재고에 못 미치게 구성한다."""
    remainder = round(material.safety_stock * 0.4, 2)
    return [
        {
            "lot_sequence": 1,
            "warehouse": RAW_MATERIAL_WAREHOUSE,
            "quantity": round(target_stock - remainder, 2),
            "received_date": reference_date - timedelta(days=40),
            "expiry_date": reference_date + timedelta(days=4),
        },
        {
            "lot_sequence": 2,
            "warehouse": PRODUCTION_WAREHOUSE,
            "quantity": remainder,
            "received_date": reference_date - timedelta(days=10),
            "expiry_date": reference_date + timedelta(days=150),
        },
    ]


def _split_first_lot_across_warehouses(entries: list[dict]) -> list[dict]:
    """첫 로트의 일부를 생산창고로 옮긴 상태를 만든다(같은 로트번호, 두 창고)."""
    first, *rest = entries
    moved_quantity = round(first["quantity"] * 0.4, 2)
    return [
        {
            **first,
            "warehouse": RAW_MATERIAL_WAREHOUSE,
            "quantity": round(first["quantity"] - moved_quantity, 2),
        },
        {**first, "warehouse": PRODUCTION_WAREHOUSE, "quantity": moved_quantity},
        *rest,
    ]


if __name__ == "__main__":
    initialize_sample_database()
