// 단위를 받지 않으면 세는 것으로 본다. 제품과 오더 수량은 전부 EA 라 그것이
// 맞고, 자재만 kg · L · m2 로 갈린다 — 단위를 아는 화면만 넘긴다.
//
// `EA` 를 그대로 적지 않고 「개」로 옮기는 것은 둘이 같은 것이기 때문이다.
// 기준정보의 코드값은 EA 이지만 한국어 화면에서 세는 단위는 개이고, 그대로
// 적으면 창고 화면만 「80 EA」가 되어 오더·생산 화면의 「80개」와 갈린다.
// 숫자에 붙여 쓰는 것도 그래서다 — 기호 단위는 띄어 쓴다(320개 · 320 kg).
const COUNTING_UNIT = "EA";

export function format_quantity(value: number, unit = COUNTING_UNIT): string {
  const formatted = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 2 }).format(value);
  return unit === COUNTING_UNIT ? `${formatted}개` : `${formatted} ${unit}`;
}

/**
 * 숫자 없이 단위만 적을 때. 「단위: 개」 · 「단위: kg」
 *
 * `null` 은 **제품을 넘어 더해서 단위가 갈린 값**이다. 그때 「개」라고 적으면
 * 화면이 거짓말을 하므로 갈렸다고 말한다.
 */
export function unit_label(unit: string | null = COUNTING_UNIT): string {
  if (unit === null) {
    return "혼재";
  }
  return unit === COUNTING_UNIT ? "개" : unit;
}

/**
 * 제품을 넘어 더한 수량.
 *
 * `null` 은 **단위를 정할 수 없다**는 뜻이고, 그 이유는 둘이다 — 실제로 섞였거나,
 * 더한 것이 하나도 없거나. 뒤의 것은 합이 0 이다(수량은 음수가 될 수 없다).
 * 값으로 그 둘을 가른다: 0 이면 붙일 단위가 없을 뿐이니 「0」을 그냥 적고, 0 이
 * 아니면 실제로 섞인 것이다. 아무 일도 없었던 날에 「0 (단위 혼재)」라고 적으면
 * 그것 자체가 거짓말이다.
 */
export function format_mixed_quantity(value: number, unit: string | null): string {
  const formatted = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 2 }).format(value);
  if (unit !== null) {
    return format_quantity(value, unit);
  }
  return value === 0 ? formatted : `${formatted} (단위 혼재)`;
}

/**
 * 물건의 양이 아니라 **건수**를 셀 때. 오더 수 · 자재 수 같은 것이다.
 *
 * 대시보드가 `format_quantity(...).replace("개", "건")` 로 적고 있었다. 붙였다가
 * 지우는 것이라 `format_quantity` 의 기본 단위가 바뀌는 순간 조용히 「3개」가
 * 남는다 — 세는 것과 재는 것은 다른 함수여야 한다.
 */
export function format_count(value: number, noun = "건"): string {
  return `${new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(value)}${noun}`;
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
