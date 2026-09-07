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

/** 숫자 없이 단위만 적을 때. 「단위: 개」 · 「단위: kg」 */
export function unit_label(unit = COUNTING_UNIT): string {
  return unit === COUNTING_UNIT ? "개" : unit;
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
