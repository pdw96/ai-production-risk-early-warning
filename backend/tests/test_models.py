from datetime import date
from typing import Any

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db import base as db_base
from app.db.base import Base
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
    RiskStatus,
)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as database_session:
        yield database_session


def test_order_has_product_and_daily_productions(session: Session) -> None:
    product = Product(code="FG-01", name="가상 소재 A")
    order = Order(
        order_number="MO-001",
        product=product,
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
    assert saved_order.product.code == "FG-01"
    assert saved_order.daily_productions[0].actual_quantity == 18


def test_create_all_and_sessionlocal_persist_all_task_one_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(db_base, "engine", engine)
    monkeypatch.setattr(db_base, "SessionLocal", session_factory)

    db_base.create_all()

    assert set(inspect(engine).get_table_names()) == {
        "bom_requirements",
        "daily_productions",
        "finished_goods_lots",
        "material_lots",
        "materials",
        "orders",
        "products",
        "purchase_receipts",
        "quality_inspections",
        "risk_statuses",
    }

    with db_base.SessionLocal() as database_session:
        product = Product(code="FG-02", name="가상 소재 B")
        material = Material(
            code="RM-01",
            name="가상 원자재 A",
            safety_stock=100,
        )
        order = Order(
            order_number="MO-002",
            product=product,
            due_date=date.today(),
            planned_quantity=200,
        )
        daily_production = DailyProduction(
            order=order,
            work_date=date.today(),
            planned_quantity=50,
            actual_quantity=45,
        )
        bom_requirement = BomRequirement(
            product=product,
            material=material,
            unit_quantity=2.5,
        )
        purchase_receipt = PurchaseReceipt(
            material=material,
            scheduled_date=date.today(),
            scheduled_quantity=300,
        )
        material_lot = MaterialLot(
            material=material,
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
                bom_requirement,
                purchase_receipt,
                material_lot,
                risk_status,
            ]
        )
        database_session.commit()

        assert database_session.query(Product).one().bom_requirements[0].unit_quantity == 2.5
        assert database_session.query(Material).one().purchase_receipts[0].scheduled_quantity == 300
        assert database_session.query(Material).one().lots[0].quantity == 500
        assert database_session.query(Order).one().daily_productions[0].actual_quantity == 45
        assert database_session.query(RiskStatus).one().status == "신규"


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
    material = Material(code="RM-02", name="가상 원자재 B", safety_stock=50)
    session.add_all(
        [
            MaterialLot(
                material=material,
                lot_number="LOT-RM-02-01",
                warehouse="원재료창고",
                quantity=60,
                received_date=date.today(),
            ),
            MaterialLot(
                material=material,
                lot_number="LOT-RM-02-01",
                warehouse="생산창고",
                quantity=40,
                received_date=date.today(),
            ),
        ]
    )
    session.commit()

    saved = session.query(Material).one()
    assert sum(lot.quantity for lot in saved.lots) == 100
    assert {lot.warehouse for lot in saved.lots} == {"원재료창고", "생산창고"}


def test_the_same_lot_number_cannot_repeat_within_one_warehouse(
    session: Session,
) -> None:
    material = Material(code="RM-03", name="가상 원자재 C", safety_stock=50)
    session.add_all(
        [
            MaterialLot(
                material=material,
                lot_number="LOT-RM-03-01",
                warehouse="원재료창고",
                quantity=10,
                received_date=date.today(),
            ),
            MaterialLot(
                material=material,
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
                material=Material(code="RM-04", name="가상 원자재 D", safety_stock=50),
                lot_number="SUP-2026-0001",
                warehouse="원재료창고",
                quantity=10,
                received_date=date.today(),
            ),
            MaterialLot(
                material=Material(code="RM-05", name="가상 원자재 E", safety_stock=50),
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
    # 완제품창고에는 완제품이 들어간다(FinishedGoodsLot). 상수와 Literal 은
    # 저장을 막지 못하므로 저장 제약으로 막는다.
    material = Material(code="RM-06", name="가상 원자재 F", safety_stock=50)
    session.add(
        MaterialLot(
            material=material,
            lot_number="LOT-RM-06-01",
            warehouse="완제품창고",
            quantity=10,
            received_date=date.today(),
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def _finished_goods_lot(product: Product, **overrides: Any) -> FinishedGoodsLot:
    values: dict[str, Any] = {
        "product": product,
        "lot_number": "LOT-FG-01-260901",
        "warehouse": "완제품창고",
        "qc_status": "합격",
        "quantity": 100,
        "produced_date": date.today(),
    }
    values.update(overrides)
    return FinishedGoodsLot(**values)


def test_finished_goods_lot_rejects_a_material_warehouse(session: Session) -> None:
    """완제품은 원재료창고에 들어가지 않는다. 창고 목록이 자재와 다르다."""
    product = Product(code="FG-01", name="가상 제품 A")
    session.add(_finished_goods_lot(product, warehouse="원재료창고"))

    with pytest.raises(IntegrityError):
        session.commit()


def test_finished_goods_lot_in_the_release_warehouse_must_have_passed_oqc(
    session: Session,
) -> None:
    """완제품창고 = 출하 대기 재고다. 검사 대기·불합격이 섞이면 출하 가능
    수량이 실제보다 많아 보인다."""
    product = Product(code="FG-02", name="가상 제품 B")
    session.add(_finished_goods_lot(product, qc_status="검사 대기"))

    with pytest.raises(IntegrityError):
        session.commit()


def test_finished_goods_lot_may_wait_in_the_production_warehouse_after_passing(
    session: Session,
) -> None:
    """합격이 곧 이동은 아니다 — 이관 대기 상태를 표현할 수 있어야 한다."""
    product = Product(code="FG-03", name="가상 제품 C")
    session.add(
        _finished_goods_lot(product, warehouse="생산창고", qc_status="합격")
    )
    session.commit()

    assert session.query(FinishedGoodsLot).one().warehouse == "생산창고"


def test_the_same_finished_goods_lot_number_cannot_repeat_within_one_warehouse(
    session: Session,
) -> None:
    product = Product(code="FG-04", name="가상 제품 D")
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
    product = Product(code="FG-05", name="가상 제품 E")
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
    material = Material(code="RM-07", name="가상 원자재 G", safety_stock=10)
    product = Product(code="FG-06", name="가상 제품 F")
    session.add(
        QualityInspection(
            inspection_type="OQC",
            inspected_date=date.today(),
            result="합격",
            finished_goods_lot=_finished_goods_lot(product),
            material_lot=MaterialLot(
                material=material,
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
    product = Product(code="FG-07", name="가상 제품 G")
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
    product = Product(code="FG-08", name="가상 제품 H")
    session.add(
        QualityInspection(
            inspection_type="OQC",
            inspected_date=date.today(),
            result="불합격",
            reason="   ",
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
