// `EA` 를 그대로 적지 않고 「개」로 옮기는 것은 둘이 같은 것이기 때문이다.
// 기준정보의 코드값은 EA 이지만 한국어 화면에서 세는 단위는 개이고, 그대로
// 적으면 창고 화면만 「80 EA」가 되어 오더·생산 화면의 「80개」와 갈린다.
// 숫자에 붙여 쓰는 것도 그래서다 — 기호 단위는 띄어 쓴다(320개 · 320 kg).
const COUNTING_UNIT = "EA";

/**
 * 품목 하나의 수량. **단위는 생략할 수 없다.**
 *
 * 예전에는 `unit = COUNTING_UNIT` 이 기본값이라, 단위를 넘기지 않은 자리가
 * 컴파일되고 타입 검사를 통과한 뒤 조용히 「개」를 적었다. 그 기본값 하나가
 * 리뷰 열두 라운드를 만들었다 — 화면 하나를 이으면 다음 화면이 아직 「개」였고,
 * 이어졌는지는 사람이 호출부를 훑어야만 알 수 있었다. `320kg` 이 「320개」로
 * 나간 것이 그 자리다.
 *
 * 기본값을 없애면 그 확인을 `tsc --noEmit` 이 한다. 단위를 모르는 자리는
 * 애초에 이 함수를 부르면 안 되고 — 제품을 넘어 더한 값이면
 * `format_mixed_quantity`, 물건이 아니라 건수면 `format_count` 다.
 */
export function format_quantity(value: number, unit: string): string {
  const formatted = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 2 }).format(value);
  return unit === COUNTING_UNIT ? `${formatted}개` : `${formatted} ${unit}`;
}

/**
 * 숫자 없이 단위만 적을 때. 「단위: 개」 · 「단위: kg」
 *
 * `null` 은 **제품을 넘어 더해서 단위가 갈린 값**이다. 그때 「개」라고 적으면
 * 화면이 거짓말을 하므로 갈렸다고 말한다.
 *
 * `format_quantity` 와 같은 이유로 기본값을 두지 않는다 — `null` 은 「모른다」가
 * 아니라 「갈렸다」는 뜻이므로, 넘기지 않은 것과 같은 값으로 읽히면 안 된다.
 */
export function unit_label(unit: string | null): string {
  if (unit === null) {
    return "혼재";
  }
  return unit === COUNTING_UNIT ? "개" : unit;
}

/**
 * 제품을 넘어 더한 수량.
 *
 * `null` 은 **단위를 정할 수 없다**는 뜻이고, 그 이유는 둘이다 — 실제로 섞였거나,
 * 더한 것이 하나도 없거나. 뒤의 것은 합이 0 이다. 값으로 그 둘을 가른다: 0 이면
 * 붙일 단위가 없을 뿐이니 「0」을 그냥 적고, 0 이 아니면 실제로 섞인 것이다.
 * 아무 일도 없었던 날에 「0 (단위 혼재)」라고 적으면 그것 자체가 거짓말이다.
 *
 * 이 구별은 **수량이 음수가 될 수 없다**는 데 기댄다. 음수가 섞이면 서로 다른
 * 단위가 0 으로 상쇄되어, 섞인 것을 빈 것으로 읽게 된다. 그래서 그 불변식을
 * 화면의 가정으로 두지 않고 **데이터베이스가 강제한다** — 수량을 가진 표
 * 여섯에 `>= 0` CHECK 가 걸려 있다.
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
