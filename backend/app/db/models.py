from __future__ import annotations

from datetime import date

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy import and_, literal_column, or_
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.expression import ColumnElement
from sqlalchemy.types import String as StringType

from app.core.config import (
    BOM_LEVELS,
    DEFECTIVE_STOCK,
    FINISHED_GOODS_WAREHOUSES,
    GOOD_STOCK,
    INCOMING_INSPECTION,
    INSPECTION_RESULTS,
    INSPECTION_TYPES,
    ITEM_CODE_PREFIXES,
    ITEM_PHASES,
    ITEM_TYPES,
    MATERIAL_WAREHOUSES,
    OUTGOING_INSPECTION,
    PROCESSES,
    PRODUCT_WAREHOUSE,
    PROCESS_INSPECTION,
    QC_FAILED,
    QC_PASSED,
    QC_STATUSES,
    RAW_ITEM,
    SEMI_FINISHED_ITEM,
    STOCK_TYPES,
    UNITS_OF_MEASURE,
)
from app.db.base import Base


def _sql_value_list(names: tuple[str, ...]) -> str:
    """허용값 목록을 코드 상수에서 그대로 끌어와 CHECK 제약 SQL로 굽는다.

    목록을 손으로 옮겨 적으면 상수만 늘어나고 제약은 그대로 남는다.
    """
    return ", ".join(f"'{name}'" for name in names)


_ALLOWED_MATERIAL_WAREHOUSES_SQL = _sql_value_list(MATERIAL_WAREHOUSES)
_ALLOWED_FINISHED_GOODS_WAREHOUSES_SQL = _sql_value_list(FINISHED_GOODS_WAREHOUSES)
_ALLOWED_QC_STATUSES_SQL = _sql_value_list(QC_STATUSES)
_ALLOWED_INSPECTION_TYPES_SQL = _sql_value_list(INSPECTION_TYPES)
_ALLOWED_INSPECTION_RESULTS_SQL = _sql_value_list(INSPECTION_RESULTS)
_ALLOWED_ITEM_TYPES_SQL = _sql_value_list(ITEM_TYPES)
_ALLOWED_STOCK_TYPES_SQL = _sql_value_list(STOCK_TYPES)
_ALLOWED_PROCESSES_SQL = _sql_value_list(PROCESSES)
_ALLOWED_UNITS_OF_MEASURE_SQL = _sql_value_list(UNITS_OF_MEASURE)
_ALLOWED_ITEM_PHASES_SQL = _sql_value_list(ITEM_PHASES)
_ALLOWED_BOM_LEVELS_SQL = ", ".join(str(level) for level in BOM_LEVELS)

# 접두는 유형과 유일성만 맡는다(지적 ⑯). 유형과 접두는 정의상 서로를 결정하므로
# 양방향으로 건다 — 창고와 검사 결과처럼 나중에 갈라질 수 있는 두 사실이 아니라,
# 접두가 곧 유형의 표기이기 때문이다.
_ITEM_CODE_PREFIX_SQL = " AND ".join(
    f"((item_type = '{item_type}') = (code LIKE '{prefix}%'))"
    for item_type, prefix in ITEM_CODE_PREFIXES.items()
)

class BlankTrimmed(ColumnElement):
    """양끝의 공백·탭·개행을 걷어낸 값.

    1인자 `trim()` 은 공백(0x20)만 지운다. 탭·개행만 담긴 사유가 그대로 통과해
    화면에는 빈 칸으로 그려지므로, 지울 문자를 명시한 형태가 필요하다.

    그런데 그 형태의 이름이 엔진마다 다르다 — SQLite 는 `trim(x, y)` 이고
    PostgreSQL 은 `btrim(x, y)` 이며, 문자 코드를 만드는 함수도 `char` 과 `chr`
    로 갈린다. 그래서 SQL 을 문자열로 박지 않고 **방언이 정하게** 한다. 문자열로
    박으면 엔진을 옮길 때 CHECK 제약이 조용히 만들어지지 않거나 터진다.
    """

    type = StringType()
    inherit_cache = True

    def __init__(self, column_name: str) -> None:
        self.column_name = column_name


@compiles(BlankTrimmed, "sqlite")
def _compile_trim_blank_sqlite(element: BlankTrimmed, compiler, **_kw: object) -> str:
    return (
        f"trim({element.column_name},"
        " ' ' || char(9) || char(10) || char(13))"
    )


@compiles(BlankTrimmed, "postgresql")
def _compile_trim_blank_postgresql(
    element: BlankTrimmed, compiler, **_kw: object
) -> str:
    return (
        f"btrim({element.column_name},"
        " ' ' || chr(9) || chr(10) || chr(13))"
    )


@compiles(BlankTrimmed)
def _compile_trim_blank_default(
    element: BlankTrimmed, compiler, **_kw: object
) -> str:
    """표준 SQL 형태. 문자 집합을 리터럴로 적어 함수 이름 차이를 피한다."""
    return f"trim(both ' \t\n\r' from {element.column_name})"


def failure_reason_is_present() -> ColumnElement:
    """「불합격이면 사유가 비어 있지 않다」를 나타내는 식.

    마이그레이션도 이 함수를 부른다. 자동 생성이 구워 낸 SQL 문자열을 그대로
    두면 SQLite 문법이 마이그레이션에 박혀, PostgreSQL 에서는 표가 만들어지지
    않거나 뜻이 다른 제약이 선다 — 제약으로 규칙을 지키는 구조에서 그것은
    규칙이 조용히 사라지는 일이다.
    """
    return or_(
        literal_column("result") == QC_PASSED,
        and_(
            literal_column("reason").is_not(None),
            BlankTrimmed("reason") != "",
        ),
    )


# 검사 유형마다 대상 테이블이 다르므로 nullable FK 를 셋 두고, "유형에 맞는
# 대상 하나만 채워져 있음" 을 DB 가 강제하게 한다. 범용 (target_type,
# target_id) 컬럼으로 두면 존재하지 않는 대상을 가리키는 기록을 막을 수 없다.
_INSPECTION_TARGET_SQL = " OR ".join(
    f"(inspection_type = '{inspection_type}'"
    + "".join(
        f" AND {column} IS {'NOT NULL' if column == target_column else 'NULL'}"
        for column in (
            "material_lot_id",
            "daily_production_id",
            "finished_goods_lot_id",
        )
    )
    + ")"
    for inspection_type, target_column in (
        (INCOMING_INSPECTION, "material_lot_id"),
        (PROCESS_INSPECTION, "daily_production_id"),
        (OUTGOING_INSPECTION, "finished_goods_lot_id"),
    )
)


class Item(Base):
    """전사 기준정보의 품목 한 표(지적 ⑧).

    `products` 와 `materials` 를 하나로 모은 표다. 두 표가 `shelf_life_days`
    라는 같은 이름의 칸을 각자 들고 있었다는 것 자체가 표가 하나여야 한다는
    신호였고, 반제품은 **만들어지면서 쓰이므로** 두 표 어느 쪽에도 온전히
    속하지 못해 앉을 자리가 아예 없었다.

    한 표가 되면서 안전재고 · 유효기간 · 리드타임 계수가 한 곳에 모인다.
    유형에 따라 비는 칸이 생기는 것은 통합의 부작용이 아니라 **정상**이다 —
    한 표라야 「이 유형에는 해당 없음」이라고 말할 수 있다.
    """

    __tablename__ = "items"
    __table_args__ = (
        CheckConstraint(
            f"item_type IN ({_ALLOWED_ITEM_TYPES_SQL})",
            name="ck_item_type",
        ),
        CheckConstraint(_ITEM_CODE_PREFIX_SQL, name="ck_item_code_prefix"),
        CheckConstraint(
            f"process IS NULL OR process IN ({_ALLOWED_PROCESSES_SQL})",
            name="ck_item_process",
        ),
        CheckConstraint(
            f"stock_uom IN ({_ALLOWED_UNITS_OF_MEASURE_SQL})",
            name="ck_item_stock_uom",
        ),
        CheckConstraint(
            f"phase IN ({_ALLOWED_ITEM_PHASES_SQL})",
            name="ck_item_phase",
        ),
        # 「반제품은 유효기간을 두지 않고 제품만 유효기간을 정한다」(발화). 표가
        # 하나여서 이 규칙을 제약으로 적을 수 있게 됐다.
        CheckConstraint(
            f"item_type <> '{SEMI_FINISHED_ITEM}' OR shelf_life_days IS NULL",
            name="ck_item_semi_finished_has_no_shelf_life",
        ),
        # 통합 전 `materials.safety_stock` 은 NOT NULL 이었다. 칸이 완제품과
        # 겸용이 되면서 nullable 로 넓어졌는데, **원자재만은 그 불변식을
        # 유지해야** 한다 — 자재 리스크가 이 값을 재고와 곧바로 견주므로
        # (`material_risk.calculate_material_risk`) 비어 있으면 비교에서 터진다.
        # 완제품은 아직 정한 사람이 없어 비어 있는 것이 맞다.
        CheckConstraint(
            f"item_type <> '{RAW_ITEM}' OR safety_stock IS NOT NULL",
            name="ck_item_raw_has_safety_stock",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    item_type: Mapped[str] = mapped_column(String(20), index=True)
    # 검사 기준을 끌어오는 라벨(지적 ⑯). 접두가 아니라 명시적인 열이어야
    # 공정이 바뀔 때 품목 코드를 바꾸지 않는다.
    process: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # 재고 단위(지적 ㉛). 모든 수량이 이 단위로 저장된다 — 잔량을 수불의 합으로
    # 내린 이상 합할 수 있으려면 단위가 하나여야 하기 때문이다.
    stock_uom: Mapped[str] = mapped_column(String(10))
    # 초기 · 양산. 게이트와 지표가 다르다(Ppk 1.67 / Cpk 1.33).
    phase: Mapped[str] = mapped_column(String(10))
    # 사내 프로세스가 정한 유효기간 설정기간(일). 로트의 유효기간은 이 값에서
    # 파생된다. None 이면 무기한 품목이다.
    shelf_life_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 통합의 이득이 그대로 드러나는 칸이다 — 자재에만 있던 것이 완제품에도
    # 생겼다. 아직 값을 정한 사람이 없는 품목은 None 이다.
    safety_stock: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 리드타임은 품목의 값이 아니라 오더마다 다른 **계산 결과**다. 품목이 갖는
    # 것은 계수 둘이고, 소요 시간 = 준비시간 + 개당 시간 × 수량이다.
    # 상수로 두면 100개와 1000개가 같은 시각에 착수한다.
    setup_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    hours_per_unit: Mapped[float | None] = mapped_column(Float, nullable=True)

    orders: Mapped[list[Order]] = relationship(back_populates="item")
    # BOM 이 상위·하위로 넓어지면서 한 품목이 두 방향의 관계를 갖는다.
    components: Mapped[list[BomComponent]] = relationship(
        back_populates="parent_item",
        foreign_keys="BomComponent.parent_item_id",
    )
    used_in: Mapped[list[BomComponent]] = relationship(
        back_populates="child_item",
        foreign_keys="BomComponent.child_item_id",
    )
    purchase_receipts: Mapped[list[PurchaseReceipt]] = relationship(back_populates="item")
    material_lots: Mapped[list[MaterialLot]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
    )
    finished_goods_lots: Mapped[list[FinishedGoodsLot]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
    )


class BomComponent(Base):
    """2단 고정 BOM 한 줄 — 상위품목이 하위품목을 얼마나 쓰는가.

    제품 ↔ 자재 직결이던 것을 상위 ↔ 하위로 넓힌다. 「단계」 열 하나가 재귀를
    막아 전개가 두 번으로 고정되므로, 계산이 단순하고 테스트할 경우의 수가
    유한하다.
    """

    __tablename__ = "bom_components"
    __table_args__ = (
        UniqueConstraint(
            "parent_item_id",
            "child_item_id",
            name="uq_bom_component_parent_child",
        ),
        CheckConstraint(
            f"level IN ({_ALLOWED_BOM_LEVELS_SQL})",
            name="ck_bom_component_level",
        ),
        CheckConstraint(
            "parent_item_id <> child_item_id",
            name="ck_bom_component_not_self_referencing",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    child_item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    # 1단 — 완제품 ← 반제품 · 2단 — 반제품 ← 원자재
    level: Mapped[int] = mapped_column(Integer)
    unit_quantity: Mapped[float] = mapped_column(Float)

    parent_item: Mapped[Item] = relationship(
        back_populates="components",
        foreign_keys=[parent_item_id],
    )
    child_item: Mapped[Item] = relationship(
        back_populates="used_in",
        foreign_keys=[child_item_id],
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    due_date: Mapped[date] = mapped_column(Date)
    planned_quantity: Mapped[float] = mapped_column(Float)

    item: Mapped[Item] = relationship(back_populates="orders")
    daily_productions: Mapped[list[DailyProduction]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )


class DailyProduction(Base):
    __tablename__ = "daily_productions"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    work_date: Mapped[date] = mapped_column(Date)
    planned_quantity: Mapped[float] = mapped_column(Float)
    actual_quantity: Mapped[float] = mapped_column(Float)

    order: Mapped[Order] = relationship(back_populates="daily_productions")
    inspections: Mapped[list[QualityInspection]] = relationship(
        back_populates="daily_production",
        passive_deletes=True,
    )


class PurchaseReceipt(Base):
    __tablename__ = "purchase_receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    scheduled_date: Mapped[date] = mapped_column(Date)
    scheduled_quantity: Mapped[float] = mapped_column(Float)
    # 도착하면 로트가 되므로 예정 입고도 유효기간을 가진다. 도착지는 원재료창고다.
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    item: Mapped[Item] = relationship(back_populates="purchase_receipts")


class MaterialLot(Base):
    """자재의 로트별 보유 재고.

    같은 로트번호가 두 창고에 나뉘어 존재할 수 있으므로(원재료창고 100EA 중
    50EA를 생산창고로 이동한 상태) 유일키는 로트번호 단독이 아니라
    (자재, 로트번호, 창고) 조합이다. 로트번호는 자재에 종속된 개념이므로
    자재까지 넣어야, 공급사가 부여한 번호를 그대로 쓰는 단계에서 서로 다른
    자재가 같은 번호를 들고 와도 충돌하지 않는다.

    창고는 `원재료창고`/`생산창고` 둘로 제한한다. 제품창고에는 자재가 아니라
    완제품이 들어가므로(`FinishedGoodsLot`) 이 목록에서 뺀다.
    """

    __tablename__ = "material_lots"
    __table_args__ = (
        UniqueConstraint(
            "item_id",
            "lot_number",
            "warehouse",
            name="uq_material_lot_warehouse",
        ),
        CheckConstraint(
            f"warehouse IN ({_ALLOWED_MATERIAL_WAREHOUSES_SQL})",
            name="ck_material_lot_warehouse",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    lot_number: Mapped[str] = mapped_column(String(50), index=True)
    warehouse: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[float] = mapped_column(Float)
    received_date: Mapped[date] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    item: Mapped[Item] = relationship(back_populates="material_lots")
    inspections: Mapped[list[QualityInspection]] = relationship(
        back_populates="material_lot",
        passive_deletes=True,
    )


class FinishedGoodsLot(Base):
    """생산된 완제품의 로트별 보유 재고.

    완제품은 자재가 아니라 제품이므로 `MaterialLot` 과 별도 테이블이다. 로트는
    생산 실적(`DailyProduction.actual_quantity`)에서 파생되며, 어긋날 때 진실은
    실적 쪽이다(이 저장소의 쓰기 경로는 시드뿐이라 어긋날 경로가 없다).

    로트 행은 삭제하지 않는다. 유효기간이 지나도 `만료` 로 표시할 뿐 남긴다.

    창고는 `생산창고`/`제품창고` 둘이다. 제품창고에 들어오는 조건은 검사 합격이지만
    **그 역은 성립하지 않는다**(지적 ①) — 제품창고 안에서 양불이동으로 불량품이
    갈리고, 합격이면서 아직 입고 처리가 안 된 로트도 있을 수 있다. 그래서 두
    사실을 양방향 하나가 아니라 **단방향 둘**로 건다.

    날짜가 둘인 것은 유효기간의 기산점이 생산일이 아니라 합격일이기 때문이다
    (지적 ⑰). 둘의 차이가 「검사에 며칠 걸렸나」가 되어, 생산창고에 완제품이
    쌓이는 이유를 그 값이 설명한다.
    """

    __tablename__ = "finished_goods_lots"
    __table_args__ = (
        UniqueConstraint(
            "item_id",
            "lot_number",
            "warehouse",
            name="uq_finished_goods_lot_warehouse",
        ),
        CheckConstraint(
            f"warehouse IN ({_ALLOWED_FINISHED_GOODS_WAREHOUSES_SQL})",
            name="ck_finished_goods_lot_warehouse",
        ),
        CheckConstraint(
            f"qc_status IN ({_ALLOWED_QC_STATUSES_SQL})",
            name="ck_finished_goods_lot_qc_status",
        ),
        CheckConstraint(
            f"stock_type IN ({_ALLOWED_STOCK_TYPES_SQL})",
            name="ck_finished_goods_lot_stock_type",
        ),
        # 지적 ① — 양방향 하나를 단방향 둘로 가른다.
        #
        # ① 제품창고에 있으면 합격이다. 검사 대기·불합격이 섞이면 출하 가능
        #    수량이 실제보다 많아 보인다.
        # ② 불량품이면 불합격이다. 재고구분은 판정에서 나오는 것이지 사람이
        #    임의로 붙이는 딱지가 아니다.
        #
        # 역방향은 걸지 않는다. 「합격이면 반드시 제품창고」로 못박으면 합격했으나
        # 아직 입고 처리 전인 로트가 표현되지 않고, 관문 6(재고이동 요청·처리)이
        # 들어오는 자리가 제약에 막힌다.
        CheckConstraint(
            f"warehouse <> '{PRODUCT_WAREHOUSE}' OR qc_status = '{QC_PASSED}'",
            name="ck_finished_goods_lot_product_warehouse_holds_passed_only",
        ),
        CheckConstraint(
            f"stock_type <> '{DEFECTIVE_STOCK}' OR qc_status = '{QC_FAILED}'",
            name="ck_finished_goods_lot_defective_is_rejected",
        ),
        # 합격일은 합격에만 붙는다(지적 ⑰). 시계가 합격에서 시작한다고 정한
        # 이상, 검사 대기·불합격 로트에 합격일이 있으면 유효기간이 없는 판정에서
        # 파생되고, 합격인데 합격일이 없으면 시계가 시작되지 않는다.
        CheckConstraint(
            f"(passed_date IS NOT NULL) = (qc_status = '{QC_PASSED}')",
            name="ck_finished_goods_lot_passed_date_matches_status",
        ),
        # 합격일이 생산일보다 앞설 수 없다. 뒤집히면 「검사에 며칠 걸렸나」가
        # 음수가 된다 — 지적 ⑰ 이 공짜로 얻는다고 한 그 지표다.
        CheckConstraint(
            "passed_date IS NULL OR passed_date >= produced_date",
            name="ck_finished_goods_lot_passed_after_produced",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    lot_number: Mapped[str] = mapped_column(String(50), index=True)
    warehouse: Mapped[str] = mapped_column(String(20))
    # OQC 판정의 캐시다. 진실은 `QualityInspection` 의 OQC 기록이며, 기록이
    # 없으면 `검사 대기`다. 캐시를 두는 이유는 위 창고 불변식을 CHECK 제약으로
    # 걸기 위해서다(테이블 간 참조는 SQLite CHECK 로 표현할 수 없다).
    qc_status: Mapped[str] = mapped_column(String(20))
    # 양품 · 불량품. 지금은 판정에서 그대로 나오지만, 관문 8(양불이동)이 들어오면
    # 총량을 바꾸지 않고 이 칸만 바꾸는 수불 줄이 생긴다.
    stock_type: Mapped[str] = mapped_column(String(10), default=GOOD_STOCK)
    quantity: Mapped[float] = mapped_column(Float)
    produced_date: Mapped[date] = mapped_column(Date)
    # 합격일 — 유효기간의 기산점이다(지적 ⑰). 아직 판정을 받지 않았거나
    # 불합격한 로트는 값이 없다. 생산일과의 차이가 곧 검사 대기 일수다.
    passed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 재작업분인가(30판). 로트번호에 `+R` 을 붙이는 관행은 라벨과 맞추기 위해
    # 그대로 두되, 판정은 번호가 아니라 이 칸에서 읽는다 — 번호는 사람이 보는
    # 라벨이고 분기는 프로그램이 하는 일이다.
    reworked: Mapped[bool] = mapped_column(Boolean, default=False)
    # 제품의 설정기간을 합격일에 더해 파생한다. 합격일이 없으면 유효기간도
    # 아직 없다 — 시계는 합격에서 시작한다. 무기한 품목도 None 이다.
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    item: Mapped[Item] = relationship(back_populates="finished_goods_lots")
    inspections: Mapped[list[QualityInspection]] = relationship(
        back_populates="finished_goods_lot",
        passive_deletes=True,
    )


class QualityInspection(Base):
    """IQC·PQC·OQC 검사 기록.

    유형마다 대상이 다르다 — IQC 는 자재 로트, PQC 는 생산 실적, OQC 는 완제품
    로트다. 유형별 테이블을 셋 두면 품질관리 화면이 세 갈래로 갈라지므로 한
    테이블에 두고, 유형과 대상이 어긋나지 않도록 CHECK 제약을 건다.

    `result` 에 `검사 대기` 가 없는 것은 검사를 하지 않은 것이 판정이 아니기
    때문이다. 검사 대기는 **기록이 없는 상태**로 표현한다.
    """

    __tablename__ = "quality_inspections"
    __table_args__ = (
        CheckConstraint(
            f"inspection_type IN ({_ALLOWED_INSPECTION_TYPES_SQL})",
            name="ck_quality_inspection_type",
        ),
        CheckConstraint(
            f"result IN ({_ALLOWED_INSPECTION_RESULTS_SQL})",
            name="ck_quality_inspection_result",
        ),
        CheckConstraint(
            _INSPECTION_TARGET_SQL,
            name="ck_quality_inspection_target",
        ),
        # 불합격은 사유 없이 남기면 담당자가 무엇을 조치할지 알 수 없다.
        # 빈 문자열과 공백뿐인 문자열도 사유가 없는 것이므로 NULL 검사만으로는
        # 부족하다 — 화면은 그 빈 칸을 그대로 그려 사유 없는 불합격 행을 만든다.
        CheckConstraint(
            failure_reason_is_present(),
            name="ck_quality_inspection_failure_reason",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_type: Mapped[str] = mapped_column(String(10), index=True)
    inspected_date: Mapped[date] = mapped_column(Date)
    result: Mapped[str] = mapped_column(String(20))
    # 불합격 사유. 합격이면 None 이다.
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # 검사 기록은 대상에 딸린 부속이 아니라 감사 기록이다. 대상을 지운다고
    # 함께 지워지면 안 되므로 `delete-orphan` 을 쓰지 않고, 검사 기록이 남아
    # 있는 대상은 DB 가 삭제를 거부하게 한다(RESTRICT). 관계 쪽 대응은
    # `passive_deletes=True` 로 넘겨 SQLAlchemy 가 대신 지우지 않게 한다.
    material_lot_id: Mapped[int | None] = mapped_column(
        ForeignKey("material_lots.id", ondelete="RESTRICT"), nullable=True
    )
    daily_production_id: Mapped[int | None] = mapped_column(
        ForeignKey("daily_productions.id", ondelete="RESTRICT"), nullable=True
    )
    finished_goods_lot_id: Mapped[int | None] = mapped_column(
        ForeignKey("finished_goods_lots.id", ondelete="RESTRICT"), nullable=True
    )

    material_lot: Mapped[MaterialLot | None] = relationship(
        back_populates="inspections"
    )
    daily_production: Mapped[DailyProduction | None] = relationship(
        back_populates="inspections"
    )
    finished_goods_lot: Mapped[FinishedGoodsLot | None] = relationship(
        back_populates="inspections"
    )


class RiskStatus(Base):
    __tablename__ = "risk_statuses"

    id: Mapped[int] = mapped_column(primary_key=True)
    risk_key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="신규")
