from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import DailyProduction, Order, Product


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
