from __future__ import annotations

import random
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select

from app.core.config import (
    FINISHED_GOODS_WAREHOUSE,
    INCOMING_INSPECTION,
    OUTGOING_INSPECTION,
    PROCESS_INSPECTION,
    PRODUCTION_WAREHOUSE,
    QC_FAILED,
    QC_PASSED,
    QC_PENDING,
    RAW_MATERIAL_WAREHOUSE,
)
from app.db import base as db_base
from app.db.models import (
    BomRequirement,
    DailyProduction,
    FinishedGoodsLot,
    Material,
    MaterialLot,
    Order,
    Product,
    PurchaseReceipt,
    QualityInspection,
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

# 품목별 유효기간 설정기간(일). 사내 프로세스가 정하는 값이라는 설정이므로
# 품목에 고정으로 붙이고, 로트의 유효기간은 여기서 파생한다. rng 를 쓰지 않는
# 이유는 난수 시퀀스를 흔들면 납기 정상·주의·위험 시나리오가 통째로 바뀌기
# 때문이다(PLAN_VARIANCE_CYCLE 과 같은 이유).
#
# `None` 은 무기한 품목이다. FEFO 는 유효기간 없는 로트를 가장 마지막에 쓰므로,
# 무기한 품목이 하나도 없으면 그 규칙이 데모에서 한 번도 발동하지 않는다.
#
# FG-02 만 21일로 짧다. 과거 30일치 생산분 중 앞쪽이 실제로 만료돼, 만료 로트가
# 출하 가능 재고에서 빠지고 목록에는 남는다는 규칙이 화면에 드러난다. 나머지가
# 모두 180일 이상이면 이 상태가 데모에서 한 번도 나오지 않는다.
PRODUCT_SHELF_LIFE_DAYS: tuple[int | None, ...] = (180, 21, None, 240, 300)

# RM-05(인덱스 4)만 44일로 짧다. 40일 전에 입고된 로트가 기준일+4일에 만료돼
# 유효기간 폐기로 부족해지는 시나리오를 만든다. 나머지는 입고일이 최대 59일
# 전이므로 150일 이상이어야 멀쩡한 로트가 만료로 뒤집히지 않는다.
MATERIAL_SHELF_LIFE_DAYS: tuple[int | None, ...] = (
    240, 300, 180, None, 44, 200, 365, 150, None, 280, 320, 190, 260, 210, 400,
)

# 생산 당일과 그 전날 생산분은 아직 OQC 를 받지 않은 것으로 둔다.
OQC_PENDING_DAYS = 1
# 검사를 마쳤지만 아직 완제품창고로 옮기지 않은 상태(이관 대기)를 만드는 날.
# 합격이 곧 이동은 아니므로 이 상태가 실제로 존재하며, 화면의 다섯 수량이
# 서로 겹치지 않는지도 이 로트들이 검증해 준다.
OQC_TRANSFER_DAYS = 2
# 검사 표본과 불합격을 고르는 고정 주기. 위와 같은 이유로 rng 를 쓰지 않는다.
OQC_FAIL_CYCLE = 17
PQC_SAMPLE_CYCLE = 7
PQC_FAIL_CYCLE = 17

# 불합격 사유는 가상의 일반적인 문구다(합성 데이터 원칙).
OQC_FAIL_REASONS = ("표면 광택 편차", "두께 규격 이탈", "외관 이물 검출")
PQC_FAIL_REASONS = ("공정 온도 이탈", "혼합 점도 편차", "라인 속도 불안정")


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
        Product(
            code=f"FG-{index:02d}",
            name=name,
            shelf_life_days=PRODUCT_SHELF_LIFE_DAYS[index - 1],
        )
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
            shelf_life_days=MATERIAL_SHELF_LIFE_DAYS[index - 1],
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
                    # 도착분도 로트가 되므로 유효기간을 갖는다. 도착일에 자재의
                    # 설정기간을 더해 파생하며, 무기한 자재면 유효기간이 없다.
                    expiry_date=_expiry_date(material.shelf_life_days, scheduled_date),
                )
            )

        _seed_material_lots(session, materials, target_stocks, effective_reference_date, rng)

        # PQC 는 (오더 × 실적일) 을 고정 주기로 표본검사한다. 전수 검사로 두면
        # 900건이 넘어 화면에서 읽을 수 없고, 공정검사는 원래 표본검사다.
        pqc_sample_index = 0

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
                work_date = effective_reference_date + timedelta(days=day_offset)
                production = DailyProduction(
                    order=order,
                    work_date=work_date,
                    planned_quantity=round(actual_quantity * variance, 2),
                    actual_quantity=actual_quantity,
                )
                session.add(production)

                if (order_index + day_offset) % PQC_SAMPLE_CYCLE == 0:
                    failed = pqc_sample_index % PQC_FAIL_CYCLE == 0
                    session.add(
                        QualityInspection(
                            inspection_type=PROCESS_INSPECTION,
                            inspected_date=work_date,
                            result=QC_FAILED if failed else QC_PASSED,
                            reason=(
                                PQC_FAIL_REASONS[
                                    pqc_sample_index % len(PQC_FAIL_REASONS)
                                ]
                                if failed
                                else None
                            ),
                            daily_production=production,
                        )
                    )
                    pqc_sample_index += 1
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

        _seed_finished_goods_lots(session, products, effective_reference_date)
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

        finished_goods_lots = session.query(FinishedGoodsLot).all()
        if not finished_goods_lots:
            raise RuntimeError("합성 데이터가 완제품 로트를 만들지 못했습니다.")
        if {lot.qc_status for lot in finished_goods_lots} != {
            QC_PENDING,
            QC_PASSED,
            QC_FAILED,
        }:
            raise RuntimeError("합성 데이터가 OQC 세 상태를 모두 만들지 못했습니다.")
        if not any(
            lot.qc_status == QC_PASSED and lot.warehouse == PRODUCTION_WAREHOUSE
            for lot in finished_goods_lots
        ):
            raise RuntimeError("합성 데이터가 이관 대기 완제품 로트를 만들지 못했습니다.")
        if not any(
            lot.expiry_date is not None and lot.expiry_date <= effective_reference_date
            for lot in finished_goods_lots
        ):
            raise RuntimeError("합성 데이터가 만료된 완제품 로트를 만들지 못했습니다.")
        if not any(lot.expiry_date is None for lot in finished_goods_lots):
            raise RuntimeError("합성 데이터가 무기한 완제품 로트를 만들지 못했습니다.")

        inspection_types = {
            inspection.inspection_type
            for inspection in session.query(QualityInspection).all()
        }
        if inspection_types != {INCOMING_INSPECTION, PROCESS_INSPECTION, OUTGOING_INSPECTION}:
            raise RuntimeError("합성 데이터가 IQC·PQC·OQC 기록을 모두 만들지 못했습니다.")

        warehouses_by_lot_number: defaultdict[str, set[str]] = defaultdict(set)
        for lot in session.query(MaterialLot).all():
            warehouses_by_lot_number[lot.lot_number].add(lot.warehouse)
        if not any(
            len(warehouses) > 1 for warehouses in warehouses_by_lot_number.values()
        ):
            raise RuntimeError("합성 데이터가 두 창고에 나뉜 로트를 만들지 못했습니다.")


def _expiry_date(shelf_life_days: int | None, start_date: date) -> date | None:
    """설정기간에서 유효기간을 파생한다.

    파생값을 그때그때 계산하지 않고 로트에 **저장**하는 이유는, 로트 라벨에
    찍혀 나간 값이 진실이기 때문이다. 사내 설정기간을 나중에 바꿔도 이미
    부여된 로트의 만료일은 바뀌지 않아야 한다.
    """
    if shelf_life_days is None:
        return None
    return start_date + timedelta(days=shelf_life_days)


def _seed_finished_goods_lots(
    session,
    products: list[Product],
    reference_date: date,
) -> None:
    """생산 실적에서 완제품 로트와 OQC 기록을 파생한다.

    로트 단위는 (제품, 생산일)이다. 같은 날 같은 제품을 만든 오더가 여럿이면
    한 로트로 합친다 — 소재 제조에서 같은 날 산출을 한 로트로 보는 게
    자연스럽고, 오더별로 쪼개면 로트 수만 불어난다.

    갓 생산된 로트는 생산창고에서 OQC 를 기다리고, 합격분만 완제품창고로
    옮긴다. 불합격분은 생산창고에 남아 출하 가능 재고에서 빠진다. 과거 생산분을
    빼지 않는 것은 로트가 영구 기록이기 때문이며, 그래서 출하가 없는 지금은
    완제품 재고가 줄지 않고 쌓이기만 한다(후속: 출하 리스크).
    """
    products_by_id = {product.id: product for product in products}
    rows = session.execute(
        select(
            Order.product_id,
            DailyProduction.work_date,
            func.sum(DailyProduction.actual_quantity),
        )
        .join(Order, DailyProduction.order_id == Order.id)
        .where(
            DailyProduction.work_date <= reference_date,
            DailyProduction.actual_quantity > 0,
        )
        .group_by(Order.product_id, DailyProduction.work_date)
        .order_by(Order.product_id, DailyProduction.work_date)
    ).all()

    for index, (product_id, work_date, quantity) in enumerate(rows):
        product = products_by_id[product_id]
        days_since_production = (reference_date - work_date).days
        if days_since_production <= OQC_PENDING_DAYS:
            qc_status = QC_PENDING
        elif index % OQC_FAIL_CYCLE == 0:
            qc_status = QC_FAILED
        else:
            qc_status = QC_PASSED
        transferred = (
            qc_status == QC_PASSED and days_since_production > OQC_TRANSFER_DAYS
        )

        lot = FinishedGoodsLot(
            product=product,
            lot_number=f"LOT-{product.code}-{work_date:%y%m%d}",
            warehouse=(
                FINISHED_GOODS_WAREHOUSE if transferred else PRODUCTION_WAREHOUSE
            ),
            qc_status=qc_status,
            quantity=round(float(quantity), 2),
            produced_date=work_date,
            expiry_date=_expiry_date(product.shelf_life_days, work_date),
        )
        session.add(lot)

        if qc_status == QC_PENDING:
            # 검사 대기는 판정이 아니라 기록이 없는 상태다.
            continue
        session.add(
            QualityInspection(
                inspection_type=OUTGOING_INSPECTION,
                inspected_date=work_date + timedelta(days=1),
                result=qc_status,
                reason=(
                    None
                    if qc_status == QC_PASSED
                    else OQC_FAIL_REASONS[index % len(OQC_FAIL_REASONS)]
                ),
                finished_goods_lot=lot,
            )
        )


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
    for index, (material, target_stock) in enumerate(
        zip(materials, target_stocks, strict=True)
    ):
        if index == EXPIRY_SHORTAGE_MATERIAL_INDEX:
            entries = _expiring_lot_plan(material, target_stock, reference_date)
        else:
            entries = _regular_lot_plan(target_stock, reference_date, rng)
        if index == SPLIT_WAREHOUSE_MATERIAL_INDEX:
            entries = _split_first_lot_across_warehouses(entries)

        for entry in entries:
            lot = MaterialLot(
                material=material,
                lot_number=f"LOT-{material.code}-{entry['lot_sequence']:02d}",
                warehouse=entry["warehouse"],
                quantity=entry["quantity"],
                received_date=entry["received_date"],
                # 유효기간은 입고일 + 자재의 설정기간이다(기준정보에서 파생).
                expiry_date=_expiry_date(
                    material.shelf_life_days, entry["received_date"]
                ),
            )
            session.add(lot)
            # IQC — 창고에 들어와 있는 자재는 수입검사를 통과했다는 뜻이므로
            # 보유 로트에는 합격 기록만 붙는다. 불합격분의 반품·격리는 자재
            # 가용 재고와 14일 판정을 바꾸는 일이라 이 범위 밖이다.
            session.add(
                QualityInspection(
                    inspection_type=INCOMING_INSPECTION,
                    inspected_date=entry["received_date"],
                    result=QC_PASSED,
                    reason=None,
                    material_lot=lot,
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
            }
        )
    return entries


def _expiring_lot_plan(
    material: Material,
    target_stock: float,
    reference_date: date,
) -> list[dict]:
    """대부분이 곧 만료되고 남는 잔량은 안전재고에 못 미치게 구성한다.

    유효기간을 직접 박지 않고 **입고일로** 만든다. 설정기간이 44일인 자재를
    40일 전에 받았으므로 기준일+4일에 만료되고, 10일 전에 받은 잔량 로트는
    기준일+34일이라 14일 전망 밖이다.
    """
    remainder = round(material.safety_stock * 0.4, 2)
    return [
        {
            "lot_sequence": 1,
            "warehouse": RAW_MATERIAL_WAREHOUSE,
            "quantity": round(target_stock - remainder, 2),
            "received_date": reference_date - timedelta(days=40),
        },
        {
            "lot_sequence": 2,
            "warehouse": PRODUCTION_WAREHOUSE,
            "quantity": remainder,
            "received_date": reference_date - timedelta(days=10),
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
