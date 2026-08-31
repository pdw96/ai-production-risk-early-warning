from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from typing import List


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
    current_stock: Mapped[float] = mapped_column(Float)
    safety_stock: Mapped[float] = mapped_column(Float)

    bom_requirements: Mapped[list[BomRequirement]] = relationship(back_populates="material")
    purchase_receipts: Mapped[list[PurchaseReceipt]] = relationship(back_populates="material")


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

    material: Mapped[Material] = relationship(back_populates="purchase_receipts")


class RiskStatus(Base):
    __tablename__ = "risk_statuses"

    id: Mapped[int] = mapped_column(primary_key=True)
    risk_key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="신규")
