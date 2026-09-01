export type RiskSeverity = "정상" | "주의" | "위험";
export type RiskWorkflowStatus = "신규" | "확인 중" | "조치 완료";

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

export interface Material {
  material_id: number;
  material_code: string;
  material_name: string;
  current_stock: number;
  safety_stock: number;
  ending_stock: number;
  minimum_stock: number;
  shortage_expected: boolean;
  stockout_date: string | null;
  severity: RiskSeverity;
  reason: string;
  recommendation: string;
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

const api_base_url = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

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
