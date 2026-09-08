import { describe, expect, it } from "vitest";

import {
  format_count,
  format_date,
  format_mixed_quantity,
  format_percentage,
  format_quantity,
  unit_label,
} from "./format";

describe("operation formatters", () => {
  it("formats quantities with Korean numeric grouping", () => {
    expect(format_quantity(1234.5, "EA")).toBe("1,234.5개");
  });

  it("requires the unit — a call site cannot fall back to 개", () => {
    // 기본값이 있던 동안에는 단위를 빠뜨린 자리가 컴파일되고 조용히 「개」를
    // 적었고, 그것이 리뷰 열두 라운드의 뿌리였다. 이제 `tsc --noEmit` 이
    // 호출부에서 잡으므로 사람이 훑을 일이 아니다.
    // @ts-expect-error 단위 없이 부를 수 없다
    expect(() => format_quantity(1234.5)).not.toBeNull();
    // @ts-expect-error 단위 없이 부를 수 없다
    expect(() => unit_label()).not.toBeNull();
  });

  it("writes the item's own unit, and counts EA as 개", () => {
    // 자재는 kg · L · m2 로 갈린다. 단위를 적지 않으면 320kg 이 「320개」가 된다.
    expect(format_quantity(320, "kg")).toBe("320 kg");
    expect(format_quantity(1234.5, "L")).toBe("1,234.5 L");
    // EA 와 개는 같은 것이다. 코드값을 그대로 적으면 창고 화면만 다른 말을 쓴다.
    expect(format_quantity(80, "EA")).toBe("80개");
  });

  it("counts things with 건, not by stripping 개 off a quantity", () => {
    // 대시보드가 `format_quantity(...).replace("개", "건")` 로 적고 있었다.
    // 붙였다가 지우는 것이라 기본 단위가 바뀌면 조용히 「3개」가 남는다.
    expect(format_count(3)).toBe("3건");
    expect(format_count(1234)).toBe("1,234건");
  });

  it("refuses to name a unit for a total that mixes units", () => {
    // 제품을 넘어 더한 값의 단위가 갈리면 붙일 단위가 없다. 「개」라고 적으면
    // 화면이 거짓말을 하므로 갈렸다고 말한다.
    expect(format_mixed_quantity(1234.5, "kg")).toBe("1,234.5 kg");
    expect(format_mixed_quantity(1234.5, "EA")).toBe("1,234.5개");
    expect(format_mixed_quantity(1234.5, null)).toBe("1,234.5 (단위 혼재)");
    expect(unit_label(null)).toBe("혼재");
  });

  it("does not call an empty total a mixed-unit total", () => {
    // 단위가 없는 이유가 둘이다 — 실제로 섞였거나, 더한 것이 하나도 없거나.
    // 뒤의 것은 합이 0 이므로 값으로 가른다. 아무 일도 없었던 날에
    // 「0 (단위 혼재)」라고 적으면 그것 자체가 거짓말이다.
    expect(format_mixed_quantity(0, null)).toBe("0");
    expect(format_mixed_quantity(120, null)).toBe("120 (단위 혼재)");
  });

  it("formats percentages to one decimal place", () => {
    expect(format_percentage(81.25)).toBe("81.3%");
  });

  it("formats API dates as YYYY.MM.DD and handles missing estimates", () => {
    expect(format_date("2026-08-31")).toBe("2026.08.31");
    expect(format_date(null)).toBe("예측 불가");
  });
});
