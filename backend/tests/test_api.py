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
        "product_trends",
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


def test_seeded_material_shortage_is_exposed_across_risk_apis(
    client: TestClient,
) -> None:
    materials = client.get("/api/materials").json()["data"]
    shortage_materials = [item for item in materials if item["shortage_expected"]]
    dashboard = client.get("/api/dashboard").json()["data"]
    risks = client.get("/api/risks").json()["data"]

    assert shortage_materials
    assert dashboard["kpis"]["material_shortage_count"] == len(shortage_materials)
    assert dashboard["top_material_risks"]
    assert {
        risk["entity_id"] for risk in risks if risk["risk_type"] == "자재"
    } == {material["material_id"] for material in shortage_materials}


def test_dashboard_prioritizes_danger_orders_with_stable_order_id_tiebreaker(
    client: TestClient,
) -> None:
    top_order_risks = client.get("/api/dashboard").json()["data"][
        "top_order_risks"
    ]

    assert [order["severity"] for order in top_order_risks] == ["위험"] * 5
    assert [order["order_id"] for order in top_order_risks] == [1, 4, 7, 10, 13]


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
                "raw_warehouse_stock",
                "production_warehouse_stock",
                "safety_stock",
                "ending_stock",
                "minimum_stock",
                "shortage_expected",
                "stockout_date",
                "expiring_quantity",
                "first_expiry_date",
                "lots",
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


def test_materials_expose_lot_level_stock_with_warehouses(client: TestClient) -> None:
    materials = client.get("/api/materials").json()["data"]

    lots = [lot for material in materials for lot in material["lots"]]
    assert lots
    assert {"lot_number", "warehouse", "quantity", "received_date", "expiry_date", "state"} <= set(
        lots[0]
    )
    assert {lot["warehouse"] for lot in lots} == {"원재료창고", "생산창고"}
    assert {lot["state"] for lot in lots} >= {"가용", "예정 입고", "기간 내 폐기"}


def test_a_lot_split_across_warehouses_is_visible_in_the_materials_api(
    client: TestClient,
) -> None:
    """원재료창고 재고 일부를 생산창고로 옮긴 로트가 응답에 그대로 드러난다."""
    materials = client.get("/api/materials").json()["data"]

    split_materials = [
        material
        for material in materials
        if len({lot["lot_number"] for lot in material["lots"]}) < len(material["lots"])
    ]

    assert split_materials
    material = split_materials[0]
    assert material["raw_warehouse_stock"] > 0
    assert material["production_warehouse_stock"] > 0


def test_expiring_lots_drive_a_material_risk_with_an_expiry_reason(
    client: TestClient,
) -> None:
    materials = client.get("/api/materials").json()["data"]
    risks = client.get("/api/risks").json()["data"]

    expiry_driven = [
        material
        for material in materials
        if material["expiring_quantity"] > 0 and material["shortage_expected"]
    ]
    assert expiry_driven
    assert all("유효기간" in material["reason"] for material in expiry_driven)
    assert {
        f"RISK-MATERIAL-{material['material_id']:03d}" for material in expiry_driven
    } <= {risk["risk_id"] for risk in risks}


def test_master_data_lists_product_and_material_item_codes(client: TestClient) -> None:
    data = client.get("/api/master-data").json()["data"]

    assert set(data) == {"items", "bom_requirements"}
    items = data["items"]
    assert {item["item_type"] for item in items} == {"제품", "자재"}
    assert len([item for item in items if item["item_type"] == "제품"]) == 5
    assert len([item for item in items if item["item_type"] == "자재"]) == 15
    assert {"item_type", "item_code", "item_name", "safety_stock", "lot_count", "linked_item_count"} <= set(
        items[0]
    )


def test_master_data_leaves_stock_fields_empty_for_products(client: TestClient) -> None:
    """제품에는 안전재고와 로트 개념이 없다."""
    items = client.get("/api/master-data").json()["data"]["items"]

    products = [item for item in items if item["item_type"] == "제품"]
    materials = [item for item in items if item["item_type"] == "자재"]

    assert all(item["safety_stock"] is None and item["lot_count"] is None for item in products)
    assert all(
        item["safety_stock"] is not None and item["lot_count"] is not None
        for item in materials
    )


def test_master_data_bom_links_every_product_to_its_materials(client: TestClient) -> None:
    data = client.get("/api/master-data").json()["data"]

    bom = data["bom_requirements"]
    assert len(bom) == 15
    assert {"product_code", "product_name", "material_code", "material_name", "unit_quantity"} <= set(
        bom[0]
    )
    # 목록은 제품 코드 → 자재 코드 순으로 안정 정렬된다.
    assert bom == sorted(bom, key=lambda row: (row["product_code"], row["material_code"]))
    linked_counts = {
        item["item_code"]: item["linked_item_count"]
        for item in data["items"]
        if item["item_type"] == "제품"
    }
    for product_code, expected in linked_counts.items():
        assert len([row for row in bom if row["product_code"] == product_code]) == expected


def test_purchases_expose_the_inbound_schedule_with_horizon_flag(
    client: TestClient,
) -> None:
    receipts = client.get("/api/purchases").json()["data"]

    assert len(receipts) == 15
    assert {
        "receipt_id",
        "material_code",
        "material_name",
        "scheduled_date",
        "scheduled_quantity",
        "expiry_date",
        "days_until_arrival",
        "within_horizon",
    } <= set(receipts[0])
    # 입고 예정일 오름차순으로 정렬된다.
    assert [item["scheduled_date"] for item in receipts] == sorted(
        item["scheduled_date"] for item in receipts
    )
    assert all(receipt["expiry_date"] is not None for receipt in receipts)


def test_purchase_horizon_flag_matches_the_fourteen_day_window(
    client: TestClient,
) -> None:
    receipts = client.get("/api/purchases").json()["data"]

    for receipt in receipts:
        assert receipt["within_horizon"] == (0 <= receipt["days_until_arrival"] <= 13)


def test_production_results_cover_fourteen_days_newest_first(client: TestClient) -> None:
    results = client.get("/api/production-results").json()["data"]

    assert len(results) == 14
    assert {
        "work_date",
        "planned_quantity",
        "actual_quantity",
        "achievement_rate",
        "active_order_count",
    } <= set(results[0])
    dates = [item["work_date"] for item in results]
    assert dates == sorted(dates, reverse=True)


def test_production_results_report_a_plan_gap_rather_than_a_flat_hundred_percent(
    client: TestClient,
) -> None:
    """계획과 실적이 늘 같으면 달성률 화면이 아무것도 말해주지 않는다."""
    results = client.get("/api/production-results").json()["data"]

    rates = {item["achievement_rate"] for item in results}
    assert len(rates) > 1
    assert any(rate < 100 for rate in rates)
    assert any(rate > 100 for rate in rates)


def test_production_result_achievement_rate_matches_plan_and_actual(
    client: TestClient,
) -> None:
    results = client.get("/api/production-results").json()["data"]

    for item in results:
        assert item["planned_quantity"] > 0
        expected = round(item["actual_quantity"] / item["planned_quantity"] * 100, 1)
        assert item["achievement_rate"] == expected
        assert item["active_order_count"] == 30


def test_production_result_totals_agree_with_the_dashboard_trend(
    client: TestClient,
) -> None:
    """같은 날짜의 수치를 두 화면이 다르게 말하면 안 된다."""
    results = {
        item["work_date"]: item
        for item in client.get("/api/production-results").json()["data"]
    }
    trend = client.get("/api/dashboard").json()["data"]["production_trend"]

    assert trend
    for point in trend:
        matched = results[point["work_date"]]
        assert matched["planned_quantity"] == point["planned_quantity"]
        assert matched["actual_quantity"] == point["actual_quantity"]


def test_dashboard_splits_the_trend_by_product(client: TestClient) -> None:
    data = client.get("/api/dashboard").json()["data"]

    trends = data["product_trends"]
    assert len(trends) == 5
    assert {"product_code", "product_name", "points"} <= set(trends[0])
    assert [trend["product_code"] for trend in trends] == sorted(
        trend["product_code"] for trend in trends
    )
    for trend in trends:
        assert len(trend["points"]) == 7


def test_product_trends_share_the_date_axis_with_the_total_trend(
    client: TestClient,
) -> None:
    """축이 어긋나면 제품을 바꿀 때마다 그래프가 튄다."""
    data = client.get("/api/dashboard").json()["data"]

    total_dates = [point["work_date"] for point in data["production_trend"]]
    for trend in data["product_trends"]:
        assert [point["work_date"] for point in trend["points"]] == total_dates


def test_product_trends_add_up_to_the_total_trend(client: TestClient) -> None:
    data = client.get("/api/dashboard").json()["data"]

    for index, total_point in enumerate(data["production_trend"]):
        planned = sum(trend["points"][index]["planned_quantity"] for trend in data["product_trends"])
        actual = sum(trend["points"][index]["actual_quantity"] for trend in data["product_trends"])
        assert round(planned, 2) == total_point["planned_quantity"]
        assert round(actual, 2) == total_point["actual_quantity"]


def test_lot_state_reports_disposal_only_when_the_lot_is_actually_discarded(
    client: TestClient,
) -> None:
    """유효기간이 기간 안이어도 수요가 먼저 먹었으면 폐기가 아니다."""
    materials = client.get("/api/materials").json()["data"]

    for material in materials:
        discarded = [lot for lot in material["lots"] if lot["state"] == "기간 내 폐기"]
        if discarded:
            assert material["expiring_quantity"] > 0
        else:
            assert material["expiring_quantity"] == 0


def test_expiry_is_named_as_the_cause_only_when_it_precedes_the_stockout(
    client: TestClient,
) -> None:
    materials = client.get("/api/materials").json()["data"]

    for material in materials:
        if "유효기간" in material["reason"]:
            assert material["expiring_quantity"] > 0
            assert material["first_expiry_date"] is not None
            if material["stockout_date"] is not None:
                assert material["first_expiry_date"] <= material["stockout_date"]


def test_every_product_stays_selectable_in_the_trend_even_without_recent_output(
    client: TestClient,
) -> None:
    """최근 7일 실적이 없어도 제품이 선택지에서 사라지면 안 된다."""
    product_codes = {
        item["item_code"]
        for item in client.get("/api/master-data").json()["data"]["items"]
        if item["item_type"] == "제품"
    }
    trends = client.get("/api/dashboard").json()["data"]["product_trends"]

    assert {trend["product_code"] for trend in trends} == product_codes
