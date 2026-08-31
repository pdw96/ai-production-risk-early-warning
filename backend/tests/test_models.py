from datetime import date

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from app.db import base as db_base
from app.db.base import Base
from app.db.models import (
    BomRequirement,
    DailyProduction,
    Material,
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
            current_stock=500,
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
        risk_status = RiskStatus(risk_key="RISK-ORDER-002")
        database_session.add_all(
            [
                daily_production,
                bom_requirement,
                purchase_receipt,
                risk_status,
            ]
        )
        database_session.commit()

        assert database_session.query(Product).one().bom_requirements[0].unit_quantity == 2.5
        assert database_session.query(Material).one().purchase_receipts[0].scheduled_quantity == 300
        assert database_session.query(Order).one().daily_productions[0].actual_quantity == 45
        assert database_session.query(RiskStatus).one().status == "신규"
