from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import base as db_base
from app.db.models import BomRequirement, DailyProduction, Material, Order, Product, PurchaseReceipt
from app.seed import reset_database
from app.services.briefing import list_materials
from app.services.order_risk import calculate_order_risk


@pytest.fixture
def seeded_session_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> sessionmaker[Session]:
    engine = create_engine("sqlite:///:memory:")
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(db_base, "engine", engine)
    monkeypatch.setattr(db_base, "SessionLocal", session_factory)
    return session_factory


def test_reset_database_creates_required_synthetic_operational_records(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    reference_date = date(2026, 8, 31)

    reset_database(reference_date)

    with seeded_session_factory() as session:
        assert session.query(Product).count() == 5
        assert session.query(Order).count() == 30
        assert session.query(Material).count() == 15
        assert session.query(BomRequirement).count() == 15
        assert session.query(PurchaseReceipt).count() == 15
        assert session.query(DailyProduction).filter(
            DailyProduction.work_date == reference_date - timedelta(days=29)
        ).count() == 30
        assert session.query(DailyProduction).filter(
            DailyProduction.work_date == reference_date + timedelta(days=14)
        ).count() == 30


def test_reset_database_is_deterministic_for_the_same_reference_date(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    reference_date = date(2026, 8, 31)

    reset_database(reference_date)
    with seeded_session_factory() as session:
        first_snapshot = [
            (order.order_number, order.product.code, order.due_date, order.planned_quantity)
            for order in session.query(Order).order_by(Order.order_number)
        ]

    reset_database(reference_date)
    with seeded_session_factory() as session:
        second_snapshot = [
            (order.order_number, order.product.code, order.due_date, order.planned_quantity)
            for order in session.query(Order).order_by(Order.order_number)
        ]

    assert second_snapshot == first_snapshot


def test_seeded_orders_include_normal_caution_and_danger_by_existing_risk_rule(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    reference_date = date(2026, 8, 31)

    reset_database(reference_date)

    with seeded_session_factory() as session:
        severities = {
            calculate_order_risk(
                planned_quantity=order.planned_quantity,
                actual_quantity=sum(
                    daily.actual_quantity
                    for daily in order.daily_productions
                    if daily.work_date <= reference_date
                ),
                average_daily_output=sum(
                    daily.actual_quantity
                    for daily in order.daily_productions
                    if reference_date - timedelta(days=6)
                    <= daily.work_date
                    <= reference_date
                )
                / 7,
                due_date=order.due_date,
                reference_date=reference_date,
            ).severity
            for order in session.query(Order).all()
        }

    assert severities == {"정상", "주의", "위험"}


def test_seeded_materials_include_a_fourteen_day_shortage_risk(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    reset_database(date(2026, 8, 31))

    with seeded_session_factory() as session:
        materials = list_materials(session)

    assert any(material.shortage_expected for material in materials)
