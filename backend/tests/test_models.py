from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db import base as db_base
from app.db.base import Base
from app.core.config import ITEM_CODE_PREFIXES
from app.db.models import (
    BomComponent,
    DailyProduction,
    FinishedGoodsLot,
    Item,
    MaterialLot,
    Order,
    PurchaseReceipt,
    QualityInspection,
    RiskStatus,
    _reject_overlapping_prefixes,
)
from tests.factories import (
    finished_item,
    raw_item,
    seed_referenced_codes,
    semi_finished_item,
)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as database_session:
        # 공정과 재고 단위는 공통코드를 가리킨다. 코드가 먼저 있어야 품목이
        # 들어간다 — 시드도 공통코드부터 넣는다.
        seed_referenced_codes(database_session)
        yield database_session


def test_order_has_product_and_daily_productions(session: Session) -> None:
    product = finished_item(code="FG-01", name="가상 소재 A")
    order = Order(
        order_number="MO-001",
        item=product,
        due_date=date.today(),
        planned_quantity=100,
    )
    order.daily_productions.append(
        DailyProduction(
            work_date=date.today(),
            planned_quantity=20,
            actual_quantity=18,
        )
    )
    session.add(order)
    session.commit()

    saved_order = session.query(Order).one()
    assert saved_order.item.code == "FG-01"
    assert saved_order.daily_productions[0].actual_quantity == 18


def test_create_all_builds_every_table_from_both_model_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(db_base, "engine", engine)
    monkeypatch.setattr(db_base, "SessionLocal", session_factory)

    db_base.create_all()

    # 기준정보와 거래 표가 다른 모듈에 있으므로, 하나만 불러오면 메타데이터가
    # 반쪽이 되고 외래키의 상대가 없어진다. 이 목록이 그것을 지킨다.
    assert set(inspect(engine).get_table_names()) == {
        # 거래·재고
        "bom_components",
        "daily_productions",
        "finished_goods_lots",
        "items",
        "material_lots",
        "orders",
        "purchase_receipts",
        "quality_inspections",
        "risk_statuses",
        # 기준정보
        "code_groups",
        "common_codes",
        "non_working_periods",
        "nonconformity_attributes",
        "nonconformity_stage_rules",
        "partners",
        "process_inspection_standards",
        "purchase_close_attributes",
        "shift_patterns",
        "supplier_items",
        "txn_type_attributes",
    }

    with db_base.SessionLocal() as database_session:
        seed_referenced_codes(database_session)
        product = finished_item(code="FG-02", name="가상 소재 B")
        material = raw_item(
            code="RM-01",
            name="가상 원자재 A",
            safety_stock=100,
        )
        order = Order(
            order_number="MO-002",
            item=product,
            due_date=date.today(),
            planned_quantity=200,
        )
        daily_production = DailyProduction(
            order=order,
            work_date=date.today(),
            planned_quantity=50,
            actual_quantity=45,
        )
        bom_component = BomComponent(
            parent_item=product,
            child_item=material,
            level=1,
            unit_quantity=2.5,
        )
        purchase_receipt = PurchaseReceipt(
            item=material,
            scheduled_date=date.today(),
            scheduled_quantity=300,
        )
        material_lot = MaterialLot(
            item=material,
            lot_number="LOT-RM-01-01",
            warehouse="원재료창고",
            quantity=500,
            received_date=date.today(),
            expiry_date=None,
        )
        risk_status = RiskStatus(risk_key="RISK-ORDER-002")
        database_session.add_all(
            [
                daily_production,
                bom_component,
                purchase_receipt,
                material_lot,
                risk_status,
            ]
        )
        database_session.commit()

        assert database_session.query(Item).filter_by(code="FG-02").one().components[0].unit_quantity == 2.5
        assert database_session.query(Item).filter_by(code="RM-01").one().purchase_receipts[0].scheduled_quantity == 300
        assert database_session.query(Item).filter_by(code="RM-01").one().material_lots[0].quantity == 500
        assert database_session.query(Order).one().daily_productions[0].actual_quantity == 45
        assert database_session.query(RiskStatus).one().status == "신규"


def test_a_semi_finished_item_finally_has_a_seat(session: Session) -> None:
    """반제품은 만들어지면서 쓰인다 — 표가 둘일 때는 어느 쪽에도 속하지 못했다.

    한 표가 되면서 반제품이 상위이면서 하위인 BOM 두 줄을 동시에 가질 수 있다.
    그것이 2단 BOM 이고, 통합 없이는 표현할 방법이 아예 없었다.
    """
    product = finished_item(code="FG-20", name="가상 제품 T")
    semi = semi_finished_item(code="SF-01", name="가상 반제품 A")
    material = raw_item(code="RM-20", name="가상 원자재 T", safety_stock=10)
    session.add_all(
        [
            BomComponent(parent_item=product, child_item=semi, level=1, unit_quantity=1),
            BomComponent(parent_item=semi, child_item=material, level=2, unit_quantity=2),
        ]
    )
    session.commit()

    saved = session.query(Item).filter_by(code="SF-01").one()
    assert [row.child_item.code for row in saved.components] == ["RM-20"]
    assert [row.parent_item.code for row in saved.used_in] == ["FG-20"]


def test_a_semi_finished_item_cannot_carry_a_shelf_life(session: Session) -> None:
    """「반제품은 유효기간을 두지 않고 제품만 유효기간을 정한다」(발화).

    표가 하나여서 이 규칙을 처음으로 제약에 적을 수 있게 됐다.
    """
    session.add(semi_finished_item(code="SF-02", name="가상 반제품 B", shelf_life_days=30))

    with pytest.raises(IntegrityError):
        session.commit()


def test_the_item_code_prefix_must_match_the_item_type(session: Session) -> None:
    """접두는 유형과 유일성만 맡는다(지적 ⑯). 한 표가 되면서 접두가 유일하게
    유형을 가리키므로, 어긋난 접두는 표 전체의 읽기를 망가뜨린다."""
    session.add(finished_item(code="RM-99", name="접두가 어긋난 제품"))

    with pytest.raises(IntegrityError):
        session.commit()


def test_no_quantity_column_accepts_a_negative_number(session: Session) -> None:
    """수량은 음수가 될 수 없다 — 표 여섯이 그것을 스스로 거부해야 한다.

    **화면이 이 불변식에 기대고 있다.** 제품을 넘어 더한 합에 붙일 단위가
    있는지를 화면은 「합이 0 이면 더한 것이 없는 것」으로 가르는데, 음수가
    섞이면 서로 다른 단위가 0 으로 상쇄되어 **섞인 것을 빈 것으로** 읽는다.
    적어 두기만 하고 강제하지 않으면 규칙이 아니므로 여기서 물게 한다.

    거부되는 것만 보면 부족하다 — 앞줄이 무른 세션에서 뒤의 줄이 **엉뚱한
    이유로** 거부되어도 통과하기 때문이다. 그래서 세이브포인트로 줄마다
    상태를 되돌리고, 터진 제약의 **이름까지** 확인한다.
    """
    product = finished_item(code="FG-31", name="가상 제품 음수")
    material = raw_item(code="RM-31", name="가상 원자재 음수", safety_stock=10)
    session.add_all([product, material])
    session.flush()
    order = Order(
        order_number="MO-931",
        item=product,
        due_date=date.today() + timedelta(days=7),
        planned_quantity=100,
    )
    session.add(order)
    session.commit()

    def negative_rows() -> list[tuple[str, Any]]:
        return [
            (
                "ck_bom_component_unit_quantity_not_negative",
                BomComponent(
                    parent_item_id=product.id,
                    child_item_id=material.id,
                    level=2,
                    unit_quantity=-1,
                ),
            ),
            (
                "ck_order_planned_quantity_not_negative",
                Order(
                    order_number="MO-932",
                    item_id=product.id,
                    due_date=date.today() + timedelta(days=7),
                    planned_quantity=-1,
                ),
            ),
            (
                "ck_daily_production_planned_quantity_not_negative",
                DailyProduction(
                    order_id=order.id,
                    work_date=date.today(),
                    planned_quantity=-1,
                    actual_quantity=0,
                ),
            ),
            (
                "ck_daily_production_actual_quantity_not_negative",
                DailyProduction(
                    order_id=order.id,
                    work_date=date.today(),
                    planned_quantity=0,
                    actual_quantity=-1,
                ),
            ),
            (
                "ck_purchase_receipt_scheduled_quantity_not_negative",
                PurchaseReceipt(
                    item_id=material.id,
                    scheduled_date=date.today() + timedelta(days=3),
                    scheduled_quantity=-1,
                ),
            ),
            (
                "ck_material_lot_quantity_not_negative",
                MaterialLot(
                    item_id=material.id,
                    lot_number="LOT-RM-31-01",
                    warehouse="원재료창고",
                    quantity=-1,
                    received_date=date.today(),
                ),
            ),
            (
                "ck_finished_goods_lot_quantity_not_negative",
                FinishedGoodsLot(
                    item_id=product.id,
                    lot_number="LOT-FG-31-01",
                    warehouse="생산창고",
                    qc_status="검사 대기",
                    stock_type="양품",
                    quantity=-1,
                    produced_date=date.today(),
                ),
            ),
        ]

    for constraint_name, row in negative_rows():
        with pytest.raises(IntegrityError) as rejection:
            with session.begin_nested():
                session.add(row)
                session.flush()
        assert constraint_name in str(rejection.value), (
            f"{constraint_name} 이 아니라 다른 이유로 거부됐습니다 —"
            " 이 줄은 음수를 막는 것을 확인하지 못합니다."
        )


def test_bom_levels_stop_at_two(session: Session) -> None:
    """「단계」 열 하나가 재귀를 막는다 — 전개가 두 번으로 고정된다."""
    product = finished_item(code="FG-21", name="가상 제품 U")
    material = raw_item(code="RM-21", name="가상 원자재 U", safety_stock=10)
    session.add(
        BomComponent(parent_item=product, child_item=material, level=3, unit_quantity=1)
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_get_session_yields_a_usable_session_and_closes_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TrackingSession(Session):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.close_called = False

        def close(self) -> None:
            self.close_called = True
            super().close()

    engine = create_engine("sqlite:///:memory:")
    session_factory = sessionmaker(bind=engine, class_=TrackingSession)
    monkeypatch.setattr(db_base, "SessionLocal", session_factory)

    session_generator = db_base.get_session()
    yielded_session = next(session_generator)

    assert isinstance(yielded_session, TrackingSession)
    assert yielded_session.execute(text("SELECT 1")).scalar_one() == 1
    assert yielded_session.close_called is False

    session_generator.close()

    assert yielded_session.close_called is True


def test_the_same_lot_number_may_exist_in_both_warehouses(session: Session) -> None:
    """원재료창고 100EA 중 40EA를 생산창고로 옮긴 상태를 표현할 수 있어야 한다."""
    material = raw_item(code="RM-02", name="가상 원자재 B", safety_stock=50)
    session.add_all(
        [
            MaterialLot(
                item=material,
                lot_number="LOT-RM-02-01",
                warehouse="원재료창고",
                quantity=60,
                received_date=date.today(),
            ),
            MaterialLot(
                item=material,
                lot_number="LOT-RM-02-01",
                warehouse="생산창고",
                quantity=40,
                received_date=date.today(),
            ),
        ]
    )
    session.commit()

    saved = session.query(Item).one()
    assert sum(lot.quantity for lot in saved.material_lots) == 100
    assert {lot.warehouse for lot in saved.material_lots} == {"원재료창고", "생산창고"}


def test_the_same_lot_number_cannot_repeat_within_one_warehouse(
    session: Session,
) -> None:
    material = raw_item(code="RM-03", name="가상 원자재 C", safety_stock=50)
    session.add_all(
        [
            MaterialLot(
                item=material,
                lot_number="LOT-RM-03-01",
                warehouse="원재료창고",
                quantity=10,
                received_date=date.today(),
            ),
            MaterialLot(
                item=material,
                lot_number="LOT-RM-03-01",
                warehouse="원재료창고",
                quantity=20,
                received_date=date.today(),
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_the_same_lot_number_can_repeat_across_different_materials(
    session: Session,
) -> None:
    # 로트번호는 자재에 종속된 개념이다. 공급사 번호를 그대로 쓰기 시작하면
    # 서로 다른 자재가 같은 번호를 들고 올 수 있으므로 자재까지 유일키에 넣는다.
    session.add_all(
        [
            MaterialLot(
                item=raw_item(code="RM-04", name="가상 원자재 D", safety_stock=50),
                lot_number="SUP-2026-0001",
                warehouse="원재료창고",
                quantity=10,
                received_date=date.today(),
            ),
            MaterialLot(
                item=raw_item(code="RM-05", name="가상 원자재 E", safety_stock=50),
                lot_number="SUP-2026-0001",
                warehouse="원재료창고",
                quantity=20,
                received_date=date.today(),
            ),
        ]
    )
    session.commit()

    assert session.query(MaterialLot).count() == 2


def test_material_lot_rejects_a_warehouse_outside_the_allowed_set(
    session: Session,
) -> None:
    # 제품창고에는 완제품이 들어간다(FinishedGoodsLot). 상수와 Literal 은
    # 저장을 막지 못하므로 저장 제약으로 막는다.
    material = raw_item(code="RM-06", name="가상 원자재 F", safety_stock=50)
    session.add(
        MaterialLot(
            item=material,
            lot_number="LOT-RM-06-01",
            warehouse="제품창고",
            quantity=10,
            received_date=date.today(),
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def _finished_goods_lot(product: Item, **overrides: Any) -> FinishedGoodsLot:
    values: dict[str, Any] = {
        "item": product,
        "lot_number": "LOT-FG-01-260901",
        "warehouse": "제품창고",
        "qc_status": "합격",
        "stock_type": "양품",
        "quantity": 100,
        "produced_date": date.today(),
    }
    values.update(overrides)
    # 합격일은 판정에서 따라 나온다 — 시계가 합격에서 시작하기 때문이다.
    # 여기서 파생시키지 않으면 판정만 바꾼 테스트가 「불합격인데 합격일이
    # 있는」 로트를 만들고, 그것은 제약이 막아야 할 바로 그 줄이다.
    values.setdefault(
        "passed_date",
        date.today() if values["qc_status"] == "합격" else None,
    )
    return FinishedGoodsLot(**values)


def test_finished_goods_lot_rejects_a_material_warehouse(session: Session) -> None:
    """완제품은 원재료창고에 들어가지 않는다. 창고 목록이 자재와 다르다."""
    product = finished_item(code="FG-01", name="가상 제품 A")
    session.add(_finished_goods_lot(product, warehouse="원재료창고"))

    with pytest.raises(IntegrityError):
        session.commit()


def test_the_product_warehouse_holds_only_lots_that_passed_inspection(
    session: Session,
) -> None:
    """제품창고 = 출하 대기 재고다. 검사 대기·불합격이 섞이면 출하 가능 수량이
    실제보다 많아 보인다."""
    product = finished_item(code="FG-02", name="가상 제품 B")
    session.add(_finished_goods_lot(product, qc_status="검사 대기"))

    with pytest.raises(IntegrityError):
        session.commit()


def test_a_lot_that_passed_inspection_may_wait_in_the_production_warehouse(
    session: Session,
) -> None:
    """지적 ① — 양방향 CHECK 를 버린다.

    제품창고에 들어오는 조건은 「합격 + 입고 처리」이지 합격 하나가 아니다.
    양방향으로 묶어 두면 **합격했으나 아직 옮기지 않은** 로트를 표현할 수 없고,
    관문 6(재고이동 요청·처리)이 들어올 자리가 제약에 막힌다.
    """
    product = finished_item(code="FG-03", name="가상 제품 C")
    session.add(
        _finished_goods_lot(product, warehouse="생산창고", qc_status="합격")
    )
    session.commit()

    saved = session.query(FinishedGoodsLot).one()
    assert (saved.warehouse, saved.qc_status) == ("생산창고", "합격")


def test_defective_stock_must_have_failed_inspection(session: Session) -> None:
    """재고구분은 판정에서 나오는 것이지 사람이 임의로 붙이는 딱지가 아니다."""
    product = finished_item(code="FG-11", name="가상 제품 K")
    session.add(_finished_goods_lot(product, stock_type="불량품"))

    with pytest.raises(IntegrityError):
        session.commit()


def test_a_lot_records_both_the_production_and_the_pass_date(session: Session) -> None:
    """지적 ⑰ — 유효기간의 기산점은 생산일이 아니라 합격일이다.

    두 날짜의 차이가 곧 「검사에 며칠 걸렸나」이고, 그 값이 생산창고에 완제품이
    쌓이는 이유를 설명한다.
    """
    product = finished_item(code="FG-12", name="가상 제품 L", shelf_life_days=30)
    session.add(
        _finished_goods_lot(
            product,
            produced_date=date(2026, 9, 1),
            passed_date=date(2026, 9, 3),
            expiry_date=date(2026, 10, 3),
        )
    )
    session.commit()

    saved = session.query(FinishedGoodsLot).one()
    assert (saved.passed_date - saved.produced_date).days == 2
    assert saved.expiry_date == saved.passed_date + timedelta(days=30)
    assert saved.reworked is False


def test_a_rejected_lot_stays_in_the_production_warehouse(session: Session) -> None:
    product = finished_item(code="FG-10", name="가상 제품 J")
    session.add(
        _finished_goods_lot(product, warehouse="생산창고", qc_status="불합격")
    )
    session.commit()

    assert session.query(FinishedGoodsLot).one().warehouse == "생산창고"


def test_the_same_finished_goods_lot_number_cannot_repeat_within_one_warehouse(
    session: Session,
) -> None:
    product = finished_item(code="FG-04", name="가상 제품 D")
    session.add_all(
        [
            _finished_goods_lot(product),
            _finished_goods_lot(product, quantity=50),
        ]
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_quality_inspection_rejects_a_target_that_does_not_match_its_type(
    session: Session,
) -> None:
    """IQC 는 자재 로트를 본다. 완제품 로트를 가리키는 IQC 기록은 있을 수 없다."""
    product = finished_item(code="FG-05", name="가상 제품 E")
    session.add(
        QualityInspection(
            inspection_type="IQC",
            inspected_date=date.today(),
            result="합격",
            finished_goods_lot=_finished_goods_lot(product),
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_quality_inspection_rejects_two_targets_at_once(session: Session) -> None:
    material = raw_item(code="RM-07", name="가상 원자재 G", safety_stock=10)
    product = finished_item(code="FG-06", name="가상 제품 F")
    session.add(
        QualityInspection(
            inspection_type="OQC",
            inspected_date=date.today(),
            result="합격",
            finished_goods_lot=_finished_goods_lot(product),
            material_lot=MaterialLot(
                item=material,
                lot_number="LOT-RM-07-01",
                warehouse="원재료창고",
                quantity=10,
                received_date=date.today(),
            ),
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_a_failed_inspection_must_carry_a_reason(session: Session) -> None:
    """사유 없는 불합격은 담당자가 무엇을 조치할지 알 수 없다."""
    product = finished_item(code="FG-07", name="가상 제품 G")
    session.add(
        QualityInspection(
            inspection_type="OQC",
            inspected_date=date.today(),
            result="불합격",
            reason=None,
            finished_goods_lot=_finished_goods_lot(
                product, warehouse="생산창고", qc_status="불합격"
            ),
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_a_failed_inspection_reason_cannot_be_blank(session: Session) -> None:
    """빈 문자열도 사유가 없는 것이다. NULL 검사만으로는 화면에 사유 없는
    불합격 행이 그대로 그려진다."""
    product = finished_item(code="FG-08", name="가상 제품 H")
    session.add(
        QualityInspection(
            inspection_type="OQC",
            inspected_date=date.today(),
            result="불합격",
            # 공백만이 아니라 탭·개행도 사유가 아니다. SQLite 의 1인자 trim() 은
            # 공백(0x20)만 지우므로 지울 문자를 명시해야 이것들이 걸린다.
            reason=" \t\n\r ",
            finished_goods_lot=_finished_goods_lot(
                product, warehouse="생산창고", qc_status="불합격"
            ),
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_an_inspection_cannot_point_at_a_target_that_does_not_exist(
    session: Session,
) -> None:
    """SQLite 는 기본적으로 외래키를 검사하지 않는다. 강제를 켜지 않으면 대상이
    없는 기록이 저장되고, 조회할 때 모든 관계가 None 이라 대상 표기를 만드는
    코드가 터진다."""
    with pytest.raises(IntegrityError):
        session.execute(
            text(
                "INSERT INTO quality_inspections"
                " (inspection_type, inspected_date, result, reason, material_lot_id)"
                " VALUES ('IQC', '2026-09-01', '합격', NULL, 999)"
            )
        )


def test_sqlite_foreign_key_enforcement_is_on_for_every_connection(
    session: Session,
) -> None:
    assert session.execute(text("PRAGMA foreign_keys")).scalar_one() == 1


def test_a_target_with_inspection_history_cannot_be_deleted(session: Session) -> None:
    """검사 기록은 대상에 딸린 부속이 아니라 감사 기록이다.

    `delete-orphan` 을 걸어 두면 대상을 지우는 것만으로 검사 기록이 조용히
    사라져, API 요약이 세는 이력이 줄어든다. 지우려면 기록을 먼저 정리하라고
    DB 가 막아야 한다.
    """
    material = raw_item(code="RM-08", name="가상 원자재 H", safety_stock=10)
    lot = MaterialLot(
        item=material,
        lot_number="LOT-RM-08-01",
        warehouse="원재료창고",
        quantity=10,
        received_date=date.today(),
    )
    lot.inspections.append(
        QualityInspection(
            inspection_type="IQC",
            inspected_date=date.today(),
            result="합격",
        )
    )
    session.add(lot)
    session.commit()

    session.delete(lot)
    with pytest.raises(IntegrityError):
        session.commit()


def test_detaching_an_inspection_from_its_target_does_not_delete_it(
    session: Session,
) -> None:
    """대상 컬렉션에서 떼어내는 것만으로도 기록이 지워지면 안 된다."""
    material = raw_item(code="RM-09", name="가상 원자재 I", safety_stock=10)
    lot = MaterialLot(
        item=material,
        lot_number="LOT-RM-09-01",
        warehouse="원재료창고",
        quantity=10,
        received_date=date.today(),
    )
    lot.inspections.append(
        QualityInspection(
            inspection_type="IQC",
            inspected_date=date.today(),
            result="합격",
        )
    )
    session.add(lot)
    session.commit()

    lot.inspections.clear()
    # 대상 없는 검사 기록은 존재할 수 없으므로 CHECK 제약이 막는다.
    with pytest.raises(IntegrityError):
        session.commit()


def test_a_raw_item_must_keep_its_safety_stock(session: Session) -> None:
    """통합 전 `materials.safety_stock` 은 NOT NULL 이었다.

    칸이 완제품과 겸용이 되면서 nullable 로 넓어졌는데, 자재 리스크는 이 값을
    재고와 곧바로 견주므로 원자재만은 그 불변식이 남아야 한다 — 비어 있으면
    비교가 아니라 계산이 터진다.
    """
    session.add(raw_item(code="RM-90", name="안전재고 없는 자재", safety_stock=None))

    with pytest.raises(IntegrityError):
        session.commit()


def test_a_finished_item_may_still_leave_its_safety_stock_empty(
    session: Session,
) -> None:
    """완제품은 칸이 생겼을 뿐 아직 정한 사람이 없다 — 비어 있는 것이 맞다."""
    session.add(finished_item(code="FG-90", name="안전재고 미정 제품"))
    session.commit()

    assert session.query(Item).filter_by(code="FG-90").one().safety_stock is None


def test_a_lot_that_has_not_passed_cannot_carry_a_pass_date(session: Session) -> None:
    """시계는 합격에서 시작한다(지적 ⑰). 불합격 로트에 합격일이 있으면
    유효기간이 없는 판정에서 파생된다."""
    product = finished_item(code="FG-91", name="가상 제품 K")
    session.add(
        _finished_goods_lot(
            product,
            warehouse="생산창고",
            qc_status="불합격",
            stock_type="불량품",
            passed_date=date.today(),
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_a_passed_lot_must_carry_a_pass_date(session: Session) -> None:
    """합격인데 합격일이 없으면 시계가 시작되지 않는다."""
    product = finished_item(code="FG-92", name="가상 제품 L")
    session.add(_finished_goods_lot(product, passed_date=None))

    with pytest.raises(IntegrityError):
        session.commit()


def test_a_lot_cannot_pass_before_it_was_produced(session: Session) -> None:
    """뒤집히면 「검사에 며칠 걸렸나」가 음수가 된다."""
    product = finished_item(code="FG-93", name="가상 제품 M")
    session.add(
        _finished_goods_lot(
            product,
            produced_date=date.today(),
            passed_date=date.today() - timedelta(days=1),
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_a_lot_cannot_carry_an_expiry_without_a_pass_date(session: Session) -> None:
    """유효기간은 합격일에서 파생된다.

    합격일 없이 유효기간만 있는 줄은 근거 없는 만료일을 들고 다니며, 화면에서
    「만료」로 그려져 검사조차 받지 않은 로트가 만료 재고에 잡힌다.
    """
    product = finished_item(code="FG-94", name="가상 제품 N")
    session.add(
        _finished_goods_lot(
            product,
            warehouse="생산창고",
            qc_status="검사 대기",
            expiry_date=date.today() + timedelta(days=30),
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_overlapping_item_code_prefixes_are_rejected() -> None:
    """한 접두가 다른 접두의 앞부분이면, 긴 쪽에 맞는 코드는 두 LIKE 를 동시에
    만족해 **어떤 유형으로도 넣을 수 없는 코드**가 된다. 조용히 거부당하는
    것보다 정의하는 자리에서 터지는 편이 낫다."""
    with pytest.raises(ValueError, match="접두가 겹칩니다"):
        _reject_overlapping_prefixes({"완제품": "FG-", "반제품": "F"})


def test_the_current_prefixes_do_not_overlap() -> None:
    _reject_overlapping_prefixes(ITEM_CODE_PREFIXES)


def test_expiry_cannot_precede_the_pass_date(session: Session) -> None:
    """시계는 합격일에서 시작한다 — 유효기간이 그보다 앞설 수 없다.

    뒤집힌 줄은 날짜 제약 셋을 모두 만족하면서 화면에서는 곧바로 「만료」로
    그려진다: 합격하자마자 만료된 로트다.
    """
    product = finished_item(code="FG-95", name="가상 제품 O")
    session.add(
        _finished_goods_lot(
            product,
            produced_date=date(2026, 9, 1),
            passed_date=date(2026, 9, 7),
            expiry_date=date(2026, 9, 1),
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_the_prefix_check_is_case_sensitive_on_this_engine(session: Session) -> None:
    """SQLite 의 `LIKE` 는 ASCII 대소문자를 가리지 않고 PostgreSQL 은 가린다.

    `LIKE` 로 적으면 `fg-01` 이 개발·테스트에서는 통과하고 운영에서 거부된다 —
    두 엔진에서 제약이 같은 뜻이어야 한다는 목표가 그 자리에서 깨진다.
    """
    session.add(finished_item(code="fg-99", name="소문자 코드"))

    with pytest.raises(IntegrityError):
        session.commit()


def test_lead_time_coefficients_cannot_be_negative(session: Session) -> None:
    """음수 계수가 표에 들어가면 계획이 시간을 거꾸로 흐르게 한다.

    소요 시간 = 준비시간 + 개당 시간 × 수량이므로 계수가 음수면 합이 음수가 되고,
    `start_at` 은 착수를 **완료보다 뒤에** 잡는다. 손으로 고치는 품목 마스터에서
    부호 하나가 그 일을 하므로 표가 먼저 막는다.
    """
    session.add(finished_item(code="FG-90", name="가상 소재 Z", hours_per_unit=-0.2))

    with pytest.raises(IntegrityError):
        session.flush()


def test_a_negative_setup_time_is_refused_too(session: Session) -> None:
    session.add(finished_item(code="FG-91", name="가상 소재 Y", setup_hours=-1))

    with pytest.raises(IntegrityError):
        session.flush()


def test_a_finished_item_cannot_hold_a_material_lot(session: Session) -> None:
    """자재 로트의 품목은 **원자재여야 한다.**

    `item_id` 만 참조하면 존재 여부만 본다. 완제품이 자재 로트에 들어가면 창고
    화면은 그 줄을 「자재」로 세는데(그 자리에서 유형을 못박는다) 자재관리 화면은
    원자재만 거르므로 보이지 않는다 — 같은 물건이 한 화면에는 있고 다른 화면에는
    없다. 표가 둘이던 때는 외래키가 이것을 지켰고, 한 표로 합치면서 잃었다.
    """
    product = finished_item(code="FG-80", name="가상 소재 W")
    session.add(product)
    session.flush()

    session.add(
        MaterialLot(
            item_id=product.id,
            lot_number="LOT-WRONG",
            warehouse="원재료창고",
            quantity=10,
            received_date=date.today(),
        )
    )

    with pytest.raises(IntegrityError):
        session.flush()


def test_a_raw_item_cannot_hold_a_finished_goods_lot(session: Session) -> None:
    """완제품 로트의 품목은 **완제품이어야 한다.** 출하검사와 유효기간이 그것의 것이다."""
    material = raw_item(code="RM-80", name="가상 원자재 W", safety_stock=10)
    session.add(material)
    session.flush()

    session.add(
        FinishedGoodsLot(
            item_id=material.id,
            lot_number="LOT-WRONG",
            warehouse="생산창고",
            qc_status="검사 대기",
            quantity=10,
            produced_date=date.today(),
        )
    )

    with pytest.raises(IntegrityError):
        session.flush()


def test_a_raw_item_cannot_carry_a_production_order(session: Session) -> None:
    """생산오더의 품목은 **완제품이어야 한다.**

    원자재가 오더에 들어가면 그 실적이 전 제품 합계 추이에는 들어가는데 제품별
    계열은 완제품만 세우므로, 고를 수 없는 계열의 실적이 합계에만 남는다. 오더
    API 도 그 원자재를 「제품」으로 적는다. 표가 둘이던 때는 외래키가 막았다.
    """
    material = raw_item(code="RM-81", name="가상 원자재 V", safety_stock=10)
    session.add(material)
    session.flush()

    session.add(
        Order(
            order_number="MO-WRONG",
            item_id=material.id,
            due_date=date.today(),
            planned_quantity=10,
        )
    )

    with pytest.raises(IntegrityError):
        session.flush()


def test_a_finished_item_cannot_be_a_scheduled_receipt(session: Session) -> None:
    """예정 입고의 품목은 **원자재여야 한다.**

    완제품이 들어가면 구매관리 화면은 그것을 자재 입고로 내보내는데 자재관리는
    원자재만 거르므로, 자재 입고로 보이면서 어느 자재의 14일 수급 전망에도
    잡히지 않는 줄이 된다.
    """
    product = finished_item(code="FG-81", name="가상 소재 V")
    session.add(product)
    session.flush()

    session.add(
        PurchaseReceipt(
            item_id=product.id,
            scheduled_date=date.today(),
            scheduled_quantity=10,
        )
    )

    with pytest.raises(IntegrityError):
        session.flush()
