from __future__ import annotations

import random
from datetime import date, timedelta

from app.db import base as db_base
from app.db.models import (
    BomRequirement,
    DailyProduction,
    Material,
    Order,
    Product,
    PurchaseReceipt,
)
from app.services.order_risk import calculate_order_risk


FIXED_SEED = 20_260_831


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
            current_stock=float(rng.randrange(700, 1_401)),
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

        for material in materials:
            session.add(
                PurchaseReceipt(
                    material=material,
                    scheduled_date=effective_reference_date + timedelta(days=rng.randrange(14)),
                    scheduled_quantity=float(rng.randrange(180, 521)),
                )
            )

        for order_index in range(30):
            risk_pattern = order_index % 3
            historical_output = [float(rng.randrange(14, 23)) for _ in range(23)]
            recent_daily_output = float(rng.randrange(8, 16))
            historical_output.extend([recent_daily_output] * 7)
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
                session.add(
                    DailyProduction(
                        order=order,
                        work_date=effective_reference_date + timedelta(days=day_offset),
                        planned_quantity=actual_quantity,
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


if __name__ == "__main__":
    reset_database()
