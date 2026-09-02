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
    Material,
    MaterialLot,
    Order,
    Product,
    PurchaseReceipt,
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
        "material_lots",
        "materials",
        "orders",
        "products",
        "purchase_receipts",
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
    # 완제품창고는 이 모델의 범위가 아니다(후속 ②). 상수와 Literal 은 저장을
    # 막지 못하므로 저장 제약으로 막는다.
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
