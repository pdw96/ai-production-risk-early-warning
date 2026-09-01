export function format_quantity(value: number): string {
  return `${new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 2 }).format(value)}개`;
}

export function format_percentage(value: number): string {
  return `${new Intl.NumberFormat("ko-KR", {
    maximumFractionDigits: 1,
    minimumFractionDigits: 1,
  }).format(value)}%`;
}

export function format_date(value: string | null): string {
  if (!value) {
    return "예측 불가";
  }

  return value.replaceAll("-", ".");
}
