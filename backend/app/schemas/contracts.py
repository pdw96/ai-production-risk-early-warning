from __future__ import annotations

from datetime import date
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel


DataT = TypeVar("DataT")
RiskSeverity = Literal["정상", "주의", "위험"]
RiskWorkflowStatus = Literal["신규", "확인 중", "조치 완료"]
Warehouse = Literal["원재료창고", "생산창고"]
LotState = Literal["가용", "예정 입고", "기간 내 폐기"]
ItemType = Literal["제품", "자재"]


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


class MaterialLotResponse(BaseModel):
    lot_number: str
    warehouse: Warehouse
    quantity: float
    received_date: date
    expiry_date: date | None
    state: LotState


class MaterialResponse(BaseModel):
    material_id: int
    material_code: str
    material_name: str
    # 로트 합계에서 파생된 기준일 가용 재고(만료분 제외, 두 창고 합산)
    current_stock: float
    raw_warehouse_stock: float
    production_warehouse_stock: float
    safety_stock: float
    ending_stock: float
    minimum_stock: float
    shortage_expected: bool
    stockout_date: date | None
    expiring_quantity: float
    first_expiry_date: date | None
    lots: list[MaterialLotResponse]
    severity: RiskSeverity
    reason: str
    recommendation: str


class ProductTrend(BaseModel):
    """추이 차트에서 제품 하나를 따로 볼 때 쓰는 계열."""

    product_code: str
    product_name: str
    points: list[ProductionPoint]


class ProductionResultResponse(BaseModel):
    """생산관리 화면의 일자별 생산실적 한 줄."""

    work_date: date
    planned_quantity: float
    actual_quantity: float
    # 계획이 0이면 0으로 둔다(나눗셈 불가).
    achievement_rate: float
    # 그날 실적이 잡힌 오더 수
    active_order_count: int


class MasterItemResponse(BaseModel):
    """기준정보관리 화면의 품목 마스터 한 줄."""

    item_type: ItemType
    item_code: str
    item_name: str
    # 자재만 값을 가진다(제품에는 안전재고·로트 개념이 없다).
    safety_stock: float | None
    lot_count: int | None
    # 제품이면 소요 자재 수, 자재면 사용하는 제품 수
    linked_item_count: int


class BomRequirementResponse(BaseModel):
    product_code: str
    product_name: str
    material_code: str
    material_name: str
    unit_quantity: float


class MasterDataResponse(BaseModel):
    items: list[MasterItemResponse]
    bom_requirements: list[BomRequirementResponse]


class PurchaseReceiptResponse(BaseModel):
    """구매관리 화면의 예정 입고 한 줄."""

    receipt_id: int
    material_code: str
    material_name: str
    scheduled_date: date
    scheduled_quantity: float
    expiry_date: date | None
    # 기준일로부터 남은 일수. 음수면 이미 지난 예정일이다.
    days_until_arrival: int
    # 14일 자재 전망에 반영되는 입고인지
    within_horizon: bool


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
    # 전 제품 합계 추이. 차트의 기본값이다.
    production_trend: list[ProductionPoint]
    # 같은 기간을 제품별로 나눈 추이. 합계와 날짜 축이 같다.
    product_trends: list[ProductTrend]
    top_order_risks: list[OrderResponse]
    top_material_risks: list[MaterialResponse]
    recommended_actions: list[str]
