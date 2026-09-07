import { describe, expect, it } from "vitest";

import { format_count, format_date, format_percentage, format_quantity } from "./format";

describe("operation formatters", () => {
  it("formats quantities with Korean numeric grouping", () => {
    expect(format_quantity(1234.5)).toBe("1,234.5개");
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

  it("formats percentages to one decimal place", () => {
    expect(format_percentage(81.25)).toBe("81.3%");
  });

  it("formats API dates as YYYY.MM.DD and handles missing estimates", () => {
    expect(format_date("2026-08-31")).toBe("2026.08.31");
    expect(format_date(null)).toBe("예측 불가");
  });
});
