from __future__ import annotations

from datetime import date
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel


DataT = TypeVar("DataT")
RiskSeverity = Literal["정상", "주의", "위험"]
RiskWorkflowStatus = Literal["신규", "확인 중", "조치 완료"]


class Envelope(BaseModel, Generic[DataT]):
    data: DataT


class ProductionPoint(BaseModel):
    work_date: date
    planned_quantity: float
    actual_quantity: float


class OrderResponse(BaseModel):
    order_id: int
    order_number: str
    product_code: str
    product_name: str
    due_date: date
    planned_quantity: float
    actual_quantity: float
    completion_rate: float
    average_daily_output: float
    remaining_quantity: float
    estimated_completion_date: date | None
    severity: RiskSeverity
    reason: str


class OrderDetailResponse(OrderResponse):
    recent_productions: list[ProductionPoint]


class MaterialResponse(BaseModel):
    material_id: int
    material_code: str
    material_name: str
    current_stock: float
    safety_stock: float
    ending_stock: float
    minimum_stock: float
    shortage_expected: bool
    stockout_date: date | None
    severity: RiskSeverity
    reason: str
    recommendation: str


class RiskResponse(BaseModel):
    risk_id: str
    risk_type: Literal["납기", "자재"]
    entity_id: int
    entity_code: str
    entity_name: str
    severity: Literal["주의", "위험"]
    reason: str
    recommendation: str
    status: RiskWorkflowStatus


class RiskStatusUpdate(BaseModel):
    status: RiskWorkflowStatus


class DashboardKpis(BaseModel):
    due_risk_order_count: int
    material_shortage_count: int
    today_plan_quantity: float
    today_actual_quantity: float


class DashboardResponse(BaseModel):
    kpis: DashboardKpis
    production_trend: list[ProductionPoint]
    top_order_risks: list[OrderResponse]
    top_material_risks: list[MaterialResponse]
    recommended_actions: list[str]
