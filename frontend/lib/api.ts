export type RiskSeverity = "정상" | "주의" | "위험";
export type RiskWorkflowStatus = "신규" | "확인 중" | "조치 완료";
export type Warehouse = "원재료창고" | "생산창고";
export type LotState = "가용" | "예정 입고" | "기간 내 폐기" | "만료";
export type ItemType = "제품" | "자재";
export type FinishedGoodsWarehouse = "생산창고" | "제품창고";
export type AnyWarehouse = "원재료창고" | "생산창고" | "제품창고";
export type QcStatus = "검사 대기" | "합격" | "불합격";
export type InspectionType = "IQC" | "PQC" | "OQC";
export type InspectionResult = "합격" | "불합격";
export type InspectionTargetType = "자재 로트" | "생산 실적" | "완제품 로트";

export interface ProductionPoint {
  work_date: string;
  planned_quantity: number;
  actual_quantity: number;
}

export interface Order {
  order_id: number;
  order_number: string;
  product_code: string;
  product_name: string;
  /** 이 오더의 모든 수량이 쓰는 단위. */
  stock_uom: string;
  due_date: string;
  planned_quantity: number;
  actual_quantity: number;
  completion_rate: number;
  average_daily_output: number;
  remaining_quantity: number;
  estimated_completion_date: string | null;
  severity: RiskSeverity;
  reason: string;
}

export interface OrderDetail extends Order {
  recent_productions: ProductionPoint[];
}

export interface MaterialLot {
  lot_number: string;
  warehouse: Warehouse;
  quantity: number;
  received_date: string;
  expiry_date: string | null;
  state: LotState;
}

export interface Material {
  material_id: number;
  material_code: string;
  material_name: string;
  /** 아래 모든 수량의 단위. 자재는 kg · L · m2 로 갈린다. */
  stock_uom: string;
  /** 로트 합계에서 파생된 기준일 가용 재고(만료분 제외, 두 창고 합산) */
  current_stock: number;
  raw_warehouse_stock: number;
  production_warehouse_stock: number;
  safety_stock: number;
  ending_stock: number;
  minimum_stock: number;
  shortage_expected: boolean;
  stockout_date: string | null;
  expiring_quantity: number;
  first_expiry_date: string | null;
  lots: MaterialLot[];
  severity: RiskSeverity;
  reason: string;
  recommendation: string;
}

export interface ProductTrend {
  product_code: string;
  product_name: string;
  /** 제품 하나를 보는 계열이므로 단위가 하나로 정해진다. */
  stock_uom: string;
  points: ProductionPoint[];
}

export interface ProductionResult {
  work_date: string;
  planned_quantity: number;
  actual_quantity: number;
  /**
   * 실적 ÷ 계획. **그 나눗셈이 뜻을 가질 때만** 값이 있다 — 계획과 실적의
   * 단위가 갈리면 null 이다. m² 계획을 개수 실적으로 나눈 90% 는 아무것도
   * 뜻하지 않으므로, 화면은 그 숫자도 판정도 적지 않는다.
   */
  achievement_rate: number | null;
  active_order_count: number;
  /**
   * 위 두 수량이 **각각** 쓰는 단위. 그날 보탠 제품들의 단위가 갈리면 null 이다.
   * 계획과 실적이 나뉘어 있는 것은 둘이 서로 다른 제품 집합에서 나오기
   * 때문이다 — 계획만 선 m² 오더와 실적만 오른 개수 오더가 한 날에 함께 있으면,
   * 단위가 하나면 각각은 단위가 분명한데도 둘 다 「혼재」가 된다.
   */
  planned_quantity_uom: string | null;
  actual_quantity_uom: string | null;
}

export interface MasterItem {
  item_type: ItemType;
  item_code: string;
  item_name: string;
  /** 이 품목의 재고 단위. 안전재고가 이 단위로 적힌다. */
  stock_uom: string;
  /** 안전재고는 자재만 관리한다. */
  safety_stock: number | null;
  lot_count: number | null;
  /** 사내 프로세스가 정한 유효기간 설정기간(일). null 이면 무기한 품목이다. */
  shelf_life_days: number | null;
  linked_item_count: number;
}

export interface FinishedGoods {
  product_id: number;
  product_code: string;
  product_name: string;
  /** 아래 모든 수량이 쓰는 단위. */
  stock_uom: string;
  shelf_life_days: number | null;
  /** 제품창고에 있고 만료되지 않은 재고. 출하는 여기서만 일어난다. */
  releasable_stock: number;
  /** 아직 출하검사를 받지 않은 재고(생산창고) */
  inspection_pending_stock: number;
  /** 출하검사 불합격 재고(생산창고) */
  rejected_stock: number;
  /**
   * 합격했으나 아직 제품창고로 옮겨지지 않은 재고(생산창고).
   *
   * 출하할 수 없으니 「출하 가능」이 아니고, 판정은 끝났으니 「검사 대기」도
   * 「불합격」도 아니다 — 넷 중 어디에 넣어도 화면이 거짓말을 하므로 칸이
   * 따로 있다. 채워지는 것은 재고이동 요청·처리가 서는 단계부터다.
   */
  intake_pending_stock: number;
  expired_stock: number;
  /** 위 다섯 수량의 합. 로트를 지우지 않으므로 만료분도 들어 있다. */
  total_lot_quantity: number;
}

export interface WarehouseLot {
  item_type: ItemType;
  item_code: string;
  item_name: string;
  lot_number: string;
  quantity: number;
  /** 수량의 단위. 창고에는 kg 와 L 이 나란히 쌓인다. */
  stock_uom: string;
  /** 자재는 입고일, 완제품은 생산일 */
  stocked_date: string;
  expiry_date: string | null;
  /** 완제품만 값을 가진다. 자재의 수입검사는 입고 시점에 이미 끝나 있다. */
  qc_status: QcStatus | null;
  expired: boolean;
}

export interface WarehouseStock {
  warehouse: AnyWarehouse;
  warehouse_slug: string;
  description: string;
  material_lot_count: number;
  /**
   * **단위를 넘어 더한 값이다.** 창고에 kg 와 L 이 함께 있으면 뜻이 없으므로
   * 화면은 이것을 쓰지 않고 `lots` 에서 단위별 합을 낸다.
   */
  material_quantity: number;
  product_lot_count: number;
  product_quantity: number;
  expired_quantity: number;
  lots: WarehouseLot[];
}

export interface QualityInspection {
  inspection_id: number;
  inspection_type: InspectionType;
  inspected_date: string;
  result: InspectionResult;
  reason: string | null;
  target_type: InspectionTargetType;
  item_code: string;
  item_name: string;
  target_label: string;
}

export interface QualityInspectionSummary {
  inspection_type: InspectionType;
  total_count: number;
  passed_count: number;
  failed_count: number;
}

export interface QualityData {
  summaries: QualityInspectionSummary[];
  inspections: QualityInspection[];
}

export interface BomRequirement {
  product_code: string;
  product_name: string;
  material_code: string;
  material_name: string;
  unit_quantity: number;
  /** 소요량의 단위는 **하위 품목의** 재고 단위다. */
  unit_quantity_uom: string;
}

export interface MasterData {
  items: MasterItem[];
  bom_requirements: BomRequirement[];
}

export interface PurchaseReceipt {
  receipt_id: number;
  material_code: string;
  material_name: string;
  /** 예정 수량의 단위. */
  stock_uom: string;
  scheduled_date: string;
  scheduled_quantity: number;
  expiry_date: string | null;
  days_until_arrival: number;
  within_horizon: boolean;
}

export interface Risk {
  risk_id: string;
  risk_type: "납기" | "자재";
  entity_id: number;
  entity_code: string;
  entity_name: string;
  severity: Exclude<RiskSeverity, "정상">;
  reason: string;
  recommendation: string;
  status: RiskWorkflowStatus;
}

export interface Dashboard {
  kpis: {
    due_risk_order_count: number;
    material_shortage_count: number;
    today_plan_quantity: number;
    today_actual_quantity: number;
    /**
     * 위 두 수량이 **각각** 쓰는 단위. 오늘 하루에 실제로 보탠 제품들의
     * 단위이며, 아래 `quantity_uom` 과 기간이 다르므로 값이 다를 수 있다.
     *
     * 계획과 실적이 나뉘어 있는 것은 둘이 **서로 다른 제품 집합에서 나오기**
     * 때문이다. 계획만 선 m² 오더와 실적만 오른 개수 오더가 오늘 함께 있으면,
     * 단위가 하나면 각각은 단위가 분명한데도 둘 다 「혼재」가 된다.
     */
    today_plan_quantity_uom: string | null;
    today_actual_quantity_uom: string | null;
  };
  /**
   * 아래 `production_trend` 의 7일 합계가 쓰는 단위. 완제품 단위가 갈리면
   * null 이고, 그때 그 합에는 붙일 단위가 없다.
   */
  quantity_uom: string | null;
  production_trend: ProductionPoint[];
  product_trends: ProductTrend[];
  top_order_risks: Order[];
  top_material_risks: Material[];
  recommended_actions: string[];
}

interface ApiEnvelope<DataT> {
  data: DataT;
}

interface ApiError {
  detail?: string;
}

const api_base_url = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export async function requestData<DataT>(
  path: string,
  options: RequestInit = {},
): Promise<DataT> {
  const response = await fetch(`${api_base_url}${path}`, {
    cache: "no-store",
    ...options,
  });
  const body = (await response.json()) as ApiEnvelope<DataT> | ApiError;

  if (!response.ok) {
    const detail = "detail" in body ? body.detail : undefined;
    throw new Error(detail ?? "API 요청에 실패했습니다.");
  }

  return (body as ApiEnvelope<DataT>).data;
}

export function getDashboard(): Promise<Dashboard> {
  return requestData<Dashboard>("/api/dashboard");
}

export function getOrders(): Promise<Order[]> {
  return requestData<Order[]>("/api/orders");
}

export function getOrder(order_id: number): Promise<OrderDetail> {
  return requestData<OrderDetail>(`/api/orders/${order_id}`);
}

export function getMaterials(): Promise<Material[]> {
  return requestData<Material[]>("/api/materials");
}

export function getProductionResults(): Promise<ProductionResult[]> {
  return requestData<ProductionResult[]>("/api/production-results");
}

export function getMasterData(): Promise<MasterData> {
  return requestData<MasterData>("/api/master-data");
}

export function getPurchases(): Promise<PurchaseReceipt[]> {
  return requestData<PurchaseReceipt[]>("/api/purchases");
}

export function getWarehouseStock(warehouse_slug: string): Promise<WarehouseStock> {
  return requestData<WarehouseStock>(`/api/warehouses/${warehouse_slug}`);
}

export function getFinishedGoods(): Promise<FinishedGoods[]> {
  return requestData<FinishedGoods[]>("/api/finished-goods");
}

export function getQualityInspections(): Promise<QualityData> {
  return requestData<QualityData>("/api/quality-inspections");
}

export function getRisks(): Promise<Risk[]> {
  return requestData<Risk[]>("/api/risks");
}

export function updateRiskStatus(
  risk_id: string,
  status: RiskWorkflowStatus,
): Promise<Risk> {
  return requestData<Risk>(`/api/risks/${risk_id}/status`, {
    body: JSON.stringify({ status }),
    headers: { "Content-Type": "application/json" },
    method: "PATCH",
  });
}
