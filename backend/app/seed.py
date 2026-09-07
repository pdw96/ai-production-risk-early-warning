from __future__ import annotations

import random
import sys
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select, text

from app.core.config import (
    DEFECTIVE_STOCK,
    is_sqlite,
    FINISHED_ITEM,
    GOOD_STOCK,
    INCOMING_INSPECTION,
    LAMINATING_PROCESS,
    MASS_PRODUCTION_PHASE,
    OUTGOING_INSPECTION,
    PRODUCT_WAREHOUSE,
    PROCESS_INSPECTION,
    PRODUCTION_WAREHOUSE,
    QC_FAILED,
    QC_PASSED,
    QC_PENDING,
    RAW_ITEM,
    RAW_MATERIAL_WAREHOUSE,
    INCOMING_PROCESS,
)
from app.db import base as db_base
from app.db.master_data_loader import load_master_data
from app.db.models import (
    DailyProduction,
    FinishedGoodsLot,
    Item,
    MaterialLot,
    Order,
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

# 자재의 재고 단위(지적 ㉛). 시드 품목이 세 무리로 갈리고 무리마다 세는 방법이
# 다르다 — 분체 다섯은 달고(kg), 액상·수지 여섯은 되며(L), 시트·필름 넷은
# 넓이로 잰다(m²). 세라믹 분말을 EA 로 셀 수 없다는 것이 이 칸이 필요한 이유다.
# rng 를 쓰지 않는 이유는 위 주기 상수들과 같다 — 난수 시퀀스를 흔들면 납기
# 정상·주의·위험 시나리오가 통째로 바뀐다.
MATERIAL_STOCK_UOMS: tuple[str, ...] = (
    "L",    # 폴리머 베이스
    "kg",   # 세라믹 분말
    "kg",   # 광학 안료
    "m2",   # 보강 섬유
    "L",    # 접착 수지
    "kg",   # 방열 첨가제
    "m2",   # 차단 필름
    "L",    # 표면 코팅제
    "kg",   # 미세 충전재
    "L",    # 유연 가소제
    "m2",   # 보호 라이너
    "L",    # 안정화 첨가제
    "L",    # 전도성 페이스트
    "kg",   # 기능성 염료
    "m2",   # 포장 라미네이트
)

# 완제품의 리드타임 계수 둘(지적 ⑬). 리드타임은 품목의 값이 아니라 오더마다
# 다른 계산 결과이고, 품목이 갖는 것은 이 계수 둘뿐이다 —
# 소요 시간 = 준비시간 + 개당 시간 × 수량.
PRODUCT_SETUP_HOURS: tuple[float, ...] = (4.0, 3.5, 5.0, 4.5, 6.0)
PRODUCT_HOURS_PER_UNIT: tuple[float, ...] = (0.2, 0.15, 0.25, 0.18, 0.3)

# 생산 당일과 그 전날 생산분은 아직 OQC 를 받지 않은 것으로 둔다.
OQC_PENDING_DAYS = 1
# 생산 다음 날 검사한다. 합격일 = 생산일 + 이 값이고, 그 차이가 곧
# 「검사에 며칠 걸렸나」다(지적 ⑰).
OQC_LEAD_DAYS = 1
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
    """표를 지우고 다시 만든 뒤 시드를 넣는다 — 개발과 테스트의 길이다.

    컨테이너 기동은 이 길로 오지 않는다. 거기서는 마이그레이션이 표를 맞추고
    `seed_if_empty` 가 내용을 본다 — 표를 지우는 것과 채우는 것은 다른 일이며,
    운영에서 지우는 쪽이 도는 것은 사고다.
    """
    db_base.drop_all()
    db_base.create_all()

    with db_base.SessionLocal() as session:
        _populate(session, reference_date or date.today())
        session.commit()


def seed_if_empty(reference_date: date | None = None) -> bool:
    """비어 있을 때만 시드하고, 넣었는지를 돌려준다.

    시드 판단의 세 조건 중 **셋째**다. 첫째(마이그레이션)와 둘째(스위치)는
    기동 스크립트가 본다.

    「표가 있는가」는 아무것도 말해 주지 않는다 — 마이그레이션이 항상 만들어
    두기 때문이다. 물어야 할 것은 **내용의 유무**이고, 그 표식으로 품목 표를
    쓴다. 가장 먼저 채워지고 마지막까지 남는 표이기 때문이다. 생산실적이나
    출하실적 같은 거래 표는 비어 있는 것이 정상 상태라 판단 기준이 될 수 없다.

    전체가 트랜잭션 하나다. 중간에 실패하면 아무것도 들어가지 않은 상태로
    되돌아가고 다음 기동에서 다시 시도된다 — 「반쯤 채워짐」이라는 상태 자체가
    없어진다. 파일을 지우고 다시 시작하는 탈출구가 PostgreSQL 에는 없으므로,
    그 상태를 만들지 않는 것이 유일한 방어다.
    """
    with db_base.SessionLocal() as session:
        _lock_for_seeding(session)
        if session.scalar(select(func.count()).select_from(Item)):
            return False
        _populate(session, reference_date or date.today())
        session.commit()
        return True


def _lock_for_seeding(session) -> None:
    """시드 구간에 잠금을 하나 건다.

    컨테이너가 둘 이상 동시에 뜨면 둘 다 「비어 있다」를 보고 둘 다 시드한다.
    이것은 PostgreSQL 이라서 생기는 문제다 — 파일 하나였을 때는 없던 일이다.
    트랜잭션 잠금이라 커밋이나 롤백에서 저절로 풀린다.
    """
    if is_sqlite():
        # 파일 하나를 쓰는 동안 다른 쓰기는 어차피 줄을 선다.
        return
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": FIXED_SEED})


def _populate(session, effective_reference_date: date) -> None:
    """기준일에 상대적인 가상 소재 공장 데이터를 만든다.

    기준정보는 SQL 파일에서 오고 시나리오만 여기서 만든다. 경계는 한 줄이다 —
    「오늘」이 안 나오면 SQL, 나오면 파이썬이다.
    """
    seed_value = FIXED_SEED + int(effective_reference_date.strftime("%Y%m%d"))
    rng = random.Random(seed_value)

    load_master_data(session)
    session.flush()

    products = list(
        session.scalars(
            select(Item).where(Item.item_type == FINISHED_ITEM).order_by(Item.code)
        ).all()
    )
    materials = list(
        session.scalars(
            select(Item).where(Item.item_type == RAW_ITEM).order_by(Item.code)
        ).all()
    )
    if not products or not materials:
        raise RuntimeError("기준정보 SQL 이 품목을 만들지 못했습니다.")

    # 로트 합계가 곧 가용 재고다(품목에는 재고 컬럼이 없다).
    target_stocks = [float(rng.randrange(700, 1_401)) for _ in materials]
    # RM-01 은 안전재고를 겨우 넘긴 상태로 고정해 부족 시나리오를 보장한다.
    target_stocks[0] = materials[0].safety_stock + 1.0

    for material_index, material in enumerate(materials):
        scheduled_offset = rng.randrange(14)
        if material_index in (0, EXPIRY_SHORTAGE_MATERIAL_INDEX):
            # 예정 입고가 일찍 도착하면 부족 시나리오가 지워지므로 뒤로 민다.
            scheduled_offset = 13
        scheduled_date = effective_reference_date + timedelta(days=scheduled_offset)
        session.add(
            PurchaseReceipt(
                item=material,
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
            item=products[order_index % len(products)],
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

    # 전체가 트랜잭션 하나여야 하므로 중간에 커밋하지 않는다. flush 는 뒤
    # 단계가 방금 넣은 행을 조회로 볼 수 있게만 해 준다 — 「반쯤 채워짐」이라는
    # 상태가 아예 생기지 않는 것이 요점이다.
    session.flush()

    _seed_finished_goods_lots(session, products, effective_reference_date)
    session.flush()

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
        lot.expiry_date is not None and lot.expiry_date <= effective_reference_date
        for lot in finished_goods_lots
    ):
        raise RuntimeError("합성 데이터가 만료된 완제품 로트를 만들지 못했습니다.")
    if not any(
        lot.passed_date is not None and lot.expiry_date is None
        for lot in finished_goods_lots
    ):
        raise RuntimeError("합성 데이터가 무기한 완제품 로트를 만들지 못했습니다.")
    if not any(lot.stock_type == DEFECTIVE_STOCK for lot in finished_goods_lots):
        raise RuntimeError("합성 데이터가 불량품 재고를 만들지 못했습니다.")

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
    products: list[Item],
    reference_date: date,
) -> None:
    """생산 실적에서 완제품 로트와 OQC 기록을 파생한다.

    로트 단위는 (제품, 생산일)이다. 같은 날 같은 제품을 만든 오더가 여럿이면
    한 로트로 합친다 — 소재 제조에서 같은 날 산출을 한 로트로 보는 게
    자연스럽고, 오더별로 쪼개면 로트 수만 불어난다.

    갓 생산된 로트는 생산창고에서 OQC 를 기다리고, 합격하면 제품창고로 옮겨진다.
    불합격분은 생산창고에 남아 출하 가능 재고에서 빠진다. 생산창고에 남는 완제품이
    검사 대기와 불합격뿐인 것은 그 규칙 때문이다.

    과거 생산분을 빼지 않는 것은 로트가 영구 기록이기 때문이며, 그래서 출하가
    없는 지금은 제품창고 재고가 줄지 않고 쌓이기만 한다(후속: 출하 리스크).
    """
    products_by_id = {product.id: product for product in products}
    rows = session.execute(
        select(
            Order.item_id,
            DailyProduction.work_date,
            func.sum(DailyProduction.actual_quantity),
        )
        .join(Order, DailyProduction.order_id == Order.id)
        .where(
            DailyProduction.work_date <= reference_date,
            DailyProduction.actual_quantity > 0,
        )
        .group_by(Order.item_id, DailyProduction.work_date)
        .order_by(Order.item_id, DailyProduction.work_date)
    ).all()

    for index, (product_id, work_date, quantity) in enumerate(rows):
        product = products_by_id[product_id]
        if (reference_date - work_date).days <= OQC_PENDING_DAYS:
            qc_status = QC_PENDING
        elif index % OQC_FAIL_CYCLE == 0:
            qc_status = QC_FAILED
        else:
            qc_status = QC_PASSED

        # 합격일이 유효기간의 기산점이다(지적 ⑰). 아직 판정을 받지 않았거나
        # 불합격한 로트는 합격일이 없고, 그래서 유효기간도 아직 시작하지 않는다.
        passed_date = (
            work_date + timedelta(days=OQC_LEAD_DAYS)
            if qc_status == QC_PASSED
            else None
        )
        lot = FinishedGoodsLot(
            item=product,
            lot_number=f"LOT-{product.code}-{work_date:%y%m%d}",
            # 창고는 검사 결과가 정한다. 합격이면 제품창고, 아니면 생산창고다.
            warehouse=(
                PRODUCT_WAREHOUSE if qc_status == QC_PASSED else PRODUCTION_WAREHOUSE
            ),
            qc_status=qc_status,
            # 재고구분은 판정에서 나온다. 양불이동으로 사람이 바꾸는 것은
            # 관문 8 이 들어오는 7단계의 일이다.
            stock_type=DEFECTIVE_STOCK if qc_status == QC_FAILED else GOOD_STOCK,
            # 재작업 흐름은 6단계에서 생긴다. 시드에는 재작업분이 없다.
            reworked=False,
            quantity=round(float(quantity), 2),
            produced_date=work_date,
            passed_date=passed_date,
            expiry_date=(
                None
                if passed_date is None
                else _expiry_date(product.shelf_life_days, passed_date)
            ),
        )
        session.add(lot)

        if qc_status == QC_PENDING:
            # 검사 대기는 판정이 아니라 기록이 없는 상태다.
            continue
        session.add(
            QualityInspection(
                inspection_type=OUTGOING_INSPECTION,
                inspected_date=work_date + timedelta(days=OQC_LEAD_DAYS),
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
    materials: list[Item],
    target_stocks: list[float],
    reference_date: date,
    rng: random.Random,
) -> None:
    """자재별 보유 로트를 합성한다. 로트 합계가 곧 그 자재의 가용 재고가 된다."""
    for index, (material, target_stock) in enumerate(
        zip(materials, target_stocks, strict=True)
    ):
        # 수입검사는 물리적 로트 단위로 한 번 한다. 한 로트가 두 창고에 나뉘어
        # 있어도(원재료창고 60 / 생산창고 40) 입고 시점에 한 번 검사한 것이므로
        # 행마다 기록을 남기면 같은 검사가 두 건으로 불어난다. 기준정보의 보유
        # 로트 수도 같은 이유로 로트번호로 센다.
        inspected_lot_numbers: set[str] = set()
        if index == EXPIRY_SHORTAGE_MATERIAL_INDEX:
            entries = _expiring_lot_plan(material, target_stock, reference_date)
        else:
            entries = _regular_lot_plan(target_stock, reference_date, rng)
        if index == SPLIT_WAREHOUSE_MATERIAL_INDEX:
            entries = _split_first_lot_across_warehouses(entries)

        for entry in entries:
            lot = MaterialLot(
                item=material,
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
            if lot.lot_number in inspected_lot_numbers:
                continue
            inspected_lot_numbers.add(lot.lot_number)
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
    material: Item,
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


def main(argv: list[str] | None = None) -> None:
    """두 길을 가른다 — 표를 지우고 다시 만드는 길과, 비었을 때만 채우는 길.

    기동 스크립트는 `--if-empty` 로 부른다. 인자 없이 부르면 표를 지우므로
    개발과 테스트에서만 쓴다.
    """
    arguments = sys.argv[1:] if argv is None else argv
    if "--if-empty" in arguments:
        if seed_if_empty():
            print("합성 샘플 데이터를 넣었습니다.")
        else:
            print("품목 표에 이미 내용이 있어 시드를 건너뜁니다.")
        return
    initialize_sample_database()
    print("표를 다시 만들고 합성 샘플 데이터를 넣었습니다.")


if __name__ == "__main__":
    main()
