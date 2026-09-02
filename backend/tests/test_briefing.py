"""자재 응답 조립(로트 상태와 위험 사유)에 대한 회귀 테스트.

`_build_material_response` 는 세션 없이도 동작하므로(전달된 자재 객체의
관계만 읽는다) DB를 띄우지 않고 경계 조건을 직접 만든다.
"""

from datetime import date

from app.db.models import Material, MaterialLot, PurchaseReceipt
from app.services.briefing import _build_material_response


REFERENCE_DATE = date(2026, 9, 1)


def _material(
    *,
    safety_stock: float,
    lots: list[MaterialLot] | None = None,
    receipts: list[PurchaseReceipt] | None = None,
) -> Material:
    material = Material(code="RM-01", name="가상 원자재 A", safety_stock=safety_stock)
    material.id = 1
    material.lots = lots or []
    material.purchase_receipts = receipts or []
    return material


def _lot(
    lot_number: str,
    quantity: float,
    *,
    warehouse: str = "원재료창고",
    received_date: date = REFERENCE_DATE,
    expiry_date: date | None = None,
) -> MaterialLot:
    return MaterialLot(
        lot_number=lot_number,
        warehouse=warehouse,
        quantity=quantity,
        received_date=received_date,
        expiry_date=expiry_date,
    )


def _state_by_lot(response) -> dict[str, str]:
    return {lot.lot_number: lot.state for lot in response.lots}


def test_a_lot_expired_before_the_reference_date_is_not_shown_as_available() -> None:
    # 기준일보다 앞서 만료된 로트는 가용 재고에도 폐기 수량에도 들어가지 않는다.
    # 상태를 따로 주지 않으면 `가용`으로 흘러가 쓸 수 없는 수량을 가용으로 읽힌다.
    response = _build_material_response(
        _material(
            safety_stock=10,
            lots=[
                _lot("LOT-OLD", 100, expiry_date=date(2026, 8, 30)),
                _lot("LOT-OK", 50),
            ],
        ),
        REFERENCE_DATE,
        {},
    )

    assert response.current_stock == 50
    assert _state_by_lot(response) == {"LOT-OLD": "만료", "LOT-OK": "가용"}
    available = sum(lot.quantity for lot in response.lots if lot.state == "가용")
    assert available == response.current_stock


def test_a_scheduled_receipt_discarded_in_the_horizon_is_labeled_as_discarded() -> None:
    # 요약이 폐기 수량을 말하는데 목록에 `기간 내 폐기` 로트가 없으면
    # 담당자가 어느 로트를 붙잡아야 할지 알 수 없다.
    response = _build_material_response(
        _material(
            safety_stock=10,
            receipts=[
                PurchaseReceipt(
                    scheduled_date=date(2026, 9, 3),
                    scheduled_quantity=100,
                    expiry_date=date(2026, 9, 5),
                )
            ],
        ),
        REFERENCE_DATE,
        {},
    )

    assert response.expiring_quantity == 100
    assert _state_by_lot(response) == {"LOT-RM-01-IN-01": "기간 내 폐기"}


def test_a_scheduled_receipt_kept_to_the_end_stays_labeled_as_scheduled() -> None:
    response = _build_material_response(
        _material(
            safety_stock=10,
            receipts=[
                PurchaseReceipt(
                    scheduled_date=date(2026, 9, 3),
                    scheduled_quantity=100,
                    expiry_date=None,
                )
            ],
        ),
        REFERENCE_DATE,
        {},
    )

    assert response.expiring_quantity == 0
    assert _state_by_lot(response) == {"LOT-RM-01-IN-01": "예정 입고"}


def test_a_shortage_present_from_day_one_is_not_blamed_on_a_later_discard() -> None:
    # 안전재고 200에 재고 150. 부족은 기준일부터 있었고 9월 5일 폐기는 그
    # 뒤에 일어난다. 폐기를 원인으로 말하면 담당자가 엉뚱한 로트를 붙잡는다.
    response = _build_material_response(
        _material(
            safety_stock=200,
            lots=[
                _lot("LOT-KEEP", 100),
                _lot("LOT-SOON", 50, expiry_date=date(2026, 9, 5)),
            ],
        ),
        REFERENCE_DATE,
        {},
    )

    assert response.severity == "주의"
    assert response.expiring_quantity == 50
    assert "폐기" not in response.reason


def test_a_discard_that_actually_drops_stock_below_safety_stock_is_reported() -> None:
    response = _build_material_response(
        _material(
            safety_stock=200,
            lots=[
                _lot("LOT-KEEP", 50),
                _lot("LOT-SOON", 250, expiry_date=date(2026, 9, 5)),
            ],
        ),
        REFERENCE_DATE,
        {},
    )

    assert response.severity == "주의"
    assert "유효기간 경과로" in response.reason


def test_only_the_discard_up_to_the_shortage_is_named_as_its_cause() -> None:
    # 9/3 에 40 이 폐기돼 재고가 바닥나고, 그 뒤 도착한 예정 입고 500 이 9/10 에
    # 또 폐기된다. 전체 폐기량(540)을 소진의 원인으로 적으면 담당자는 아직
    # 오지도 않았던 수량 때문에 재고가 떨어졌다고 읽게 된다.
    response = _build_material_response(
        _material(
            safety_stock=10,
            lots=[_lot("LOT-SOON", 40, expiry_date=date(2026, 9, 3))],
            receipts=[
                PurchaseReceipt(
                    scheduled_date=date(2026, 9, 6),
                    scheduled_quantity=500,
                    expiry_date=date(2026, 9, 10),
                )
            ],
        ),
        REFERENCE_DATE,
        {},
    )

    assert response.stockout_date == date(2026, 9, 3)
    assert response.expiring_quantity == 540
    assert "폐기 40.0으로" in response.reason


def test_a_scheduled_lot_sharing_a_lot_number_keeps_its_own_state() -> None:
    # 예정 입고의 가상 로트번호가 보유 로트와 겹쳐도 폐기 기록이 섞이면 안 된다.
    response = _build_material_response(
        _material(
            safety_stock=10,
            lots=[_lot("LOT-RM-01-IN-01", 40, expiry_date=date(2026, 12, 31))],
            receipts=[
                PurchaseReceipt(
                    scheduled_date=date(2026, 9, 3),
                    scheduled_quantity=60,
                    expiry_date=date(2026, 9, 5),
                )
            ],
        ),
        REFERENCE_DATE,
        {},
    )

    assert response.expiring_quantity == 60
    states = sorted(lot.state for lot in response.lots)
    assert states == ["가용", "기간 내 폐기"]
