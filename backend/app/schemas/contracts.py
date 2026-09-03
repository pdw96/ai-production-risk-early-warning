from __future__ import annotations

from datetime import date
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel


DataT = TypeVar("DataT")
RiskSeverity = Literal["정상", "주의", "위험"]
RiskWorkflowStatus = Literal["신규", "확인 중", "조치 완료"]
Warehouse = Literal["원재료창고", "생산창고"]
LotState = Literal["가용", "예정 입고", "기간 내 폐기", "만료"]
ItemType = Literal["제품", "자재"]
FinishedGoodsWarehouse = Literal["생산창고", "완제품창고"]
QcStatus = Literal["검사 대기", "합격", "불합격"]
# 완제품 로트의 화면 상태. 요약 지표와 1:1로 대응하며 서로 겹치지 않는다.
FinishedGoodsLotState = Literal["출하 가능", "이관 대기", "검사 대기", "불합격", "만료"]
InspectionType = Literal["IQC", "PQC", "OQC"]
# 검사 결과에 `검사 대기`가 없는 것은 검사를 하지 않은 것이 판정이 아니기
# 때문이다. 검사 대기는 기록이 없는 상태로 표현한다.
InspectionResult = Literal["합격", "불합격"]
InspectionTargetType = Literal["자재 로트", "생산 실적", "완제품 로트"]


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
    # 기준일에 도착했고 만료되지 않은 로트의 합(두 창고 합산). 입고를 수요
    # 차감보다 먼저 반영하므로 기준일 당일 도착하는 예정 입고분이 포함되며,
    # 그래서 `material_lots` 행 합계와 다를 수 있다.
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
    # 안전재고는 자재만 값을 가진다.
    safety_stock: float | None
    # 제품·자재 모두 로트를 가진다(제품은 완제품 로트).
    lot_count: int | None
    # 사내 프로세스가 정한 유효기간 설정기간(일). None 이면 무기한 품목이다.
    shelf_life_days: int | None
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


class FinishedGoodsLotResponse(BaseModel):
    """영업관리 화면의 완제품 로트 한 줄."""

    lot_number: str
    warehouse: FinishedGoodsWarehouse
    qc_status: QcStatus
    quantity: float
    produced_date: date
    expiry_date: date | None
    state: FinishedGoodsLotState


class FinishedGoodsResponse(BaseModel):
    """제품 한 건의 완제품 재고.

    다섯 수량은 서로 겹치지 않으며 합이 `total_lot_quantity` 와 같다. 로트를
    지우지 않으므로(영구 기록) 만료분도 목록과 합계에 남는다.
    """

    product_id: int
    product_code: str
    product_name: str
    shelf_life_days: int | None
    # 완제품창고에 있고 만료되지 않은 재고. 출하는 여기서만 일어난다.
    releasable_stock: float
    # OQC 합격이지만 아직 생산창고에 있는 재고
    transfer_pending_stock: float
    # 아직 OQC 를 받지 않은 재고
    inspection_pending_stock: float
    rejected_stock: float
    expired_stock: float
    total_lot_quantity: float
    lots: list[FinishedGoodsLotResponse]


class QualityInspectionResponse(BaseModel):
    """품질관리 화면의 검사 기록 한 줄."""

    inspection_id: int
    inspection_type: InspectionType
    inspected_date: date
    result: InspectionResult
    # 불합격 사유. 합격이면 None 이다.
    reason: str | None
    target_type: InspectionTargetType
    item_code: str
    item_name: str
    # 로트번호(IQC·OQC) 또는 오더번호(PQC)
    target_label: str


class QualityInspectionSummary(BaseModel):
    inspection_type: InspectionType
    total_count: int
    passed_count: int
    failed_count: int


class QualityDataResponse(BaseModel):
    # 잘라낸 기록까지 포함한 전체 집계다. 아래 목록 길이와 일치하지 않는다.
    summaries: list[QualityInspectionSummary]
    # 유형별 최신 기록만 담고 검사일 내림차순으로 정렬한다. 기록이 영구히
    # 쌓이므로 전체를 싣지 않는다.
    inspections: list[QualityInspectionResponse]


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
