export type RiskSeverity = "정상" | "주의" | "위험";
export type RiskWorkflowStatus = "신규" | "확인 중" | "조치 완료";
export type Warehouse = "원재료창고" | "생산창고";
export type LotState = "가용" | "예정 입고" | "기간 내 폐기";
export type ItemType = "제품" | "자재";

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
  points: ProductionPoint[];
}

export interface ProductionResult {
  work_date: string;
  planned_quantity: number;
  actual_quantity: number;
  achievement_rate: number;
  active_order_count: number;
}

export interface MasterItem {
  item_type: ItemType;
  item_code: string;
  item_name: string;
  safety_stock: number | null;
  lot_count: number | null;
  linked_item_count: number;
}

export interface BomRequirement {
  product_code: string;
  product_name: string;
  material_code: string;
  material_name: string;
  unit_quantity: number;
}

export interface MasterData {
  items: MasterItem[];
  bom_requirements: BomRequirement[];
}

export interface PurchaseReceipt {
  receipt_id: number;
  material_code: string;
  material_name: string;
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
  };
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
