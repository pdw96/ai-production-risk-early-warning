"""테스트가 쓰는 품목 생성기.

품목 표가 하나로 합쳐지면서 모든 품목이 유형 · 재고 단위 · 단계를 갖게 됐다.
테스트가 알고 싶은 것은 대개 코드와 이름뿐이므로, 나머지는 여기서 기본값을
채운다. 기본값을 각 테스트에 흩어 놓으면 칸이 하나 늘 때마다 스무 곳을 고친다.
"""

from typing import Any

from app.core.config import (
    FINISHED_ITEM,
    INCOMING_PROCESS,
    LAMINATING_PROCESS,
    MASS_PRODUCTION_PHASE,
    PROCESSES,
    RAW_ITEM,
    SEMI_FINISHED_ITEM,
    UNITS_OF_MEASURE,
)
from app.core import codes
from app.db.master_data import CodeGroup, CommonCode
from app.db.models import Item


def seed_referenced_codes(session: Any) -> None:
    """품목이 가리키는 공통코드를 넣는다.

    공정과 재고 단위는 늘 수 있는 그룹이라 허용값이 파이썬 상수가 아니라
    공통코드에 있고, 품목은 그것을 복합 외래키로 가리킨다. 그래서 품목 하나를
    넣으려면 그 코드가 **먼저 있어야** 한다 — 시드는 공통코드부터 넣지만,
    표만 만들고 시작하는 테스트에는 그 앞줄이 없다.
    """
    for group_code, values in (
        (codes.PROCESS, PROCESSES),
        (codes.UOM, UNITS_OF_MEASURE),
    ):
        session.add(
            CodeGroup(
                group_code=group_code,
                name=group_code,
                # 이 둘은 값이 늘 수 있는 그룹이다 — 품목이 상수가 아니라
                # 코드를 가리키게 된 이유가 그것이다.
                value_fixed=False,
                description=group_code,
            )
        )
        for order, value in enumerate(values):
            session.add(
                CommonCode(
                    group_code=group_code,
                    code=value,
                    name=value,
                    sort_order=order,
                )
            )
    session.flush()


def finished_item(*, code: str, name: str, **overrides: Any) -> Item:
    """완제품 한 줄. 안전재고 칸은 통합으로 생겼을 뿐 기본값이 없다."""
    return _item(code, name, FINISHED_ITEM, LAMINATING_PROCESS, "EA", overrides)


def semi_finished_item(*, code: str, name: str, **overrides: Any) -> Item:
    """반제품 한 줄. 통합 전에는 앉을 자리가 아예 없던 유형이다."""
    return _item(code, name, SEMI_FINISHED_ITEM, LAMINATING_PROCESS, "EA", overrides)


def raw_item(*, code: str, name: str, **overrides: Any) -> Item:
    """원자재 한 줄. 수입검사 공정에서 검사 기준을 끌어온다."""
    return _item(code, name, RAW_ITEM, INCOMING_PROCESS, "kg", overrides)


def _item(
    code: str,
    name: str,
    item_type: str,
    process: str,
    stock_uom: str,
    overrides: dict[str, Any],
) -> Item:
    values: dict[str, Any] = {
        "item_type": item_type,
        "process": process,
        "stock_uom": stock_uom,
        "phase": MASS_PRODUCTION_PHASE,
    }
    values.update(overrides)
    return Item(code=code, name=name, **values)
