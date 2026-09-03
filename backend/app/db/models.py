from __future__ import annotations

from datetime import date

from sqlalchemy import (
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import (
    FINISHED_GOODS_WAREHOUSE,
    FINISHED_GOODS_WAREHOUSES,
    INCOMING_INSPECTION,
    INSPECTION_RESULTS,
    INSPECTION_TYPES,
    MATERIAL_WAREHOUSES,
    OUTGOING_INSPECTION,
    PROCESS_INSPECTION,
    QC_PASSED,
    QC_STATUSES,
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


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    # 사내 프로세스가 정한 유효기간 설정기간(일). 로트의 유효기간은 이 값에서
    # 파생된다. None 이면 무기한 품목이다.
    shelf_life_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    orders: Mapped[list[Order]] = relationship(back_populates="product")
    bom_requirements: Mapped[list[BomRequirement]] = relationship(back_populates="product")
    finished_goods_lots: Mapped[list[FinishedGoodsLot]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    due_date: Mapped[date] = mapped_column(Date)
    planned_quantity: Mapped[float] = mapped_column(Float)

    product: Mapped[Product] = relationship(back_populates="orders")
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
        cascade="all, delete-orphan",
    )


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    safety_stock: Mapped[float] = mapped_column(Float)
    # 제품과 같은 의미의 설정기간(일). None 이면 무기한 품목이다.
    shelf_life_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    bom_requirements: Mapped[list[BomRequirement]] = relationship(back_populates="material")
    purchase_receipts: Mapped[list[PurchaseReceipt]] = relationship(back_populates="material")
    lots: Mapped[list[MaterialLot]] = relationship(
        back_populates="material",
        cascade="all, delete-orphan",
    )


class BomRequirement(Base):
    __tablename__ = "bom_requirements"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"))
    unit_quantity: Mapped[float] = mapped_column(Float)

    product: Mapped[Product] = relationship(back_populates="bom_requirements")
    material: Mapped[Material] = relationship(back_populates="bom_requirements")


class PurchaseReceipt(Base):
    __tablename__ = "purchase_receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"))
    scheduled_date: Mapped[date] = mapped_column(Date)
    scheduled_quantity: Mapped[float] = mapped_column(Float)
    # 도착하면 로트가 되므로 예정 입고도 유효기간을 가진다. 도착지는 원재료창고다.
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    material: Mapped[Material] = relationship(back_populates="purchase_receipts")


class MaterialLot(Base):
    """자재의 로트별 보유 재고.

    같은 로트번호가 두 창고에 나뉘어 존재할 수 있으므로(원재료창고 100EA 중
    50EA를 생산창고로 이동한 상태) 유일키는 로트번호 단독이 아니라
    (자재, 로트번호, 창고) 조합이다. 로트번호는 자재에 종속된 개념이므로
    자재까지 넣어야, 공급사가 부여한 번호를 그대로 쓰는 단계에서 서로 다른
    자재가 같은 번호를 들고 와도 충돌하지 않는다.

    창고는 `원재료창고`/`생산창고` 둘로 제한한다. 완제품창고에는 자재가 아니라
    완제품이 들어가므로(`FinishedGoodsLot`) 이 목록에서 뺀다.
    """

    __tablename__ = "material_lots"
    __table_args__ = (
        UniqueConstraint(
            "material_id",
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
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"))
    lot_number: Mapped[str] = mapped_column(String(50), index=True)
    warehouse: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[float] = mapped_column(Float)
    received_date: Mapped[date] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    material: Mapped[Material] = relationship(back_populates="lots")
    inspections: Mapped[list[QualityInspection]] = relationship(
        back_populates="material_lot",
        cascade="all, delete-orphan",
    )


class FinishedGoodsLot(Base):
    """생산된 완제품의 로트별 보유 재고.

    완제품은 자재가 아니라 제품이므로 `MaterialLot` 과 별도 테이블이다. 로트는
    생산 실적(`DailyProduction.actual_quantity`)에서 파생되며, 어긋날 때 진실은
    실적 쪽이다(이 저장소의 쓰기 경로는 시드뿐이라 어긋날 경로가 없다).

    로트 행은 삭제하지 않는다. 유효기간이 지나도 `만료` 로 표시할 뿐 남긴다.

    창고는 `생산창고`/`완제품창고` 둘이며, **완제품창고에 있으려면 OQC 합격이어야
    한다.** 갓 생산된 로트는 생산창고에서 검사를 기다리고, 합격분만 완제품창고로
    이동한다. 출하는 완제품창고 재고에 한해 일어난다(후속: 출하 리스크).
    """

    __tablename__ = "finished_goods_lots"
    __table_args__ = (
        UniqueConstraint(
            "product_id",
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
        # 완제품창고 = 출하 대기 재고다. 검사 대기·불합격 로트가 여기 섞이면
        # 출하 가능 수량이 실제보다 많아 보인다.
        CheckConstraint(
            f"warehouse <> '{FINISHED_GOODS_WAREHOUSE}' OR qc_status = '{QC_PASSED}'",
            name="ck_finished_goods_lot_release_requires_pass",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    lot_number: Mapped[str] = mapped_column(String(50), index=True)
    warehouse: Mapped[str] = mapped_column(String(20))
    # OQC 판정의 캐시다. 진실은 `QualityInspection` 의 OQC 기록이며, 기록이
    # 없으면 `검사 대기`다. 캐시를 두는 이유는 위 창고 불변식을 CHECK 제약으로
    # 걸기 위해서다(테이블 간 참조는 SQLite CHECK 로 표현할 수 없다).
    qc_status: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[float] = mapped_column(Float)
    produced_date: Mapped[date] = mapped_column(Date)
    # 제품의 설정기간에서 파생해 저장한다. 무기한 품목이면 None 이다.
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    product: Mapped[Product] = relationship(back_populates="finished_goods_lots")
    inspections: Mapped[list[QualityInspection]] = relationship(
        back_populates="finished_goods_lot",
        cascade="all, delete-orphan",
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
        CheckConstraint(
            f"result = '{QC_PASSED}' OR reason IS NOT NULL",
            name="ck_quality_inspection_failure_reason",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_type: Mapped[str] = mapped_column(String(10), index=True)
    inspected_date: Mapped[date] = mapped_column(Date)
    result: Mapped[str] = mapped_column(String(20))
    # 불합격 사유. 합격이면 None 이다.
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)

    material_lot_id: Mapped[int | None] = mapped_column(
        ForeignKey("material_lots.id"), nullable=True
    )
    daily_production_id: Mapped[int | None] = mapped_column(
        ForeignKey("daily_productions.id"), nullable=True
    )
    finished_goods_lot_id: Mapped[int | None] = mapped_column(
        ForeignKey("finished_goods_lots.id"), nullable=True
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
