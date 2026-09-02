from __future__ import annotations

from datetime import date

from sqlalchemy import (
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import WAREHOUSES
from app.db.base import Base


# 창고명은 코드 상수(`WAREHOUSES`)에서 그대로 끌어와 저장 제약으로 건다.
# 목록을 손으로 옮겨 적으면 상수만 늘어나고 제약은 그대로 남는다.
_ALLOWED_WAREHOUSES_SQL = ", ".join(f"'{name}'" for name in WAREHOUSES)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))

    orders: Mapped[list[Order]] = relationship(back_populates="product")
    bom_requirements: Mapped[list[BomRequirement]] = relationship(back_populates="product")


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


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    safety_stock: Mapped[float] = mapped_column(Float)

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

    창고는 `원재료창고`/`생산창고` 둘로 제한한다. 완제품창고는 이 모델의
    범위가 아니다(docs/2026-09-02-warehouse-erp-followup.md 후속 ②).
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
            f"warehouse IN ({_ALLOWED_WAREHOUSES_SQL})",
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


class RiskStatus(Base):
    __tablename__ = "risk_statuses"

    id: Mapped[int] = mapped_column(primary_key=True)
    risk_key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="신규")
