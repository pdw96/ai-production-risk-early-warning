from __future__ import annotations

import warnings
from collections.abc import Generator
from datetime import date

warnings.filterwarnings(
    "ignore",
    message="Using `httpx` with `starlette.testclient` is deprecated.*",
)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import base as db_base
from app.main import app
from app.seed import reset_database


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(db_base, "engine", engine)
    monkeypatch.setattr(db_base, "SessionLocal", session_factory)
    reset_database(date(2026, 8, 31))

    def override_session() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[db_base.get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def test_dashboard_returns_kpis_trend_top_risks_and_actions(client: TestClient) -> None:
    response = client.get("/api/dashboard")

    assert response.status_code == 200
    data = response.json()["data"]
    assert set(data) == {
        "kpis",
        "production_trend",
        "top_order_risks",
        "top_material_risks",
        "recommended_actions",
    }
    assert set(data["kpis"]) == {
        "due_risk_order_count",
        "material_shortage_count",
        "today_plan_quantity",
        "today_actual_quantity",
    }
    assert len(data["production_trend"]) == 7
    assert len(data["top_order_risks"]) <= 5
    assert len(data["top_material_risks"]) <= 5
    assert data["recommended_actions"]


def test_local_frontend_origin_is_allowed_by_cors(client: TestClient) -> None:
    response = client.options(
        "/api/dashboard",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


@pytest.mark.parametrize(
    ("path", "required_fields"),
    [
        (
            "/api/orders",
            {
                "order_id",
                "order_number",
                "product_code",
                "product_name",
                "due_date",
                "planned_quantity",
                "actual_quantity",
                "completion_rate",
                "average_daily_output",
                "remaining_quantity",
                "estimated_completion_date",
                "severity",
                "reason",
            },
        ),
        (
            "/api/materials",
            {
                "material_id",
                "material_code",
                "material_name",
                "current_stock",
                "safety_stock",
                "ending_stock",
                "minimum_stock",
                "shortage_expected",
                "stockout_date",
                "severity",
                "recommendation",
            },
        ),
        (
            "/api/risks",
            {
                "risk_id",
                "risk_type",
                "entity_id",
                "entity_code",
                "entity_name",
                "severity",
                "reason",
                "recommendation",
                "status",
            },
        ),
    ],
)
def test_list_endpoints_return_required_contract_fields(
    client: TestClient,
    path: str,
    required_fields: set[str],
) -> None:
    response = client.get(path)

    assert response.status_code == 200
    items = response.json()["data"]
    assert items
    assert required_fields <= set(items[0])


def test_order_detail_returns_recent_production(client: TestClient) -> None:
    order = client.get("/api/orders").json()["data"][0]

    response = client.get(f"/api/orders/{order['order_id']}")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["order_id"] == order["order_id"]
    assert len(data["recent_productions"]) == 7
    assert {"work_date", "planned_quantity", "actual_quantity"} <= set(
        data["recent_productions"][0]
    )


def test_missing_order_detail_returns_detail_error(client: TestClient) -> None:
    response = client.get("/api/orders/999999")

    assert response.status_code == 404
    assert response.json() == {"detail": "오더를 찾을 수 없습니다."}


def test_invalid_risk_status_returns_validation_error(client: TestClient) -> None:
    risk = client.get("/api/risks").json()["data"][0]

    response = client.patch(
        f"/api/risks/{risk['risk_id']}/status",
        json={"status": "보류"},
    )

    assert response.status_code == 422
    assert "detail" in response.json()


def test_patch_risk_status_persists_after_followup_get(client: TestClient) -> None:
    risk = client.get("/api/risks").json()["data"][0]

    updated = client.patch(
        f"/api/risks/{risk['risk_id']}/status",
        json={"status": "확인 중"},
    )

    assert updated.status_code == 200
    assert updated.json()["data"]["status"] == "확인 중"
    found = next(
        item
        for item in client.get("/api/risks").json()["data"]
        if item["risk_id"] == risk["risk_id"]
    )
    assert found["status"] == "확인 중"


def test_patch_missing_risk_returns_detail_error(client: TestClient) -> None:
    response = client.patch(
        "/api/risks/RISK-ORDER-999999/status",
        json={"status": "조치 완료"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "리스크를 찾을 수 없습니다."}
